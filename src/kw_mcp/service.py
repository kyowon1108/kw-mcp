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
from .text import html_to_text

KST = ZoneInfo("Asia/Seoul")

SEMESTERS = "/std/cmn/frame/YearhakgiAtnlcSbjectList.do"
HOME = "/std/cmn/frame/StdHome.do"
TASKS = "/std/lis/evltn/TaskStdList.do"
ONLINE = "/std/lis/evltn/SelectOnlineCntntsStdList.do"
PROJECTS = "/std/lis/evltn/PrjctStdList.do"
QUIZZES = "/std/lis/evltn/AnytmQuizStdList.do"
TASK_VIEW = "/std/lis/evltn/TaskStdView.do"
FILE_LIST = "/common/file/UploadFileList.do"
SYLLABUS = "/std/cps/atnlc/LectrePlanData.do"
# Course boards (same ids for every course; from the course home page). Q&A is left out on
# purpose: its posts and comments are written by other students.
BOARDS = (("강의 공지사항", "d052b8f845784c639f036b102fdc3023", "1"),
          ("강의 자료실", "6972896bfe72408eb72926780e85d041", "3"))
SYLLABUS_TEXT_CHARS = 2000
# Syllabus grading fields (percent; null means 0) -> our names.
GRADING = (("attendance", "attendBiyul"), ("midterm", "middleBiyul"), ("final", "lastBiyul"),
           ("assignments", "reportBiyul"), ("participation", "learnBiyul"), ("quizzes", "quizBiyul"),
           ("presentation", "presentationBiyul"), ("discussion", "discussionBiyul"), ("other", "gitaBiyul"))
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

    # -- single items ----------------------------------------------------------

    async def _one_course(self, course: str) -> dict[str, Any]:
        rows = await self._course_rows(None, course or None)
        exact = [r for r in rows if (r.get("subjNm") or "").strip() == course.strip()]
        if len(exact) == 1 or len(rows) == 1:
            return (exact or rows)[0]
        names = ", ".join(r.get("subjNm") or "?" for r in rows)
        raise LookupError(f"과목을 하나로 정할 수 없습니다. 과목명을 더 구체적으로 주세요: {names}")

    async def search_course_posts(self, course: str, keyword: str = "") -> dict[str, Any]:
        """Notice and materials posts of one course, newest first; keyword searches titles and bodies.

        The home page's list (notices()) only has the latest few posts; this reaches the whole board.
        Each board returns its first page (10 posts); `total` says how many matched.
        """
        row = await self._one_course(course)
        base = {"selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y"}
        posts, total = [], {}
        for board, master_id, _ in BOARDS:
            listed = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdList.do", {
                **base, "cmd": None, "pageInit": True, "searchCondition": "ALL", "searchKeyword": keyword.strip(),
                "currentPage": 0}) or {}
            total[board] = ((listed.get("page") or {}).get("totalElements"))
            posts += [{"board": board, "title": html_to_text(item.get("title")), "posted": fmt_kst(item.get("registDt")),
                       "pinned": item.get("topAt") == "Y", "attachments": _int(item.get("fileCnt")) or 0}
                      for item in listed.get("list") or []]
        posts.sort(key=lambda p: p["posted"] or "", reverse=True)
        return {"course": row.get("subjNm"), "keyword": keyword.strip() or None, "total": total, "posts": posts}

    async def course_post(self, course: str, title: str) -> dict[str, Any]:
        """One notice/materials post: body as text and attachment names. Author ids, names and IPs are left out."""
        row = await self._one_course(course)
        base = {"selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y"}
        found = []
        for board, master_id, master_no in BOARDS:
            listed = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdList.do", {
                **base, "cmd": None, "pageInit": True, "searchCondition": "TLE", "searchKeyword": title,
                "currentPage": 0})
            for item in (listed or {}).get("list") or []:
                if _matches(html_to_text(item.get("title")), title or None):
                    found.append((board, master_id, master_no, item))
        exact = [f for f in found if html_to_text(f[3].get("title")) == title.strip()]
        if not found:
            raise LookupError(f"{row.get('subjNm')} 공지사항·자료실에서 '{title}' 제목의 글을 찾지 못했습니다.")
        if len(exact) != 1 and len(found) > 1:
            names = ", ".join(f"[{b}] {html_to_text(i.get('title'))}" for b, _, _, i in found[:8])
            raise LookupError(f"'{title}'와 일치하는 글이 여러 개입니다. 제목을 더 구체적으로 주세요: {names}")
        board, master_id, master_no, item = (exact or found)[0]
        view = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdView.do", {
            **base, "cmd": "select", "boardNo": str(item.get("boardNo")), "masterNo": master_no})
        post = (view or {}).get("board") or {}
        if not post:
            raise LookupError("글을 열지 못했습니다(삭제됐거나 권한이 없을 수 있음).")
        files: list[dict[str, Any]] = []
        if post.get("atchFileId"):
            listed = await self._client.post(FILE_LIST, {"storageId": "CLS_BOARD", "attachId": post["atchFileId"]})
            files = [{"name": f.get("fileName"), "size_kb": round((f.get("fileSize") or 0) / 1024)}
                     for f in listed or [] if isinstance(f, dict)]
        return {
            "course": row.get("subjNm"),
            "board": board,
            "title": html_to_text(post.get("title")),
            "posted": fmt_kst(post.get("registDt")),
            "updated": fmt_kst(post.get("updtDt")),
            "body": html_to_text(post.get("content")),
            "attachments": files,
        }

    async def syllabus(self, course: str) -> dict[str, Any]:
        """The course's syllabus (강의계획서). Professor's mobile number and TA details are left out."""
        row = await self._one_course(course)
        data = await self._client.post(SYLLABUS, {"selectSubj": row.get("subj")})
        plan = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        if not plan:
            raise LookupError(f"{row.get('subjNm')}의 강의계획서가 아직 없습니다.")

        def text(field: str) -> str | None:
            value = (plan.get(field) or "").strip()
            return value[:SYLLABUS_TEXT_CHARS] or None

        weeks = [{"week": i, "topic": text(f"week{i}Lecture"), "note": text(f"week{i}Bigo")}
                 for i in range(1, 17) if text(f"week{i}Lecture") or text(f"week{i}Bigo")]
        grading = {name: _int(plan.get(field)) or 0 for name, field in GRADING}
        books = [{"title": text(f"{p}Name"), "author": text(f"{w}Name"), "publisher": text(f"{c}Name"),
                  "year": text(f"{y}Year")}
                 for p, w, c, y in [("book", "write", "company", "print")]
                 + [(f"book{i}", f"write{i}", f"company{i}", f"print{i}") for i in (1, 2, 3)]
                 if text(f"{p}Name")]
        return {
            "course": row.get("subjNm"),
            "category": text("codeName1"),
            "credits": plan.get("hakjumNum"),
            "professor": text("memberName") or row.get("profNm"),
            "professor_title": text("jikgeubName"),
            "professor_email": text("email"),
            "professor_office_phone": text("telNo"),
            "overview": text("summary"),
            "objectives_and_method": text("purpose"),
            "competencies": text("gwamokAble"),
            "prerequisites": text("preGwamok"),
            "weekly_plan": weeks,
            "grading_percent": {k: v for k, v in grading.items() if v},
            "grading_note": text("gitaDetail"),
            "textbooks": books,
            "notes": text("bigo"),
            "other": text("weekGita"),
        }

    async def _find_task(self, course: str, title: str) -> tuple[dict[str, Any], dict[str, Any]]:
        found = [(row, t) for row, items in await self._per_course(TASKS, None, course or None)
                 for t in items if _matches(t.get("title"), title or None)]
        exact = [(row, t) for row, t in found if (t.get("title") or "").strip() == title.strip()]
        if len(exact) == 1 or len(found) == 1:
            return (exact or found)[0]
        if not found:
            raise LookupError(f"'{title}'와 일치하는 과제가 없습니다. my_assignments로 과제 제목을 확인하세요.")
        names = ", ".join(f"{row.get('subjNm')}: {t.get('title')}" for row, t in found[:8])
        raise LookupError(f"'{title}'와 일치하는 과제가 여러 개입니다. 과목명이나 제목을 더 구체적으로 주세요: {names}")

    async def assignment_detail(self, course: str, title: str) -> dict[str, Any]:
        """What one assignment asks for: instructions, format, attachments (names), my submission.

        Fields are whitelisted: the view response also carries my student id (projid), name and
        department, which are left out.
        """
        row, task = await self._find_task(course, title)
        view = await self._client.post(TASK_VIEW, {"selectChangeYn": "Y", "selectYearhakgi": row.get("yearhakgi"),
                                                   "selectSubj": row.get("subj"), "ordseq": task.get("ordseq")})
        rpt = (view or {}).get("rpt") or {}
        smt = (view or {}).get("smt") or None
        files: list[dict[str, Any]] = []
        if rpt.get("atchFileId") and rpt.get("attachopen") != "N":
            listed = await self._client.post(FILE_LIST, {"storageId": "CLS_PROF_TASK", "attachId": rpt["atchFileId"]})
            files = [{"name": f.get("fileName"), "size_kb": round((f.get("fileSize") or 0) / 1024)}
                     for f in listed or [] if isinstance(f, dict)]
        # Same rule as the KLAS page: a score shows only once graded and the professor made scores public.
        score_visible = bool(smt and smt.get("tutordate") and rpt.get("isopenscore") == "Y")
        return {
            "course": row.get("subjNm"),
            "title": rpt.get("title") or task.get("title"),
            "instructions": html_to_text(rpt.get("contents")),
            "submit_format": rpt.get("submitfiletype"),
            "file_limit_mb": _int(rpt.get("filelimit")),
            "team_assignment": rpt.get("reptype") not in (None, "P"),
            "opens": fmt_kst(task.get("startdate")),
            "due": fmt_kst(task.get("expiredate")),
            "late_due": fmt_kst(task.get("reexpiredate")),
            "can_submit_now": rpt.get("indate") == "Y" or rpt.get("adddate") == "Y",
            "attachments": files,
            "attachments_hidden_until_due": rpt.get("attachopen") == "N",
            "submitted": rpt.get("submityn") == "Y" or smt is not None,
            "my_submission": None if not smt else {
                "submitted_at": fmt_kst(smt.get("registDt")),
                "score": smt.get("finalscore") if score_visible else None,
                "score_status": "공개" if score_visible else ("채점 전" if not smt.get("tutordate") else "비공개"),
                "feedback": html_to_text(smt.get("tutorcontents")) or None,
            },
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
