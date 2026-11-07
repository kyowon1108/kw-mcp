"""KLAS data shaped for LLM tools.

Raw KLAS rows use romanized Korean field names (`subjNm`, `expiredate`, ...).
This module maps the fields we have verified against the live site to plain
English keys and leaves the rest out.
"""

from __future__ import annotations

import asyncio
import contextvars
import math
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import simulation
from .attachments import (
    MAX_DOWNLOAD_BYTES,
    UnreadableAttachment,
    extract_text,
    split_parts,
)
from .klas import (
    KlasClient,
    KlasError,
    KlasFileTooLarge,
    KlasLoginError,
    KlasRequestLimit,
)
from .text import clean, html_to_text, untrusted

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
SCHOLARSHIP_HISTORY = "/std/cps/inqire/JanghakHistoryStdList.do"  # 장학조회 page (checked 2026-11-07)
DROP_CREDITS_TERM = "/std/cps/inqire/DelHakjumApplyStdTerm.do"
GRADUATION_CHECK = "/std/ext/grdtn/SelectGraduateCheck.do"
COURSE_HOME = "/std/lis/evltn/LctrumHomeStdInfo.do"
# 학적 and 어학 reads (field names from the page templates, checked 2026-11-07; no live values recorded).
LEAVE_WINDOWS = "/std/hak/hakjuk/TmpabssklGetHakjuk.do"  # 휴·복학 신청 가능 여부와 기간
LEAVE_STATUS = "/std/hak/hakjuk/TmpabssklStatu.do"  # 내 휴·복학 신청 내역
MAJOR_APPLIED = "/std/hak/hakjuk/CompnoApplyResult.do"  # 복수·부·심화전공 신청 결과
MICRO_APPLIED = "/std/hak/hakjuk/MicroMajorResult.do"
LINKED_APPLIED = "/std/hak/hakjuk/CntcSbjectResult.do"
MULTI_MAJOR_APPLIED = (("복수·부·심화", MAJOR_APPLIED), ("마이크로", MICRO_APPLIED), ("연계", LINKED_APPLIED))
LANGUAGE_REQUIREMENT = "/std/cps/inqire/ToeicInfoStd.do"  # 어학 졸업요건
COURSE_DROP_PAGE = "/std/cps/atnlc/GiveupStdPage.do"  # 수강포기: an HTML page, not JSON
NOTE_CHARS = 200
# Class periods as KLAS's own timetable page prints them (TimetableStdPage.do, 2026-11-06).
PERIOD_TIMES = {0: ("08:00", "08:50"), 1: ("09:00", "10:15"), 2: ("10:30", "11:45"), 3: ("12:00", "13:15"),
                4: ("13:30", "14:45"), 5: ("15:00", "16:15"), 6: ("16:30", "17:45"), 7: ("18:00", "18:45"),
                8: ("18:50", "19:35"), 9: ("19:40", "20:25"), 10: ("20:30", "21:15"), 11: ("21:20", "22:05")}
# GyoyangIsuStdPage.do's table: 필수교양 aa8128, then the 8 balanced areas (과학과기술 = aa63 + aa76).
BALANCED_AREAS = (("대학실용영어", ("aa62",)), ("언어와표현", ("aa64",)), ("과학과기술", ("aa63", "aa76")),
                  ("인간과철학", ("aa65",)), ("사회와경제", ("aa66",)), ("글로벌문화와제2외국어", ("aa67",)),
                  ("예술과체육", ("aa68",)), ("수리와자연", ("aa7881",)))
# Online-list rows that point at other coursework (already listed as tasks/quizzes/projects).
NOT_LECTURES = {"proj", "task", "report", "quiz", "exam", "test"}
# Status codes of KLAS's e-attendance page (KwAttendListStdPage.do: O, X, L, R, A).
ATTEND_STATUS = {"AT": "출석", "AB": "결석", "LT": "지각", "LE": "조퇴", "OA": "공결"}
EXAM_WORDS = re.compile(r"시험|고사|중간|기말|퀴즈|평가 방법|범위")
# Titles about a class that is cancelled, made up, moved or held another way. The room/time/day part
# matches what kw-campus routing._URGENT treats as a class change.
CLASS_CHANGE_WORDS = re.compile(
    r"휴강|보강|결강|대체\s*수업|수업\s*대체|비대면|"
    r"(?:온라인|실시간|원격|zoom|줌)\s*(?:수업|강의)\s*(?:으로|로)?\s*(?:대체|진행|전환)|"
    r"(?:강의|수업)\s*(?:실|장소|시간|요일|일정)\s*(?:변경|이동|조정)|시간표\s*변경",
    re.IGNORECASE)
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


def _grade_row(g: dict[str, Any]) -> dict[str, Any]:
    """One AtnlcScreSungjukInfo row. The grade is the first word of getGrade (KLAS can add a note
    after it, as KLAS Helper reads it); a row whose grade text says 삭제 is a dropped course."""
    raw = clean(str(g.get("getGrade") or "")).strip()
    code = clean(str(g.get("hakjungNo") or "")).strip()
    row = {"course": g.get("gwamokKname"), "category": g.get("codeName1"), "credits": g.get("hakjumNum"),
           "grade": raw.split()[0] if raw else None, "retake": g.get("retakeOpt") == "Y"}
    if "삭제" in raw:
        row["deleted"] = True
    if code:
        row["code"] = code
    return row


def _course_key(course: dict[str, Any]) -> str:
    """Retakes pair by course number (학정번호 without the section, as KW-Graduation does), else by name."""
    code = str(course.get("code") or "")
    parts = code.split("-")
    return f"code:{'-'.join(parts[:3]) if len(parts) >= 4 else code}" if code else f"name:{_norm(course.get('course'))}"


def grade_summary(semesters: list[dict[str, Any]]) -> dict[str, Any]:
    """Averages KLAS doesn't show, from the courses already listed. A retaken course counts once, with
    its latest grade. A later row of the same course (same course number, else same name) is a retake
    when it is marked as one or the earlier grade could be retaken (C+ and below); otherwise both
    count (repeatable courses such as 독립연구). Deleted rows count nowhere. KLAS's gpa is official."""
    kept: list[dict[str, Any]] = []
    ungraded_later: list[dict[str, Any]] = []
    for sem in sorted(semesters, key=_term_order):
        for c in sem["courses"]:
            if c.get("deleted"):
                continue
            row = {**c, "year": sem["year"], "term": sem["term"]}
            if not c["grade"]:
                ungraded_later.append(row)
                continue
            key = _course_key(c)
            earlier = next((k for k in reversed(kept) if _course_key(k) == key), None)
            if earlier is not None and (c.get("retake") or earlier["grade"] in RETAKE_GRADES):
                kept.remove(earlier)
            kept.append(row)
    graded = [c for c in kept if c["grade"] in GRADE_POINTS]

    def avg(rows: list[dict[str, Any]]) -> float | None:
        return _gpa([(c["credits"] or 0, GRADE_POINTS[c["grade"]]) for c in rows])

    def later_ungraded(c: dict[str, Any]) -> bool:
        return any(_course_key(u) == _course_key(c) and _term_order(u) > _term_order(c) for u in ungraded_later)

    failed = [c for c in graded if c["grade"] == "F"]
    major = [c for c in graded if (c["category"] or "").startswith("전")]
    out = {
        "major_gpa": avg(major),
        "non_major_gpa": avg([c for c in graded if c not in major]),
        "gpa_excluding_f": avg([c for c in graded if c["grade"] != "F"]),
        "f_not_retaken": [{"course": c["course"], "year": c["year"], "term": c["term"], "category": c["category"]}
                          for c in failed if not later_ungraded(c)],
        "note": "이 도구가 과목 목록으로 계산한 참고값입니다(재수강은 마지막 성적만, 삭제 과목 제외). 공식 평점은 gpa 항목을 보세요.",
    }
    retaking = [{"course": c["course"], "year": c["year"], "term": c["term"]} for c in failed if later_ungraded(c)]
    if retaking:
        out["retaking_now"] = retaking  # an F with an ungraded later row: being retaken this term
    return out


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
UNREADABLE_TTL = 300.0  # a file that can't be read stays unread for a while: a retry doesn't download it again
COURSE_TTL = 60.0
BOARD_TTL = 180.0  # board lists and searches (exam info, class changes)
ATTENDANCE_TTL = 180.0
SYLLABUS_TTL = 600.0  # a syllabus rarely changes within a term
RECORD_TTL = 3600.0  # 학적 (department, year, transfer credits)
CREDITS_TTL = 300.0  # 교양 이수현황, grade totals and the transcript, shared by the graduation tools
STATUS_TTL = 300.0  # 휴·복학 and 다전공 신청 내역, shared by academic_status and multi_major_options
MAX_DEADLINE_DAYS = 180
# Per-course lists, by the kind names deadlines() and snapshot() use.
PATH_KIND = {TASKS: "assignment", ONLINE: "online_lecture", QUIZZES: "quiz", PROJECTS: "team_project",
             ONLINE_TESTS: "online_test", SURVEYS: "survey", DISCUSSIONS: "discussion"}
KIND_NAMES = {"assignment": "과제", "online_lecture": "온라인 강의", "quiz": "퀴즈", "team_project": "팀 프로젝트",
              "online_test": "온라인시험", "survey": "설문", "discussion": "토론"}
SNAPSHOT_KIND = {TASKS: "tasks", ONLINE: "online", PROJECTS: "projects", QUIZZES: "quizzes"}
# Errors that must reach the user as they are, never folded into a partial answer.
STOP_ERRORS = (KlasLoginError, KlasRequestLimit)
# Course lists that failed for some courses while others worked, collected by deadlines() and
# snapshot(). Outside them (a direct list tool) any failing course fails the call.
_COURSE_FAILURES: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "kw_mcp_course_failures", default=None)
# A Korean mobile number anywhere in a syllabus 연락처 (a personal phone): 010-1234-5678, 010.123.4567,
# 01012345678, (010)1234-5678, 010–1234–5678, 010/1234/5678 (up to three characters other than letters
# and digits between the groups), and with the country code +82-10-…, 82 10 …, 0082-10-… or +82(0)10-….
_SEP = r"[\W_]{0,3}"
_MOBILE = re.compile(rf"(?<!\d)(?:(?:(?:\+|00){_SEP})?82{_SEP}(?:\(0\){_SEP}|0{_SEP})?1[016789]|\(01[016789]\)|01[016789])"
                     rf"{_SEP}\d{{3,4}}{_SEP}\d{{4}}(?!\d)")
# What still looks like one after those are cut out (a mistyped 010-1234-567, odd grouping): 01x, or
# 82 and 1x, then six or more digits. The whole 연락처 is then left out.
_MOBILE_LIKE = re.compile(rf"(?<!\d)(?:(?:(?:\+|00){_SEP})?82{_SEP}(?:0{_SEP})?|0)1[016789](?:{_SEP}\d){{6,}}")
_MOBILE_DIGITS = re.compile(r"(?:0|(?:00)?820?)1[016789]")  # the old rule, on the digits alone
# Grades that can be retaken (C+ and below): a later row of the same course after one of these is
# a retake. A course passed with B0 or better and taken again (독립연구, 현장실습) counts twice.
RETAKE_GRADES = {"C+", "C0", "C", "D+", "D0", "D", "F", "NP"}


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


def _free_text(value: Any) -> Any:
    """A text field someone typed into KLAS (a title, a purpose), cleaned like assignment titles;
    None and non-text values stay as they are."""
    return clean(value) if isinstance(value, str) else value


def _matches(name: str | None, query: str | None) -> bool:
    """Case- and space-insensitive substring match; None matches everything."""
    return query is None or _norm(query) in _norm(name)


# Class periods (month, day), roughly KW's academic calendar: classes and finals (with the make-up
# week) of the first and second semesters, and the seasonal sessions (2026: summer 6/23~7/13, winter
# 12/22~1/14) with about two weeks more for late reports and grades, not the whole break.
TERM_WINDOWS = {"1": ((3, 1), (6, 22)), "2": ((9, 1), (12, 22)), "3": ((6, 23), (7, 31)), "4": ((12, 23), (1, 31))}


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
        if isinstance(result, STOP_ERRORS):
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


def period_time(periods: list[int]) -> str | None:
    """'09:00~11:45' for periods [1, 2]; None if KLAS used a period we don't know."""
    known = [PERIOD_TIMES[p] for p in periods if p in PERIOD_TIMES]
    if not known or len(known) != len(periods):
        return None
    return f"{min(t[0] for t in known)}~{max(t[1] for t in known)}"


def schedule_slots(text: str | None) -> list[dict[str, Any]]:
    """parse_schedule's slots with each one's clock time from the school's period table (PERIOD_TIMES)."""
    out = []
    for slot in parse_schedule(text):
        time = period_time(slot["periods"])
        out.append({**slot, **({"time": time} if time else {})})
    return out


def schedule_note(text: str | None) -> str | None:
    """KLAS marks classes without a fixed room/time as '미지정' (often online or irregular)."""
    if not text or "미지정" in text:
        return "강의 시간·강의실이 KLAS에 정해져 있지 않습니다(온라인·비정기 수업일 수 있음). 공지를 확인하세요."
    return None


def _yyyymmdd(value: Any) -> str | None:
    text = str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if re.fullmatch(r"\d{8}", text) else (text or None)


_YMD = r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
_PERIOD = re.compile(rf"{_YMD}\s*일?\s*(?:부터|~|∼|-|–)\s*{_YMD}")
_TIME = re.compile(r"시간\s*:\s*([^\n]+)")


def _ymd(year: str, month: str, day: str) -> str | None:
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _day(value: Any) -> str | None:
    """A KLAS date as YYYY-MM-DD when it is 8 digits or dotted ("20260302", "2026.03.02"); other text as
    it is, None when empty."""
    text = clean(str(value if value is not None else "")).strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text) or re.fullmatch(_YMD + r"\.?", text)
    return (_ymd(*m.groups()) or text) if m else (text or None)


def _label(value: Any) -> str | None:
    """A short KLAS label (학적 상태, 전공명) as clean text; None when empty."""
    return clean(str(value if value is not None else "")).strip() or None


def _flat(html: Any) -> str:
    """KLAS HTML as one line of plain text."""
    return re.sub(r"\s+", " ", html_to_text(str(html or ""))).strip()


def leave_window(commit: Any, comment: Any) -> dict[str, Any] | None:
    """One 휴·복학 칸 of TmpabssklGetHakjuk.do: commitStrN ("<b>일반휴학</b><br>(신청불가)") and commentStrN
    ("신청기간이 아닙니다! <br>기간 : 2026.03.02부터 2026.03.20까지시간 : …", or a notice). The notice is
    the school's text, so it comes wrapped like other free text; None for an empty pair."""
    head, body = _flat(commit), html_to_text(str(comment or ""))
    if not head and not body:
        return None
    marks = " ".join(re.findall(r"\(([^()]*)\)", head)) or head
    can_apply = False if "불가" in marks else True if "가능" in marks else None
    kind = re.sub(r"\s+", " ", re.sub(r"\([^()]*\)|신청\s*(?:불가능?|가능)", " ", head)).strip()
    period = _PERIOD.search(body)
    time = _TIME.search(body) if period else None
    note = None if period else _flat(comment)
    if note and len(note) > NOTE_CHARS:
        note = note[:NOTE_CHARS].rstrip() + "…"
    return {"type": kind or None, "can_apply": can_apply,
            "period": {"from": _ymd(*period.groups()[:3]), "to": _ymd(*period.groups()[3:])} if period else None,
            "time": (time.group(1).strip()[:60] or None) if time else None,
            "note": untrusted(note) if note else None}


def leave_windows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """TmpabssklGetHakjuk.do's commitStr01.. / commentStr01.. pairs in order; empty pairs are left out."""
    keys = sorted((k for k in data if re.fullmatch(r"commitStr\d+", str(k))), key=lambda k: int(k[9:]))
    return [row for k in keys if (row := leave_window(data.get(k), data.get(f"commentStr{k[9:]}")))]


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _percent(value: Any) -> int | None:
    """KLAS progress as a whole percent: 100, "100", "100.0" and "99.5" all work; odd values are None."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return math.floor(min(number, 100.0)) if math.isfinite(number) and number >= 0 else None


def _list(data: Any, path: str) -> list[Any]:
    """A list answer; null counts as no rows. Anything else (an error object, a wrapper KLAS started
    sending) is an error, so it never reads as "nothing due"."""
    if data is None:
        return []
    if not isinstance(data, list):
        raise KlasError(f"{path}: KLAS 응답 형식이 예상과 다릅니다(목록이 아님).")
    return data


def _dict(data: Any, path: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise KlasError(f"{path}: KLAS 응답 형식이 예상과 다릅니다(객체가 아님).")
    return data


_SEMESTER = re.compile(r"\d{4},[1-4]")
_SEASON = {"여름": "3", "하계": "3", "겨울": "4", "동계": "4"}
_TERM_LABEL = {"1": "1학기", "2": "2학기", "3": "여름학기", "4": "겨울학기"}


def _normalize_semester(value: str) -> str | None:
    """"2026,2" from "2026-2", "2026/2", "2026, 2", "2026년 2학기", "2026 여름"/"동계"; None otherwise."""
    text = value.strip()
    season = re.match(r"^(\d{4})\D*?(여름|하계|겨울|동계)", text)
    if season:
        return f"{season.group(1)},{_SEASON[season.group(2)]}"
    m = re.match(r"^(\d{4})\s*(?:학년도|년)?\s*[,./\-]?\s*([1-4])\s*(?:학기)?$", text)
    return f"{m.group(1)},{m.group(2)}" if m else None


def _semester_order(value: str) -> tuple[int, int]:
    year, _, term = value.partition(",")
    return _term_order({"year": year, "term": term})


def _office_phone(phone: str | None) -> str | None:
    """The 연락처 without any mobile number in it ("02-940-0000 / 010-…" keeps the office number);
    None when nothing with digits is left, or when what is left still looks like a mobile number."""
    text = unicodedata.normalize("NFKC", clean(phone))  # fullwidth digits and dashes as plain ones
    rest = re.sub(r"\(\s*\)", " ", _MOBILE.sub(" ", text))  # and brackets a cut-out number stood in
    rest = re.sub(r"\s{2,}", " ", rest).strip(" \t/,;|·")
    if _MOBILE_LIKE.search(rest) or _MOBILE_DIGITS.match(re.sub(r"\D", "", rest)):
        return None
    return rest if re.search(r"\d", rest) else None


def _text_expired(entry: list[Any], now: float) -> bool:
    """An attachment read (a KlasService._texts entry) past its time: text after ATTACHMENT_TEXT_TTL,
    a file that couldn't be read after UNREADABLE_TTL. A read still running never expires."""
    task, finished_at = entry
    if finished_at is None or not task.done() or task.cancelled():
        return False
    return now - finished_at >= (UNREADABLE_TTL if task.exception() else ATTACHMENT_TEXT_TTL)


def _course_misses(failures: list[dict[str, Any]], kinds: dict[str, str], whole: list[str]) -> list[dict[str, Any]]:
    """{"kind", "course"} once each, for lists that failed for single courses (not whole kinds)."""
    out: list[dict[str, Any]] = []
    for f in failures:
        miss = {"kind": kinds.get(f["path"], f["path"]), "course": f["course"]}
        if miss["kind"] not in whole and miss not in out:
            out.append(miss)
    return out


class KlasService:
    def __init__(self, client: KlasClient, *, now: Callable[[], datetime] | None = None) -> None:
        self._client = client
        self._now = now or (lambda: datetime.now(KST))
        # key -> [task, finished_at (None while running), ttl]
        self._cache: dict[tuple[Any, ...], list[Any]] = {}
        # attachment path -> [task of (kind, text), finished_at]
        self._texts: dict[str, list[Any]] = {}

    async def _cached(self, key: tuple[Any, ...], ttl: float, fetch: Callable[[], Awaitable[Any]]) -> Any:
        """Share one in-flight or recent request per key, so parallel tools don't repeat calls.

        A request still running is always shared, however long it takes; a finished answer is
        reused for `ttl` seconds counted from when it arrived. Failures are never reused."""
        now = time.monotonic()
        self._prune(now)
        entry = self._cache.get(key)
        if entry:
            task, finished_at, _ = entry
            if not task.done():
                return await asyncio.shield(task)
            if finished_at is not None and now - finished_at < ttl:
                return task.result()
        task = asyncio.ensure_future(fetch())
        entry = [task, None, ttl]
        self._cache[key] = entry

        def finished(t: asyncio.Task[Any]) -> None:
            if t.cancelled() or t.exception() is not None:  # also marks the error as seen
                if self._cache.get(key) is entry:
                    del self._cache[key]
            else:
                entry[1] = time.monotonic()

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    def _prune(self, now: float) -> None:
        """Expired answers hold personal data and keys can carry search words: drop them."""
        for key in [k for k, (task, finished_at, ttl) in self._cache.items()
                    if task.done() and finished_at is not None and now - finished_at >= ttl]:
            del self._cache[key]

    # -- semesters and courses -------------------------------------------------

    async def _semester_rows(self) -> list[dict[str, Any]]:
        rows = await self._cached(("semesters",), HOME_TTL, lambda: self._client.post(SEMESTERS))
        return [r for r in _list(rows, SEMESTERS) if isinstance(r, dict)]

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
        """The semester that matters now: a regular semester in session, else a seasonal one in
        session, else the latest one.

        KLAS's list order is not trusted (a finished summer term can sort above the 2nd semester),
        so the terms are put in calendar order here. After registering for winter/summer classes
        (e.g. 11/18), KLAS lists that term too; until the regular semester ends, its deadlines are
        still the ones that matter. A regular semester KLAS lists after a seasonal one wins over it:
        KLAS lists it once its course registration is done (2026: 2/11 and 8/18), when the seasonal
        classes before it are over.
        """
        values = sorted({str(r.get("value")) for r in await self._semester_rows()
                         if _SEMESTER.fullmatch(str(r.get("value") or ""))}, key=_semester_order, reverse=True)
        if not values:
            raise LookupError("KLAS에 수강 학기 정보가 없습니다.")
        now = self._now()
        regular_terms = [v for v in values if v.endswith((",1", ",2"))]
        running = [v for v in values if term_in_session(v, now) and (
            v in regular_terms or not any(_semester_order(r) > _semester_order(v) for r in regular_terms))]
        regular = [v for v in running if v in regular_terms]
        return (regular or running or values)[0]

    async def _resolve_semester(self, semester: str | None) -> str:
        """None: the current semester. Otherwise one of the semesters KLAS lists, in "2026,2" form;
        "2026-2", "2026년 2학기" and the like are accepted. Anything else is an error, never an
        empty answer."""
        if semester is None or not str(semester).strip():
            return await self.current_semester()
        values = [str(r.get("value")) for r in await self._semester_rows() if r.get("value")]
        normalized = _normalize_semester(str(semester))
        if normalized in values:
            return normalized
        raise LookupError(f"'{semester}' 학기를 찾지 못했습니다. 학기는 \"2026,2\" 형식(연도,학기: 1·2 정규, 3 여름, "
                          f"4 겨울)이고, 수강 이력이 있는 학기는 {', '.join(values) or '없음'}입니다.")

    async def _home(self, semester: str | None) -> dict[str, Any]:
        semester = await self._resolve_semester(semester)
        home = await self._cached(
            ("home", semester), HOME_TTL, lambda: self._client.post(HOME, {"searchYearhakgi": semester})
        )
        home = _dict(home, HOME)
        if "atnlcSbjectList" not in home or not isinstance(home["atnlcSbjectList"], list | None):
            raise KlasError(f"{HOME}: KLAS 응답에 과목 목록이 없습니다(사이트가 바뀌었을 수 있음).")
        return home

    async def _course_rows(self, semester: str | None, course: str | None) -> list[dict[str, Any]]:
        all_rows = [r for r in (await self._home(semester)).get("atnlcSbjectList") or [] if isinstance(r, dict)]
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
                "slots": schedule_slots(r.get("lctrumSchdulInfo")),
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
        """(course row, items) per course. Inside deadlines()/snapshot() a course whose list fails
        is left out and recorded (see _COURSE_FAILURES); elsewhere, or when every course fails,
        the error is raised. Login trouble and the request cap always raise."""
        rows = await self._course_rows(semester, course)
        results = await asyncio.gather(*(self._items(path, r) for r in rows), return_exceptions=True)
        done, failed = [], []
        for row, result in zip(rows, results, strict=True):
            if isinstance(result, BaseException):
                if isinstance(result, STOP_ERRORS) or not isinstance(result, Exception):
                    raise result
                failed.append((row, result))
            else:
                done.append((row, result))
        if failed:
            collector = _COURSE_FAILURES.get()
            if collector is None or not done:
                raise failed[0][1]
            collector.extend({"path": path, "course": row.get("subjNm")} for row, _ in failed)
        return done

    async def _items(self, path: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        """One course's list from a per-course endpoint (tasks, online lectures, ...), cached briefly."""
        body = {"selectChangeYn": "Y", "selectSubj": row.get("subj"), "selectYearhakgi": row.get("yearhakgi")}
        items = await self._cached((path, body["selectSubj"], body["selectYearhakgi"]), COURSE_TTL,
                                   lambda: self._client.post(path, body))
        return [i for i in _list(items, path) if isinstance(i, dict)]

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
                        "title": clean(t.get("title")),
                        "id": t.get("ordseq"),  # for get_assignment_detail when two titles are the same
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
                progress = _percent(o.get("prog"))
                if incomplete_only and progress is not None and progress >= 100:
                    continue
                out.append(
                    {
                        "course": row.get("subjNm"),
                        "week": o.get("weekNo") or o.get("weeklyseq"),
                        "module": _free_text(o.get("moduletitle")),
                        "title": _free_text(o.get("sbjt")),
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
                        "title": _free_text(p.get("title")),
                        "purpose": _free_text(p.get("purpose")),
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
                        "title": _free_text(q.get("papernm")),
                        "type": _free_text(q.get("examtypenm")),
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
                    "course": row.get("subjNm"), "title": _free_text(t.get("papernm")),
                    "type": _free_text(t.get("examtypenm")),
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
                out.append({"course": row.get("subjNm"), "title": clean(q.get("sulpapernm")).strip(),
                            "opens": q.get("sulstart"), "due": fmt_due(q.get("sulend")), "submitted": answered})
        return sorted(out, key=lambda a: a["due"] or "9999")

    async def discussions(self, semester: str | None = None, course: str | None = None) -> list[dict[str, Any]]:
        """Discussion topics (토론). The list has no "did I post" flag, only the topic's post count."""
        out = []
        for row, items in await self._per_course(DISCUSSIONS, semester, course):
            for d in items:
                out.append({"course": row.get("subjNm"), "title": _free_text(d.get("title")), "opens": fmt_kst(d.get("started")),
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
            if isinstance(n, dict) and _matches(n.get("subjNm"), course)
        ]

    async def deadlines(self, days: int | str = 7) -> dict[str, Any]:
        """Everything due from now to the end of the day `days` days from today (0: rest of today,
        1: through tomorrow) that I haven't done: assignments, quizzes, online exams, team
        projects, surveys and unfinished online lectures, plus discussions that end in that window.

        Assignments and projects past their due date but inside the late window come with
        `late_submission: true`. If one list can't be read the rest still come back, and
        `incomplete` names what's missing (whole kinds in `missing`, single courses in
        `missing_courses`). A kind with rows but no due date that can be read (KLAS changed the field
        or its format) is in `missing` too, and in `unreadable_due`.
        """
        days = _int(days)
        days = max(0, min(7 if days is None else days, MAX_DEADLINE_DAYS))
        now = self._now().astimezone(KST)
        # KLAS deadlines cluster at 23:59:59: the window ends at the end of the target day.
        until = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59, microsecond=0)
        semester = await self.current_semester()
        failures: list[dict[str, Any]] = []
        token = _COURSE_FAILURES.set(failures)
        try:
            lists, missing = await _gather_some({
                "assignment": self.assignments(semester, pending_only=True),
                "online_lecture": self.online_lectures(semester, incomplete_only=True),
                "quiz": self.quizzes(semester, pending_only=True),
                "team_project": self.projects(semester),
                "online_test": self.online_tests(semester, pending_only=True),
                "survey": self.surveys(semester, pending_only=True),
                "discussion": self.discussions(semester),
            })
        finally:
            _COURSE_FAILURES.reset(token)

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
        topics = [t for t in lists.get("discussion", [])
                  if in_window(t["due"]) and (parse_kst(t["opens"]) is None or parse_kst(t["opens"]) <= now)]
        if topics:
            # The topic list has no "did I post", but each course home counts 참여/전체 (dscsnJoinCnt/dscsnCnt):
            # a course where I joined every topic has nothing left.
            joined, _ = await _gather_some({"overview": self.course_overview()}, optional=True)
            counts = {o["course"]: o["discussions"] for o in joined.get("overview") or []}
            for topic in topics:
                done = counts.get(topic["course"])
                if done and done["total"] and (done["done"] or 0) >= done["total"]:
                    continue
                note = (f"이 과목 토론 {done['done']}/{done['total']} 참여(주제별 참여 여부는 토론실에서 확인)" if done
                        else "참여 여부는 KLAS 목록에 없어 토론실에서 확인하세요.")
                items.append({"kind": "discussion", **topic, "note": note})

        def effective_due(item: dict[str, Any]) -> str:
            if item.get("late_submission"):
                return item["late_due"]
            return item.get("effective_due") or item["due"] or "9999"

        def has_due(kind: str, row: dict[str, Any]) -> bool:
            dues = [row["due"], row.get("late_due")]
            if kind == "online_test" and row["retry"]:
                dues.append(row["retry"]["due"])
            return any(parse_due(d) for d in dues)

        # Rows, but not one with a due date we can read: KLAS renamed the field or changed its date
        # format. Without this the kind would just drop out, which reads as "nothing due".
        unreadable = [kind for kind in PATH_KIND.values()
                      if lists.get(kind) and not any(has_due(kind, row) for row in lists[kind])]

        out = {"semester": semester, "now": now.strftime("%Y-%m-%d %H:%M"), "until": until.strftime("%Y-%m-%d %H:%M"),
               "days": days, "items": sorted(items, key=effective_due)}
        courses = _course_misses(failures, PATH_KIND, missing)
        missing = missing + [kind for kind in unreadable if kind not in missing]
        if missing or courses:
            message = "KLAS에서 일부 목록을 읽지 못해 빠진 마감이 있을 수 있습니다."
            if unreadable:
                message += (f" {'·'.join(KIND_NAMES[k] for k in unreadable)} 목록은 마감 시각을 읽지 못했습니다"
                            "(KLAS 형식이 바뀐 것 같습니다). KLAS에서 직접 확인하세요.")
            out["incomplete"] = {"missing": missing, **({"missing_courses": courses} if courses else {}),
                                 **({"unreadable_due": unreadable} if unreadable else {}), "message": message}
        return out

    async def snapshot(self) -> dict[str, Any]:
        """This semester's courses, course posts and per-course lists as whitelisted raw rows.

        The PC agent sends this (encrypted) to the bridge, which shapes it the same way as
        the methods above. Grades are not included. A list that fails for one course (or one
        kind) leaves the rest; `missing` then names what is left out.
        """
        semester = await self.current_semester()
        home = await self._home(semester)
        failures: list[dict[str, Any]] = []
        token = _COURSE_FAILURES.set(failures)
        try:
            lists, missing = await _gather_some({kind: self._per_course(path, semester, None)
                                                 for path, kind in SNAPSHOT_KIND.items()})
        finally:
            _COURSE_FAILURES.reset(token)

        def pick(kind: str, row: dict[str, Any]) -> dict[str, Any]:
            # Text is cleaned here as well as by the bridge, so no hidden characters leave this PC.
            return {k: _free_text(row.get(k)) for k in SNAPSHOT_FIELDS[kind]}

        sections: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for kind, per_course in lists.items():
            for course, items in per_course:
                sections.setdefault(str(course.get("subj")), {})[kind] = [pick(kind, i) for i in items]
        out = {
            "semester": semester,
            "fetched_at": self._now().isoformat(timespec="seconds"),
            "courses": [pick("courses", r) for r in home.get("atnlcSbjectList") or [] if isinstance(r, dict)],
            "course_posts": [pick("course_posts", n) for n in home.get("subjNotiList") or [] if isinstance(n, dict)],
            "sections": sections,
        }
        courses = _course_misses(failures, SNAPSHOT_KIND, missing)
        if missing or courses:
            out["missing"] = {"lists": missing, "courses": courses}
        return out

    # -- single items ----------------------------------------------------------

    async def _one_course(self, course: str) -> dict[str, Any]:
        rows = await self._course_rows(None, course or None)
        exact = [r for r in rows if _norm(r.get("subjNm")) == _norm(course)]
        if len(exact) == 1 or len(rows) == 1:
            return (exact or rows)[0]
        names = ", ".join(r.get("subjNm") or "?" for r in rows)
        raise LookupError(f"과목을 하나로 정할 수 없습니다. 과목명을 더 구체적으로 주세요: {names}")

    async def _board_list(self, row: dict[str, Any], master_id: str, condition: str, keyword: str) -> dict[str, Any]:
        body = {"selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y",
                "cmd": None, "pageInit": True, "searchCondition": condition, "searchKeyword": keyword.strip(),
                "currentPage": 0}
        path = f"/std/lis/sport/{master_id}/BoardStdList.do"
        listed = await self._cached(("board", master_id, row.get("subj"), row.get("yearhakgi"), condition,
                                     keyword.strip()), BOARD_TTL, lambda: self._client.post(path, body))
        listed = _dict(listed, path)
        if not isinstance(listed.get("list"), list | None):
            raise KlasError(f"{path}: KLAS 응답 형식이 예상과 다릅니다(글 목록이 아님).")
        return listed

    async def _boards(self, row: dict[str, Any], condition: str, keyword: str,
                      boards: tuple = BOARDS) -> list[tuple[tuple, dict[str, Any]]]:
        """((board, master_id, master_no), list response) for each board, fetched together."""
        listed = await _gather(*(self._board_list(row, b[1], condition, keyword) for b in boards))
        return list(zip(boards, listed, strict=True))

    @staticmethod
    def _post_id(master_no: str, item: dict[str, Any]) -> str:
        return f"{master_no}-{item.get('boardNo')}"

    @classmethod
    def _post_row(cls, board: str, item: dict[str, Any], master_no: str = "") -> dict[str, Any]:
        return {"board": board, "title": html_to_text(item.get("title")), "posted": fmt_kst(item.get("registDt")),
                "pinned": item.get("topAt") == "Y", "attachments": _int(item.get("fileCnt")) or 0,
                **({"id": cls._post_id(master_no, item)} if master_no and item.get("boardNo") is not None else {})}

    async def search_course_posts(self, course: str, keyword: str = "") -> dict[str, Any]:
        """Notice and materials posts of one course, newest first; keyword searches titles and bodies.

        The home page's list (notices()) only has the latest few posts; this reaches the whole board.
        Each board returns its first page (10 posts); `total` says how many matched.
        """
        row = await self._one_course(course)
        posts, total = [], {}
        for (board, _, master_no), listed in await self._boards(row, "ALL", keyword):
            total[board] = (listed.get("page") or {}).get("totalElements")
            posts += [self._post_row(board, item, master_no) for item in listed.get("list") or [] if isinstance(item, dict)]
        posts.sort(key=lambda p: p["posted"] or "", reverse=True)
        return {"course": row.get("subjNm"), "keyword": keyword.strip() or None, "total": total, "posts": posts}

    async def _find_post(self, course: str, title: str, post_id: str | int | None = None
                         ) -> tuple[dict[str, Any], dict[str, Any], tuple, dict[str, Any]]:
        """(course row, list base body, (board, master_id, master_no), list item) for one post by title.
        post_id (the "id" search_course_posts returns, str or int) picks one among posts with the same title."""
        row = await self._one_course(course)
        base = {"selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y"}
        title = (title or "").strip()
        found = []
        for (board, master_id, master_no), listed in await self._boards(row, "TLE" if title else "ALL", title):
            for item in listed.get("list") or []:
                if isinstance(item, dict) and _matches(html_to_text(item.get("title")), title or None):
                    found.append((board, master_id, master_no, item))
        if post_id is not None and str(post_id).strip():
            # Only a post the list itself returned: an id never reaches KLAS unchecked.
            chosen = [f for f in found if self._post_id(f[2], f[3]) == str(post_id).strip()]
            if not chosen:
                raise LookupError(f"{row.get('subjNm')} 게시판에서 id '{post_id}'인 글을 찾지 못했습니다"
                                  f"{f'(제목 {title!r})' if title else ''}. 게시판 검색 결과나 '여러 개' 안내에 나온 "
                                  "id와 제목을 함께 주세요.")
            board, master_id, master_no, item = chosen[0]
            return row, base, (board, master_id, master_no), item
        exact = [f for f in found if html_to_text(f[3].get("title")) == title]
        if not found:
            raise LookupError(f"{row.get('subjNm')} 공지사항·자료실에서 '{title}' 제목의 글을 찾지 못했습니다.")
        if len(exact) != 1 and len(found) > 1:
            names = ", ".join(f"[{b}] {html_to_text(i.get('title'))} (id {self._post_id(n, i)}, {fmt_kst(i.get('registDt')) or '?'})"
                              for b, _, n, i in found[:8])
            raise LookupError(f"'{title}'와 일치하는 글이 여러 개입니다. 제목을 더 구체적으로 주거나 id를 함께 주세요: {names}")
        board, master_id, master_no, item = (exact or found)[0]
        return row, base, (board, master_id, master_no), item

    async def _file_list(self, storage: str, attach_id: Any) -> list[dict[str, Any]]:
        if not attach_id:
            return []
        listed = await self._client.post(FILE_LIST, {"storageId": storage, "attachId": attach_id})
        return [f for f in _list(listed, FILE_LIST) if isinstance(f, dict)]

    @staticmethod
    def _file_rows(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"index": i, "name": clean(f.get("fileName")), "size_kb": round((_int(f.get("fileSize")) or 0) / 1024)}
                for i, f in enumerate(files, start=1)]

    async def course_post(self, course: str, title: str, post_id: str | int | None = None) -> dict[str, Any]:
        """One notice/materials post: body as text and attachment names. Author ids, names and IPs are left out.
        The body is someone else's text and comes wrapped in the KLAS_CONTENT marker."""
        row, base, (board, master_id, master_no), item = await self._find_post(course, title, post_id)
        view = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdView.do", {
            **base, "cmd": "select", "boardNo": str(item.get("boardNo")), "masterNo": master_no})
        post = (view if isinstance(view, dict) else {}).get("board") or {}
        if not isinstance(post, dict) or not post:
            raise LookupError("글을 열지 못했습니다(삭제됐거나 권한이 없을 수 있음).")
        files = self._file_rows(await self._file_list("CLS_BOARD", post.get("atchFileId")))
        return {
            "course": row.get("subjNm"),
            "board": board,
            "id": self._post_id(master_no, item),
            "title": html_to_text(post.get("title")),
            "posted": fmt_kst(post.get("registDt")),
            "updated": fmt_kst(post.get("updtDt")),
            "body": untrusted(html_to_text(post.get("content"))),
            "attachments": files,
        }

    async def read_attachment(self, course: str, title: str, file_name: str = "", part: str = "1",
                              source: str = "post", item_id: str | int | None = None,
                              file_index: str | int | None = None) -> dict[str, Any]:
        """Text of one attachment on a board post (source "post") or an assignment (source "assignment").

        item_id is the post's or assignment's id from the list tools; file_index (1, 2, ...) the
        attachment's index from get_course_post / get_assignment_detail. Long text comes in parts of
        PART_CHARS characters; ask again with part=2, 3, ... The text is someone else's and comes
        wrapped in the KLAS_CONTENT marker.
        """
        if source not in ("post", "assignment"):
            raise LookupError("source는 'post'(게시판 글) 또는 'assignment'(과제)여야 합니다.")
        if source == "assignment":
            row, task = await self._find_task(course, title, item_id)
            view = await self._client.post(TASK_VIEW, {"selectChangeYn": "Y", "selectYearhakgi": row.get("yearhakgi"),
                                                       "selectSubj": row.get("subj"), "ordseq": task.get("ordseq")})
            rpt = (view if isinstance(view, dict) else {}).get("rpt") or {}
            if rpt.get("attachopen") == "N":
                raise LookupError("이 과제의 첨부 파일은 제출 기한 전에는 공개되지 않습니다.")
            attach_id, storage, where = rpt.get("atchFileId"), "CLS_PROF_TASK", clean(rpt.get("title") or task.get("title"))
        else:
            row, base, (_, master_id, master_no), item = await self._find_post(course, title, item_id)
            attach_id, storage, where = item.get("atchFileId"), "CLS_BOARD", html_to_text(item.get("title"))
            if not attach_id:  # list rows normally carry it; open the post if this one doesn't
                view = await self._client.post(f"/std/lis/sport/{master_id}/BoardStdView.do", {
                    **base, "cmd": "select", "boardNo": str(item.get("boardNo")), "masterNo": master_no})
                attach_id = (((view if isinstance(view, dict) else {}).get("board")) or {}).get("atchFileId")
        files = await self._file_list(storage, attach_id)
        if not files:
            raise LookupError(f"'{where}'에는 첨부 파일이 없습니다.")
        names = ", ".join(f"{i}. {clean(f.get('fileName'))}" for i, f in enumerate(files, start=1))
        index = _int(file_index) if file_index not in (None, "") else None
        if index is not None:
            if not 1 <= index <= len(files):
                raise LookupError(f"file_index는 1~{len(files)} 사이여야 합니다. 첨부 파일: {names}")
            chosen = [files[index - 1]]
        else:
            exact = [f for f in files if file_name and _norm(f.get("fileName")) == _norm(file_name)]
            chosen = exact or [f for f in files if _matches(f.get("fileName"), file_name or None)]
        if len(chosen) != 1:
            hint = ("파일 이름을 정해 주세요(또는 file_index)" if len(chosen) > 1
                    else f"'{file_name}'와 일치하는 파일이 없습니다")
            raise LookupError(f"{hint}. 첨부 파일: {names}")
        f = chosen[0]
        size, label = _int(f.get("fileSize")) or 0, clean(f.get("fileName"))
        if size > MAX_DOWNLOAD_BYTES:  # refuse before downloading, so a retry costs the school nothing
            raise LookupError(f"{label}: 파일이 너무 큽니다({size / 1024 / 1024:.0f}MB, 최대 "
                              f"{MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB). KLAS에서 직접 내려받아 주세요.")
        try:
            kind, text = await self._attachment_text(str(f.get("download") or ""), str(f.get("fileName")))
        except UnreadableAttachment as e:
            raise LookupError(f"{label}: {e}") from None
        chunk, total = split_parts(text, _int(part) or 1)
        return {"course": row.get("subjNm"), "from": where, "file": label,
                "size_kb": round(size / 1024), "kind": kind,
                "part": min(max(_int(part) or 1, 1), total), "total_parts": total, "text": untrusted(chunk) or ""}

    async def _attachment_text(self, path: str, name: str) -> tuple[str, str]:
        """Download and extract once per file: a retry or part=2, 3, ... while the first read is still
        running waits for it, and finished text is reused for a few minutes. A caller that gives up
        (a cancelled tool call) doesn't cancel the read for the next one."""
        now = time.monotonic()
        for old in [p for p, e in self._texts.items() if _text_expired(e, now)]:
            del self._texts[old]  # read text is personal data: don't keep it past its time
        entry = self._texts.get(path)
        if entry and not entry[0].cancelled() and (not entry[0].done() or entry[1] is not None):
            return await asyncio.shield(entry[0])  # still running, or finished a moment ago
        task = asyncio.ensure_future(self._read_file(path, name))
        entry = [task, None]
        self._texts.pop(path, None)  # a read again goes in as the newest entry, not in the old one's place
        self._texts[path] = entry

        def finished(t: asyncio.Task[tuple[str, str]]) -> None:
            error = None if t.cancelled() else t.exception()  # also marks the error as seen
            if t.cancelled() or (error is not None and not isinstance(error, UnreadableAttachment)):
                # KLAS or network trouble: the next try downloads again
                if self._texts.get(path) is entry:
                    del self._texts[path]
                return
            entry[1] = when = time.monotonic()
            # Over the cap: expired reads go first, then the ones that finished longest ago. Reads
            # still running stay, so a part=2 doesn't download the file again.
            done = sorted((p for p, (other, at) in self._texts.items() if other.done() and at is not None),
                          key=lambda p: (not _text_expired(self._texts[p], when), self._texts[p][1]))
            for old in done[:max(0, len(self._texts) - ATTACHMENT_TEXT_CACHE)]:
                del self._texts[old]

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def _read_file(self, path: str, name: str) -> tuple[str, str]:
        try:
            data = await self._client.download(path, MAX_DOWNLOAD_BYTES)
        except KlasFileTooLarge as e:  # found out while downloading: as final as any unreadable file
            raise UnreadableAttachment(str(e)) from e
        try:
            kind, text = await asyncio.to_thread(extract_text, name, data)  # big PDFs: keep the event loop free
        except UnreadableAttachment:
            raise
        except Exception as e:  # a parser failing on a broken file is not "KLAS changed"
            raise UnreadableAttachment("파일을 읽지 못했습니다(손상됐거나 지원하지 않는 형식일 수 있음).") from e
        return kind, clean(text)

    async def syllabus(self, course: str) -> dict[str, Any]:
        """The course's syllabus (강의계획서). KLAS's mobile-number and TA fields are left out, and so is
        a 연락처 that is a mobile number. Free text the professor wrote is passed on as written,
        wrapped in the KLAS_CONTENT marker."""
        return await self._syllabus(await self._one_course(course))

    async def _syllabus(self, row: dict[str, Any]) -> dict[str, Any]:
        data = await self._cached((SYLLABUS, row.get("subj")), SYLLABUS_TTL,
                                  lambda: self._client.post(SYLLABUS, {"selectSubj": row.get("subj")}))
        data = _list(data, SYLLABUS)
        plan = data[0] if data and isinstance(data[0], dict) else {}
        if not plan:
            raise LookupError(f"{row.get('subjNm')}의 강의계획서가 아직 없습니다.")

        def text(field: str) -> str | None:
            value = clean(str(plan.get(field) or "")).strip()
            return value[:SYLLABUS_TEXT_CHARS] or None

        def free(field: str) -> str | None:
            return untrusted(text(field))

        weeks = [{"week": i, "topic": free(f"week{i}Lecture"), "note": free(f"week{i}Bigo")}
                 for i in range(1, 17) if text(f"week{i}Lecture") or text(f"week{i}Bigo")]
        grading = {name: _int(plan.get(field)) or 0 for name, field in GRADING}
        books = [{"title": text(f"{p}Name"), "author": text(f"{w}Name"), "publisher": text(f"{c}Name"),
                  "year": text(f"{y}Year")}
                 for p, w, c, y in [("book", "write", "company", "print")]
                 + [(f"book{i}", f"write{i}", f"company{i}", f"print{i}") for i in (1, 2, 3)]
                 if text(f"{p}Name")]
        phone = text("telNo")
        return {
            "course": row.get("subjNm"),
            "category": text("codeName1"),
            "credits": plan.get("hakjumNum"),
            "professor": text("memberName") or row.get("profNm"),
            "professor_title": text("jikgeubName"),
            "professor_email": text("email"),
            "professor_office_phone": _office_phone(phone),
            "overview": free("summary"),
            "objectives_and_method": free("purpose"),
            "competencies": free("gwamokAble"),
            "prerequisites": free("preGwamok"),
            "weekly_plan": weeks,
            "grading_percent": {k: v for k, v in grading.items() if v},
            "grading_note": free("gitaDetail"),
            "textbooks": books,
            "notes": free("bigo"),
            "other": free("weekGita"),
        }

    async def _find_task(self, course: str, title: str, task_id: str | int | None = None
                         ) -> tuple[dict[str, Any], dict[str, Any]]:
        """One assignment by title; task_id (the "id" the assignment lists return, str or int) picks
        one among assignments with the same title."""
        if course and course.strip():
            # Settle the course first (exact name wins), so "자료구조" doesn't also search "자료구조실습".
            row = await self._one_course(course)
            per_course = [(row, await self._items(TASKS, row))]
        else:
            per_course = await self._per_course(TASKS, None, None)
        title = (title or "").strip()
        found = [(row, t) for row, items in per_course for t in items if _matches(clean(t.get("title")), title or None)]
        if task_id is not None and str(task_id).strip():
            # Only an assignment the list itself returned: an id never reaches KLAS unchecked.
            chosen = [(row, t) for row, t in found if str(t.get("ordseq")) == str(task_id).strip()]
            if len(chosen) == 1:
                return chosen[0]
            raise LookupError(f"id '{task_id}'인 과제를 찾지 못했습니다. 과제 목록·마감 목록이나 '여러 개' 안내에 나온 "
                              "id와 과제 제목을 확인하세요.")
        exact = [(row, t) for row, t in found if _norm(t.get("title")) == _norm(title)]
        if len(exact) == 1 or len(found) == 1:
            return (exact or found)[0]
        if not found:
            raise LookupError(f"'{title}'와 일치하는 과제가 없습니다. 과제 목록 도구로 과제 제목을 확인하세요.")
        names = ", ".join(f"{row.get('subjNm')}: {clean(t.get('title'))} (id {t.get('ordseq')}, 마감 {fmt_kst(t.get('expiredate')) or '?'})"
                          for row, t in found[:8])
        raise LookupError(f"'{title}'와 일치하는 과제가 여러 개입니다. 과목명이나 제목을 더 구체적으로 주거나 id를 함께 주세요: {names}")

    async def assignment_detail(self, course: str, title: str, task_id: str | int | None = None) -> dict[str, Any]:
        """What one assignment asks for: instructions, format, attachments (names), my submission.

        Fields are whitelisted: the view response also carries my student id (projid), name and
        department, which are left out. Instructions and feedback are someone else's text and come
        wrapped in the KLAS_CONTENT marker.
        """
        row, task = await self._find_task(course, title, task_id)
        view = await self._client.post(TASK_VIEW, {"selectChangeYn": "Y", "selectYearhakgi": row.get("yearhakgi"),
                                                   "selectSubj": row.get("subj"), "ordseq": task.get("ordseq")})
        view = _dict(view, TASK_VIEW)
        rpt = view.get("rpt") or {}
        smt = view.get("smt") or None
        files: list[dict[str, Any]] = []
        if rpt.get("atchFileId") and rpt.get("attachopen") != "N":
            files = self._file_rows(await self._file_list("CLS_PROF_TASK", rpt["atchFileId"]))
        # Same rule as the KLAS page: a score shows only once graded and the professor made scores public.
        score_visible = bool(smt and smt.get("tutordate") and rpt.get("isopenscore") == "Y")
        return {
            "course": row.get("subjNm"),
            "title": clean(rpt.get("title") or task.get("title")),
            "id": task.get("ordseq"),
            "instructions": untrusted(html_to_text(rpt.get("contents"))),
            "submit_format": _free_text(rpt.get("submitfiletype")),
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
                "feedback": untrusted(html_to_text(smt.get("tutorcontents"))),
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
            body = {"selectYear": year, "selectHakgi": term, "subj": row.get("subj")}
            data = await self._cached((ATTENDANCE, row.get("subj"), semester), ATTENDANCE_TTL,
                                      lambda: self._client.post(ATTENDANCE, body))
            counts: Counter[str] = Counter()
            weeks = []
            for week in _list(data, ATTENDANCE):
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
        """Per course: exam weeks and grading from the syllabus, plus board posts about exams: '시험'
        on both boards and '고사' (중간고사·기말고사) on the notice board."""
        rows = await self._course_rows(None, course or None)

        async def one(row: dict[str, Any]) -> dict[str, Any]:
            plan, exams, tests = await _gather(self._syllabus_or_none(row), self._boards(row, "ALL", "시험"),
                                               self._boards(row, "ALL", "고사", BOARDS[:1]))
            seen, posts = set(), []
            for (board, _, master_no), listed in [*exams, *tests]:
                for item in listed.get("list") or []:
                    if not isinstance(item, dict):
                        continue
                    post = self._post_row(board, item, master_no)
                    key = (post["board"], post["title"], post["posted"])
                    if key not in seen:
                        seen.add(key)
                        posts.append(post)
            posts.sort(key=lambda p: p["posted"] or "", reverse=True)
            weeks = [w for w in (plan or {}).get("weekly_plan", [])
                     if EXAM_WORDS.search(f"{w.get('topic') or ''} {w.get('note') or ''}")]
            return {"course": row.get("subjNm"),
                    "grading_percent": (plan or {}).get("grading_percent"),
                    "grading_note": (plan or {}).get("grading_note"),
                    "exam_related_weeks": weeks,
                    "exam_posts": posts[:6],
                    "hint": "글 본문(시험 범위·장소)은 게시판 글 열기 도구로 확인하세요. exam_posts가 비어도 공지가 없다는 "
                            "뜻은 아닙니다. 게시판 검색 도구로 '기말'·'중간'을 찾아보세요."}

        return await _gather(*(one(r) for r in rows))

    async def _syllabus_or_none(self, row: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return await self._syllabus(row)
        except LookupError:
            return None

    async def class_changes(self, days: str | int = 14) -> dict[str, Any]:
        """Class cancellations, make-ups, online switches and room, time or day changes (휴강·보강·결강·
        비대면·강의실/시간/요일 변경) on every course's notice board in the last `days` days.

        Three requests per course, each cached for BOARD_TTL: the newest posts, kept when the title
        matches CLASS_CHANGE_WORDS, and a '휴강' and a '보강' search (titles and bodies, so older
        posts and posts that say it only in the body are found too)."""
        days = max(1, min(_int(days) or 14, 60))
        since = (self._now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        rows = await self._course_rows(None, None)
        notice_board = BOARDS[:1]
        searches = [(row, "", self._boards(row, "ALL", "", notice_board)) for row in rows]
        searches += [(row, word, self._boards(row, "ALL", word, notice_board)) for word in ("휴강", "보강") for row in rows]
        results = await _gather(*(search for _, _, search in searches))
        seen, posts = set(), []
        for (row, keyword, _), result in zip(searches, results, strict=True):
            for (board, _, master_no), listed in result:
                for item in listed.get("list") or []:
                    if not isinstance(item, dict):
                        continue
                    post = {"course": row.get("subjNm"), **self._post_row(board, item, master_no)}
                    if not keyword and not CLASS_CHANGE_WORDS.search(post["title"]):
                        continue  # the newest posts: only titles about class changes
                    key = (post["course"], post["title"], post["posted"])
                    if key not in seen and (post["posted"] or "") >= since:
                        seen.add(key)
                        posts.append(post)
        posts.sort(key=lambda p: p["posted"] or "", reverse=True)
        return {"days": days, "since": since, "posts": posts,
                "note": "각 과목 강의 공지사항의 최근 글 중 휴강·보강·결강·비대면(온라인 전환)·강의실·시간·요일 변경 제목과, "
                        "'휴강'·'보강' 검색(제목·본문) 결과입니다. 내용은 게시판 글 열기 도구로 확인하세요. 휴강은 문자·메일·"
                        "수업 중에만 알리는 경우도 있어, 여기 없다고 휴강이 아니라는 뜻은 아닙니다."}

    async def _student_record(self) -> dict[str, Any]:
        """학적 (AtnlcScreHakjukInfo.do), shared by grades, graduation progress and department()."""
        record = await self._cached(("record",), RECORD_TTL, lambda: self._client.post(STUDENT_RECORD))
        return _dict(record, STUDENT_RECORD)

    async def department(self) -> str | None:
        """My department (학과/학부) from the 학적, e.g. "정보융합학부"; a track after a space is dropped.
        The extension's my_notices filters department notices with it on this PC. The bridge's
        my_notices asks the PC agent for it (the agent's "department" call), and gets only this name,
        never the rest of the 학적, to pick the department's boards."""
        name = str((await self._student_record()).get("hakgwa") or "").split()
        return name[0] if name else None

    async def _gen_ed(self) -> dict[str, Any]:
        """교양 이수현황 (GyoyangIsuInfo.do) as its page totals it: the 필수교양 column (aa8128) and
        the balanced areas (BALANCED_AREAS)."""
        gen = _dict(await self._cached(("gen_ed",), CREDITS_TTL, lambda: self._client.post(GEN_ED)), GEN_ED)
        return {"required": _int(gen.get("aa8128")) or 0,
                "balanced_by_area": {name: sum(_int(gen.get(k)) or 0 for k in keys) for name, keys in BALANCED_AREAS}}

    async def _grade_totals(self) -> dict[str, Any]:
        """취득 학점과 평점 합계 (AtnlcScreSungjukTot.do)."""
        totals = await self._cached(("grade_totals",), CREDITS_TTL, lambda: self._client.post(GRADE_TOTALS))
        return _dict(totals, GRADE_TOTALS)

    async def _transcript(self) -> list[dict[str, Any]]:
        """The transcript's semesters with their courses as _grade_row reads them (category = 이수구분)."""
        data = await self._cached(("transcript",), CREDITS_TTL, lambda: self._client.post(GRADES))
        return [{"year": s.get("thisYear"), "term": s.get("hakgi"),
                 "courses": [_grade_row(g) for g in s.get("sungjukList") or [] if isinstance(g, dict)]}
                for s in _list(data, GRADES) if isinstance(s, dict)]

    async def graduation_progress(self) -> dict[str, Any]:
        """Where I stand on credits and general-education rules (교양 필수·균형 이수현황).

        The admission year is read from the first four digits of the student id; the id itself is
        not returned. The 교양 rule is the admission year's from rules/graduation.json (2025학번 이하
        don't need 광운인되기 since 2026-03-01); what KLAS's table can't show is 확인 필요, not a guess.
        Department-specific major requirements are not in KLAS's data, so they are pointed to the
        department office.
        """
        gen_ed, totals, record = await _gather(self._gen_ed(), self._grade_totals(), self._student_record())
        areas, required = gen_ed["balanced_by_area"], gen_ed["required"]
        me = simulation.student(record)
        transfer = {"total": record.get("prevHakjumNum"), "general_education": record.get("cultureHakjum"),
                    "major": record.get("majorHakjum"), "elective": record.get("generalHakjum")}
        check = simulation.general_education_check(me, gen_ed)
        rule = check.pop("rule")
        if me["transfer"]:
            check["transfer_credits"] = transfer
        extra, _ = await _gather_some({"check": self.graduation_check(), "language": self.language_requirement()},
                                      optional=True)
        return {
            "student": {"department": record.get("hakgwa"), "year": record.get("grade"),
                        "status": record.get("hakjukStatu"), "admission_year": me["admission_year"]},
            "earned_credits": {"total": totals.get("chidukHakjum"), "major": totals.get("majorChidukHakjum"),
                               "general_education": totals.get("cultureChidukHakjum"),
                               "other": totals.get("etcChidukHakjum")},
            "gpa": {"transcript_record": totals.get("hwakinScoresum"), "certificate": totals.get("jaechulScoresum")},
            "general_education": {"required": required, "balanced_by_area": areas,
                                  "balanced_areas_taken": sum(1 for v in areas.values() if v > 0),
                                  "total": required + sum(areas.values())},
            "rule": rule,
            "check": check,
            "official_check": extra.get("check"),
            "language_requirement": extra.get("language", "unavailable"),
            "notes": ["성적 처리가 끝난 과목만 합산(F·NP·삭제 학점 제외)", "균형교양은 3·4학점 과목만 인정, e러닝·K-MOOC 등 일부 계열 제외",
                      "전공 졸업 학점·공학인증 등 학과별 요건은 학과 사무실에 확인하세요",
                      "어학 요건의 target·passed는 KLAS 코드 그대로예요. 뜻은 KLAS에서 확인해 주세요"],
        }

    async def language_requirement(self) -> dict[str, Any] | None:
        """어학 졸업요건 (ToeicInfoStd.do), None when KLAS has no row. Only the requirement fields leave: the
        row also carries my name and student id. The codes are KLAS's own (what Y/N means isn't confirmed)."""
        rows = _list(await self._client.post(LANGUAGE_REQUIREMENT, {}), LANGUAGE_REQUIREMENT)
        row = next((r for r in rows if isinstance(r, dict)), None)
        if row is None:
            return None
        return {"target": _free_text(row.get("daesangOpt")), "passed": _free_text(row.get("passOpt")),
                "test": _label(row.get("langName")), "score": _free_text(row.get("langScore")),
                "date": _day(row.get("langDate"))}

    async def graduation_check(self) -> dict[str, Any]:
        """The school's own 졸업가부 / 불가사유 (GrdtnYnImprtyResnStdPage.do). It answers only for students
        on the graduation review list; anyone else gets an empty body, which the page shows as
        "졸업자 명단에 없습니다" (checked 2026-11-06). graduateOpt 1 = 졸업가능, 2 = 졸업불가 with a
        reason, as the page's template reads it. Name and student id in the answer are left out."""
        data = await self._client.post(GRADUATION_CHECK, {"info": ""}, allow_empty=True)
        if not isinstance(data, dict) or not data:
            return {"on_list": False, "message": "학교 졸업 사정 명단에 없습니다(졸업 예정 학기가 아니거나 아직 사정 전). "
                                                  "명단에 오르면 졸업 가능 여부와 불가 사유가 여기 나옵니다."}
        option = str(data.get("graduateOpt") or "")
        return {"on_list": True, "eligible": option == "1" if option in ("1", "2") else None,
                "reason": clean(str(data.get("reason") or "")).strip() or None if option == "2" else None,
                "as_of": data.get("entryDate"), "college": data.get("organName"), "department": data.get("className"),
                "note": "졸업불가면 대표 홈페이지 공지사항의 졸업불가자 행정사항을 확인하세요."}

    async def graduation_outlook(self) -> dict[str, Any]:
        """졸업 시뮬레이션 (reference only): every graduation requirement of the published rules for my
        admission year and department, from the same reads as graduation_progress plus the transcript."""
        record, totals, transcript, gen_ed = await _gather(self._student_record(), self._grade_totals(),
                                                           self._transcript(), self._gen_ed())
        return simulation.graduation_outlook(record, totals, transcript, gen_ed)

    async def multi_major_options(self, track: str | None = None, track_type: str | None = None) -> dict[str, Any]:
        """다전공 options (reference only) for my admission year and college; with track, one 연계·마이크로
        전공 or department, with track_type one kind (심화·복수·부·연계·마이크로·학생설계). Without track, the
        다전공 I applied for come along (my_applications) when KLAS lists any."""
        mine = {} if track else {kind: self._majors_applied(kind, path) for kind, path in MULTI_MAJOR_APPLIED}
        (record, transcript), (applied, _) = await _gather(_gather(self._student_record(), self._transcript()),
                                                           _gather_some(mine, optional=True))
        out = simulation.multi_major_options(record, transcript, track=track, track_type=track_type)
        if rows := [row for kind, _ in MULTI_MAJOR_APPLIED for row in applied.get(kind, [])]:
            out["my_applications"] = rows
        return out

    # -- 학적: 휴·복학, 다전공 ----------------------------------------------------------

    async def _hakjuk(self, path: str) -> dict[str, Any]:
        """One 학적 read (POST {}), shared for STATUS_TTL."""
        return _dict(await self._cached((path,), STATUS_TTL, lambda: self._client.post(path, {})), path)

    async def _leave_windows(self) -> list[dict[str, Any]]:
        return leave_windows(await self._hakjuk(LEAVE_WINDOWS))

    async def _leave_status(self) -> dict[str, Any]:
        """My 학적 state and my 휴·복학 applications (TmpabssklStatu.do). 비고 is staff text, wrapped."""
        data = await self._hakjuk(LEAVE_STATUS)
        return {
            "status": {"state": _label(data.get("hakjukName")), "state_date": _day(data.get("hakjukDate")),
                       "return_date": _day(data.get("combackDate"))},
            "applications": [{"type": _label(r.get("gubun")), "applied": _day(r.get("applyDate")),
                              "status": _label(r.get("processName")), "processed": _day(r.get("processDate")),
                              "note": untrusted(_flat(r.get("bigo"))[:NOTE_CHARS])}
                             for r in _list(data.get("statu"), LEAVE_STATUS) if isinstance(r, dict)],
        }

    async def _majors_applied(self, kind: str, path: str) -> list[dict[str, Any]]:
        """My applications of one 다전공 kind. Only resultList is read: hakjukMap holds my name, student id
        and my advisor's name and e-mail, and none of it may leave this PC."""
        data = await self._hakjuk(path)
        return [{"kind": kind, "track_type": _label(r.get("submajor")), "name": _label(r.get("majorName")),
                 "college": _label(r.get("organName")), "department": _label(r.get("className")),
                 "applied": _day(r.get("applyDate")), "finished": _free_text(r.get("finishOpt"))}
                for r in _list(data.get("resultList"), path) if isinstance(r, dict)]

    async def academic_status(self) -> dict[str, Any]:
        """휴·복학 (my 학적 state, my applications, the application windows) and the 다전공 I applied for.
        Each KLAS read fails on its own and shows as "unavailable", never as an empty list. Login
        trouble still raises, and so does every read failing."""
        found, failed = await _gather_some({
            "status": self._leave_status(), "windows": self._leave_windows(),
            **{kind: self._majors_applied(kind, path) for kind, path in MULTI_MAJOR_APPLIED}})
        leave = found.get("status") or {"status": "unavailable", "applications": "unavailable"}
        majors = [row for kind, _ in MULTI_MAJOR_APPLIED
                  for row in found.get(kind, [{"kind": kind, "status": "unavailable"}])]
        return {
            "leave": {**leave, "windows": found.get("windows", "unavailable")},
            "multi_major": majors,
            "note": "신청은 KLAS에서 직접 해야 해요." + (" unavailable은 KLAS에서 못 읽은 항목이에요." if failed else ""),
        }

    async def course_overview(self, course: str | None = None) -> list[dict[str, Any]]:
        """Each course's home-page summary (LctrumHomeStdInfo.do): done/total for lectures and every
        kind of coursework, new items, and attendance counts. The same numbers KLAS shows on the
        course home, e.g. 과제 2/3 = submitted 2 of 3. Notices, staff ids and contact fields are left out."""
        rows = await self._course_rows(None, course)

        async def one(row: dict[str, Any]) -> dict[str, Any]:
            body = {"selectYearhakgi": row.get("yearhakgi"), "selectSubj": row.get("subj"), "selectChangeYn": "Y"}
            info = await self._cached((COURSE_HOME, body["selectSubj"], body["selectYearhakgi"]), COURSE_TTL,
                                      lambda: self._client.post(COURSE_HOME, body))
            info = info if isinstance(info, dict) else {}

            def pair(done: str, total: str, new: str | None = None) -> dict[str, Any]:
                out = {"done": _int(info.get(done)), "total": _int(info.get(total))}
                if new:
                    out["new"] = _int(info.get(new))
                return out

            attendance = Counter(ATTEND_STATUS.get(a.get("attendancediv")) for a in info.get("atendList") or []
                                 if isinstance(a, dict) and a.get("attendancediv") in ATTEND_STATUS)
            lectures = info.get("cntntList") if isinstance(info.get("cntntList"), list) else []
            return {
                "course": row.get("subjNm"),
                "online_lectures": {"done": _int(info.get("cntntCmpltCnt")), "total": len(lectures)},
                "assignments": pair("taskPrsntCnt", "taskCnt", "taskNewCnt"),
                "quizzes": pair("quizPrsntCnt", "quizCnt", "quizNewCnt"),
                "online_tests": pair("examPrsntCnt", "examCnt", "examNewCnt"),
                "team_projects": pair("prjctPrsntCnt", "prjctCnt", "prjctNewCnt"),
                "surveys": pair("surveyPrsntCnt", "surveyCnt", "surveyNewCnt"),
                "discussions": pair("dscsnJoinCnt", "dscsnCnt", "dscsnNewCnt"),
                "materials": {"total": _int(info.get("pdsCnt")), "new": _int(info.get("pdsNewCnt"))},
                "attendance": {status: attendance.get(status, 0) for status in ATTEND_STATUS.values()},
            }

        return list(await _gather(*(one(r) for r in rows)))

    # -- grades ----------------------------------------------------------------

    async def grades(self) -> dict[str, Any]:
        """Grades by semester, credits and the two KLAS grade averages.

        Whitelisted: the student record endpoint also returns my name, student id, e-mail and
        advisor, which are left out. The grade is the first word of KLAS's grade text; rows marked
        삭제 (dropped credits) are listed with deleted=true and left out of every computed number.
        KLAS's own averages (gpa) are the official ones.
        """
        semesters, totals, record = await _gather(self._client.post(GRADES), self._client.post(GRADE_TOTALS),
                                                  self._student_record())
        totals = _dict(totals, GRADE_TOTALS)
        extra, _ = await _gather_some({"standing": self.standing(), "period": self.grade_period()}, optional=True)

        def credits(kind: str) -> dict[str, Any]:
            prefix = {"applied": "Apply", "deleted": "Del", "earned": "Chiduk"}[kind]
            return {"major": totals.get(f"major{prefix}Hakjum"), "general_education": totals.get(f"culture{prefix}Hakjum"),
                    "other": totals.get(f"etc{prefix}Hakjum"), "total": totals.get(f"{prefix[0].lower()}{prefix[1:]}Hakjum")}

        out_semesters = []
        for s in _list(semesters, GRADES):
            if not isinstance(s, dict):
                continue
            courses = [_grade_row(g) for g in s.get("sungjukList") or [] if isinstance(g, dict)]
            counted = [c for c in courses if not c.get("deleted")]
            graded = [(c["credits"] or 0, GRADE_POINTS[c["grade"]]) for c in counted if c["grade"] in GRADE_POINTS]
            weight = sum(w for w, _ in graded)
            # Earned: graded and passed only. While grades come in course by course, the rest is pending.
            pending = sum(c["credits"] or 0 for c in counted if not c["grade"])
            out_semesters.append({
                "year": s.get("thisYear"), "term": s.get("hakgi"),
                "registered_credits": sum(c["credits"] or 0 for c in counted),
                "earned_credits": (sum(c["credits"] or 0 for c in counted if c["grade"] and c["grade"] not in ("F", "NP"))
                                   if any(c["grade"] for c in counted) else None),
                **({"pending_credits": pending} if pending else {}),
                "gpa": round(sum(w * p for w, p in graded) / weight, 2) if weight else None,
                "courses": courses,
            })
        transfer = {"general_education": record.get("cultureHakjum"), "major": record.get("majorHakjum"),
                    "elective": record.get("generalHakjum"), "total": record.get("prevHakjumNum")}
        return {
            "student": {"department": record.get("hakgwa"), "year": record.get("grade"),
                        "status": record.get("hakjukStatu")},
            "gpa": {"transcript_record": totals.get("hwakinScoresum"), "certificate": totals.get("jaechulScoresum"),
                    "scale": 4.5, "note": "KLAS 계산값(학적부 기준 / 성적증명서 기준, 재수강 반영)이 공식 평점입니다. 학기별 gpa와 "
                                          "summary는 이 도구가 과목 목록으로 계산한 참고값입니다"},
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
                for r in _list(rows, STANDING) if isinstance(r, dict)]

    async def scholarships(self) -> dict[str, Any]:
        """장학 수혜 내역 (JanghakHistoryStdList.do), as KLAS's 장학조회 page lists it: per term, each
        scholarship's name and amount. The page's other list (JanghakStdList.do) is only the student
        header and is not read. KLAS doesn't say whether a scholarship reduced tuition or was paid
        out separately (생활비 등), so the answer says so instead of guessing."""
        rows = await self._client.post(SCHOLARSHIP_HISTORY, {}, allow_empty=True)
        terms: dict[str, dict[str, Any]] = {}
        for row in _list(rows or [], SCHOLARSHIP_HISTORY):
            if not isinstance(row, dict):
                continue
            raw = str(row.get("yearHakgi") or "")  # "2026-2"
            key = _normalize_semester(raw) or raw
            year, _, term = key.partition(",")
            label = f"{year}학년도 {_TERM_LABEL.get(term, term + '학기')}" if _SEMESTER.fullmatch(key) else raw
            entry = terms.setdefault(key, {"semester": key, "label": label, "year_level": _int(row.get("grade")),
                                           "scholarships": [], "total": 0})
            amount = _int(row.get("janghakAmt")) or 0
            entry["scholarships"].append({"name": clean(str(row.get("janghakName") or "")) or None, "amount": amount})
            entry["total"] += amount
        ordered = sorted(terms.values(), key=lambda t: _semester_order(t["semester"]), reverse=True)
        return {"terms": ordered, "total_amount": sum(t["total"] for t in ordered),
                "note": "KLAS 장학조회 화면과 같은 내역입니다(금액은 원). 등록금 감면인지 생활비처럼 따로 받는 장학금인지는 "
                        "KLAS가 알려 주지 않으니, 다른 장학금과의 중복 여부는 해당 장학 공지나 학생복지팀에 확인하세요."}

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
        rows = [r for r in _list(rows, EVAL_COURSES) if isinstance(r, dict)]
        return {
            "open": True, "round": {"middle": "중간", "last": "기말"}.get(round_, round_),
            "courses": len(rows),
            "not_evaluated": [r.get("gwamokKname") for r in rows if r.get("judgeOpt") == "N"],
            "note": "평가하지 않은 과목은 성적 열람이 제한될 수 있습니다. 평가는 KLAS에서 직접 하세요.",
        }

    async def course_drop(self) -> dict[str, Any]:
        """수강포기 window from KLAS's 수강포기 page (HTML). The page says "수강포기 기간이 아닙니다" when it
        is closed; anything else isn't read as open."""
        page = await self._client.page(COURSE_DROP_PAGE)
        if "수강포기기간이아닙니다" in re.sub(r"\s+", "", page.replace("&nbsp;", " ")):
            return {"open": False}
        return {"open": None, "note": "KLAS 수강포기 신청 메뉴에서 확인해 주세요"}

    async def application_windows(self) -> dict[str, Any]:
        """KLAS's own "is it open now" answers for scholarship applications and dropping earned
        credits (취득학점포기), plus the grade viewing period, the course evaluation window and
        수강포기 (course_drop)."""
        found, missing = await _gather_some({
            "scholarship": self._client.post(SCHOLARSHIP_TERM), "drop_credits": self._client.post(DROP_CREDITS_TERM),
            "grade_viewing": self.grade_period(), "course_evaluation": self.course_evaluation(),
            "course_drop": self.course_drop()})
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
        if "course_drop" in found:
            out["course_drop"] = found["course_drop"]
        if missing:
            out["incomplete"] = missing
        return out
