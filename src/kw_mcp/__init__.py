"""KLAS (Kwangwoon University) MCP server."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys


def main() -> None:
    # Windows consoles behind a pipe may not be UTF-8; print Korean as "?" rather than crash.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="kw-mcp", description="KLAS MCP server")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="MCP 서버 실행 (stdio, 기본값)")
    sub.add_parser("setup", help="KLAS 아이디/비밀번호를 키체인에 저장")
    sub.add_parser("check", help="로그인하고 조회가 되는지 개수만 출력")
    sub.add_parser("forget", help="키체인에 저장한 로그인 정보 삭제")
    link = sub.add_parser("link", help="이 PC를 KW Campus 중계에 연결하고 로그인 시 자동 실행 (처음 한 번)")
    link.add_argument("invite", help="받은 초대 코드 (kwc_...)")
    link.add_argument("--no-autostart", action="store_true", help="자동 실행을 등록하지 않음")
    link.add_argument("--server", help=argparse.SUPPRESS)  # set by the installer: the bridge it came from
    sub.add_parser("code", help="Claude/ChatGPT 커넥터 승인에 넣을 1회용 연결 코드 발급")
    sub.add_parser("status", help="연결·자동 실행 상태 확인")
    sub.add_parser("unlink", help="이 PC 연결 해제 (커넥터도 더 이상 동작하지 않음)")
    agent = sub.add_parser("agent", help="중계 요청에 응답하는 백그라운드 에이전트 (자동 실행이 씀)")
    agent.add_argument("--log-file")
    agent.add_argument("--replace", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.command == "setup":
        _setup()
    elif args.command == "check":
        sys.exit(asyncio.run(_check()))
    elif args.command == "forget":
        from . import credentials

        credentials.delete()
        print("키체인에서 KLAS 로그인 정보를 삭제했습니다.")
    elif args.command == "link":
        sys.exit(_link(args.invite, autostart=not args.no_autostart, server=args.server))
    elif args.command == "code":
        sys.exit(_code())
    elif args.command == "status":
        _status()
    elif args.command == "unlink":
        from . import agent as agent_mod

        try:
            agent_mod.unlink()
        except agent_mod.NotLinked as e:
            sys.exit(str(e))
        print("이 PC의 연결을 해제했습니다. Claude/ChatGPT의 커넥터도 지워 주세요.")
    elif args.command == "agent":
        _agent(args.log_file, args.replace)
    else:
        from .server import run

        run()


def _link(invite: str, autostart: bool, server: str | None = None) -> int:
    import httpx

    from . import agent, credentials

    try:
        invite_server, _ = agent.parse_invite(invite)
        if server and invite_server != server.rstrip("/"):
            raise ValueError(f"초대 코드의 서버({invite_server})가 설치한 곳({server})과 다릅니다. 받은 링크를 다시 확인하세요.")
    except ValueError as e:
        print(e)
        return 1
    try:
        credentials.load()
    except credentials.MissingCredentials:
        print("먼저 KLAS 학번과 비밀번호를 이 PC 키체인에 저장합니다(서버로는 보내지 않습니다).")
        _setup()
    if asyncio.run(_login_ok()) != 0:
        return 1
    try:
        _, mcp_url = agent.register(invite, server)
        if autostart:
            print(f"자동 실행 등록: {agent.install_autostart()}")
        code = agent.pair_code()
    except (ValueError, agent.NotLinked, NotImplementedError) as e:
        print(e)
        return 1
    except httpx.HTTPError as e:
        print(f"중계 서버에 연결하지 못했습니다: {e.__class__.__name__}")
        return 1
    _print_connect(mcp_url, code)
    return 0


def _code() -> int:
    import httpx

    from . import agent

    try:
        code = agent.pair_code()
    except agent.NotLinked as e:
        print(e)
        return 1
    except httpx.HTTPError as e:
        print(f"중계 서버에 연결하지 못했습니다: {e.__class__.__name__}")
        return 1
    _print_connect(code["mcp_url"], code)
    return 0


def _print_connect(mcp_url: str, code: dict) -> None:
    print()
    print("이제 Claude 또는 ChatGPT에 커넥터를 추가하세요.")
    print(f"  커넥터 URL : {mcp_url}")
    print(f"  연결 코드  : {code['code']}   ({code['expires_in'] // 60}분 안에, 한 번만 사용)")
    print("  Claude: 설정 → 커넥터 → 커스텀 커넥터 추가 → URL 입력 → 연결 → 승인 페이지에 연결 코드 입력")
    print("  ChatGPT: 설정 → 앱과 커넥터 → 만들기 → URL 입력(OAuth) → 승인 페이지에 연결 코드 입력")
    print("다른 앱도 연결하려면 `kw-mcp code`로 새 코드를 받으세요.")
    print("※ 연결 코드는 비밀번호처럼 다루세요. 이 코드를 가진 사람은 내 KLAS 정보를 조회하는 연결을 만들 수 있습니다.")


def _status() -> None:
    from . import agent

    try:
        link = agent.load_link()
        print(f"연결됨: {link.server} (기기 {link.uid[:8]}…)")
    except agent.NotLinked as e:
        print(e)
    print(f"자동 실행: {'등록됨' if agent.autostart_installed() else '없음'}")
    print(f"에이전트: {'실행 중' if agent.agent_running() else '꺼져 있음'}")
    print(f"로그: {agent.default_log_file()}")


def _agent(log_file: str | None, replace: bool) -> None:
    from . import agent

    agent.configure_logging(log_file)
    try:
        asyncio.run(agent.main(replace))
    except agent.AlreadyRunning as e:
        agent.log.info("%s", e)
    except agent.NotLinked as e:
        agent.log.error("%s", e)
    except KeyboardInterrupt:
        pass


async def _login_ok() -> int:
    from .klas import KlasClient, KlasError

    from . import credentials

    creds = credentials.load()
    async with KlasClient(creds.login_id, creds.password) as client:
        try:
            await client.login()
        except KlasError as e:
            print(f"KLAS 로그인 실패: {e}")
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
    print("키체인에 저장했습니다. `uv run kw-mcp check`로 로그인을 확인하세요.")


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
    async with KlasClient(creds.login_id, creds.password) as client:
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
