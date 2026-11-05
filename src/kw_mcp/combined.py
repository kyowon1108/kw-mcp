"""Tools that join personal KLAS data with kw-campus public data.

The join happens here, on the user's own machine: personal data never goes to the public
API, which only receives generic filters (date range, category).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .public_api import PublicApi
from .service import CLASS_CHANGE_WORDS, KST, KlasService, parse_kst, parse_schedule, term_in_session

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
                classes.append({"course": c["course"], "periods": slot["periods"], "room": slot["room"],
                                "professor": c.get("professor")})
    classes.sort(key=lambda x: x["periods"][0] if x["periods"] else 99)

    end_of_tomorrow = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    deadlines = await svc.deadlines(2)
    soon = []
    for item in deadlines["items"]:
        due = parse_kst(item.get("late_due") if item.get("late_submission") else item.get("due"))
        if due and due <= end_of_tomorrow:
            soon.append(item)

    since = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    course_posts = [n for n in await svc.notices() if (n.get("posted") or "") >= since]
    school = await public.notices(limit=10, since=(now.date() - timedelta(days=1)).isoformat(), pinned=False)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "weekday": weekday,
        "classes": classes,
        **({} if in_session else {"classes_note": f"{semester} 학기 수업 기간이 아니라 시간표를 비웠습니다."}),
        "due_today_or_tomorrow": soon,
        "cafeteria": await public.menu(now.date().isoformat()),
        "new_course_posts": course_posts,
        # Recent posts that look like a class being cancelled, made up or moved online.
        "possible_class_changes": [n for n in course_posts if CLASS_CHANGE_WORDS.search(n.get("title") or "")],
        "new_school_notices": school,
        "note": "교시 번호는 KLAS 표기 그대로입니다. 강의실 변경·휴강은 과목 게시판을 확인하세요.",
    }


async def my_notices(svc: KlasService, public: PublicApi, days: int = 7) -> dict[str, Any]:
    now = _today(svc)
    since_dt = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    course_posts = [n for n in await svc.notices() if (n.get("posted") or "") >= since_dt]
    since = (now.date() - timedelta(days=days)).isoformat()
    academic = await public.notices(category="학사", limit=20, since=since)
    scholarship = await public.notices(category="장학", limit=20, since=since)
    return {
        "days": days,
        "course_posts": course_posts,
        "school_academic": academic,
        "school_scholarship": scholarship,
        "public_data": "ok" if public.configured else "공개 API(kw-campus)가 설정되지 않아 학교 공지는 비어 있습니다.",
    }
