"""Service, combined tools and server after review 1: end-of-day deadline windows, per-course
isolation, error-shaped answers, semester handling, caching, grades, untrusted text, public-data
status and the department filter."""

import asyncio
import json
import time
from datetime import datetime
from typing import Any
from urllib.parse import unquote

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from kw_mcp import combined, credentials, klas, server, service
from kw_mcp.attachments import UnreadableAttachment
from kw_mcp.klas import KlasError, KlasLoginError
from kw_mcp.public_api import PublicApi
from kw_mcp.service import (
    ATTENDANCE,
    BOARDS,
    FILE_LIST,
    GRADES,
    HOME,
    KST,
    ONLINE,
    SEMESTERS,
    STUDENT_RECORD,
    SYLLABUS,
    TASK_VIEW,
    TASKS,
    KlasService,
    grade_summary,
)
from kw_mcp.text import html_to_text, untrusted
from tests.test_attachments import MINI_PDF
from tests.test_items import SYLLABUS_ROW, ItemClient
from tests.test_needs import NeedsClient
from tests.test_service import FakeClient

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=KST)


def at(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


def wrapped(text: str) -> str:
    return f"<<<KLAS_CONTENT\n{text}\nKLAS_CONTENT>>>"


# -- deadline window ------------------------------------------------------------------------------

class NightClient(FakeClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == TASKS:
            if (body or {}).get("selectSubj") != "U2026A":
                return []
            return [{"title": "오늘 밤", "expiredate": "2026-11-05 23:59:59", "submityn": "N"},
                    {"title": "내일 밤", "expiredate": "2026-11-06 23:59:59", "submityn": "N"}]
        if path == ONLINE:
            return []
        return await super().post(path, body)


async def test_deadline_window_runs_to_the_end_of_the_target_day():
    svc = KlasService(NightClient(), now=lambda: at(2026, 11, 5, 22, 0))
    titles = lambda due: [i["title"] for i in due["items"] if i["kind"] == "assignment"]
    today = await svc.deadlines(0)
    assert titles(today) == ["오늘 밤"] and today["until"] == "2026-11-05 23:59"
    assert titles(await svc.deadlines(1)) == ["오늘 밤", "내일 밤"]  # "내일 마감" asked at 22:00


# -- one course failing ------------------------------------------------------------------------

class OneCourseFails(FakeClient):
    error: type[Exception] = KlasError

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path in (TASKS, ONLINE) and (body or {}).get("selectSubj") == "U2026B":
            raise self.error(f"{path}: HTTP 500")
        return await super().post(path, body)


async def test_one_failing_course_keeps_the_others_and_is_reported():
    svc = KlasService(OneCourseFails(), now=lambda: NOW)
    due = await svc.deadlines(7)
    assert ("assignment", "HW3") in [(i["kind"], i["title"]) for i in due["items"]]
    assert due["incomplete"]["missing"] == []
    assert due["incomplete"]["missing_courses"] == [{"kind": "assignment", "course": "확장현실"},
                                                    {"kind": "online_lecture", "course": "확장현실"}]
    with pytest.raises(KlasError):  # a direct list tool still says it couldn't read everything
        await svc.assignments()


async def test_snapshot_keeps_what_it_could_read():
    svc = KlasService(OneCourseFails(), now=lambda: NOW)
    snap = await svc.snapshot()
    assert snap["sections"]["U2026A"]["tasks"] and "tasks" not in snap["sections"].get("U2026B", {})
    assert snap["missing"] == {"lists": [], "courses": [{"kind": "tasks", "course": "확장현실"},
                                                        {"kind": "online", "course": "확장현실"}]}


async def test_login_trouble_in_one_course_is_not_a_partial_answer():
    client = OneCourseFails()
    client.error = KlasLoginError
    with pytest.raises(KlasLoginError):
        await KlasService(client, now=lambda: NOW).deadlines(7)


class ErrorShaped(FakeClient):
    home_error = False

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == TASKS and (body or {}).get("selectSubj") == "U2026A":
            return {"error": {"message": "server busy"}}
        if path == HOME and self.home_error:
            return {"error": {"message": "server busy"}}
        return await super().post(path, body)


async def test_error_shaped_answers_are_errors_not_empty_lists():
    svc = KlasService(ErrorShaped(), now=lambda: NOW)
    due = await svc.deadlines(7)
    assert {"kind": "assignment", "course": "데이터마이닝"} in due["incomplete"]["missing_courses"]
    client = ErrorShaped()
    client.home_error = True
    with pytest.raises(KlasError, match="과목 목록"):
        await KlasService(client, now=lambda: NOW).deadlines(7)


# -- semesters ---------------------------------------------------------------------------------

class Terms(FakeClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == SEMESTERS:  # string-sorted, the way KLAS may list them
            return [{"value": "2026,3"}, {"value": "2026,2"}, {"value": "2026,1"}]
        return await super().post(path, body)


@pytest.mark.parametrize(("now", "expected"), [
    (at(2026, 10, 1), "2026,2"), (at(2026, 12, 23), "2026,2"), (at(2026, 12, 28), "2026,2"),
    (at(2027, 2, 10), "2026,2"), (at(2026, 7, 15), "2026,3"),
])
async def test_current_semester_uses_calendar_order(now, expected):
    assert await KlasService(Terms(), now=lambda: now).current_semester() == expected


async def test_semester_values_are_checked_and_normalized():
    svc = KlasService(FakeClient(), now=lambda: NOW)
    assert [a["title"] for a in await svc.assignments(semester="2026년 2학기")] == ["HW2", "HW3", "HW4"]
    assert ("searchYearhakgi", "2026,2") in [kv for p, b in svc._client.calls if p == HOME for kv in b.items()]
    for bad in ("2025,1", "bogus"):
        with pytest.raises(LookupError, match="2026,2"):
            await svc.assignments(semester=bad)


# -- online progress, cache ------------------------------------------------------------------------

class Progress(FakeClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == ONLINE:
            if (body or {}).get("selectSubj") != "U2026A":
                return []
            return [{"sbjt": "다 봄", "endDate": "2026-11-09 23:59", "prog": "100.0"},
                    {"sbjt": "거의", "endDate": "2026-11-09 23:59", "prog": "99.5"}]
        return await super().post(path, body)


async def test_decimal_progress_counts_as_done():
    rows = await KlasService(Progress(), now=lambda: NOW).online_lectures(incomplete_only=True)
    assert [(r["title"], r["progress_percent"]) for r in rows] == [("거의", 99)]


class Slow(FakeClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == SEMESTERS:
            await asyncio.sleep(0.05)
        return await super().post(path, body)


async def test_cache_shares_a_slow_request_and_counts_ttl_from_its_answer(monkeypatch):
    monkeypatch.setattr(service, "HOME_TTL", 0.02)
    svc = KlasService(Slow(), now=lambda: NOW)
    await asyncio.gather(svc.current_semester(), svc.current_semester())  # slower than the TTL
    assert [p for p, _ in svc._client.calls].count(SEMESTERS) == 1
    await svc.current_semester()  # within the TTL counted from the answer
    assert [p for p, _ in svc._client.calls].count(SEMESTERS) == 1
    await asyncio.sleep(0.03)
    await svc.current_semester()
    assert [p for p, _ in svc._client.calls].count(SEMESTERS) == 2
    await asyncio.sleep(0.03)
    svc._prune(time.monotonic())
    assert ("semesters",) not in svc._cache  # expired answers don't linger


async def test_syllabus_boards_and_attendance_are_cached():
    client = NeedsClient()
    svc = KlasService(client, now=lambda: NOW)
    await svc.exam_info()
    await svc.exam_info()
    await svc.attendance()
    await svc.attendance()
    calls = [p for p, _ in client.calls]
    assert calls.count(SYLLABUS) == 2  # once per course
    assert calls.count(ATTENDANCE) == 2
    assert sum(p.endswith("/BoardStdList.do") for p in calls) == 6  # 3 searches per course, once


# -- boards ------------------------------------------------------------------------------------

class ExamPosts(NeedsClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path.endswith("/BoardStdList.do") and (body or {}).get("searchKeyword") == "고사":
            self.calls.append((path, body))
            if body["selectSubj"] != "U2026A":
                return {"list": [], "page": {"totalElements": 0}}
            return {"list": [{"boardNo": 35, "title": "기말고사 범위 및 장소 안내",
                              "registDt": "2026-11-02T09:00:00.000+09:00"}], "page": {"totalElements": 1}}
        if path.endswith("/BoardStdList.do") and (body or {}).get("searchKeyword") == "":
            self.calls.append((path, body))
            if body["selectSubj"] != "U2026A":
                return {"list": [], "page": {"totalElements": 0}}
            return {"list": [{"boardNo": 36, "title": "12/10 수업 비대면 대체 안내", "registDt": "2026-11-04T10:00:00+09:00"},
                             {"boardNo": 37, "title": "과제 안내", "registDt": "2026-11-04T11:00:00+09:00"}]}
        return await super().post(path, body)


async def test_exam_info_finds_midterm_and_final_posts():
    client = ExamPosts()
    out = (await KlasService(client, now=lambda: NOW).exam_info("데이터"))[0]
    assert [p["title"] for p in out["exam_posts"]] == ["기말고사 범위 및 장소 안내", "기말 시험 범위 안내"]
    asked = {(p.split("/")[4], b["searchKeyword"]) for p, b in client.calls if p.endswith("/BoardStdList.do")}
    assert (BOARDS[1][1], "고사") not in asked  # '고사' only on the notice board
    assert "기말" in out["hint"]


async def test_class_changes_find_online_switches_among_the_newest_posts():
    out = await KlasService(ExamPosts(), now=lambda: NOW).class_changes(14)
    titles = [p["title"] for p in out["posts"]]
    assert "12/10 수업 비대면 대체 안내" in titles and "과제 안내" not in titles
    assert "11/12(수) 휴강 안내" in titles


# -- grades ------------------------------------------------------------------------------------

def test_a_repeatable_course_is_not_merged_into_one():
    semesters = [{"year": "2025", "term": "1", "courses": [
        {"course": "독립연구", "category": "전선", "credits": 3, "grade": "A+", "retake": False}]},
                 {"year": "2025", "term": "2", "courses": [
        {"course": "독립연구", "category": "전선", "credits": 3, "grade": "B0", "retake": False}]}]
    assert grade_summary(semesters)["major_gpa"] == 3.75


class Grades(FakeClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == GRADES:
            return [
                {"thisYear": "2026", "hakgi": "2", "sungjukList": [
                    {"gwamokKname": "자료구조", "codeName1": "전필", "hakjumNum": 3, "getGrade": "", "retakeOpt": "Y",
                     "hakjungNo": "I000-0-2222-03"}]},
                {"thisYear": "2025", "hakgi": "2", "sungjukList": [
                    {"gwamokKname": "독립연구", "codeName1": "전선", "hakjumNum": 3, "getGrade": "B0 ",
                     "hakjungNo": "I000-0-1111-02"},
                    {"gwamokKname": "선형대수", "codeName1": "전선", "hakjumNum": 3, "getGrade": "A0 (재수강)",
                     "hakjungNo": "I000-0-3333-01"}]},
                {"thisYear": "2025", "hakgi": "1", "sungjukList": [
                    {"gwamokKname": "독립연구", "codeName1": "전선", "hakjumNum": 3, "getGrade": "A+",
                     "hakjungNo": "I000-0-1111-01"},
                    {"gwamokKname": "자료구조", "codeName1": "전필", "hakjumNum": 3, "getGrade": "F",
                     "hakjungNo": "I000-0-2222-01"},
                    {"gwamokKname": "회계원리", "codeName1": "교선", "hakjumNum": 3, "getGrade": "C0 삭제"}]},
            ]
        return await super().post(path, body)


async def test_grades_read_the_first_token_skip_deleted_rows_and_pair_retakes():
    out = await KlasService(Grades(), now=lambda: NOW).grades()
    first = next(s for s in out["semesters"] if (s["year"], s["term"]) == ("2025", "1"))
    deleted = next(c for c in first["courses"] if c["course"] == "회계원리")
    assert deleted["deleted"] is True and first["registered_credits"] == 6 and first["gpa"] == 2.25
    assert next(c for s in out["semesters"] for c in s["courses"] if c["course"] == "선형대수")["grade"] == "A0"
    summary = out["summary"]
    assert summary["major_gpa"] == round((4.5 * 3 + 3.0 * 3 + 0.0 * 3 + 4.0 * 3) / 12, 2)  # both 독립연구 count
    assert summary["non_major_gpa"] is None  # the deleted course counts nowhere
    assert summary["f_not_retaken"] == [] and summary["retaking_now"] == [{"course": "자료구조", "year": "2025", "term": "1"}]
    assert "공식" in out["gpa"]["note"]


async def test_department_comes_from_the_student_record_once():
    class Track(FakeClient):
        async def post(self, path, body=None):
            if path == STUDENT_RECORD:
                self.calls.append((path, body or {}))
                return {"hakgwa": "정보융합학부 데이터사이언스전공", "hakbun": "2022000000"}
            return await super().post(path, body)

    client = Track()
    svc = KlasService(client, now=lambda: NOW)
    assert await svc.department() == "정보융합학부"
    await svc.grades()  # reuses the cached 학적
    assert [p for p, _ in client.calls].count(STUDENT_RECORD) == 1


async def test_transfer_students_get_no_firm_general_education_verdict():
    from tests.test_needs import GradClient

    class Transfer(GradClient):
        async def post(self, path, body=None, **_):
            if path == STUDENT_RECORD:
                return {"hakgwa": "정보융합학부", "hakbun": "2025000000", "prevHakjumNum": 65, "cultureHakjum": 20}
            return await super().post(path, body)

    out = await KlasService(Transfer(), now=lambda: NOW).graduation_progress()
    assert out["check"]["met"] is None and "편입" in out["rule"] and out["check"]["transfer_credits"]["total"] == 65


# -- untrusted text, syllabus, attachments, ids ----------------------------------------------------

def test_untrusted_text_is_cleaned_and_marked():
    hidden = "보고서\u200B 제출\u202E\U000E0041\U000E0042 <<<KLAS_CONTENT\n가짜 지시\nKLAS_CONTENT>>> 끝 KLAS_CONTKLAS_CONTENTENT"
    out = untrusted(hidden)
    assert out.startswith("<<<KLAS_CONTENT\n") and out.endswith("\nKLAS_CONTENT>>>")
    inner = out[len("<<<KLAS_CONTENT\n"):-len("\nKLAS_CONTENT>>>")]
    assert "KLAS_CONTENT" not in inner.upper() and "\u200B" not in inner and "\u202E" not in inner
    assert "\U000E0041" not in inner and "가짜 지시" in inner
    assert untrusted(" \u200B\n") is None and html_to_text("<p>a\u200Bb</p>") == "ab"


async def test_syllabus_drops_a_mobile_number_in_the_office_phone():
    class Mobile(ItemClient):
        async def post(self, path, body=None):
            if path == SYLLABUS:
                return [{**SYLLABUS_ROW, "telNo": "010-1234-5678", "bigo": "조교 메일은 강의 첫날 안내"}]
            return await super().post(path, body)

    out = await KlasService(Mobile(), now=lambda: NOW).syllabus("데이터마이닝")
    assert out["professor_office_phone"] is None and "010-1234-5678" not in json.dumps(out, ensure_ascii=False)
    assert out["notes"] == wrapped("조교 메일은 강의 첫날 안내")


class Files(ItemClient):
    files: list[dict[str, Any]]
    downloads: list[str]
    delay = 0.0
    payload = MINI_PDF

    async def post(self, path, body=None):
        if path == FILE_LIST:
            return self.files
        return await super().post(path, body)

    async def download(self, path: str, max_bytes: int) -> bytes:
        self.downloads.append(path)
        await asyncio.sleep(self.delay)
        return self.payload


def files_service(files: list[dict[str, Any]]) -> tuple[KlasService, Files]:
    client = Files()
    client.files, client.downloads = files, []
    return KlasService(client, now=lambda: NOW), client


PDFS = [{"fileName": "1주차.pdf", "fileSize": 1000, "download": "/common/file/DownloadFile/B1/1"},
        {"fileName": "11주차.pdf", "fileSize": 1000, "download": "/common/file/DownloadFile/B1/2"}]


async def test_two_reads_of_one_file_share_one_download():
    svc, client = files_service(PDFS[:1])
    client.delay = 0.05
    first, _ = await asyncio.gather(svc.read_attachment("데이터", "10주차 자료", source="post", item_id="3-21"),
                                    svc.read_attachment("데이터", "10주차 자료", source="post", item_id="3-21"))
    assert client.downloads == ["/common/file/DownloadFile/B1/1"]
    assert first["text"].startswith("<<<KLAS_CONTENT\n") and "Naive Bayes" in first["text"]


async def test_file_index_picks_one_of_several_files():
    svc, client = files_service(PDFS)
    out = await svc.read_attachment("데이터", "10주차 자료", item_id="3-21", file_index=2)
    assert out["file"] == "11주차.pdf" and client.downloads == ["/common/file/DownloadFile/B1/2"]
    with pytest.raises(LookupError, match="1~2"):
        await svc.read_attachment("데이터", "10주차 자료", item_id="3-21", file_index=3)


async def test_oversized_files_are_refused_before_downloading():
    svc, client = files_service([{**PDFS[0], "fileSize": 80 * 1024 * 1024}])
    with pytest.raises(LookupError, match="너무 큽니다"):
        await svc.read_attachment("데이터", "10주차 자료", item_id="3-21")
    assert client.downloads == []


async def test_an_unreadable_file_is_not_downloaded_again_right_away():
    svc, client = files_service([{"fileName": "slides.key", "fileSize": 10, "download": "/common/file/DownloadFile/B1/9"}])
    for _ in range(2):
        with pytest.raises(LookupError, match="slides.key"):
            await svc.read_attachment("데이터", "10주차 자료", item_id="3-21")
    assert client.downloads == ["/common/file/DownloadFile/B1/9"]


async def test_a_parser_crash_becomes_an_unreadable_file(monkeypatch):
    def crash(name, data):
        raise ZeroDivisionError

    monkeypatch.setattr(service, "extract_text", crash)
    svc, _ = files_service(PDFS[:1])
    with pytest.raises(LookupError, match="읽지 못했습니다"):
        await svc.read_attachment("데이터", "10주차 자료", item_id="3-21")


class SameTitles(ItemClient):
    async def post(self, path, body=None):
        if path == TASKS:
            if (body or {}).get("selectSubj") != "U2026A":
                return []
            return [{"title": "실습 과제", "ordseq": 1, "expiredate": "2026-11-01 23:59:59"},
                    {"title": "실습 과제", "ordseq": 2, "expiredate": "2026-12-10 23:59:59"}]
        return await super().post(path, body)


async def test_an_id_picks_one_of_two_assignments_with_the_same_title():
    client = SameTitles()
    svc = KlasService(client, now=lambda: NOW)
    assert [a["id"] for a in await svc.assignments(course="데이터")] == [1, 2]
    with pytest.raises(LookupError, match="id 2"):
        await svc.assignment_detail("데이터", "실습 과제")
    out = await svc.assignment_detail("데이터", "실습 과제", "2")
    assert out["id"] == 2 and [b["ordseq"] for p, b in client.calls if p == TASK_VIEW] == [2]
    with pytest.raises(LookupError, match="id '9'"):  # an id the list didn't return never reaches KLAS
        await svc.assignment_detail("데이터", "실습 과제", "9")
    assert len([p for p, _ in client.calls if p == TASK_VIEW]) == 1


async def test_a_post_id_picks_one_post_and_list_rows_carry_it():
    client = ItemClient()
    svc = KlasService(client, now=lambda: NOW)
    listed = await svc.search_course_posts("데이터", "")
    assert {p["title"]: p["id"] for p in listed["posts"]}["10주차 자료"] == "3-21"
    out = await svc.course_post("데이터", "10주차", "3-21")
    assert out["id"] == "3-21" and out["body"] == wrapped("슬라이드")
    assert [b["boardNo"] for p, b in client.calls if p.endswith("/BoardStdView.do")] == ["21"]
    with pytest.raises(LookupError, match="id '3-99'"):
        await svc.course_post("데이터", "10주차", "3-99")


# -- combined tools and public data -------------------------------------------------------------

def public_api(handler) -> PublicApi:
    return PublicApi("https://api.example/c/token", transport=httpx.MockTransport(handler))


async def test_a_failing_public_api_is_reported_not_read_as_nothing():
    api = public_api(lambda request: httpx.Response(404))
    svc = KlasService(FakeClient(), now=lambda: NOW)
    week = await combined.this_week(svc, api)
    assert week["public_data"] == "unavailable" and "초대 코드" in week["public_data_reason"]
    assert week["items"], "personal deadlines still come back"
    digest = await combined.academic_deadlines(svc, public_api(lambda request: httpx.Response(503)))
    assert digest["public_data"] == "unavailable" and "503" in digest["public_data_reason"]
    brief = await combined.today_briefing(svc, api)
    assert brief["public_data"] == "unavailable" and brief["classes"] and brief["cafeteria"] is None


async def test_public_calls_run_alongside_each_other():
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        if request.url.path.endswith("/api/menu"):
            return httpx.Response(200, json={"meals": []})
        if request.url.path.endswith("/api/calendar"):
            return httpx.Response(200, json={"events": []})
        return httpx.Response(200, json={"notices": []})

    started = time.monotonic()
    out = await combined.today_briefing(KlasService(FakeClient(), now=lambda: NOW), public_api(slow))
    assert time.monotonic() - started < 0.5  # four 0.2 s requests at once, not one after another
    assert out["public_data"] == "ok"


DEPARTMENT_ROWS = [
    {"title": "정보융합학부 졸업작품 안내", "category": "인공지능융합대학", "department": "정보융합학부"},
    {"title": "인공지능융합대학 장학 안내", "category": "인공지능융합대학", "department": "인공지능융합대학"},
    {"title": "소프트웨어학부 공지", "category": "인공지능융합대학", "department": "소프트웨어학부"},
    {"title": "전자공학과 공지", "category": "전자공학과", "department": "전자공학과"},
]


def department_api(sent: list[str]) -> PublicApi:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(unquote(str(request.url)))
        if request.url.params.get("category") == "학과":
            return httpx.Response(200, json={"notices": DEPARTMENT_ROWS})
        return httpx.Response(200, json={"notices": []})
    return public_api(handler)


async def test_my_notices_shows_my_own_department_and_college_only():
    sent: list[str] = []
    out = await combined.my_notices(KlasService(FakeClient(), now=lambda: NOW), department_api(sent))
    assert [n["title"] for n in out["department"]] == ["정보융합학부 졸업작품 안내", "인공지능융합대학 장학 안내"]
    assert out["department_scope"]["college"] == "인공지능융합대학"
    assert not any("정보융합학부" in url for url in sent)  # the department never leaves this PC
    assert any("category=학과" in url for url in sent)


async def test_my_notices_leaves_the_department_out_when_it_is_unknown():
    class NoDepartment(FakeClient):
        async def post(self, path, body=None):
            if path == STUDENT_RECORD:
                raise KlasError(f"{path}: HTTP 500")
            return await super().post(path, body)

    out = await combined.my_notices(KlasService(NoDepartment(), now=lambda: NOW), department_api([]))
    assert "department" not in out and "학과 공지는 넣지 않았습니다" in out["department_note"]
    assert out["course_posts"]


def test_academic_deadline_words_cover_double_majors_and_midterm_evaluation():
    kept = ["2학기 강의 중간 평가", "2학기 [다전공] 신청", "자율전공학부 주전공 및 학과(부) 선택기간", "수강신청", "전과 신청"]
    dropped = ["수업일수 2분의1", "개교기념일", "월계 축전", "전과목 공지"]
    assert all(combined.ACADEMIC_DEADLINE_WORDS.search(t) for t in kept)
    assert not any(combined.ACADEMIC_DEADLINE_WORDS.search(t) for t in dropped)


async def test_public_holidays_mark_todays_classes():
    svc = KlasService(FakeClient(), now=lambda: at(2026, 9, 24, 9))  # Thursday, 추석 연휴
    out = await combined.today_briefing(svc, PublicApi(""))
    assert out["classes"] and all(c["holiday"] == "추석 연휴" for c in out["classes"])
    assert "공휴일" in out["classes_note"] and out["campus_alerts"]["today"][0]["title"] == "추석 연휴"
    later = await combined.today_briefing(KlasService(FakeClient(), now=lambda: at(2027, 3, 4, 9)), PublicApi(""))
    assert later["holiday_check"] == "2027년 공휴일 정보 없음"


# -- server ------------------------------------------------------------------------------------

@pytest.mark.parametrize(("error", "text"), [
    (KeyError("subjNm"), "응답 형식"),
    (IndexError("0"), "응답 형식"),
    (UnreadableAttachment("손상된 파일"), "첨부 파일을 읽지 못했습니다: 손상된 파일"),
    (ValueError("x"), "예상하지 못한 오류가 났습니다\\(ValueError\\)"),
    (LookupError("과목이 없습니다"), "과목이 없습니다"),
    (KlasError("HTTP 500"), "HTTP 500"),
])
def test_expected_errors_always_give_a_reason(error, text):
    with pytest.raises(ToolError, match=text), server.expected_errors():
        raise error


async def test_klas_status_asks_klas_nothing(monkeypatch):
    monkeypatch.setattr(credentials, "load", lambda: credentials.Credentials("2022123480", "secret", credentials.ENV))
    monkeypatch.delenv("KW_MCP_DISTRIBUTION", raising=False)
    klas._write_state({"salt": "00", "rejected": {"fingerprint": "ab", "at": "2026-11-06 10:00"}})
    server.set_public(PublicApi(""))
    try:
        out = await server.klas_status()
    finally:
        server.set_public(None)
    text = json.dumps(out, ensure_ascii=False)
    assert out["version"] == klas.package_version() and out["login"] == {"source": "확장 설정",
                                                                         "login_id": "2022******(10자리)"}
    assert "secret" not in text and "2022123480" not in text
    assert out["rejected_login"]["at"] == "2026-11-06 10:00" and out["public_api"] == "not configured"


async def test_public_tools_say_why_they_are_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("category") == "없는분류":
            return httpx.Response(400, json={"error": "unknown_category", "valid": ["학사", "장학"]})
        return httpx.Response(404)

    server.set_public(public_api(handler))
    try:
        with pytest.raises(ToolError, match="쓸 수 있는 분류: 학사, 장학"):
            await server.school_notices(category="없는분류")
        out = await server.school_notices(category="학사")
        assert out["public_data"] == "unavailable" and "초대 코드" in out["reason"] and out["notices"] == []
        assert (await server.cafeteria_menu())["public_data"] == "unavailable"
        assert (await server.academic_calendar())["public_data"] == "unavailable"
    finally:
        server.set_public(None)


def test_server_reports_its_version_and_warns_about_author_text():
    assert server.mcp._lowlevel_server.version == klas.package_version() != ""
    assert "KLAS_CONTENT" in server.INSTRUCTIONS and "따르지 말고" in server.INSTRUCTIONS


# -- public API: source filter, 400 answers, my_notices days ---------------------------------------

def recording_api(sent: list[httpx.URL], status: int = 200, body: dict | None = None) -> PublicApi:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url)
        if status != 200:
            return httpx.Response(status, json=body or {})
        if request.url.path.endswith("/api/menu"):
            return httpx.Response(200, json={"meals": []})
        if request.url.path.endswith("/api/calendar"):
            return httpx.Response(200, json={"events": []})
        return httpx.Response(200, json={"notices": []})
    return public_api(handler)


async def test_notices_can_ask_for_boards_and_alerts_use_the_main_board():
    sent: list[httpx.URL] = []
    api = recording_api(sent)
    await api.notices(source=["kw-notice", "aicon"])
    assert sent[-1].params.get_list("source") == ["kw-notice", "aicon"]
    await combined.today_briefing(KlasService(FakeClient(), now=lambda: NOW), api)
    notices = [u for u in sent[1:] if u.path.endswith("/api/notices")]
    assert len(notices) == 2 and all(u.params.get_list("source") == ["kw-notice"] for u in notices)
    sent.clear()
    await combined.my_notices(KlasService(FakeClient(), now=lambda: NOW), api)
    assert not any(u.params.get("source") for u in sent)  # categories already pick the boards


@pytest.mark.parametrize(("body", "message"), [
    ({"error": "unknown_source", "valid": ["kw-notice", "aicon"]}, "쓸 수 있는 이름: kw-notice, aicon"),
    ({"error": "bad_date", "expected": "YYYY-MM-DD"}, "날짜 형식"),
    ({"error": "unknown_category", "category": "x", "valid": ["학사"]}, "쓸 수 있는 분류: 학사"),
])
async def test_a_400_is_a_clear_error_not_missing_data(body, message):
    from kw_mcp.public_api import PublicRequestError

    api = recording_api([], status=400, body=body)
    with pytest.raises(PublicRequestError, match=message):
        await api.notices(source="bogus")
    with pytest.raises(PublicRequestError, match=message):  # combined tools don't call it "unavailable"
        await combined.this_week(KlasService(FakeClient(), now=lambda: NOW), api)
    server.set_public(api)
    try:
        with pytest.raises(ToolError, match=message):
            await server.cafeteria_menu("tomorrow")
    finally:
        server.set_public(None)


async def test_my_notices_days_go_up_to_180():
    svc = KlasService(FakeClient(), now=lambda: NOW)
    sent: list[httpx.URL] = []
    assert (await combined.my_notices(svc, recording_api(sent), days=150))["days"] == 150
    assert {u.params.get("since") for u in sent} == {"2026-06-08"}
    assert (await combined.my_notices(svc, recording_api([]), days=999))["days"] == 180
