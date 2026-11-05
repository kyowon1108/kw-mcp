"""MCP server exposing read-only KLAS tools."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
from keyring.errors import KeyringError
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import combined, credentials
from .klas import KlasClient, KlasError
from .public_api import PublicApi
from .service import KlasService

INSTRUCTIONS = """\
광운대학교 KLAS(학습관리시스템)의 본인 데이터를 읽기 전용으로 조회합니다.
- 학기 값은 "2026,2" 형식입니다. 생략하면 현재 학기입니다.
- course 인자는 과목명 일부(예: "데이터")로 거르며, 생략하면 전체 과목입니다.
- 시각은 모두 한국 시간(KST)입니다.
- "이번 주 할 일"은 this_week, "오늘 뭐 있어"는 today_briefing, "새 공지"는 my_notices를 먼저 쓰세요.
  이 세 도구는 KLAS 개인 데이터와 학교 공개 정보(공지·학식·학사일정)를 이 PC에서 합칩니다.
- 학교 공지·학식·학사일정만 필요하면 school_notices, cafeteria_menu, academic_calendar를 쓰세요.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

mcp = MCPServer("kw-klas", instructions=INSTRUCTIONS)

_service: KlasService | None = None
_public: PublicApi | None = None


def public() -> PublicApi:
    global _public
    if _public is None:
        _public = PublicApi()
    return _public


def set_public(api: PublicApi | None) -> None:
    global _public
    _public = api


def set_service(service: KlasService | None) -> None:
    global _service
    _service = service


async def service() -> KlasService:
    global _service
    if _service is None:
        # Keychain access can block on a macOS permission prompt; keep it off the event loop.
        creds = await asyncio.to_thread(credentials.load)
        _service = KlasService(KlasClient(creds.login_id, creds.password))
    return _service


@contextmanager
def expected_errors() -> Iterator[None]:
    """Pass anticipated failures to the model as readable messages instead of a generic crash."""
    try:
        yield
    except (credentials.MissingCredentials, KlasError, LookupError) as e:
        raise ToolError(str(e)) from e
    except KeyringError as e:
        raise ToolError(f"키체인에서 KLAS 로그인 정보를 읽지 못했습니다: {e}") from e
    except httpx.HTTPError as e:
        raise ToolError(f"KLAS에 연결하지 못했습니다: {e!r}") from e
    except (KeyError, TypeError, AttributeError) as e:
        raise ToolError(f"KLAS 응답 형식이 예상과 다릅니다(사이트가 바뀌었을 수 있음): {e!r}") from e


@mcp.tool(annotations=READ_ONLY)
async def list_semesters() -> list[dict[str, Any]]:
    """수강 이력이 있는 학기 목록(최신순)과 학기별 과목명."""
    with expected_errors():
        return await (await service()).semesters()


@mcp.tool(annotations=READ_ONLY)
async def get_courses(semester: str | None = None) -> list[dict[str, Any]]:
    """학기의 수강 과목: 과목명, 담당교수, 강의 시간·강의실."""
    with expected_errors():
        return await (await service()).courses(semester)


@mcp.tool(annotations=READ_ONLY)
async def get_assignments(
    course: str | None = None, semester: str | None = None, pending_only: bool = False
) -> list[dict[str, Any]]:
    """과제 목록(마감순): 제목, 시작·마감·지각 마감, 제출 여부, 점수. pending_only=True면 미제출만."""
    with expected_errors():
        return await (await service()).assignments(semester, course, pending_only)


@mcp.tool(annotations=READ_ONLY)
async def get_online_lectures(
    course: str | None = None, semester: str | None = None, incomplete_only: bool = False
) -> list[dict[str, Any]]:
    """온라인 강의(마감순): 주차, 제목, 수강 기간, 진도율. incomplete_only=True면 진도 100% 미만만."""
    with expected_errors():
        return await (await service()).online_lectures(semester, course, incomplete_only)


@mcp.tool(annotations=READ_ONLY)
async def get_team_projects(course: str | None = None, semester: str | None = None) -> list[dict[str, Any]]:
    """팀 프로젝트(마감순): 제목, 목적, 시작·마감·지각 마감, 제출 여부, 점수, 팀 번호. 팀원 정보는 돌려주지 않습니다."""
    with expected_errors():
        return await (await service()).projects(semester, course)


@mcp.tool(annotations=READ_ONLY)
async def get_course_notices(course: str | None = None, semester: str | None = None) -> list[dict[str, Any]]:
    """과목 게시판의 최근 글(KLAS 홈 화면에 뜨는 몇 개만): 과목, 게시판, 제목, 작성일.
    오래된 공지나 특정 주제(시험·휴강 등)는 search_course_posts로 찾으세요."""
    with expected_errors():
        return await (await service()).notices(semester, course)


@mcp.tool(annotations=READ_ONLY)
async def get_deadlines(days: int = 7) -> dict[str, Any]:
    """현재 학기에서 앞으로 days일(최대 180) 안에 마감되는 미제출 과제와 진도 100% 미만 온라인 강의.
    마감은 지났지만 지각 제출 기간인 과제도 late_submission=true로 포함합니다."""
    with expected_errors():
        return await (await service()).deadlines(days)


@mcp.tool(annotations=READ_ONLY)
async def get_grades() -> dict[str, Any]:
    """성적·학점: 학기별 과목 성적과 학기 평점(4.5 만점, 도구 계산), KLAS 평량평균(학적부·성적증명서 기준),
    전공·교양·기타 신청/취득/삭제 학점, 학과·학년·학적 상태. 이름·학번·이메일·지도교수는 포함하지 않습니다."""
    with expected_errors():
        return await (await service()).grades()


@mcp.tool(annotations=READ_ONLY)
async def get_quizzes(
    course: str | None = None, semester: str | None = None, pending_only: bool = False
) -> list[dict[str, Any]]:
    """퀴즈(마감순): 제목, 유형, 시작·마감, 제출 여부, 제한 시간, 문항 수. pending_only=True면 미제출만."""
    with expected_errors():
        return await (await service()).quizzes(semester, course, pending_only)


@mcp.tool(annotations=READ_ONLY)
async def get_assignment_detail(course: str, title: str) -> dict[str, Any]:
    """과제 하나의 상세: 무엇을 내야 하는지(본문), 제출 형식·용량, 첨부 파일 이름, 기간, 지금 제출 가능한지,
    내 제출 시각·점수(공개된 경우)·교수 의견. course는 과목명 일부, title은 과제 제목 일부(get_assignments 결과)."""
    with expected_errors():
        return await (await service()).assignment_detail(course, title)


@mcp.tool(annotations=READ_ONLY)
async def search_course_posts(course: str, keyword: str = "") -> dict[str, Any]:
    """한 과목의 강의 공지사항·자료실 전체에서 글 찾기(최신순, 게시판마다 10개). keyword는 제목·본문 검색어
    (예: "시험", "휴강", "기말"). get_course_notices는 홈 화면의 최근 글만 보므로, 오래된 공지나 특정 주제는 이걸 쓰세요.
    본문은 get_course_post로 여세요."""
    with expected_errors():
        return await (await service()).search_course_posts(course, keyword)


@mcp.tool(annotations=READ_ONLY)
async def get_course_post(course: str, title: str) -> dict[str, Any]:
    """과목 게시판(강의 공지사항·강의 자료실) 글 하나의 본문과 첨부 파일 이름.
    course는 과목명 일부, title은 글 제목 일부(get_course_notices 결과)."""
    with expected_errors():
        return await (await service()).course_post(course, title)


@mcp.tool(annotations=READ_ONLY)
async def get_attachment_text(course: str, title: str, file_name: str = "", part: int = 1,
                              source: str = "post") -> dict[str, Any]:
    """첨부 파일 내용을 텍스트로 읽기(PDF·PPTX·DOCX·XLSX·HWP·HWPX·ipynb·코드/텍스트, zip은 파일 목록).
    source="post"면 과목 게시판 글(title=글 제목), "assignment"면 과제(title=과제 제목)의 첨부.
    file_name은 파일 이름 일부(첨부가 하나면 생략 가능). 길면 part=2, 3…으로 이어서 읽으세요(total_parts 참고)."""
    with expected_errors():
        return await (await service()).read_attachment(course, title, file_name, str(part), source)


@mcp.tool(annotations=READ_ONLY)
async def get_syllabus(course: str) -> dict[str, Any]:
    """강의계획서: 개요·학습목표, 주차별 계획, 평가 비율, 교재, 교수 이메일·연구실 전화. course는 과목명 일부."""
    with expected_errors():
        return await (await service()).syllabus(course)


@mcp.tool(annotations=READ_ONLY)
async def this_week(days: int = 7) -> dict[str, Any]:
    """이번 주 할 일: 앞으로 days일 안에 마감되는 미제출 과제·퀴즈·팀플과 미완료 온라인 강의, 그리고 같은 기간의 학사일정."""
    with expected_errors():
        return await combined.this_week(await service(), public(), days)


@mcp.tool(annotations=READ_ONLY)
async def today_briefing() -> dict[str, Any]:
    """오늘 브리핑: 오늘 수업(교시·강의실), 오늘·내일 마감, 오늘 학식, 최근 과목 게시판 글과 학교 공지."""
    with expected_errors():
        return await combined.today_briefing(await service(), public())


@mcp.tool(annotations=READ_ONLY)
async def my_notices(days: int = 7) -> dict[str, Any]:
    """내 공지함: 최근 days일의 내 과목 게시판 글 + 학교 학사·장학 공지."""
    with expected_errors():
        return await combined.my_notices(await service(), public(), days)


@mcp.tool(annotations=READ_ONLY)
async def school_notices(category: str | None = None, query: str | None = None, limit: int = 10) -> dict[str, Any]:
    """학교 메인 공지(공개): category(학사, 장학, 취업, 국제 등)와 query(제목 검색)로 거릅니다."""
    api = public()
    rows = await api.notices(category=category, limit=limit, query=query)
    return {"notices": rows, "configured": api.configured}


@mcp.tool(annotations=READ_ONLY)
async def cafeteria_menu(day: str | None = None) -> dict[str, Any]:
    """함지마루 학식 메뉴(공개). day는 YYYY-MM-DD(기본: 오늘)."""
    api = public()
    return (await api.menu(day)) or {"meals": [], "configured": api.configured}


@mcp.tool(annotations=READ_ONLY)
async def academic_calendar(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """학사일정(공개). start~end(YYYY-MM-DD, 기본: 오늘부터 30일)."""
    api = public()
    return {"events": await api.calendar(start, end), "configured": api.configured}


def run() -> None:
    # httpx logs every request URL at INFO; keep the MCP client's log view quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run("stdio")
