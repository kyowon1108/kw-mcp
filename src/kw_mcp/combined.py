"""Tools that join personal KLAS data with kw-campus public data.

The join happens here, on the user's own machine: personal data never goes to the public
API, which only receives generic filters (date range, category). The public requests run
alongside the KLAS work; when they fail, the answer says so (public_data: "unavailable").
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Self

import httpx

from .klas import KlasError, KlasLoginError, KlasRequestLimit
from .public_api import PublicApi, PublicUnavailable, _rows
from .service import (
    CLASS_CHANGE_WORDS,
    KST,
    MAX_DEADLINE_DAYS,
    KlasService,
    _int,
    parse_kst,
    parse_schedule,
    period_time,
    term_in_session,
)

WEEKDAYS = "월화수목금토일"

# Legal holidays (관공서의 공휴일, incl. 대체공휴일 and election days) the school calendar doesn't list.
# Years not here get "공휴일 정보 없음". Add a year before its winter session starts (late December).
# 노동절 and 제헌절 are 관공서 공휴일 since 2026 (규정 개정, 2026-04-28 국무회의). 2027 follows the
# 우주항공청 2027년 월력요항 as published by 한국천문연구원 (astro.kasi.re.kr), 대체공휴일 included.
KR_HOLIDAYS = {
    "2026-01-01": "신정", "2026-02-16": "설날 연휴", "2026-02-17": "설날", "2026-02-18": "설날 연휴",
    "2026-03-01": "삼일절", "2026-03-02": "대체공휴일(삼일절)", "2026-05-01": "노동절", "2026-05-05": "어린이날",
    "2026-05-24": "부처님오신날", "2026-05-25": "대체공휴일(부처님오신날)", "2026-06-03": "전국동시지방선거",
    "2026-06-06": "현충일", "2026-07-17": "제헌절", "2026-08-15": "광복절", "2026-08-17": "대체공휴일(광복절)",
    "2026-09-24": "추석 연휴", "2026-09-25": "추석", "2026-09-26": "추석 연휴", "2026-10-03": "개천절",
    "2026-10-05": "대체공휴일(개천절)", "2026-10-09": "한글날", "2026-12-25": "성탄절",
    "2027-01-01": "신정", "2027-02-06": "설날 연휴", "2027-02-07": "설날", "2027-02-08": "설날 연휴",
    "2027-02-09": "대체공휴일(설날)", "2027-03-01": "삼일절", "2027-05-01": "노동절", "2027-05-03": "대체공휴일(노동절)",
    "2027-05-05": "어린이날", "2027-05-13": "부처님오신날", "2027-06-06": "현충일", "2027-07-17": "제헌절",
    "2027-07-19": "대체공휴일(제헌절)", "2027-08-15": "광복절", "2027-08-16": "대체공휴일(광복절)",
    "2027-09-14": "추석 연휴", "2027-09-15": "추석", "2027-09-16": "추석 연휴", "2027-10-03": "개천절",
    "2027-10-04": "대체공휴일(개천절)", "2027-10-09": "한글날", "2027-10-11": "대체공휴일(한글날)",
    "2027-12-25": "성탄절", "2027-12-27": "대체공휴일(성탄절)",
}
HOLIDAY_YEARS = frozenset(day[:4] for day in KR_HOLIDAYS)

# Department (KLAS 학적 hakgwa) -> college, for the college boards kw-campus collects. Taken from
# kw-campus's own board table (routing.COLLEGE_OF, deptboards, aicon.SCHOOLS) plus the 경영대학
# and 인제니움학부대학 departments. A department not listed still gets its own board's notices.
COLLEGE_OF_DEPARTMENT = {
    **dict.fromkeys(("전자공학과", "전자통신공학과", "전자융합공학과", "전기공학과", "전자재료공학과", "반도체시스템공학부"),
                    "전자정보공과대학"),
    **dict.fromkeys(("컴퓨터정보공학부", "소프트웨어학부", "정보융합학부", "로봇학부"), "인공지능융합대학"),
    **dict.fromkeys(("건축공학과", "화학공학과", "건축학과"), "공과대학"),
    "스포츠융합과학과": "자연과학대학",
    **dict.fromkeys(("국어국문학과", "영어산업학과", "산업심리학과", "동북아문화산업학부", "미디어커뮤니케이션학부"),
                    "인문사회과학대학"),
    **dict.fromkeys(("법학부", "행정학과"), "정책법학대학"),
    **dict.fromkeys(("경영학부", "국제통상학부"), "경영대학"),
    **dict.fromkeys(("금융부동산법무학과", "게임콘텐츠학과", "스포츠상담재활학과"), "참빛인재대학"),
    "자율전공학부": "인제니움학부대학",
}
# The department and college boards kw-campus collects, by the name the public API gives them as
# category (kw-campus checks this list against its own board table). A department not here has no
# board of its own in the public data; one whose college is not here gets no college posts either.
DEPARTMENT_BOARDS = frozenset({
    "인공지능융합대학", "전자정보공과대학", "전자공학과", "전자통신공학과", "전자융합공학과", "전기공학과", "전자재료공학과",
    "반도체시스템공학부", "법학부", "건축공학과", "인문사회과학대학", "국어국문학과", "영어산업학과", "산업심리학과",
    "동북아문화산업학부", "행정학과", "경영대학", "참빛인재대학", "금융부동산법무학과", "게임콘텐츠학과", "스포츠상담재활학과",
    "인제니움학부대학", "화학공학과", "스포츠융합과학과", "건축학과", "미디어커뮤니케이션학부", "자율전공학부",
})
# The public API's generic "every department and college board" category (no personal data).
DEPARTMENT_CATEGORY = "학과"
# Rows asked of it. kw-campus 1.0 answers up to this many for department boards and says the cap it
# applied (max_limit); older servers stop at LEGACY_LIMIT without saying so. An answer that reached
# the cap may have cut older posts, and my_notices says so.
DEPARTMENT_LIMIT = 200
LEGACY_LIMIT = 50
MAIN_BOARD = "kw-notice"  # the public API's source name for the school's main notice board
# Main-board categories that are never about this campus: outside organisations' recruiting and contests.
NOT_CAMPUS_CATEGORIES = frozenset({"external", "job", "faq"})


def _today(svc: KlasService) -> datetime:
    return svc._now().astimezone(KST)


class _Public:
    """Public API calls started at once, next to the KLAS work, each falling back to a default and
    remembering why. Leaving the block cancels whatever is still running (a KLAS error)."""

    def __init__(self, api: PublicApi) -> None:
        self.api = api
        self.failures: dict[str, str] = {}
        self._tasks: list[asyncio.Task[Any]] = []
        self._calls: list[Awaitable[Any]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, kind: type[BaseException] | None, error: BaseException | None,
                        tb: TracebackType | None) -> None:
        pending = [t for t in self._tasks if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in self._tasks:  # a request error nobody awaited (the KLAS part failed first): mark it seen
            if not task.cancelled():
                task.exception()
        for call in self._calls:  # a task cancelled before it ran never started its request: close it
            if inspect.iscoroutine(call):
                call.close()

    def start(self, label: str, call: Awaitable[Any], default: Any) -> asyncio.Task[Any]:
        async def run() -> Any:
            try:
                return await call
            except PublicUnavailable as e:
                self.failures[label] = str(e)
                return default

        task = asyncio.ensure_future(run())
        self._tasks.append(task)
        self._calls.append(call)
        return task

    def status(self, what: str) -> dict[str, Any]:
        """public_data "ok", "unavailable" (+ the reason), or why nothing was asked."""
        if not self.api.configured:
            return {"public_data": f"공개 API(kw-campus)가 설정되지 않아 {what}은 비어 있습니다."}
        if not self.failures:
            return {"public_data": "ok"}
        reasons = list(dict.fromkeys(self.failures.values()))
        return {"public_data": "unavailable",
                "public_data_reason": f"{' / '.join(reasons)} (빠진 것: {', '.join(self.failures)}). "
                                      "비어 있는 학교 정보는 '없음'이 아니라 '확인하지 못함'입니다."}


def _span(days: Any) -> int:
    """The same clamp deadlines() uses (0..MAX_DEADLINE_DAYS, default 7)."""
    value = _int(days)
    return max(0, min(7 if value is None else value, MAX_DEADLINE_DAYS))


async def this_week(svc: KlasService, public: PublicApi, days: int = 7) -> dict[str, Any]:
    today = _today(svc).date()
    async with _Public(public) as pub:
        events = pub.start("학사일정", public.calendar(today.isoformat(), (today + timedelta(days=_span(days))).isoformat()),
                           [])
        deadlines = await svc.deadlines(days)
        return {**deadlines, "academic_events": await events, **pub.status("학사일정")}


def holiday(day: datetime) -> str | None:
    return KR_HOLIDAYS.get(day.strftime("%Y-%m-%d"))


def holiday_check(day: datetime) -> dict[str, str]:
    """"공휴일 정보 없음" for a year KR_HOLIDAYS doesn't cover; {} otherwise."""
    return {} if day.strftime("%Y") in HOLIDAY_YEARS else {"holiday_check": f"{day.year}년 공휴일 정보 없음"}


def classes_note(semester: str | None, in_session: bool | None, day_off: str | None) -> dict[str, str]:
    """Why today's timetable is empty or doesn't hold. in_session None: the term is unknown (the bridge
    without a snapshot), so only a holiday is said."""
    if in_session is False:
        return {"classes_note": f"{semester} 학기 수업 기간이 아니라 시간표를 비웠습니다."}
    if day_off:
        return {"classes_note": f"오늘은 공휴일({day_off})이라 정규 수업은 쉬는 날입니다(휴업일). "
                                "보강이 잡혔을 수 있으니 possible_class_changes와 과목 공지를 확인하세요."}
    return {}


def with_holiday(alerts: dict[str, Any], day_off: str | None, today: str) -> dict[str, Any]:
    """Campus alerts with today's legal holiday first among today's days off."""
    if not day_off:
        return alerts
    return {**alerts, "today": [{"start": today, "end": today, "title": day_off, "source": "법정 공휴일"},
                                *alerts["today"]]}


async def today_briefing(svc: KlasService, public: PublicApi) -> dict[str, Any]:
    now = _today(svc)
    weekday = WEEKDAYS[now.weekday()]
    today = now.date().isoformat()
    async with _Public(public) as pub:
        school = pub.start("학교 공지", public.notices(limit=10, since=(now.date() - timedelta(days=1)).isoformat(),
                                                    pinned=False, source=MAIN_BOARD), [])
        alerts = pub.start("학교 알림", campus_alerts(public, now), {"notices": [], "today": []})
        menu = pub.start("학식", public.menu(today), None)

        semester = await svc.current_semester()
        in_session = term_in_session(semester, now)
        courses = await svc.courses() if in_session else []  # no timetable during breaks
        day_off = holiday(now)
        classes = []
        for c in courses:
            for slot in parse_schedule(c.get("schedule")):
                if slot["weekday"] == weekday:
                    classes.append({"course": c["course"], "periods": slot["periods"], "time": period_time(slot["periods"]),
                                    "room": slot["room"], "professor": c.get("professor"),
                                    **({"holiday": day_off} if day_off else {})})
        classes.sort(key=lambda x: x["periods"][0] if x["periods"] else 99)

        end_of_tomorrow = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        deadlines = await svc.deadlines(2)
        soon = []
        for item in deadlines["items"]:
            due = parse_kst(item.get("late_due") if item.get("late_submission") else item.get("effective_due") or item.get("due"))
            if due and due <= end_of_tomorrow:
                soon.append(item)

        since = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
        course_posts = [n for n in await svc.notices() if (n.get("posted") or "") >= since]
        alert = with_holiday(await alerts, day_off, today)
        return {
            "date": now.strftime("%Y-%m-%d"),
            "weekday": weekday,
            "classes": classes,
            **classes_note(semester, in_session, day_off),
            "due_today_or_tomorrow": soon,
            **({"deadlines_incomplete": deadlines["incomplete"]} if deadlines.get("incomplete") else {}),
            "cafeteria": await menu,
            "new_course_posts": course_posts,
            # Recent posts that look like a class being cancelled, made up or moved online.
            "possible_class_changes": [n for n in course_posts if CLASS_CHANGE_WORDS.search(n.get("title") or "")],
            "new_school_notices": await school,
            **({"campus_alerts": alert} if alert["notices"] or alert["today"] else {}),
            **pub.status("학교 공지·학식"),
            **holiday_check(now),
            "note": "시간은 KLAS 시간표의 교시표 기준입니다. 강의실 변경·휴강은 과목 게시판을 확인하세요.",
        }


def _mine(row: dict[str, Any], department: str, college: str | None) -> bool:
    category, dept = str(row.get("category") or ""), str(row.get("department") or "")
    return department in (category, dept) or bool(college) and category == college and dept in ("", college)


def department_notices(rows: list[dict[str, Any]], department: str, college: str | None) -> list[dict[str, Any]]:
    """Rows from the department/college boards that belong to me: my department's own board, posts a
    college board tags with my department, and my college's general posts. A notice several boards
    posted under one title comes once, with the other copies in also_boards; when one of those copies
    is on my board, that copy (its board, date and link) is the one kept."""
    out = []
    for r in rows:
        if _mine(r, department, college):
            out.append(r)
            continue
        copies = [c for c in r.get("also_boards") or [] if isinstance(c, dict)]
        mine = next((c for c in copies if _mine(c, department, college)), None)
        if mine is not None:
            out.append({**{k: v for k, v in r.items() if k not in ("also", "also_boards")}, **mine})
    return out


def department_section(rows: list[dict[str, Any]], department: str, cap: int | None = None,
                       note: str = "") -> dict[str, Any]:
    """my_notices' "department" and "department_scope" from the department-board rows the public data
    gave: which boards are collected, and, when the answer reached `cap` (the most rows it could carry;
    None for a server before kw-campus 1.0, which stops at LEGACY_LIMIT without saying so), how far
    back it reached. The bridge builds the same section from its own query of the student's boards."""
    college = COLLEGE_OF_DEPARTMENT.get(department)
    own, college_board = department in DEPARTMENT_BOARDS, bool(college) and college in DEPARTMENT_BOARDS
    parts = ["내 학과 게시판과 단과대 공지(다른 학과를 지정한 글 제외)입니다."]
    if not college:
        parts.append("이 학과의 단과대를 몰라 단과대 공지는 넣지 못했습니다.")
    elif not college_board:
        parts.append(f"단과대({college}) 게시판은 아직 모으지 않아 단과대 공지는 넣지 못했습니다.")
    if not own and college_board:
        parts.append(f"내 학과 게시판은 따로 모으지 않아 {college} 게시판의 글만 넣었습니다.")
    elif not own:
        parts.append("내 학과 게시판도 아직 모으지 않아 학과 공지를 확인하지 못했습니다. 비어 있어도 '없음'이 아닙니다.")
    scope: dict[str, Any] = {"department": department, "college": college,
                             "boards": [name for name in (department, college) if name and name in DEPARTMENT_BOARDS]}
    if rows and len(rows) >= (LEGACY_LIMIT if cap is None else cap):
        oldest = min(str(r.get("posted_date") or "") for r in rows) or None
        scope.update(truncated=True, covered_from=oldest)
        parts.append(f"학과 게시판 글을 최근 {len(rows)}개까지만 받아 {oldest or '?'} 이후 글만 확인했습니다. "
                     "그 전 글은 빠졌을 수 있습니다.")
    scope["note"] = " ".join([*parts, note] if note else parts)
    return {"department": department_notices(rows, department, college), "department_scope": scope}


async def department_rows(public: PublicApi, since: str) -> tuple[list[dict[str, Any]], int | None]:
    """Every department board's posts since `since` (generic: the student's department stays on this
    PC), and the most rows the answer could carry: DEPARTMENT_LIMIT, or the smaller cap a kw-campus
    1.0 server says it applied (max_limit); None from an older server, which doesn't say."""
    # PublicApi.notices() gives only the rows; this needs the answer's max_limit too (same request).
    data = await public._get("/api/notices", {"category": DEPARTMENT_CATEGORY, "limit": DEPARTMENT_LIMIT,
                                              "since": since, "pinned": "true"})
    applied = data.get("max_limit") if isinstance(data, dict) else None
    known = isinstance(applied, int) and not isinstance(applied, bool) and applied > 0
    return _rows(data, "notices"), min(applied, DEPARTMENT_LIMIT) if known else None


async def my_notices(svc: KlasService, public: PublicApi, days: int = 7) -> dict[str, Any]:
    now = _today(svc)
    days = max(1, min(_int(days) or 7, 180))
    since_dt = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    since = (now.date() - timedelta(days=days)).isoformat()
    async with _Public(public) as pub:
        academic = pub.start("학사 공지", public.notices(category="학사", limit=20, since=since), [])
        scholarship = pub.start("장학 공지", public.notices(category="장학", limit=20, since=since), [])
        # Every department board, filtered here: the student's department never leaves this PC.
        boards = pub.start("학과 공지", department_rows(public, since), ([], None))
        course_posts = [n for n in await svc.notices() if (n.get("posted") or "") >= since_dt]
        try:
            department = await svc.department()
        except (KlasLoginError, KlasRequestLimit):  # STOP_ERRORS: their own message says what to do and when
            raise
        except (KlasError, httpx.HTTPError) as e:  # a hiccup on the 학적 must not sink the other notices
            department, why = None, f"학적에서 학과를 읽지 못했습니다({e.__class__.__name__})"
        else:
            why = None if department else "KLAS 학적에 학과가 없습니다"
        out = {
            "days": days,
            "course_posts": course_posts,
            "school_academic": await academic,
            "school_scholarship": await scholarship,
        }
        rows, cap = await boards
        if department:
            out.update(department_section(rows, department, cap, note="학과 이름은 이 PC에서만 씁니다."))
        else:
            out["department_note"] = f"{why}. 학과 공지는 넣지 않았습니다."
        return {**out, **pub.status("학교 공지")}


# 학사일정 entries students ask deadlines for (에브리타임: "학사일정에 안 뜬다", 2026-11). (?!목) keeps 전과목 out.
ACADEMIC_DEADLINE_WORDS = re.compile(
    r"수강|(?:수업|강의)\s*(?:중간\s*)?평가|성적|이의|휴학|복학|등록|계절|졸업|장학|학점\s*포기|정정|중간고사|기말고사|"
    r"다전공|복수전공|부전공|연계전공|주전공|전과(?!목)|선택\s*기간|신청\s*기간")


async def academic_deadlines(svc: KlasService, public: PublicApi, days: int = 30) -> dict[str, Any]:
    """학사 기한 모음: KLAS's own "open now?" answers (scholarship applications, dropping earned
    credits, grade viewing, course evaluation) next to the 학사일정 entries for registration,
    course changes, evaluation, grades, leave of absence, 다전공 and the like."""
    days = max(1, min(_int(days) or 30, 180))
    today = _today(svc).date()
    end = today + timedelta(days=days)
    async with _Public(public) as pub:
        events = pub.start("학사일정", public.calendar(today.isoformat(), end.isoformat()), [])
        windows = await svc.application_windows()
        return {
            "from": today.isoformat(), "to": end.isoformat(),
            "klas": windows,
            "calendar": [e for e in await events if ACADEMIC_DEADLINE_WORDS.search(e.get("title") or "")],
            **pub.status("학사일정"),
            "note": "klas는 KLAS가 지금 열려 있는지 직접 알려 준 값, calendar는 학교 학사일정입니다. 학과별 일정은 학과 공지를 확인하세요.",
        }


# School-wide notices that can change today's classes or getting around campus. Broad words need
# their context: a bare 점검/통제/이전/기상/재난 also fits job ads and contests (품질점검 인턴, 생산통제,
# 기상청 인턴, "이전 공지 참고", 국민재난안전 공모전), and 정전협정·단수전공·폐쇄회로 are not outages.
# The context stays wide enough for facility notices: 소방시설 정기점검, 일부 구역 통제, 학생지원팀 이전
# (an office: 팀·처·실·과·단 before 이전, unless 이전 means "earlier": 이전 학기, 이전 공지, 이전에는).
CAMPUS_ALERT_WORDS = re.compile(
    r"휴강|휴업|공휴일|대체\s*공휴일|임시\s*공휴일|개교기념일|임시\s*휴관|태풍|폭설|한파|폭염|"
    r"출입\s*(?:통제|제한)|(?:교통|차량|통행|도로|주차장?)\s*(?:통제|제한)|(?:구역|시설|건물|출입구|통로)\s*통제|"
    r"정전(?!협정|기)|단수(?!전공)|폐쇄(?!회로|몰)|"
    r"(?:시스템|전산|서버|네트워크|인터넷|와이파이|무선\s*랜|KLAS|클라스|홈페이지|전기|소방|승강기|엘리베이터)\s*"
    r"(?:시설\s*|설비\s*)?(?:정기\s*|긴급\s*|안전\s*)?점검|"
    r"(?:건물|사무실|사무소|열람실|도서관|센터|위치|강의실|팀|처|실|과|단)\s*(?:\S{1,10}\s*)?이전"
    r"(?!\s*(?:에는|에도|의|과|보다|까지|부터|처럼|공지|학기|글|게시|버전|년도|연도|기수|회차|내용|자료|대비|이수))|"
    r"기상\s*(?:악화|특보|경보|주의보)|(?:재난|재해)\s*(?:상황|발생|경보|문자|대응\s*단계)", re.IGNORECASE)
HOLIDAY_WORDS = re.compile(r"휴일|공휴일|개교기념일|휴업|방학")
ALERT_LIMIT = 50  # three days of the main board stay well under this (the server's cap)


def campus_alert_notices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Main-board notices that look like closures, outages or holidays (not 외부 recruiting or contests)."""
    return [n for n in rows if n.get("category_id") not in NOT_CAMPUS_CATEGORIES
            and CAMPUS_ALERT_WORDS.search(n.get("title") or "")]


async def campus_alerts(public: PublicApi, now: datetime) -> dict[str, Any]:
    """Recent school notices (3 days) that look like closures, outages or holidays, and today's
    calendar entries that are days off. KLAS course boards don't carry these. Raises
    PublicUnavailable when the public API fails."""
    today = now.date()
    notices, events = await asyncio.gather(  # main board only: job ads and other colleges crowd the window
        public.notices(limit=ALERT_LIMIT, since=(today - timedelta(days=3)).isoformat(), pinned=True, source=MAIN_BOARD),
        public.calendar(today.isoformat(), today.isoformat()), return_exceptions=True)
    for result in (notices, events):
        if isinstance(result, BaseException):
            raise result
    return {"notices": campus_alert_notices(notices or []),
            "today": [e for e in events or [] if HOLIDAY_WORDS.search(e.get("title") or "")]}
