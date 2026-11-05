"""KLAS (Kwangwoon University) MCP server."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="kw-mcp", description="KLAS MCP server")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="MCP 서버 실행 (stdio, 기본값)")
    sub.add_parser("setup", help="KLAS 아이디/비밀번호를 키체인에 저장")
    sub.add_parser("check", help="로그인하고 조회가 되는지 개수만 출력")
    sub.add_parser("forget", help="키체인에 저장한 로그인 정보 삭제")
    args = parser.parse_args()

    if args.command == "setup":
        _setup()
    elif args.command == "check":
        sys.exit(asyncio.run(_check()))
    elif args.command == "forget":
        from . import credentials

        credentials.delete()
        print("키체인에서 KLAS 로그인 정보를 삭제했습니다.")
    else:
        from .server import run

        run()


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
