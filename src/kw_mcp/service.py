"""KLAS data shaped for LLM tools.

Raw KLAS rows use romanized Korean field names (`subjNm`, `expiredate`, ...).
This module maps the fields we have verified against the live site to plain
English keys and leaves the rest out.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .attachments import MAX_DOWNLOAD_BYTES, UnreadableAttachment, extract_text, split_parts
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
STUDENT_RECORD = "/std/cps/inqire/AtnlcScreHakjukInfo.do"
ATTENDANCE = "/std/ads/admst/KwAttendStdAttendList.do"
# Status codes of KLAS's e-attendance page (KwAttendListStdPage.do: O, X, L, R, A).
ATTEND_STATUS = {"AT": "출석", "AB": "결석", "LT": "지각", "LE": "조퇴", "OA": "공결"}
EXAM_WORDS = re.compile(r"시험|고사|중간|기말|퀴즈|평가 방법|범위")
CLASS_CHANGE_WORDS = re.compile(r"휴강|보강|결강|대체\s*수업|수업\s*대체|비대면|온라인\s*(?:수업|강의)\s*(?:대체|진행|전환)|강의실\s*변경")
# Korean 4.5 scale; P/NP and not-yet-graded courses don't count toward a semester average.
GRADE_POINTS = {"A+": 4.5, "A0": 4.0, "A": 4.0, "B+": 3.5, "B0": 3.0, "B": 3.0, "C+": 2.5, "C0": 2.0, "C": 2.0,
                "D+": 1.5, "D0": 1.0, "D": 1.0, "F": 0.0}

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
ATTACHMENT_TEXT_TTL = 600.0
ATTACHMENT_TEXT_CACHE = 8
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


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _matches(name: str | None, query: str | None) -> bool:
    """Case- and space-insensitive substring match; None matches everything."""
    return query is None or _norm(query) in _norm(name)


# Regular-semester class periods (month, day), roughly KW's academic calendar: classes and finals
# (with the make-up week) of the first and second semesters.
TERM_WINDOWS = {"1": ((3, 1), (6, 22)), "2": ((9, 1), (12, 22)), "3": ((6, 23), (8, 31)), "4": ((12, 23), (2, 28))}


def term_in_session(semester: str | None, now: datetime) -> bool:
    """True while `semester` ("2026,2") has classes, judged by TERM_WINDOWS."""
    year, _, term = (semester or "").partition(",")
    window = TERM_WINDOWS.get(term)
    if not window or not year.isdigit():
        return True  # unknown format: don't hide anything
    (m1, d1), (m2, d2) = window
    start = datetime(int(year), m1, d1, tzinfo=KST)
    end = datetime(int(year) + (1 if (m2, d2) < (m1, d1) else 0), m2, d2, 23, 59, 59, tzinfo=KST)
    return start <= now <= end


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


def schedule_note(text: str | None) -> str | None:
    """KLAS marks classes without a fixed room/time as '미지정' (often online or irregular)."""
    if not text or "미지정" in text:
        return "강의 시간·강의실이 KLAS에 정해져 있지 않습니다(온라인·비정기 수업일 수 있음). 공지를 확인하세요."
    return None


def _yyyymmdd(value: Any) -> str | None:
    text = str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if re.fullmatch(r"\d{8}", text) else (text or None)


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
        self._texts: dict[str, tuple[float, str, str]] = {}

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
        """The latest semester KLAS lists, except a seasonal one while a regular semester is running.

        After registering for winter/summer classes (e.g. 11/18), KLAS lists that term first; until
        the regular semester ends, its deadlines are still the ones that matter.
        """
        values = [r["value"] for r in await self._semester_rows() if r.get("value")]
        if not values:
            raise LookupError("KLAS에 수강 학기 정보가 없습니다.")
        if values[0].endswith((",3", ",4")):
            regular = next((v for v in values if v.endswith((",1", ",2"))), None)
            if regular and term_in_session(regular, self._now()):
                return regular
        return values[0]

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
                **({"note": schedule_note(r.get("lctrumSchdulInfo"))} if schedule_note(r.get("lctrumSchdulInfo")) else {}),
            }
            for r in await self._course_rows(semester, None)
        ]

    async def _per_course(
        self, path: str, semester: str | None, course: str | None
    ) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        rows = await self._course_rows(semester, course)
        results = await _gather(*(self._items(path, r) for r in rows))
        return list(zip(rows, results, strict=True))

    async def _items(self, path: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        """One course's list from a per-course endpoint (tasks, online lectures, ...), cached briefly."""
        body = {"selectChangeYn": "Y", "selectSubj": row.get("subj"), "selectYearhakgi": row.get("yearhakgi")}
        items = await self._cached((path, body["selectSubj"], body["selectYearhakgi"]), COURSE_TTL,
                                   lambda: self._client.post(path, body))
        return items if isinstance(items, list) else []

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
                "title": html_to_text(n.get("title")),
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
                due, late_due = parse_kst(row["due"]), parse_kst(row.get("late_due"))
                if due and now <= due <= until:
                    items.append({"kind": kind, **row})
                elif due and late_due and due < now <= late_due:
                    items.append({"kind": kind, "late_submission": True, **row})

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
        exact = [r for r in rows if _norm(r.get("subjNm")) == _norm(course)]
        if len(exact) == 1 or len(rows) == 1:
            return (exact or rows)[0]
        names = ", ".join(r.get("subjNm") or "?" for r in rows)
        raise LookupError(f"과목을 하나로 정할 수 없습니다. 과목명을 더 구체적으로 주세요: {names}")

    async def _board_list(self, row: dict[str, Any], master_id: str, condition: str, keyword: str) -> dict[str, Any]:
        listed = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdList.do", {
            "selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y",
            "cmd": None, "pageInit": True, "searchCondition": condition, "searchKeyword": keyword.strip(),
            "currentPage": 0})
        return listed if isinstance(listed, dict) else {}

    async def _boards(self, row: dict[str, Any], condition: str, keyword: str,
                      boards: tuple = BOARDS) -> list[tuple[tuple, dict[str, Any]]]:
        """((board, master_id, master_no), list response) for each board, fetched together."""
        listed = await _gather(*(self._board_list(row, b[1], condition, keyword) for b in boards))
        return list(zip(boards, listed, strict=True))

    @staticmethod
    def _post_row(board: str, item: dict[str, Any]) -> dict[str, Any]:
        return {"board": board, "title": html_to_text(item.get("title")), "posted": fmt_kst(item.get("registDt")),
                "pinned": item.get("topAt") == "Y", "attachments": _int(item.get("fileCnt")) or 0}

    async def search_course_posts(self, course: str, keyword: str = "") -> dict[str, Any]:
        """Notice and materials posts of one course, newest first; keyword searches titles and bodies.

        The home page's list (notices()) only has the latest few posts; this reaches the whole board.
        Each board returns its first page (10 posts); `total` says how many matched.
        """
        row = await self._one_course(course)
        posts, total = [], {}
        for (board, _, _), listed in await self._boards(row, "ALL", keyword):
            total[board] = (listed.get("page") or {}).get("totalElements")
            posts += [self._post_row(board, item) for item in listed.get("list") or []]
        posts.sort(key=lambda p: p["posted"] or "", reverse=True)
        return {"course": row.get("subjNm"), "keyword": keyword.strip() or None, "total": total, "posts": posts}

    async def _find_post(self, course: str, title: str) -> tuple[dict[str, Any], dict[str, Any], tuple, dict[str, Any]]:
        """(course row, list base body, (board, master_id, master_no), list item) for one post by title."""
        row = await self._one_course(course)
        base = {"selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y"}
        found = []
        for (board, master_id, master_no), listed in await self._boards(row, "TLE", title):
            for item in listed.get("list") or []:
                if _matches(html_to_text(item.get("title")), title or None):
                    found.append((board, master_id, master_no, item))
        exact = [f for f in found if html_to_text(f[3].get("title")) == title.strip()]
        if not found:
            raise LookupError(f"{row.get('subjNm')} 공지사항·자료실에서 '{title}' 제목의 글을 찾지 못했습니다.")
        if len(exact) != 1 and len(found) > 1:
            names = ", ".join(f"[{b}] {html_to_text(i.get('title'))}" for b, _, _, i in found[:8])
            raise LookupError(f"'{title}'와 일치하는 글이 여러 개입니다. 제목을 더 구체적으로 주세요: {names}")
        board, master_id, master_no, item = (exact or found)[0]
        return row, base, (board, master_id, master_no), item

    async def course_post(self, course: str, title: str) -> dict[str, Any]:
        """One notice/materials post: body as text and attachment names. Author ids, names and IPs are left out."""
        row, base, (board, master_id, master_no), item = await self._find_post(course, title)
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

    async def read_attachment(self, course: str, title: str, file_name: str = "", part: str = "1",
                              source: str = "post") -> dict[str, Any]:
        """Text of one attachment on a board post (source "post") or an assignment (source "assignment").

        Long text comes in parts of PART_CHARS characters; ask again with part=2, 3, ...
        """
        if source not in ("post", "assignment"):
            raise LookupError("source는 'post'(게시판 글) 또는 'assignment'(과제)여야 합니다.")
        if source == "assignment":
            row, task = await self._find_task(course, title)
            view = await self._client.post(TASK_VIEW, {"selectChangeYn": "Y", "selectYearhakgi": row.get("yearhakgi"),
                                                       "selectSubj": row.get("subj"), "ordseq": task.get("ordseq")})
            rpt = (view or {}).get("rpt") or {}
            if rpt.get("attachopen") == "N":
                raise LookupError("이 과제의 첨부 파일은 제출 기한 전에는 공개되지 않습니다.")
            attach_id, storage, where = rpt.get("atchFileId"), "CLS_PROF_TASK", rpt.get("title") or task.get("title")
        else:
            row, base, (_, master_id, master_no), item = await self._find_post(course, title)
            attach_id, storage, where = item.get("atchFileId"), "CLS_BOARD", html_to_text(item.get("title"))
            if not attach_id:  # list rows normally carry it; open the post if this one doesn't
                view = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdView.do", {
                    **base, "cmd": "select", "boardNo": str(item.get("boardNo")), "masterNo": master_no})
                attach_id = ((view or {}).get("board") or {}).get("atchFileId")
        files = [f for f in (await self._client.post(FILE_LIST, {"storageId": storage, "attachId": attach_id})
                             if attach_id else []) or [] if isinstance(f, dict)]
        if not files:
            raise LookupError(f"'{where}'에는 첨부 파일이 없습니다.")
        exact = [f for f in files if file_name and _norm(f.get("fileName")) == _norm(file_name)]
        chosen = exact or [f for f in files if _matches(f.get("fileName"), file_name or None)]
        if len(chosen) != 1:
            names = ", ".join(str(f.get("fileName")) for f in files)
            hint = "파일 이름을 정해 주세요" if len(chosen) > 1 else f"'{file_name}'와 일치하는 파일이 없습니다"
            raise LookupError(f"{hint}. 첨부 파일: {names}")
        f = chosen[0]
        try:
            kind, text = await self._attachment_text(str(f.get("download") or ""), str(f.get("fileName")))
        except UnreadableAttachment as e:
            raise LookupError(f"{f.get('fileName')}: {e}") from None
        chunk, total = split_parts(text, _int(part) or 1)
        return {"course": row.get("subjNm"), "from": where, "file": f.get("fileName"),
                "size_kb": round((f.get("fileSize") or 0) / 1024), "kind": kind,
                "part": min(max(_int(part) or 1, 1), total), "total_parts": total, "text": chunk}

    async def _attachment_text(self, path: str, name: str) -> tuple[str, str]:
        """Download and extract once; part=2, 3, ... reuse the text for a few minutes."""
        hit = self._texts.get(path)
        if hit and time.monotonic() - hit[0] < ATTACHMENT_TEXT_TTL:
            return hit[1], hit[2]
        data = await self._client.download(path, MAX_DOWNLOAD_BYTES)
        kind, text = await asyncio.to_thread(extract_text, name, data)  # big PDFs: keep the event loop free
        self._texts[path] = (time.monotonic(), kind, text)
        while len(self._texts) > ATTACHMENT_TEXT_CACHE:
            self._texts.pop(next(iter(self._texts)))
        return kind, text

    async def syllabus(self, course: str) -> dict[str, Any]:
        """The course's syllabus (강의계획서). Professor's mobile number and TA details are left out."""
        return await self._syllabus(await self._one_course(course))

    async def _syllabus(self, row: dict[str, Any]) -> dict[str, Any]:
        data = await self._client.post(SYLLABUS, {"selectSubj": row.get("subj")})
        plan = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        if not plan:
            raise LookupError(f"{row.get('subjNm')}의 강의계획서가 아직 없습니다.")

        def text(field: str) -> str | None:
            value = str(plan.get(field) or "").replace("\r\n", "\n").replace("\r", "\n").strip()
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
        if course and course.strip():
            # Settle the course first (exact name wins), so "자료구조" doesn't also search "자료구조실습".
            row = await self._one_course(course)
            per_course = [(row, await self._items(TASKS, row))]
        else:
            per_course = await self._per_course(TASKS, None, None)
        found = [(row, t) for row, items in per_course for t in items if _matches(t.get("title"), title or None)]
        exact = [(row, t) for row, t in found if _norm(t.get("title")) == _norm(title)]
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

    # -- what students keep asking about -----------------------------------------

    async def attendance(self, course: str | None = None) -> list[dict[str, Any]]:
        """My attendance per course from KLAS e-attendance: counts by status and each recorded session.

        Staff ids in the response (who recorded it) are left out.
        """
        semester = await self.current_semester()
        year, _, term = semester.partition(",")
        rows = await self._course_rows(semester, course or None)

        async def one(row: dict[str, Any]) -> dict[str, Any]:
            data = await self._client.post(ATTENDANCE, {"selectYear": year, "selectHakgi": term, "subj": row.get("subj")})
            counts: Counter[str] = Counter()
            weeks = []
            for week in data if isinstance(data, list) else []:
                if not isinstance(week, dict):
                    continue  # weeks not held yet come back as null
                sessions = []
                for n in range(1, 5):
                    code = week.get(f"attendancediv{n}")
                    if not code:
                        continue
                    status = ATTEND_STATUS.get(code, code)
                    counts[status] += 1
                    sessions.append({"session": n, "status": status, "date": _yyyymmdd(week.get(f"attendancedate{n}"))})
                if sessions:
                    weeks.append({"week": week.get("weeklyseq"), "sessions": sessions})
            return {"course": row.get("subjNm"), "recorded_sessions": sum(counts.values()),
                    "summary": {status: counts.get(status, 0) for status in ATTEND_STATUS.values()},
                    "weeks": weeks,
                    "note": "KLAS 전자출석 기준입니다. 교수님이 따로 출석을 관리하면 다를 수 있습니다."}

        return await _gather(*(one(r) for r in rows))

    async def exam_info(self, course: str | None = None) -> list[dict[str, Any]]:
        """Per course: exam weeks and grading from the syllabus, plus board posts that mention exams."""
        rows = await self._course_rows(None, course or None)

        async def one(row: dict[str, Any]) -> dict[str, Any]:
            plan, boards = await _gather(self._syllabus_or_none(row), self._boards(row, "ALL", "시험"))
            posts = sorted((self._post_row(board, item) for (board, _, _), listed in boards
                            for item in listed.get("list") or []), key=lambda p: p["posted"] or "", reverse=True)
            weeks = [w for w in (plan or {}).get("weekly_plan", [])
                     if EXAM_WORDS.search(f"{w.get('topic') or ''} {w.get('note') or ''}")]
            return {"course": row.get("subjNm"),
                    "grading_percent": (plan or {}).get("grading_percent"),
                    "grading_note": (plan or {}).get("grading_note"),
                    "exam_related_weeks": weeks,
                    "exam_posts": posts[:6],
                    "hint": "글 본문(시험 범위·장소)은 게시판 글 열기 도구로 확인하세요."}

        return await _gather(*(one(r) for r in rows))

    async def _syllabus_or_none(self, row: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return await self._syllabus(row)
        except LookupError:
            return None

    async def class_changes(self, days: str | int = 14) -> dict[str, Any]:
        """휴강·보강 notices on every course's notice board in the last `days` days."""
        days = max(1, min(_int(days) or 14, 60))
        since = (self._now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        rows = await self._course_rows(None, None)
        notice_board = BOARDS[:1]
        searches = await _gather(*(self._boards(row, "ALL", word, notice_board)
                                   for row in rows for word in ("휴강", "보강")))
        seen, posts = set(), []
        for row, result in zip([r for r in rows for _ in (0, 1)], searches, strict=True):
            for (board, _, _), listed in result:
                for item in listed.get("list") or []:
                    post = {"course": row.get("subjNm"), **self._post_row(board, item)}
                    key = (post["course"], post["title"], post["posted"])
                    if key not in seen and (post["posted"] or "") >= since:
                        seen.add(key)
                        posts.append(post)
        posts.sort(key=lambda p: p["posted"] or "", reverse=True)
        return {"days": days, "since": since, "posts": posts,
                "note": "각 과목 강의 공지사항에서 '휴강'·'보강'을 검색한 결과입니다. 내용은 게시판 글 열기 도구로 확인하세요."}

    # -- grades ----------------------------------------------------------------

    async def grades(self) -> dict[str, Any]:
        """Grades by semester, credits and the two KLAS grade averages.

        Whitelisted: the student record endpoint also returns my name, student id, e-mail and
        advisor, which are left out.
        """
        semesters, totals, record = await _gather(self._client.post(GRADES), self._client.post(GRADE_TOTALS),
                                                  self._client.post(STUDENT_RECORD))
        totals = totals if isinstance(totals, dict) else {}
        record = record if isinstance(record, dict) else {}

        def credits(kind: str) -> dict[str, Any]:
            prefix = {"applied": "Apply", "deleted": "Del", "earned": "Chiduk"}[kind]
            return {"major": totals.get(f"major{prefix}Hakjum"), "general_education": totals.get(f"culture{prefix}Hakjum"),
                    "other": totals.get(f"etc{prefix}Hakjum"), "total": totals.get(f"{prefix[0].lower()}{prefix[1:]}Hakjum")}

        out_semesters = []
        for s in semesters or []:
            courses = [{"course": g.get("gwamokKname"), "category": g.get("codeName1"), "credits": g.get("hakjumNum"),
                        "grade": (g.get("getGrade") or "").strip() or None, "retake": g.get("retakeOpt") == "Y"}
                       for g in s.get("sungjukList") or []]
            graded = [(c["credits"] or 0, GRADE_POINTS[c["grade"]]) for c in courses if c["grade"] in GRADE_POINTS]
            weight = sum(w for w, _ in graded)
            out_semesters.append({
                "year": s.get("thisYear"), "term": s.get("hakgi"),
                "registered_credits": sum(c["credits"] or 0 for c in courses),
                "earned_credits": (sum(c["credits"] or 0 for c in courses if c["grade"] not in ("F", "NP"))
                                   if any(c["grade"] for c in courses) else None),
                "gpa": round(sum(w * p for w, p in graded) / weight, 2) if weight else None,
                "courses": courses,
            })
        transfer = {"general_education": record.get("cultureHakjum"), "major": record.get("majorHakjum"),
                    "elective": record.get("generalHakjum"), "total": record.get("prevHakjumNum")}
        return {
            "student": {"department": record.get("hakgwa"), "year": record.get("grade"),
                        "status": record.get("hakjukStatu")},
            "gpa": {"transcript_record": totals.get("hwakinScoresum"), "certificate": totals.get("jaechulScoresum"),
                    "scale": 4.5, "note": "KLAS 계산값(학적부 기준 / 성적증명서 기준). 학기별 gpa는 이 도구가 계산한 값"},
            "credits": {"applied": credits("applied"), "earned": credits("earned"), "deleted": credits("deleted")},
            "transfer_credits": transfer if any(transfer.values()) else None,
            "semesters": out_semesters,
        }
