"""Tools that join personal KLAS data with kw-campus public data.

The join happens here, on the user's own machine: personal data never goes to the public
API, which only receives generic filters (date range, category).
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any

from .public_api import PublicApi
from .service import CLASS_CHANGE_WORDS, KST, KlasService, parse_kst, parse_schedule, period_time, term_in_session

WEEKDAYS = "월화수목금토일"


def _today(svc: KlasService) -> datetime:
    return svc._now().astimezone(KST)  # noqa: SLF001 - the service owns the clock (tests inject it)


async def this_week(svc: KlasService, public: PublicApi, days: int = 7) -> dict[str, Any]:
    deadlines = await svc.deadlines(days)
    today = _today(svc).date()
    # deadlines() clamps days (0..180); use the same range for the calendar.
    events = await public.calendar(today.isoformat(), (today + timedelta(days=deadlines["days"])).isoformat())
    return {
        **deadlines,
        "academic_events": events,
        "public_data": "ok" if public.configured else "공개 API(kw-campus)가 설정되지 않아 학사일정은 비어 있습니다.",
    }


async def today_briefing(svc: KlasService, public: PublicApi) -> dict[str, Any]:
    now = _today(svc)
    weekday = WEEKDAYS[now.weekday()]
    semester = await svc.current_semester()
    in_session = term_in_session(semester, now)
    courses = await svc.courses() if in_session else []  # no timetable during breaks
    classes = []
    for c in courses:
        for slot in parse_schedule(c.get("schedule")):
            if slot["weekday"] == weekday:
                classes.append({"course": c["course"], "periods": slot["periods"], "time": period_time(slot["periods"]),
                                "room": slot["room"], "professor": c.get("professor")})
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
    school = await public.notices(limit=10, since=(now.date() - timedelta(days=1)).isoformat(), pinned=False)
    alerts = await campus_alerts(public, now)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "weekday": weekday,
        "classes": classes,
        **({} if in_session else {"classes_note": f"{semester} 학기 수업 기간이 아니라 시간표를 비웠습니다."}),
        "due_today_or_tomorrow": soon,
        **({"deadlines_incomplete": deadlines["incomplete"]} if deadlines.get("incomplete") else {}),
        "cafeteria": await public.menu(now.date().isoformat()),
        "new_course_posts": course_posts,
        # Recent posts that look like a class being cancelled, made up or moved online.
        "possible_class_changes": [n for n in course_posts if CLASS_CHANGE_WORDS.search(n.get("title") or "")],
        "new_school_notices": school,
        **({"campus_alerts": alerts} if alerts["notices"] or alerts["today"] else {}),
        "note": "시간은 KLAS 시간표의 교시표 기준입니다. 강의실 변경·휴강은 과목 게시판을 확인하세요.",
    }


async def my_notices(svc: KlasService, public: PublicApi, days: int = 7) -> dict[str, Any]:
    now = _today(svc)
    since_dt = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    course_posts = [n for n in await svc.notices() if (n.get("posted") or "") >= since_dt]
    since = (now.date() - timedelta(days=days)).isoformat()
    academic = await public.notices(category="학사", limit=20, since=since)
    scholarship = await public.notices(category="장학", limit=20, since=since)
    department = await public.notices(category="인공지능융합대학", limit=20, since=since)
    return {
        "days": days,
        "course_posts": course_posts,
        "school_academic": academic,
        "school_scholarship": scholarship,
        "department": department,
        "public_data": "ok" if public.configured else "공개 API(kw-campus)가 설정되지 않아 학교 공지는 비어 있습니다.",
    }


# 학사일정 entries students ask deadlines for (에브리타임: "학사일정에 안 뜬다", 2026-11).
ACADEMIC_DEADLINE_WORDS = re.compile(r"수강|수업평가|강의평가|성적|이의|휴학|복학|등록|계절|졸업|장학|학점\s*포기|정정|중간고사|기말고사")


async def academic_deadlines(svc: KlasService, public: PublicApi, days: int = 30) -> dict[str, Any]:
    """학사 기한 모음: KLAS's own "open now?" answers (scholarship applications, dropping earned
    credits, grade viewing, course evaluation) next to the 학사일정 entries for registration,
    course changes, evaluation, grades, leave of absence and the like."""
    days = max(1, min(int(days), 180))
    today = _today(svc).date()
    end = today + timedelta(days=days)
    windows, events = await asyncio.gather(svc.application_windows(), public.calendar(today.isoformat(), end.isoformat()))
    return {
        "from": today.isoformat(), "to": end.isoformat(),
        "klas": windows,
        "calendar": [e for e in events if ACADEMIC_DEADLINE_WORDS.search(e.get("title") or "")],
        "public_data": "ok" if public.configured else "공개 API(kw-campus)가 설정되지 않아 학사일정은 비어 있습니다.",
        "note": "klas는 KLAS가 지금 열려 있는지 직접 알려 준 값, calendar는 학교 학사일정입니다. 학과별 일정은 학과 공지를 확인하세요.",
    }


# School-wide notices that can change today's classes or getting around campus.
CAMPUS_ALERT_WORDS = re.compile(r"휴강|휴업|공휴일|대체\s*공휴일|임시\s*공휴일|개교기념일|출입\s*(?:통제|제한)|통제|정전|단수|폐쇄|"
                                r"점검|이전|임시\s*휴관|재난|기상|태풍|폭설|한파|폭염")
HOLIDAY_WORDS = re.compile(r"휴일|공휴일|개교기념일|휴업|방학")


async def campus_alerts(public: PublicApi, now: datetime) -> dict[str, Any]:
    """Recent school notices (3 days) that look like closures, outages or holidays, and today's
    calendar entries that are days off. KLAS course boards don't carry these."""
    today = now.date()
    notices, events = await asyncio.gather(
        public.notices(limit=30, since=(today - timedelta(days=3)).isoformat(), pinned=True),
        public.calendar(today.isoformat(), today.isoformat()))
    return {"notices": [n for n in notices or [] if CAMPUS_ALERT_WORDS.search(n.get("title") or "")],
            "today": [e for e in events or [] if HOLIDAY_WORDS.search(e.get("title") or "")]}
