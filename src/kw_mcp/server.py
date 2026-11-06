"""MCP server exposing read-only KLAS tools."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

import httpx
from keyring.errors import KeyringError
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import combined, credentials, updates
from .holder import KlasHolder
from .klas import KlasError
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
- 결과에 update_available이 있으면 새 버전이 있다고 사용자에게 한 번 알려 주세요.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
# Saves one file into Downloads; Claude asks the user before calling a tool that isn't read-only.
SAVES_FILE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)

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


_holder = KlasHolder()


async def service() -> KlasService:
    """The KLAS service; re-reads the saved login each call so a fixed password takes effect at once."""
    return _service if _service is not None else await _holder.service()


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
    """현재 학기에서 앞으로 days일(최대 180) 안에 마감되는 안 한 일: 과제·퀴즈·온라인시험(재응시 포함)·팀플·설문,
    진도 100% 미만 온라인 강의, 그리고 그 안에 끝나는 토론(참여 여부는 KLAS가 알려 주지 않음).
    마감은 지났지만 지각 제출 기간인 과제·팀플도 late_submission=true로 포함합니다(이때 due는 과거).
    incomplete가 있으면 일부 목록을 읽지 못한 것이니 사용자에게 알리세요."""
    with expected_errors():
        return await (await service()).deadlines(days)


@mcp.tool(annotations=READ_ONLY)
async def get_online_tests(course: str | None = None, pending_only: bool = False) -> list[dict[str, Any]]:
    """온라인시험 목록: 응시 기간, 응시 여부(in_progress는 응시 중), 교수가 연 재응시 기간(retry)."""
    with expected_errors():
        return await (await service()).online_tests(None, course, pending_only)


@mcp.tool(annotations=READ_ONLY)
async def get_surveys(course: str | None = None, pending_only: bool = False) -> list[dict[str, Any]]:
    """과목 설문 목록: 기간과 참여 여부."""
    with expected_errors():
        return await (await service()).surveys(None, course, pending_only)


@mcp.tool(annotations=READ_ONLY)
async def get_discussions(course: str | None = None) -> list[dict[str, Any]]:
    """과목 토론 주제: 시작·종료와 글 수. 내가 참여했는지는 KLAS 목록에 없어 토론실에서 확인해야 합니다."""
    with expected_errors():
        return await (await service()).discussions(None, course)


@mcp.tool(annotations=READ_ONLY)
async def get_course_overview(course: str | None = None) -> list[dict[str, Any]]:
    """과목별 한눈에 보기(KLAS 과목 홈과 같은 숫자): 온라인강의 완료/전체, 과제·퀴즈·온라인시험·팀플·설문 제출/전체,
    토론 참여/전체, 새 글 수, 자료실 글 수, 출석·결석·지각·조퇴·공결 횟수. "이 과목 뭐 남았어?"에 먼저 쓰세요."""
    with expected_errors():
        return await (await service()).course_overview(course)


@mcp.tool(annotations=READ_ONLY)
async def get_course_evaluation() -> dict[str, Any]:
    """수업평가: 지금 평가 기간인지(중간/기말)와 아직 평가하지 않은 과목. 평가는 KLAS에서 직접 해야 합니다."""
    with expected_errors():
        return await (await service()).course_evaluation()


@mcp.tool(annotations=READ_ONLY)
async def academic_deadlines(days: int = 30) -> dict[str, Any]:
    """학사 기한 모음: KLAS가 알려 주는 장학 신청·취득학점포기·성적 조회·수업평가 기간과, 앞으로 days일(최대 180)
    학사일정 중 수강신청·정정·포기, 등록, 휴·복학, 성적·이의신청, 계절학기, 졸업 관련 일정."""
    with expected_errors():
        return await combined.academic_deadlines(await service(), public(), days)


@mcp.tool(annotations=READ_ONLY)
async def get_grades() -> dict[str, Any]:
    """성적·학점: 학기별 과목 성적과 학기 평점(4.5 만점, 도구 계산), KLAS 평량평균(학적부·성적증명서 기준),
    전공·교양·기타 신청/취득/삭제 학점, 학과·학년·학적 상태, 학기별 석차·학사경고(standing), 이번 학기 성적 조회 기간,
    summary(전공·전공 외 평점, F 제외 평점, 재수강하지 않은 F 과목; 도구 계산). 이름·학번·이메일·지도교수는 포함하지 않습니다."""
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
                              source: Literal["post", "assignment"] = "post") -> dict[str, Any]:
    """첨부 파일 내용을 텍스트로 읽기(PDF·PPTX·DOCX·XLSX·HWP·HWPX·ipynb·코드/텍스트, zip은 파일 목록).
    source="post"면 과목 게시판 글(title=글 제목), "assignment"면 과제(title=과제 제목)의 첨부.
    file_name은 파일 이름 일부(첨부가 하나면 생략 가능). 길면 part=2, 3…으로 이어서 읽으세요(total_parts 참고)."""
    with expected_errors():
        return await (await service()).read_attachment(course, title, file_name, str(part), source)


@mcp.tool(annotations=READ_ONLY)
async def get_graduation_progress() -> dict[str, Any]:
    """졸업 이수 현황: 취득 학점(전공·교양·기타), 필수교양(광운인되기)과 균형교양 8개 영역별 이수 학점,
    입학 연도에 맞는 교양 규칙 충족 여부, 학교 졸업 사정 결과(official_check: 명단에 오른 경우 졸업 가능 여부와 불가 사유).
    "균형교양 더 들어야 해?", "졸업 가능해?"에 쓰세요."""
    with expected_errors():
        return await (await service()).graduation_progress()


@mcp.tool(annotations=READ_ONLY)
async def get_attendance(course: str | None = None) -> list[dict[str, Any]]:
    """출석 현황(KLAS 전자출석): 과목별 출석·결석·지각·조퇴·공결 횟수와 주차·회차별 기록. course는 과목명 일부(생략하면 전체)."""
    with expected_errors():
        return await (await service()).attendance(course)


@mcp.tool(annotations=READ_ONLY)
async def get_exam_info(course: str | None = None) -> list[dict[str, Any]]:
    """시험 정보 모아 보기: 과목별 강의계획서의 시험 주차·평가 비율과, 게시판에서 '시험'이 들어간 글(최신 6개).
    "시험 범위", "기말 언제" 같은 질문에 먼저 쓰고, 범위·장소는 get_course_post로 글을 열어 확인하세요."""
    with expected_errors():
        return await (await service()).exam_info(course)


@mcp.tool(annotations=READ_ONLY)
async def get_class_changes(days: int = 14) -> dict[str, Any]:
    """휴강·보강 공지: 모든 수강 과목의 강의 공지사항에서 최근 days일 안의 '휴강'·'보강' 글. "오늘 휴강이야?"에 쓰세요."""
    with expected_errors():
        return await (await service()).class_changes(days)


@mcp.tool(annotations=READ_ONLY)
async def get_syllabus(course: str) -> dict[str, Any]:
    """강의계획서: 개요·학습목표, 주차별 계획, 평가 비율, 교재, 교수 이메일·연구실 전화. course는 과목명 일부."""
    with expected_errors():
        return await (await service()).syllabus(course)


UPDATE_WAIT_S = 1.5
_checks: set[asyncio.Task] = set()  # keep running checks referenced until they finish


def _settle(task: asyncio.Task) -> None:
    _checks.discard(task)
    if not task.cancelled():
        task.exception()  # retrieved, so a failure is never logged as unhandled


async def with_update_notice(answer: Any) -> dict[str, Any]:
    """Run a combined tool while the (cached) new-version check runs alongside it. The answer never
    waits more than UPDATE_WAIT_S for the check; a slow check still fills the cache for next time."""
    check = asyncio.create_task(updates.latest())
    _checks.add(check)
    check.add_done_callback(_settle)
    result = await answer
    done, _ = await asyncio.wait({check}, timeout=UPDATE_WAIT_S)
    if check in done and not check.cancelled() and check.exception() is None and check.result():
        result["update_available"] = updates.notice(check.result())
    return result


@mcp.tool(annotations=READ_ONLY)
async def this_week(days: int = 7) -> dict[str, Any]:
    """이번 주 할 일: 앞으로 days일 안에 마감되는 미제출 과제·퀴즈·팀플과 미완료 온라인 강의, 그리고 같은 기간의 학사일정."""
    with expected_errors():
        return await with_update_notice(combined.this_week(await service(), public(), days))


@mcp.tool(annotations=READ_ONLY)
async def today_briefing() -> dict[str, Any]:
    """오늘 브리핑: 오늘 수업(교시·강의실), 오늘·내일 마감, 오늘 학식, 최근 과목 게시판 글과 학교 공지."""
    with expected_errors():
        return await with_update_notice(combined.today_briefing(await service(), public()))


@mcp.tool(annotations=READ_ONLY)
async def my_notices(days: int = 7) -> dict[str, Any]:
    """내 공지함: 최근 days일의 학교 학사·장학 공지 + 내 과목 게시판 새 글(KLAS 홈에 뜨는 최근 몇 개만).
    오래된 과목 공지나 특정 주제는 search_course_posts로 찾으세요."""
    with expected_errors():
        return await with_update_notice(combined.my_notices(await service(), public(), days))


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


async def check_update() -> dict[str, Any]:
    """이 확장(광운대 KLAS)의 새 버전이 있는지 확인합니다. 우리 릴리스 키로 서명된 버전만 알려 줍니다."""
    newer = await updates.latest(force=True)
    return {"installed": updates.installed_version(), "update_available": updates.notice(newer) if newer else None}


async def download_update() -> dict[str, Any]:
    """새 버전 확장 파일을 받아 서명된 해시와 맞는지 확인한 뒤 다운로드 폴더에 저장합니다.
    사용자가 받겠다고 할 때만 쓰세요. 저장된 파일을 더블클릭하면 Claude 데스크톱이 새 버전을 설치합니다."""
    with expected_errors():
        path = await updates.download()
    return {"saved_to": str(path), "next": "이 파일을 더블클릭해 설치하세요. 학번·비밀번호를 다시 물으면 다시 입력하면 됩니다."}


if updates.enabled():  # only the Claude Desktop extension can't update itself
    mcp.tool(annotations=READ_ONLY)(check_update)
    mcp.tool(annotations=SAVES_FILE)(download_update)


def run() -> None:
    # httpx logs every request URL at INFO; keep the MCP client's log view quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run("stdio")
