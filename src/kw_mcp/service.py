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
from .klas import KlasClient, KlasLoginError
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
GEN_ED = "/std/cps/inqire/GyoyangIsuInfo.do"
ONLINE_TESTS = "/std/lis/evltn/OnlineTestStdList.do"
DISCUSSIONS = "/std/lis/evltn/DscsnStdList.do"
SURVEYS = "/std/lis/sport/QustnrStdList.do"
EVAL_TERM = "/std/cps/inqire/LctreEvlTermCheck.do"
EVAL_COURSES = "/std/cps/inqire/LctreEvlsugangList.do"
GRADE_TERM = "/std/cps/inqire/AtnlcScreCheckTerm.do"
STANDING = "/std/cps/inqire/StandStdList.do"
SCHOLARSHIP_TERM = "/std/cps/inqire/JanghakApplyStdTerm.do"
DROP_CREDITS_TERM = "/std/cps/inqire/DelHakjumApplyStdTerm.do"
# GyoyangIsuStdPage.do's table: 필수교양 aa8128, then the 8 balanced areas (과학과기술 = aa63 + aa76).
BALANCED_AREAS = (("대학실용영어", ("aa62",)), ("언어와표현", ("aa64",)), ("과학과기술", ("aa63", "aa76")),
                  ("인간과철학", ("aa65",)), ("사회와경제", ("aa66",)), ("글로벌문화와제2외국어", ("aa67",)),
                  ("예술과체육", ("aa68",)), ("수리와자연", ("aa7881",)))
# Online-list rows that point at other coursework (already listed as tasks/quizzes/projects).
NOT_LECTURES = {"proj", "task", "report", "quiz", "exam", "test"}
# Status codes of KLAS's e-attendance page (KwAttendListStdPage.do: O, X, L, R, A).
ATTEND_STATUS = {"AT": "출석", "AB": "결석", "LT": "지각", "LE": "조퇴", "OA": "공결"}
EXAM_WORDS = re.compile(r"시험|고사|중간|기말|퀴즈|평가 방법|범위")
CLASS_CHANGE_WORDS = re.compile(r"휴강|보강|결강|대체\s*수업|수업\s*대체|비대면|온라인\s*(?:수업|강의)\s*(?:대체|진행|전환)|강의실\s*변경")
# Korean 4.5 scale; P/NP and not-yet-graded courses don't count toward a semester average.
GRADE_POINTS = {"A+": 4.5, "A0": 4.0, "A": 4.0, "B+": 3.5, "B0": 3.0, "B": 3.0, "C+": 2.5, "C0": 2.0, "C": 2.0,
                "D+": 1.5, "D0": 1.0, "D": 1.0, "F": 0.0}

def _gpa(pairs: list[tuple[float, float]]) -> float | None:
    weight = sum(w for w, _ in pairs)
    return round(sum(w * p for w, p in pairs) / weight, 2) if weight else None


# Within a year: 1st semester, summer (3), 2nd semester, winter (4).
_TERM_RANK = {"1": 0, "3": 1, "2": 2, "4": 3}


def _term_order(sem: dict[str, Any]) -> tuple[int, int]:
    year = str(sem.get("year") or "")
    return (int(year) if year.isdigit() else 0, _TERM_RANK.get(str(sem.get("term")), 9))


def grade_summary(semesters: list[dict[str, Any]]) -> dict[str, Any]:
    """Averages KLAS doesn't show, from the courses already listed. A retaken course counts once,
    with its latest grade (matched by name, so a renamed course counts twice)."""
    latest: dict[str, dict[str, Any]] = {}
    for sem in sorted(semesters, key=_term_order):
        for c in sem["courses"]:
            if c["grade"]:
                latest[_norm(c["course"])] = {**c, "year": sem["year"], "term": sem["term"]}
    graded = [c for c in latest.values() if c["grade"] in GRADE_POINTS]

    def avg(rows: list[dict[str, Any]]) -> float | None:
        return _gpa([(c["credits"] or 0, GRADE_POINTS[c["grade"]]) for c in rows])

    major = [c for c in graded if (c["category"] or "").startswith("전")]
    return {
        "major_gpa": avg(major),
        "non_major_gpa": avg([c for c in graded if c not in major]),
        "gpa_excluding_f": avg([c for c in graded if c["grade"] != "F"]),
        "f_not_retaken": [{"course": c["course"], "year": c["year"], "term": c["term"], "category": c["category"]}
                          for c in graded if c["grade"] == "F"],
        "note": "이 도구가 과목 목록으로 계산한 값입니다(같은 이름 과목은 마지막 성적만). 공식 평점은 gpa 항목을 보세요.",
    }


def _klas_datetime(day: Any, clock: Any = None) -> datetime | None:
    """KLAS's "20261201" + "090000" (or with dots/colons) → datetime."""
    d, t = re.sub(r"\D", "", str(day or "")), re.sub(r"\D", "", str(clock or "")) or "000000"
    if len(d) != 8:
        return None
    t = (t + "000000")[:6]
    try:
        return datetime(int(d[:4]), int(d[4:6]), int(d[6:]), int(t[:2]), int(t[2:4]), int(t[4:]), tzinfo=KST)
    except ValueError:
        return None


def _dotted(day: Any, clock: Any = None) -> str | None:
    parsed = _klas_datetime(day, clock)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else None


# Raw KLAS fields the PC agent may send to the bridge (kwcampus.bridge.shapes reads these).
SNAPSHOT_FIELDS = {
    "courses": ("subj", "yearhakgi", "subjNm", "profNm", "lctrumSchdulInfo", "subjLabel"),
    "course_posts": ("subjNm", "typeNm", "title", "registDt"),
    "tasks": ("title", "startdate", "expiredate", "reexpiredate", "submityn", "score"),
    "online": ("evltnSe", "isonoff", "prog", "weekNo", "weeklyseq", "moduletitle", "sbjt", "startDate", "endDate",
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


_NO_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
_DATE_ONLY = re.compile(r"^\d{4}[-.]?\d{2}[-.]?\d{2}$")


def parse_due(value: Any) -> datetime | None:
    """A deadline as KLAS shows it: "23:59" without seconds is open through 23:59:59, and a bare
    date (surveys) through the end of that day."""
    text = str(value or "").strip()
    if _DATE_ONLY.match(text):
        digits = re.sub(r"\D", "", text)
        try:
            return datetime(int(digits[:4]), int(digits[4:6]), int(digits[6:8]), 23, 59, 59, tzinfo=KST)
        except ValueError:  # "0000-00-00" and friends: one odd row must not sink the whole list
            return None
    parsed = parse_kst(text)
    return parsed + timedelta(seconds=59) if parsed and _NO_SECONDS.match(text) else parsed


def fmt_due(value: Any) -> str | None:
    parsed = parse_due(value)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else (str(value) if value else None)


def is_lecture(row: dict[str, Any]) -> bool:
    """A watchable online lecture. The online list also links other coursework (proj, quiz, ...),
    and KLAS Helper skips rows that aren't lessons or are marked offline the same way."""
    kind = row.get("evltnSe") or None
    return kind in (None, "lesson") and row.get("isonoff") != "OFF"


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


async def _gather_some(named: dict[str, Awaitable[Any]], optional: bool = False) -> tuple[dict[str, Any], list[str]]:
    """Like _gather, but one list failing (a KLAS hiccup on one endpoint) leaves the others.
    Login problems still raise, and so does a failure of everything unless the parts are optional
    extras, so the user hears why."""
    results = await asyncio.gather(*named.values(), return_exceptions=True)
    done, failed, first = {}, [], None
    for name, result in zip(named, results, strict=True):
        if isinstance(result, KlasLoginError):
            raise result
        if isinstance(result, BaseException):
            if not isinstance(result, Exception):
                raise result
            failed.append(name)
            first = first or result
        else:
            done[name] = result
    if not done and first and not optional:
        raise first
    return done, failed


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
                # The online-content list also carries project/quiz links; those already show up
                # in assignments, quizzes and projects.
                if not is_lecture(o):
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

    async def online_tests(
        self, semester: str | None = None, course: str | None = None, pending_only: bool = False
    ) -> list[dict[str, Any]]:
        """Online exams (온라인시험). issubmit: Y taken, I in progress; a professor can open a retry
        window (isretry, rsdt~redt, isresubmit), as the KLAS page shows."""
        out = []
        for row, items in await self._per_course(ONLINE_TESTS, semester, course):
            for t in items:
                submitted, retry = t.get("issubmit") == "Y", t.get("isretry") == "Y"
                retry_submitted = retry and t.get("isresubmit") == "Y"
                if pending_only and (retry_submitted or (submitted and not retry)):
                    continue
                out.append({
                    "course": row.get("subjNm"), "title": t.get("papernm"), "type": t.get("examtypenm"),
                    "week": t.get("weeklyseq"), "opens": fmt_kst(t.get("sdt")), "due": fmt_kst(t.get("edt")),
                    "submitted": submitted, "in_progress": t.get("issubmit") == "I",
                    "retry": {"opens": fmt_kst(t.get("rsdt")), "due": fmt_kst(t.get("redt")),
                              "submitted": retry_submitted} if retry else None,
                })
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def surveys(
        self, semester: str | None = None, course: str | None = None, pending_only: bool = False
    ) -> list[dict[str, Any]]:
        """Course surveys (설문). appcnt counts my answers; the page shows a 참여 button while it is 0."""
        out = []
        for row, items in await self._per_course(SURVEYS, semester, course):
            for q in items:
                answered = (_int(q.get("appcnt")) or 0) > 0
                if pending_only and answered:
                    continue
                out.append({"course": row.get("subjNm"), "title": (q.get("sulpapernm") or "").strip(),
                            "opens": q.get("sulstart"), "due": fmt_due(q.get("sulend")), "submitted": answered})
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def discussions(self, semester: str | None = None, course: str | None = None) -> list[dict[str, Any]]:
        """Discussion topics (토론). The list has no "did I post" flag, only the topic's post count."""
        out = []
        for row, items in await self._per_course(DISCUSSIONS, semester, course):
            for d in items:
                out.append({"course": row.get("subjNm"), "title": d.get("title"), "opens": fmt_kst(d.get("started")),
                            "due": fmt_due(d.get("ended")), "posts": _int(d.get("toroncnt"))})
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

    async def deadlines(self, days: int | str = 7) -> dict[str, Any]:
        """Everything with a deadline in the next `days` days that I haven't done: assignments,
        quizzes, online exams, team projects, surveys and unfinished online lectures, plus
        discussions that end in that window (KLAS doesn't say whether I took part).

        Assignments and projects past their due date but inside the late window come with
        `late_submission: true`. If one list can't be read the rest still come back, and
        `incomplete` names what's missing.
        """
        days = _int(days)
        days = max(0, min(7 if days is None else days, MAX_DEADLINE_DAYS))
        now = self._now()
        until = now + timedelta(days=days)
        semester = await self.current_semester()
        lists, missing = await _gather_some({
            "assignment": self.assignments(semester, pending_only=True),
            "online_lecture": self.online_lectures(semester, incomplete_only=True),
            "quiz": self.quizzes(semester, pending_only=True),
            "team_project": self.projects(semester),
            "online_test": self.online_tests(semester, pending_only=True),
            "survey": self.surveys(semester, pending_only=True),
            "discussion": self.discussions(semester),
        })

        def in_window(value: str | None) -> bool:
            due = parse_due(value)
            return bool(due and now <= due <= until)

        items = []
        for kind in ("assignment", "team_project"):
            for row in lists.get(kind, []):
                if kind == "team_project" and row["submitted"]:
                    continue
                due, late_due = parse_due(row["due"]), parse_due(row.get("late_due"))
                if due and now <= due <= until:
                    items.append({"kind": kind, **row})
                elif due and late_due and due < now <= late_due:
                    items.append({"kind": kind, "late_submission": True, **row})
        for kind in ("online_lecture", "quiz", "survey"):
            items += [{"kind": kind, **row} for row in lists.get(kind, []) if in_window(row["due"])]
        for test in lists.get("online_test", []):
            retry, first_due = test["retry"], parse_due(test["due"])
            missed = first_due is not None and first_due < now
            due = retry["due"] if retry and (test["submitted"] or missed) else test["due"]
            if in_window(due):
                items.append({"kind": "online_test", **test, "effective_due": due})
        for topic in lists.get("discussion", []):
            opens = parse_kst(topic["opens"])
            if in_window(topic["due"]) and (opens is None or opens <= now):
                items.append({"kind": "discussion", **topic, "note": "참여 여부는 KLAS 목록에 없어 토론실에서 확인하세요."})

        def effective_due(item: dict[str, Any]) -> str:
            if item.get("late_submission"):
                return item["late_due"]
            return item.get("effective_due") or item["due"] or "9999"

        out = {"semester": semester, "now": now.strftime("%Y-%m-%d %H:%M"), "days": days,
               "items": sorted(items, key=effective_due)}
        if missing:
            out["incomplete"] = {"missing": missing, "message": "KLAS에서 일부 목록을 읽지 못해 빠진 마감이 있을 수 있습니다."}
        return out

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
                "note": "각 과목 강의 공지사항에서 '휴강'·'보강'을 검색한 결과입니다. 내용은 게시판 글 열기 도구로 확인하세요. "
                        "휴강은 문자·메일·수업 중에만 알리는 경우도 있어, 여기 없다고 휴강이 아니라는 뜻은 아닙니다."}

    async def graduation_progress(self) -> dict[str, Any]:
        """Where I stand on credits and general-education rules (교양 필수·균형 이수현황).

        The admission year is read from the first four digits of the student id; the id itself is
        not returned. Department-specific major requirements are not in KLAS's data, so they are
        pointed to the department office.
        """
        gen, totals, record = await _gather(self._client.post(GEN_ED), self._client.post(GRADE_TOTALS),
                                            self._client.post(STUDENT_RECORD))
        gen = gen if isinstance(gen, dict) else {}
        totals = totals if isinstance(totals, dict) else {}
        record = record if isinstance(record, dict) else {}
        areas = {name: sum(_int(gen.get(k)) or 0 for k in keys) for name, keys in BALANCED_AREAS}
        required = _int(gen.get("aa8128")) or 0
        general_total = required + sum(areas.values())
        areas_taken = sum(1 for v in areas.values() if v > 0)
        hakbun = str(record.get("hakbun") or "")
        admitted = int(hakbun[:4]) if hakbun[:4].isdigit() else None
        if admitted and admitted >= 2025:
            rule = "균형교양 8개 영역 중 4개 영역 이상을 포함해 교양 30학점"
            check = {"areas_needed": max(0, 4 - areas_taken), "credits_needed": max(0, 30 - general_total),
                     "met": areas_taken >= 4 and general_total >= 30}
        else:
            rule = "필수교양 '광운인되기' 이수 + 입학 연도별 총 교양 학점(나머지는 균형교양으로 채움)"
            check = {"kwangwoonin_done": required > 0, "met": None,
                     "note": "총 교양 이수 학점 기준은 입학 연도·학과 졸업기준표를 확인하세요."}
        return {
            "student": {"department": record.get("hakgwa"), "year": record.get("grade"),
                        "status": record.get("hakjukStatu"), "admission_year": admitted},
            "earned_credits": {"total": totals.get("chidukHakjum"), "major": totals.get("majorChidukHakjum"),
                               "general_education": totals.get("cultureChidukHakjum"),
                               "other": totals.get("etcChidukHakjum")},
            "gpa": {"transcript_record": totals.get("hwakinScoresum"), "certificate": totals.get("jaechulScoresum")},
            "general_education": {"required_kwangwoonin": required, "balanced_by_area": areas,
                                  "balanced_areas_taken": areas_taken, "total": general_total},
            "rule": rule,
            "check": check,
            "notes": ["성적 처리가 끝난 과목만 합산(F·NP·삭제 학점 제외)", "균형교양은 3·4학점 과목만 인정, e러닝·K-MOOC 등 일부 계열 제외",
                      "전공 졸업 학점·공학인증 등 학과별 요건은 학과 사무실에 확인하세요"],
        }

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
        extra, _ = await _gather_some({"standing": self.standing(), "period": self.grade_period()}, optional=True)

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
                    "scale": 4.5, "note": "KLAS 계산값(학적부 기준 / 성적증명서 기준, 재수강 반영). 학기별 gpa는 "
                                          "이 도구가 그 학기 당시 성적으로 계산한 값"},
            "credits": {"applied": credits("applied"), "earned": credits("earned"), "deleted": credits("deleted")},
            "transfer_credits": transfer if any(transfer.values()) else None,
            "summary": grade_summary(out_semesters),
            "standing": extra.get("standing"),
            "grade_viewing_period": extra.get("period"),
            "semesters": out_semesters,
        }

    async def standing(self) -> list[dict[str, Any]]:
        """석차 by semester (StandStdList.do): my rank among the department's students that term."""
        rows = await self._client.post(STANDING, {"selectYearhakgi": await self.current_semester(), "selectChangeYn": "Y"})
        return [{"year": r.get("thisYear"), "term": r.get("hakgi"), "credits": r.get("applyHakjum"),
                 "gpa": r.get("applyPoint"), "rank": r.get("classOrder"), "of": r.get("manNum"),
                 "percentile": r.get("pcnt"), "academic_warning": r.get("warningOpt") or None}
                for r in rows or [] if isinstance(r, dict)]

    async def grade_period(self) -> dict[str, Any]:
        """When this term's grades can be viewed (AtnlcScreCheckTerm.do). The grade page asks with
        the calendar year and 1 for Jan-Aug, 2 for Sep-Dec, so this does the same."""
        now = self._now()
        data = await self._client.post(GRADE_TERM, {"thisYear": str(now.year), "hakgi": "1" if now.month <= 8 else "2"})
        term = data.get("termMap") if isinstance(data, dict) else None
        if not isinstance(term, dict) or not term.get("fromDate"):
            return {"status": "not_set", "message": "KLAS에 이번 학기 성적 조회 기간이 아직 없습니다."}
        start = _klas_datetime(term.get("fromDate"), term.get("fromTime"))
        end = _klas_datetime(term.get("toDate"), term.get("toTime"))
        status = "before" if start and now < start else "after" if end and now > end else "open"
        return {"status": status, "from": start.strftime("%Y-%m-%d %H:%M") if start else term.get("fromDate"),
                "to": end.strftime("%Y-%m-%d %H:%M") if end else term.get("toDate")}

    async def course_evaluation(self) -> dict[str, Any]:
        """수업평가: whether the window is open and which courses I haven't evaluated.

        Outside the window LctreEvlTermCheck.do answers with an empty body (checked 2026-11-06). In
        the window the page reads judgeChasu (middle/last) from it and lists courses with
        judgeOpt 'N' as 수업평가전; those shapes come from the page's template, not a live answer.
        """
        term = await self._client.post(EVAL_TERM, None, allow_empty=True)
        if isinstance(term, list):
            return {"open": None, "message": "KLAS가 평가 기간을 둘 이상 알려 와 판단하지 못했습니다. KLAS 수업평가 화면을 확인하세요."}
        if not isinstance(term, dict):
            return {"open": False, "message": "지금은 수업평가 기간이 아닙니다."}
        round_ = term.get("judgeChasu")
        year, _, hakgi = (await self.current_semester()).partition(",")
        rows = await self._client.post(EVAL_COURSES, {"thisYear": year, "hakgi": hakgi, "judgeChasu": round_, "termYn": "Y"})
        rows = [r for r in rows or [] if isinstance(r, dict)]
        return {
            "open": True, "round": {"middle": "중간", "last": "기말"}.get(round_, round_),
            "courses": len(rows),
            "not_evaluated": [r.get("gwamokKname") for r in rows if r.get("judgeOpt") == "N"],
            "note": "평가하지 않은 과목은 성적 열람이 제한될 수 있습니다. 평가는 KLAS에서 직접 하세요.",
        }

    async def application_windows(self) -> dict[str, Any]:
        """KLAS's own "is it open now" answers for scholarship applications and dropping earned
        credits (취득학점포기), plus the grade viewing period and the course evaluation window."""
        found, missing = await _gather_some({
            "scholarship": self._client.post(SCHOLARSHIP_TERM), "drop_credits": self._client.post(DROP_CREDITS_TERM),
            "grade_viewing": self.grade_period(), "course_evaluation": self.course_evaluation()})
        out: dict[str, Any] = {}
        scholarship = found.get("scholarship")
        if isinstance(scholarship, dict):
            window = scholarship.get("janghakApplyTerm") or {}
            # KLAS's returnMsg is free text; fixed wording keeps anything personal it might carry out.
            out["scholarship_application"] = {
                "open": scholarship.get("stats") is True,
                "from": _dotted(window.get("fromDate"), window.get("fromTime")),
                "to": _dotted(window.get("toDate"), window.get("toTime")),
            }
        drop = found.get("drop_credits")
        if isinstance(drop, dict):
            out["drop_earned_credits"] = {"open": drop.get("stats") in (True, "Y")}
        if "grade_viewing" in found:
            out["grade_viewing"] = found["grade_viewing"]
        if "course_evaluation" in found:
            ev = found["course_evaluation"]
            out["course_evaluation"] = {k: ev.get(k) for k in ("open", "round", "not_evaluated", "message") if k in ev}
        if missing:
            out["incomplete"] = missing
        return out
