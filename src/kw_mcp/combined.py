"""Tools that join personal KLAS data with kw-campus public data.

The join happens here, on the user's own machine: personal data never goes to the public
API, which only receives generic filters (date range, category). The public requests run
alongside the KLAS work; when they fail, the answer says so (public_data: "unavailable").
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Self

import httpx

from .klas import KlasError, KlasLoginError
from .public_api import PublicApi, PublicUnavailable
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
# Years not here get "공휴일 정보 없음". Add a year before its spring semester starts.
KR_HOLIDAYS = {
    "2026-01-01": "신정", "2026-02-16": "설날 연휴", "2026-02-17": "설날", "2026-02-18": "설날 연휴",
    "2026-03-01": "삼일절", "2026-03-02": "대체공휴일(삼일절)", "2026-05-05": "어린이날",
    "2026-05-24": "부처님오신날", "2026-05-25": "대체공휴일(부처님오신날)", "2026-06-03": "전국동시지방선거",
    "2026-06-06": "현충일", "2026-08-15": "광복절", "2026-08-17": "대체공휴일(광복절)",
    "2026-09-24": "추석 연휴", "2026-09-25": "추석", "2026-09-26": "추석 연휴", "2026-10-03": "개천절",
    "2026-10-05": "대체공휴일(개천절)", "2026-10-09": "한글날", "2026-12-25": "성탄절",
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
# The public API's generic "every department and college board" category (no personal data).
DEPARTMENT_CATEGORY = "학과"
MAIN_BOARD = "kw-notice"  # the public API's source name for the school's main notice board


def _today(svc: KlasService) -> datetime:
    return svc._now().astimezone(KST)


class _Public:
    """Public API calls started at once, next to the KLAS work, each falling back to a default and
    remembering why. Leaving the block cancels whatever is still running (a KLAS error)."""

    def __init__(self, api: PublicApi) -> None:
        self.api = api
        self.failures: dict[str, str] = {}
        self._tasks: list[asyncio.Task[Any]] = []

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

    def start(self, label: str, call: Awaitable[Any], default: Any) -> asyncio.Task[Any]:
        async def run() -> Any:
            try:
                return await call
            except PublicUnavailable as e:
                self.failures[label] = str(e)
                return default

        task = asyncio.ensure_future(run())
        self._tasks.append(task)
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
        alert = await alerts
        if day_off:
            alert = {**alert, "today": [{"start": today, "end": today, "title": day_off, "source": "법정 공휴일"},
                                        *alert["today"]]}
        if not in_session:
            classes_note = {"classes_note": f"{semester} 학기 수업 기간이 아니라 시간표를 비웠습니다."}
        elif day_off:
            classes_note = {"classes_note": f"오늘은 공휴일({day_off})이라 정규 수업은 쉬는 날입니다(휴업일). "
                                            "보강이 잡혔을 수 있으니 possible_class_changes와 과목 공지를 확인하세요."}
        else:
            classes_note = {}
        return {
            "date": now.strftime("%Y-%m-%d"),
            "weekday": weekday,
            "classes": classes,
            **classes_note,
            "due_today_or_tomorrow": soon,
            **({"deadlines_incomplete": deadlines["incomplete"]} if deadlines.get("incomplete") else {}),
            "cafeteria": await menu,
            "new_course_posts": course_posts,
            # Recent posts that look like a class being cancelled, made up or moved online.
            "possible_class_changes": [n for n in course_posts if CLASS_CHANGE_WORDS.search(n.get("title") or "")],
            "new_school_notices": await school,
            **({"campus_alerts": alert} if alert["notices"] or alert["today"] else {}),
            **pub.status("학교 공지·학식"),
            **({} if now.strftime("%Y") in HOLIDAY_YEARS else {"holiday_check": f"{now.year}년 공휴일 정보 없음"}),
            "note": "시간은 KLAS 시간표의 교시표 기준입니다. 강의실 변경·휴강은 과목 게시판을 확인하세요.",
        }


def department_notices(rows: list[dict[str, Any]], department: str, college: str | None) -> list[dict[str, Any]]:
    """Rows from the department/college boards that belong to me: my department's own board, posts a
    college board tags with my department, and my college's general posts."""
    out = []
    for r in rows:
        category, dept = str(r.get("category") or ""), str(r.get("department") or "")
        if department in (category, dept) or college and category == college and dept in ("", college):
            out.append(r)
    return out


async def my_notices(svc: KlasService, public: PublicApi, days: int = 7) -> dict[str, Any]:
    now = _today(svc)
    days = max(1, min(_int(days) or 7, 180))
    since_dt = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    since = (now.date() - timedelta(days=days)).isoformat()
    async with _Public(public) as pub:
        academic = pub.start("학사 공지", public.notices(category="학사", limit=20, since=since), [])
        scholarship = pub.start("장학 공지", public.notices(category="장학", limit=20, since=since), [])
        # Every department board, filtered here: the student's department never leaves this PC.
        boards = pub.start("학과 공지", public.notices(category=DEPARTMENT_CATEGORY, limit=50, since=since), [])
        course_posts = [n for n in await svc.notices() if (n.get("posted") or "") >= since_dt]
        try:
            department = await svc.department()
        except KlasLoginError:
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
        rows = await boards
        if department:
            college = COLLEGE_OF_DEPARTMENT.get(department)
            out["department"] = department_notices(rows, department, college)
            out["department_scope"] = {
                "department": department, "college": college,
                "note": "내 학과 게시판과 단과대 공지(다른 학과를 지정한 글 제외)입니다. 학과 이름은 이 PC에서만 씁니다."
                        + ("" if college else " 이 학과의 단과대를 몰라 단과대 공지는 넣지 못했습니다."),
            }
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


# School-wide notices that can change today's classes or getting around campus.
CAMPUS_ALERT_WORDS = re.compile(r"휴강|휴업|공휴일|대체\s*공휴일|임시\s*공휴일|개교기념일|출입\s*(?:통제|제한)|통제|정전|단수|폐쇄|"
                                r"점검|이전|임시\s*휴관|재난|기상|태풍|폭설|한파|폭염")
HOLIDAY_WORDS = re.compile(r"휴일|공휴일|개교기념일|휴업|방학")


async def campus_alerts(public: PublicApi, now: datetime) -> dict[str, Any]:
    """Recent school notices (3 days) that look like closures, outages or holidays, and today's
    calendar entries that are days off. KLAS course boards don't carry these. Raises
    PublicUnavailable when the public API fails."""
    today = now.date()
    notices, events = await asyncio.gather(  # main board only: job ads and other colleges crowd the window
        public.notices(limit=30, since=(today - timedelta(days=3)).isoformat(), pinned=True, source=MAIN_BOARD),
        public.calendar(today.isoformat(), today.isoformat()), return_exceptions=True)
    for result in (notices, events):
        if isinstance(result, BaseException):
            raise result
    return {"notices": [n for n in notices or [] if CAMPUS_ALERT_WORDS.search(n.get("title") or "")],
            "today": [e for e in events or [] if HOLIDAY_WORDS.search(e.get("title") or "")]}
