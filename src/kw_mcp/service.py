"""KLAS data shaped for LLM tools.

Raw KLAS rows use romanized Korean field names (`subjNm`, `expiredate`, ...).
This module maps the fields we have verified against the live site to plain
English keys and leaves the rest out.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .klas import KlasClient

KST = ZoneInfo("Asia/Seoul")

SEMESTERS = "/std/cmn/frame/YearhakgiAtnlcSbjectList.do"
HOME = "/std/cmn/frame/StdHome.do"
TASKS = "/std/lis/evltn/TaskStdList.do"
ONLINE = "/std/lis/evltn/SelectOnlineCntntsStdList.do"
PROJECTS = "/std/lis/evltn/PrjctStdList.do"
QUIZZES = "/std/lis/evltn/AnytmQuizStdList.do"
GRADES = "/std/cps/inqire/AtnlcScreSungjukInfo.do"
GRADE_TOTALS = "/std/cps/inqire/AtnlcScreSungjukTot.do"

# Raw KLAS fields the PC agent may send to the bridge (kwcampus.bridge.shapes reads these).
SNAPSHOT_FIELDS = {
    "courses": ("subj", "yearhakgi", "subjNm", "profNm", "lctrumSchdulInfo", "subjLabel"),
    "course_posts": ("subjNm", "typeNm", "title", "registDt"),
    "tasks": ("title", "startdate", "expiredate", "reexpiredate", "submityn", "score"),
    "online": ("evltnSe", "prog", "weekNo", "weeklyseq", "moduletitle", "sbjt", "startDate", "endDate",
               "rcognTime", "achivTime"),
    "projects": ("title", "purpose", "startdate", "expiredate", "reexpiredate", "submityn", "score", "teamno"),
    "quizzes": ("papernm", "examtypenm", "sdt", "edt", "issubmit", "examtime", "examcnt", "totalscore"),
}

HOME_TTL = 120.0
COURSE_TTL = 60.0
MAX_DEADLINE_DAYS = 180


def parse_kst(value: str | None) -> datetime | None:
    """Parse KLAS timestamps: naive KST strings, or ISO strings with an offset."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=KST)


def fmt_kst(value: str | None) -> str | None:
    parsed = parse_kst(value)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else value


def _matches(name: str | None, course: str | None) -> bool:
    return course is None or course.casefold() in (name or "").casefold()


async def _gather(*aws: Awaitable[Any]) -> list[Any]:
    """Run concurrently; on the first failure cancel the rest and raise that error itself."""
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_as_coro(a)) for a in aws]
    except ExceptionGroup as group:
        raise group.exceptions[0] from None
    return [t.result() for t in tasks]


async def _as_coro(aw: Awaitable[Any]) -> Any:
    return await aw


_SLOT = re.compile(r"^\s*([월화수목금토일])\s*([\d,\s]+)교시\s*(?:/\s*(.*?))?\s*$")


def parse_schedule(text: str | None) -> list[dict[str, Any]]:
    """KLAS 'lctrumSchdulInfo' like '화 3교시/새빛103, 목 4교시/새빛103' → weekday/periods/room slots."""
    slots = []
    for part in re.split(r",\s*(?=[월화수목금토일]\s)", text or ""):
        m = _SLOT.match(part)
        if m:
            periods = [int(x) for x in re.findall(r"\d+", m.group(2))]
            slots.append({"weekday": m.group(1), "periods": periods, "room": (m.group(3) or "").strip()})
    return slots


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class KlasService:
    def __init__(self, client: KlasClient, *, now: Callable[[], datetime] | None = None) -> None:
        self._client = client
        self._now = now or (lambda: datetime.now(KST))
        self._cache: dict[tuple[Any, ...], tuple[float, asyncio.Task[Any]]] = {}

    async def _cached(self, key: tuple[Any, ...], ttl: float, fetch: Callable[[], Awaitable[Any]]) -> Any:
        """Share one in-flight or recent request per key, so parallel tools don't repeat calls."""
        entry = self._cache.get(key)
        if entry:
            started, task = entry
            failed = task.done() and (task.cancelled() or task.exception() is not None)
            if not failed and time.monotonic() - started < ttl:
                return await asyncio.shield(task)
        task = asyncio.ensure_future(fetch())
        # Mark the error as seen even if every waiter was cancelled before it arrived.
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        self._cache[key] = (time.monotonic(), task)
        try:
            return await asyncio.shield(task)
        except Exception:
            if self._cache.get(key, (0.0, None))[1] is task:
                del self._cache[key]
            raise

    # -- semesters and courses -------------------------------------------------

    async def _semester_rows(self) -> list[dict[str, Any]]:
        rows = await self._cached(("semesters",), HOME_TTL, lambda: self._client.post(SEMESTERS))
        return rows if isinstance(rows, list) else []

    async def semesters(self) -> list[dict[str, Any]]:
        return [
            {
                "semester": row.get("value"),
                "label": row.get("label"),
                "courses": [s.get("name") or s.get("label") for s in row.get("subjList") or []],
            }
            for row in await self._semester_rows()
        ]

    async def current_semester(self) -> str:
        """The latest semester KLAS lists for this student."""
        rows = await self._semester_rows()
        if not rows or not rows[0].get("value"):
            raise LookupError("KLAS에 수강 학기 정보가 없습니다.")
        return rows[0]["value"]

    async def _home(self, semester: str | None) -> dict[str, Any]:
        semester = semester or await self.current_semester()
        home = await self._cached(
            ("home", semester), HOME_TTL, lambda: self._client.post(HOME, {"searchYearhakgi": semester})
        )
        return home if isinstance(home, dict) else {}

    async def _course_rows(self, semester: str | None, course: str | None) -> list[dict[str, Any]]:
        all_rows = (await self._home(semester)).get("atnlcSbjectList") or []
        rows = [r for r in all_rows if _matches(r.get("subjNm"), course)]
        if course and not rows:
            names = ", ".join(r.get("subjNm") or "?" for r in all_rows)
            raise LookupError(f"'{course}'와 일치하는 과목이 없습니다. 이 학기 과목: {names}")
        return rows

    async def courses(self, semester: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "course": r.get("subjNm"),
                "professor": r.get("profNm"),
                "schedule": r.get("lctrumSchdulInfo"),
                "course_id": r.get("subj"),
                "semester": r.get("yearhakgi"),
                "label": r.get("subjLabel"),
            }
            for r in await self._course_rows(semester, None)
        ]

    async def _per_course(
        self, path: str, semester: str | None, course: str | None
    ) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        rows = await self._course_rows(semester, course)

        async def fetch(row: dict[str, Any]) -> list[dict[str, Any]]:
            body = {
                "selectChangeYn": "Y",
                "selectSubj": row.get("subj"),
                "selectYearhakgi": row.get("yearhakgi"),
            }
            items = await self._cached(
                (path, body["selectSubj"], body["selectYearhakgi"]),
                COURSE_TTL,
                lambda: self._client.post(path, body),
            )
            return items if isinstance(items, list) else []

        results = await _gather(*(fetch(r) for r in rows))
        return list(zip(rows, results, strict=True))

    # -- coursework ------------------------------------------------------------

    async def assignments(
        self, semester: str | None = None, course: str | None = None, pending_only: bool = False
    ) -> list[dict[str, Any]]:
        out = []
        for row, items in await self._per_course(TASKS, semester, course):
            for t in items:
                submitted = t.get("submityn") == "Y"
                if pending_only and submitted:
                    continue
                out.append(
                    {
                        "course": row.get("subjNm"),
                        "title": t.get("title"),
                        "opens": fmt_kst(t.get("startdate")),
                        "due": fmt_kst(t.get("expiredate")),
                        "late_due": fmt_kst(t.get("reexpiredate")),
                        "submitted": submitted,
                        "score": t.get("score"),
                    }
                )
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def online_lectures(
        self, semester: str | None = None, course: str | None = None, incomplete_only: bool = False
    ) -> list[dict[str, Any]]:
        out = []
        for row, items in await self._per_course(ONLINE, semester, course):
            for o in items:
                # The online-content list also carries project links (evltnSe "proj", no progress);
                # those already show up in assignments/projects.
                if o.get("evltnSe") == "proj":
                    continue
                progress = _int(o.get("prog"))
                if incomplete_only and progress is not None and progress >= 100:
                    continue
                out.append(
                    {
                        "course": row.get("subjNm"),
                        "week": o.get("weekNo") or o.get("weeklyseq"),
                        "module": o.get("moduletitle"),
                        "title": o.get("sbjt"),
                        "opens": fmt_kst(o.get("startDate")),
                        "due": fmt_kst(o.get("endDate")),
                        "progress_percent": progress,
                        "required_time": o.get("rcognTime"),
                        "achieved_time": o.get("achivTime"),
                    }
                )
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def projects(self, semester: str | None = None, course: str | None = None) -> list[dict[str, Any]]:
        # Only whitelisted fields leave this function: if KLAS adds team-member names or
        # student IDs to these rows later, they must not reach the model.
        out = []
        for row, items in await self._per_course(PROJECTS, semester, course):
            for p in items:
                out.append(
                    {
                        "course": row.get("subjNm"),
                        "title": p.get("title"),
                        "purpose": p.get("purpose"),
                        "opens": fmt_kst(p.get("startdate")),
                        "due": fmt_kst(p.get("expiredate")),
                        "late_due": fmt_kst(p.get("reexpiredate")),
                        "submitted": p.get("submityn") == "Y",
                        "score": p.get("score"),
                        "team_no": p.get("teamno"),
                    }
                )
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def quizzes(
        self, semester: str | None = None, course: str | None = None, pending_only: bool = False
    ) -> list[dict[str, Any]]:
        # Whitelisted fields only, like projects (KLAS Helper reads the same endpoint).
        out = []
        for row, items in await self._per_course(QUIZZES, semester, course):
            for q in items:
                submitted = q.get("issubmit") == "Y"
                if pending_only and submitted:
                    continue
                out.append(
                    {
                        "course": row.get("subjNm"),
                        "title": q.get("papernm"),
                        "type": q.get("examtypenm"),
                        "opens": fmt_kst(q.get("sdt")),
                        "due": fmt_kst(q.get("edt")),
                        "submitted": submitted,
                        "time_limit_minutes": _int(q.get("examtime")),
                        "questions": q.get("examcnt"),
                        "total_score": q.get("totalscore"),
                    }
                )
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def notices(self, semester: str | None = None, course: str | None = None) -> list[dict[str, Any]]:
        home = await self._home(semester)
        return [
            {
                "course": n.get("subjNm"),
                "board": n.get("typeNm"),
                "title": n.get("title"),
                "posted": fmt_kst(n.get("registDt")),
            }
            for n in home.get("subjNotiList") or []
            if _matches(n.get("subjNm"), course)
        ]

    async def deadlines(self, days: int = 7) -> dict[str, Any]:
        """Unsubmitted assignments, quizzes and team projects, and unfinished online lectures,
        due in the next `days` days.

        Assignments already past their due date but still inside the late-submission
        window are included with `late_submission: true`.
        """
        days = max(0, min(days, MAX_DEADLINE_DAYS))
        now = self._now()
        until = now + timedelta(days=days)
        semester = await self.current_semester()
        tasks, lectures, quizzes, projects = await _gather(
            self.assignments(semester, pending_only=True),
            self.online_lectures(semester, incomplete_only=True),
            self.quizzes(semester, pending_only=True),
            self.projects(semester),
        )

        items = []
        for a in tasks:
            due, late_due = parse_kst(a["due"]), parse_kst(a["late_due"])
            if due and now <= due <= until:
                items.append({"kind": "assignment", **a})
            elif due and late_due and due < now <= late_due:
                items.append({"kind": "assignment", "late_submission": True, **a})
        for lec in lectures:
            due = parse_kst(lec["due"])
            if due and now <= due <= until:
                items.append({"kind": "online_lecture", **lec})
        for kind, rows in (("quiz", quizzes), ("team_project", [p for p in projects if not p["submitted"]])):
            for row in rows:
                due = parse_kst(row["due"])
                if due and now <= due <= until:
                    items.append({"kind": kind, **row})

        def effective_due(item: dict[str, Any]) -> str:
            return item["late_due"] if item.get("late_submission") else item["due"]

        return {
            "semester": semester,
            "now": now.strftime("%Y-%m-%d %H:%M"),
            "days": days,
            "items": sorted(items, key=effective_due),
        }

    async def snapshot(self) -> dict[str, Any]:
        """This semester's courses, course posts and per-course lists as whitelisted raw rows.

        The PC agent sends this (encrypted) to the bridge, which shapes it the same way as
        the methods above. Grades are not included.
        """
        semester = await self.current_semester()
        home = await self._home(semester)
        lists = dict(zip(("tasks", "online", "projects", "quizzes"), await _gather(
            *(self._per_course(path, semester, None) for path in (TASKS, ONLINE, PROJECTS, QUIZZES))), strict=True))

        def pick(kind: str, row: dict[str, Any]) -> dict[str, Any]:
            return {k: row.get(k) for k in SNAPSHOT_FIELDS[kind]}

        sections: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for kind, per_course in lists.items():
            for course, items in per_course:
                sections.setdefault(str(course.get("subj")), {})[kind] = [pick(kind, i) for i in items]
        return {
            "semester": semester,
            "fetched_at": self._now().isoformat(timespec="seconds"),
            "courses": [pick("courses", r) for r in home.get("atnlcSbjectList") or []],
            "course_posts": [pick("course_posts", n) for n in home.get("subjNotiList") or []],
            "sections": sections,
        }

    # -- grades ----------------------------------------------------------------

    async def grades(self) -> dict[str, Any]:
        semesters, totals = await _gather(self._client.post(GRADES), self._client.post(GRADE_TOTALS))
        return {
            "semesters": [
                {
                    "year": s.get("thisYear"),
                    "term": s.get("hakgi"),
                    "courses": [
                        {
                            "course": g.get("gwamokKname"),
                            "category": g.get("codeName1"),
                            "credits": g.get("hakjumNum"),
                            "grade": g.get("getGrade"),
                            "retake": g.get("retakeOpt"),
                        }
                        for g in s.get("sungjukList") or []
                    ],
                }
                for s in semesters or []
            ],
            "credit_totals": totals,
        }
