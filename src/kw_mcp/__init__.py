"""KLAS (Kwangwoon University) MCP server."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def main() -> None:
    # Windows consoles behind a pipe may not be UTF-8; print Korean as "?" rather than crash.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="kw-mcp", description="KLAS MCP server")
    parser.add_argument("--version", action="store_true", help="버전 출력 (모든 모듈을 불러와 설치가 온전한지도 확인)")
    parser.add_argument("--expect", help=argparse.SUPPRESS)  # with --version: fail unless this version is installed
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="MCP 서버 실행 (stdio, 기본값)")
    sub.add_parser("setup", help="KLAS 아이디/비밀번호를 키체인에 저장")
    sub.add_parser("check", help="로그인하고 조회가 되는지 개수만 출력")
    sub.add_parser("forget", help="키체인에 저장한 로그인 정보 삭제")
    link = sub.add_parser("link", help="이 PC를 KW Campus 중계에 연결하고 로그인 시 자동 실행 (처음 한 번)")
    link.add_argument("invite", help="받은 초대 코드 (kwc_...)")
    link.add_argument("--no-autostart", action="store_true", help="자동 실행을 등록하지 않음")
    link.add_argument("--server", help=argparse.SUPPRESS)  # set by the installer: the bridge it came from
    link.add_argument("--relink", action="store_true", help="이미 연결돼 있어도 기기를 새로 등록 (기존 커넥터는 다시 연결해야 함)")
    sub.add_parser("code", help="Claude/ChatGPT 커넥터 승인에 넣을 1회용 연결 코드 발급")
    sub.add_parser("connections", help="이 PC의 연결 코드로 연결한 앱 목록")
    revoke = sub.add_parser("revoke", help="연결한 앱 하나만 끊기 (PC와 다른 앱은 그대로)")
    revoke.add_argument("grant_id", help="`kw-mcp connections`에 나온 ID")
    sub.add_parser("status", help="연결·자동 실행·업데이트 상태 확인")
    sub.add_parser("update", help="새 버전이 있으면 서명을 확인하고 지금 설치 (PC 에이전트)")
    unlink = sub.add_parser("unlink", help="이 PC 연결 해제 (커넥터도 더 이상 동작하지 않음)")
    unlink.add_argument("--force", action="store_true", help="중계 서버에 알리지 않고 이 PC의 키와 설정만 지움")
    agent = sub.add_parser("agent", help="중계 요청에 응답하는 백그라운드 에이전트 (자동 실행이 씀)")
    agent.add_argument("--log-file")
    agent.add_argument("--replace", action="store_true", help=argparse.SUPPRESS)
    # Set by the autostart the extension installs: that agent never installs releases itself.
    agent.add_argument("--from-extension", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.version:
        sys.exit(_version(args.expect))
    if args.command == "agent":
        if args.from_extension:
            from .agent import EXTENSION

            os.environ["KW_MCP_DISTRIBUTION"] = EXTENSION  # agent.from_extension(), also for what it starts
        _agent(args.log_file, args.replace)
    elif args.command in (None, "serve"):
        from .server import run

        run()
    else:
        try:
            sys.exit(_command(args))
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:  # a message people can act on, not a traceback
            if os.environ.get("KW_MCP_DEBUG"):
                raise
            sys.exit(friendly_error(e))


def _command(args: argparse.Namespace) -> int:
    if args.command == "setup":
        _setup()
    elif args.command == "check":
        return asyncio.run(_check())
    elif args.command == "forget":
        from . import credentials

        credentials.delete()
        print("키체인에서 KLAS 로그인 정보를 삭제했습니다.")
    elif args.command == "link":
        return _link(args.invite, autostart=not args.no_autostart, server=args.server, relink=args.relink)
    elif args.command == "code":
        return _code()
    elif args.command == "connections":
        return _connections()
    elif args.command == "revoke":
        from . import agent

        agent.revoke(args.grant_id)
        print(f"연결 {args.grant_id}을(를) 끊었습니다. 그 앱은 더 이상 이 PC에 물을 수 없습니다.")
    elif args.command == "status":
        _status()
    elif args.command == "update":
        return _update()
    elif args.command == "unlink":
        from . import agent

        agent.unlink(force=args.force)
        print("이 PC의 연결을 해제했습니다. Claude/ChatGPT의 커넥터도 지워 주세요.")
    return 0


def friendly_error(e: BaseException) -> str:
    """One line for an error linking can hit (network, keychain, clock, ...), in the command line and in
    the extension's connect_other_devices alike: what didn't work, why, and what to do."""
    import subprocess

    import httpx
    from keyring.errors import KeyringError

    from . import agent, credentials

    name = e.__class__.__name__
    if isinstance(e, KeyringError):
        return "키체인을 열지 못했어요. 허용 창이 뜨면 '허용'을 눌러 주세요."
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:  # throttled, not refused
        return "요청이 많아요. 잠시 뒤에 다시 해 주세요."
    if isinstance(e, httpx.HTTPStatusError):
        return f"연결 서버에 문제가 있어요(HTTP {e.response.status_code}). 잠시 뒤 다시 해 주세요."
    if isinstance(e, httpx.HTTPError):
        return "서버에 연결하지 못했어요. 인터넷을 확인하고 VPN은 꺼 주세요."
    if isinstance(e, subprocess.CalledProcessError):
        return "자동 실행 등록이 안 됐어요. 잠시 뒤 다시 해 주세요."
    if isinstance(e, (agent.ClockSkew, agent.NotLinked, agent.UnlinkFailed, agent.DeviceRefused, credentials.MissingCredentials,
                      ValueError, LookupError, NotImplementedError, OSError)):
        return str(e) or name
    return f"예상하지 못한 오류가 났어요({name}: {e}). KW_MCP_DEBUG=1을 붙여 다시 실행하면 자세한 내용이 나와요."


def _version(expect: str | None) -> int:
    # Loading everything an agent and the server need makes this the post-update health check.
    from . import agent, server  # noqa: F401

    installed = agent.installed_version()
    print(f"kw-mcp {installed}")
    if expect is not None and installed != expect:
        print(f"expected {expect}", file=sys.stderr)
        return 1
    return 0


def _link(invite: str, autostart: bool, server: str | None = None, relink: bool = False) -> int:
    import subprocess

    from . import agent, credentials, webconnect

    try:
        invite_server, _ = agent.official_invite(invite)  # only the KW CAMPUS bridge
        if server and invite_server != server.rstrip("/"):
            raise ValueError(f"초대 코드의 서버({invite_server})가 설치한 곳({server})과 다릅니다. 받은 링크를 다시 확인하세요.")
    except ValueError as e:
        print(e)
        return 1
    # A wrong PC clock makes every signed request fail; say so before it looks like "device unknown".
    agent.check_server_clock(invite_server)
    agent.remember_uv()
    try:
        credentials.load()
    except credentials.MissingCredentials:
        print("먼저 KLAS 학번과 비밀번호를 이 PC 키체인에 저장합니다(서버로는 보내지 않습니다).")
        _setup()
    if asyncio.run(_login_ok()) != 0:
        return 1
    # Re-running the installer is how people updated: an already linked PC keeps its device (and the
    # Claude/ChatGPT connections bound to it), and only the agent restarts on the new version.
    mcp_url = webconnect.ensure_device(invite, relink=relink, expected_server=server)
    if mcp_url is None:
        print("이미 연결된 PC입니다. 에이전트만 새 버전으로 다시 시작합니다.")
    if autostart:
        try:
            print(f"자동 실행 등록: {agent.install_autostart()}")
        except subprocess.CalledProcessError as e:
            print(friendly_error(e))
            print("기기 등록은 끝났습니다. 잠시 뒤 `kw-mcp link`를 다시 실행하면 자동 실행만 다시 등록합니다.")
    if mcp_url is None:
        print("업데이트를 마쳤습니다. 이미 연결한 Claude/ChatGPT 커넥터는 그대로 쓰면 됩니다.")
        print("앱을 하나 더 연결하려면 `kw-mcp code`로 연결 코드를 받으세요.")
        return 0
    _print_connect(mcp_url, agent.pair_code())
    return 0


def _code() -> int:
    from . import agent

    try:
        code = agent.pair_code()
    except agent.NotLinked as e:
        print(e)
        return 1
    _print_connect(code["mcp_url"], code)
    return 0


def _when(value: object) -> str:
    """A grant timestamp (epoch seconds, or ISO 8601) in KST."""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            moment = datetime.fromtimestamp(int(value), KST)
        elif isinstance(value, str) and value:
            moment = datetime.fromisoformat(value).astimezone(KST)
        else:
            return "-"
    except (ValueError, OverflowError, OSError):
        return "-"
    return moment.strftime("%Y-%m-%d %H:%M")


def _connections() -> int:
    from . import agent

    rows = agent.grants()
    if not rows:
        print("이 PC에 연결된 앱이 없습니다. 연결하려면 `kw-mcp code`로 연결 코드를 받으세요.")
        return 0
    print(f"이 PC에 연결된 앱 {len(rows)}개 (시각은 한국 시간):")
    for g in rows:
        # grants() keeps only ids in the bridge's format, so what is shown can be pasted into `kw-mcp revoke`.
        print(f"  {g['id'] or '(ID 형식 오류)'}  {g['client'] or '(이름 없음)'}  {g['redirect_host']}")
        used = _when(g["last_used"]) if g["last_used"] else "아직 없음"
        print(f"      연결 {_when(g['created'])} · 마지막 사용 {used} · 만료 {_when(g['expires'])}")
    print("모르는 앱이 있으면 `kw-mcp revoke <ID>`로 끊으세요. 모두 끊으려면 `kw-mcp unlink`.")
    return 0


def _print_connect(mcp_url: str, code: dict) -> None:
    print()
    print("이제 Claude 또는 ChatGPT에 커넥터를 추가하세요.")
    print(f"  커넥터 URL : {mcp_url}")
    print(f"  연결 코드  : {code['code']}   ({code['expires_in'] // 60}분 안에, 한 번만 사용)")
    print("  Claude: 설정 → 커넥터 → 커스텀 커넥터 추가 → URL 입력 → 연결 → 승인 페이지에 연결 코드 입력")
    print("  ChatGPT: 설정 → 앱과 커넥터 → 만들기 → URL 입력(OAuth) → 승인 페이지에 연결 코드 입력")
    print("다른 앱도 연결하려면 `kw-mcp code`로 새 코드를 받으세요.")
    print("※ 연결 코드는 비밀번호처럼 다루세요(화면을 찍어 올리지 마세요). 이 코드를 가진 사람은 내 KLAS 정보를 조회하는 연결을 만들 수 있습니다.")
    print("   연결된 앱은 `kw-mcp connections`로 확인하고 `kw-mcp revoke <ID>`로 끊을 수 있습니다.")


def _status() -> None:
    import httpx

    from . import agent

    print(f"버전: {agent.installed_version()}")
    try:
        link = agent.load_link()
        print(f"연결됨: {link.server} (기기 {link.uid[:8]}…)")
    except agent.NotLinked as e:
        link = None
        print(e)
    print(f"자동 실행: {'등록됨' if agent.autostart_installed() else '없음'}")
    print(f"에이전트: {'실행 중' if agent.agent_running() else '꺼져 있음'}")
    uv = agent.find_uv()
    if not agent.in_uv_tool():
        print("자동 업데이트: 꺼짐 (uv tool로 설치한 에이전트만 스스로 업데이트합니다)")
    elif uv:
        print(f"자동 업데이트: 켜짐 (uv: {uv})")
    else:
        print("자동 업데이트: uv를 찾지 못해 꺼져 있습니다. 터미널에서 `kw-mcp link <초대코드>`를 다시 실행하세요.")
    if link is not None:
        try:
            agent.check_server_clock(link.server)
            print("PC 시계: 정상")
        except agent.ClockSkew as e:
            print(f"PC 시계: {e}")
        except httpx.HTTPError as e:
            print(f"중계 서버: 연결하지 못했습니다({e.__class__.__name__})")
    print(f"로그: {agent.default_log_file()}")


def _update() -> int:
    import httpx

    from . import agent

    try:
        server = agent.load_link().server
    except agent.NotLinked:
        print("이 PC가 연결돼 있지 않아 업데이트를 받을 서버를 모릅니다. 초대 링크(/setup)의 설치 명령을 실행하세요.")
        return 1
    if not agent.in_uv_tool():
        print("uv tool로 설치한 에이전트만 업데이트합니다. 초대 링크(/setup)의 설치 명령으로 설치하세요.")
        return 1
    if not agent.find_uv():
        print("uv를 찾지 못했습니다. https://docs.astral.sh/uv/ 에서 설치한 뒤 다시 실행하세요.")
        return 1
    async def fetch():
        async with httpx.AsyncClient(timeout=120) as http:
            return await agent.fetch_update(http, server)

    before = agent.installed_version()
    found = asyncio.run(fetch())
    if found is None:
        print(f"설치할 새 버전이 없습니다(지금 {before}). 실패한 업데이트가 있었다면 로그를 확인하세요: {agent.default_log_file()}")
        return 0
    manifest, wheel, constraints = found
    version = str(manifest["version"])
    if os.name == "nt":
        # Windows can't replace files a running agent holds open. Terminated, it can't record that
        # it stopped, so this does: the new version's first start must not count as a crash.
        agent.stop_agent_cleanly()
    if not agent.install_update(wheel, constraints, version):
        if os.name == "nt" and agent.autostart_installed():
            agent.install_autostart()  # start the agent again
        print(f"{version} 설치에 실패해 {before}을(를) 그대로 둡니다. 로그를 확인하세요: {agent.default_log_file()}")
        return 1
    if os.name == "nt":
        print(f"{version}을(를) 설치하고 에이전트를 다시 시작합니다. 1~2분 걸립니다(기록: {agent.default_log_file().with_name('update.log')}).")
        return 0
    now = agent.installed_version()
    if now != version:  # it failed, `before` couldn't be put back, and the last version that stayed up was
        print(f"{version} 설치에 실패했고 {before}(으)로 되돌리지 못해 마지막으로 잘 돌던 {now}(으)로 되돌렸습니다. "
              f"로그를 확인하세요: {agent.default_log_file()}")
        if agent.restart_autostarted_agent():
            print(f"에이전트를 {now}(으)로 다시 시작했습니다.")
        return 1
    print(f"{before} → {version} 설치를 마쳤습니다.")
    if agent.restart_autostarted_agent():
        print("에이전트를 새 버전으로 다시 시작했습니다.")
    return 0


def _agent(log_file: str | None, replace: bool) -> None:
    from keyring.errors import KeyringError

    from . import agent

    agent.configure_logging(log_file)
    try:
        if code := asyncio.run(agent.main(replace)):
            sys.exit(code)
    except agent.AlreadyRunning as e:
        agent.log.info("%s", e)
    except agent.NotLinked as e:
        agent.log.error("%s", e)
    except KeyringError as e:
        # Exit 0: launchd would otherwise restart the agent every 30 s, each run asking the keychain again.
        agent.log.error("the OS keychain refused access (%s). Allow access when it asks, then run `kw-mcp link` "
                        "again; the agent also starts at the next login", e.__class__.__name__)
    except KeyboardInterrupt:
        pass


async def _login_ok(retry: bool = True) -> int:
    import httpx

    from . import credentials, webconnect
    from .klas import KlasBadPassword, KlasError

    creds = credentials.load()
    try:
        await webconnect.check_login(creds)
    except KlasBadPassword as e:
        print(f"KLAS 로그인 실패: {e}")
        # The saved pair would fail again on every installer run: offer to fix it now, once.
        if retry and creds.source == credentials.KEYCHAIN and sys.stdin is not None and sys.stdin.isatty():
            print("학번과 비밀번호를 다시 입력하세요(한 번만 다시 시도합니다).")
            _setup()
            return await _login_ok(retry=False)
        return 1
    except KlasError as e:
        print(f"KLAS 로그인 실패: {e}")
        return 1
    except httpx.HTTPError as e:
        print(f"KLAS에 연결하지 못했습니다({e.__class__.__name__}). 인터넷 연결을 확인하고(VPN은 끄기) 다시 실행하세요.")
        return 1
    print("KLAS 로그인 확인")
    return 0


def _setup() -> None:
    from . import credentials

    login_id = input("KLAS 아이디(학번): ").strip()
    print("※ 비밀번호는 화면에 표시되지 않습니다. 한/영 입력 상태를 확인하세요.")
    password = getpass.getpass("KLAS 비밀번호: ")
    if not login_id or not password:
        sys.exit("아이디와 비밀번호를 모두 입력하세요.")
    if getpass.getpass("비밀번호 한 번 더: ") != password:
        sys.exit("두 비밀번호가 다릅니다. 저장하지 않았습니다.")
    credentials.save(login_id, password)
    print("키체인에 저장했습니다. `kw-mcp check`로 로그인을 확인하세요.")


async def _check() -> int:
    import httpx
    from keyring.errors import KeyringError

    from . import credentials
    from .klas import KlasClient, KlasError
    from .service import KlasService

    try:
        creds = credentials.load()
    except (credentials.MissingCredentials, KeyringError) as e:
        print(e)
        return 1
    async with KlasClient(creds.login_id, creds.password, login_hint=credentials.login_hint(creds)) as client:
        svc = KlasService(client)
        try:
            await client.login()
            print("로그인 성공")
            courses = await svc.courses()
            print(f"현재 학기 과목: {len(courses)}개")
            print(f"과제: {len(await svc.assignments())}개")
            print(f"온라인 강의: {len(await svc.online_lectures())}개")
            deadlines = await svc.deadlines()
            print(f"{deadlines['semester']} 학기, 7일 내 마감: {len(deadlines['items'])}건")
        except (KlasError, LookupError, httpx.HTTPError) as e:
            print(f"실패: {e}")
            return 1
    return 0
