import json
from datetime import datetime
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from kw_mcp import server
from kw_mcp.service import (
    GRADE_TOTALS,
    GRADES,
    HOME,
    KST,
    ONLINE,
    PROJECTS,
    QUIZZES,
    SEMESTERS,
    TASKS,
    KlasService,
    fmt_kst,
)

# Field names and value formats below were copied from live KLAS responses (values made up).
COURSES = [
    {"subj": "U2026A", "yearhakgi": "2026,2", "subjNm": "데이터마이닝", "profNm": "김교수",
     "lctrumSchdulInfo": "목 3교시/새빛101, 화 3교시/새빛101", "subjLabel": "데이터마이닝 (I000-0-0000-01)"},
    {"subj": "U2026B", "yearhakgi": "2026,2", "subjNm": "확장현실", "profNm": "이교수",
     "lctrumSchdulInfo": "수 5,6교시/새빛205", "subjLabel": "확장현실 (I000-0-0000-02)"},
]
TASK_ROWS = {
    "U2026A": [
        {"title": "HW3", "startdate": "2026-11-02 00:00:00", "expiredate": "2026-11-07 23:59:59",
         "reexpiredate": None, "submityn": "N", "score": None},
        {"title": "HW2", "startdate": "2026-10-01 00:00:00", "expiredate": "2026-10-10 23:59:59",
         "reexpiredate": None, "submityn": "Y", "score": "10"},
        {"title": "HW4", "startdate": "2026-11-10 00:00:00", "expiredate": "2026-11-20 12:00:59",
         "reexpiredate": "2026-11-22 12:00:59", "submityn": "N", "score": None},
    ],
    "U2026B": [],
}
ONLINE_ROWS = {
    "U2026A": [
        {"weekNo": 10, "moduletitle": "10주차", "sbjt": "결정트리", "startDate": "2026-11-03 00:00",
         "endDate": "2026-11-09 23:59", "prog": 40, "rcognTime": "45", "achivTime": "18"},
        {"weekNo": 1, "moduletitle": "1주차", "sbjt": "소개", "startDate": "2026-09-04 00:00",
         "endDate": "2026-09-17 23:59", "prog": 100, "rcognTime": "45", "achivTime": "45"},
        {"evltnSe": "proj", "sbjt": "HW4", "startDate": "2026-11-10 00:00", "endDate": "2026-11-20 12:00",
         "prog": None},
    ],
    "U2026B": [],
}


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        body = body or {}
        self.calls.append((path, body))
        if path == SEMESTERS:
            return [{"value": "2026,2", "label": "2026년도 2학기",
                     "subjList": [{"value": "U2026A", "label": "x", "name": "데이터마이닝"}]}]
        if path == HOME:
            return {"yearhakgi": "2026학년도 2학기", "atnlcSbjectList": COURSES,
                    "subjNotiList": [{"subjNm": "데이터마이닝", "typeNm": "강의 자료실", "title": "10주차 자료",
                                      "registDt": "2026-11-04T13:04:40.000+00:00"}]}
        if path == TASKS:
            return TASK_ROWS[body["selectSubj"]]
        if path == ONLINE:
            return ONLINE_ROWS[body["selectSubj"]]
        if path == PROJECTS:
            if body["selectSubj"] != "U2026A":
                return []
            # Field names from a live PrjctStdList row; studentName/hakbun are hypothetical extras.
            return [{"title": "팀 프로젝트 1", "purpose": "중간 발표", "startdate": "2026-10-01 00:00:00",
                     "expiredate": "2026-11-12 23:59:59", "reexpiredate": None, "submityn": "N",
                     "score": None, "teamno": 3, "teamseq": 1, "ordseq": 1, "isopen": "Y",
                     "studentName": "홍길동", "hakbun": "2022000000"}]
        if path == QUIZZES:
            if body["selectSubj"] != "U2026A":
                return []
            # Field names from a live AnytmQuizStdList row (values made up).
            return [{"papernm": "3주차 퀴즈", "examtypenm": "온라인", "sdt": "2026-11-03 00:00:00",
                     "edt": "2026-11-06 18:00:00", "issubmit": "N", "examtime": "20", "examcnt": 5,
                     "totalscore": 10, "subj": "U2026A"},
                    {"papernm": "2주차 퀴즈", "examtypenm": "온라인", "sdt": "2026-10-20 00:00:00",
                     "edt": "2026-10-23 18:00:00", "issubmit": "Y", "examtime": "20", "examcnt": 5,
                     "totalscore": 10, "subj": "U2026A"}]
        if path == GRADES:
            return [{"thisYear": "2026", "hakgi": "1", "sungjukList": [
                {"gwamokKname": "회귀분석", "codeName1": "전선", "hakjumNum": 3, "getGrade": "A+", "retakeOpt": "N"}]}]
        if path == GRADE_TOTALS:
            return {"chidukHakjum": 99}
        raise AssertionError(f"unexpected path {path}")


@pytest.fixture
def svc():
    return KlasService(FakeClient(), now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=KST))


def test_fmt_kst_handles_klas_formats():
    assert fmt_kst("2026-11-20 12:00:59") == "2026-11-20 12:00"
    assert fmt_kst("2026-09-17 23:59") == "2026-09-17 23:59"
    assert fmt_kst("2026-11-04T13:04:40.000+00:00") == "2026-11-04 22:04"  # UTC -> KST
    assert fmt_kst(None) is None


async def test_assignments_use_course_codes_and_sort_by_due(svc):
    rows = await svc.assignments()
    assert [r["title"] for r in rows] == ["HW2", "HW3", "HW4"]
    task_bodies = [b for p, b in svc._client.calls if p == TASKS]
    assert {"selectChangeYn": "Y", "selectSubj": "U2026A", "selectYearhakgi": "2026,2"} in task_bodies

    pending = await svc.assignments(course="데이터", pending_only=True)
    assert [r["title"] for r in pending] == ["HW3", "HW4"]
    assert pending[1]["late_due"] == "2026-11-22 12:00"


async def test_unknown_course_lists_choices(svc):
    with pytest.raises(LookupError, match="데이터마이닝, 확장현실"):
        await svc.assignments(course="없는과목")


async def test_deadlines_window(svc):
    due = await svc.deadlines(days=7)
    assert due["semester"] == "2026,2"
    assert [(d["kind"], d["title"]) for d in due["items"]] == [
        ("quiz", "3주차 퀴즈"),
        ("assignment", "HW3"),
        ("online_lecture", "결정트리"),
    ]


async def test_deadlines_include_team_projects_in_range(svc):
    due = await svc.deadlines(days=8)
    assert ("team_project", "팀 프로젝트 1") in [(d["kind"], d["title"]) for d in due["items"]]


async def test_quizzes_whitelist_and_pending_filter(svc):
    rows = await svc.quizzes(pending_only=True)
    assert rows == [{"course": "데이터마이닝", "title": "3주차 퀴즈", "type": "온라인", "opens": "2026-11-03 00:00",
                     "due": "2026-11-06 18:00", "submitted": False, "time_limit_minutes": 20,
                     "questions": 5, "total_score": 10}]


async def test_deadlines_include_late_submission_window():
    # 11/21: HW4 is past its due (11/20 12:00) but still inside late_due (11/22 12:00).
    svc = KlasService(FakeClient(), now=lambda: datetime(2026, 11, 21, 9, 0, tzinfo=KST))
    due = await svc.deadlines(days=1)
    assert [(d["title"], d.get("late_submission")) for d in due["items"]] == [("HW4", True)]


async def test_online_lectures_skip_project_links(svc):
    assert [o["title"] for o in await svc.online_lectures()] == ["소개", "결정트리"]


async def test_deadlines_clamps_days(svc):
    assert (await svc.deadlines(days=10**10))["days"] == 180


async def test_parallel_tools_share_requests(svc):
    await svc.deadlines()
    calls = [p for p, _ in svc._client.calls]
    assert calls.count(SEMESTERS) == 1
    assert calls.count(HOME) == 1
    assert calls.count(TASKS) == len(COURSES)


async def test_home_is_cached(svc):
    await svc.courses()
    await svc.notices()
    assert sum(1 for p, _ in svc._client.calls if p == HOME) == 1
    assert sum(1 for p, _ in svc._client.calls if p == SEMESTERS) == 1


async def test_notices_and_grades(svc):
    notices = await svc.notices(course="데이터")
    assert notices == [{"course": "데이터마이닝", "board": "강의 자료실", "title": "10주차 자료", "posted": "2026-11-04 22:04"}]

    grades = await svc.grades()
    assert grades["semesters"][0]["courses"][0] == {
        "course": "회귀분석", "category": "전선", "credits": 3, "grade": "A+", "retake": "N"}
    assert grades["credit_totals"] == {"chidukHakjum": 99}


async def test_mcp_tools_are_registered_and_callable(svc):
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert set(tools) == {
        "list_semesters", "get_courses", "get_assignments", "get_online_lectures",
        "get_team_projects", "get_course_notices", "get_deadlines", "get_grades", "get_quizzes",
        "get_assignment_detail", "get_syllabus", "get_course_post", "search_course_posts",
        "this_week", "today_briefing", "my_notices", "school_notices", "cafeteria_menu", "academic_calendar",
    }
    assert all(t.annotations.read_only_hint for t in tools.values())

    server.set_service(svc)
    try:
        result = await server.mcp.call_tool("get_deadlines", {"days": 7})
    finally:
        server.set_service(None)
    assert not result.is_error
    text = "".join(c.text for c in result.content if c.type == "text")
    assert '"semester"' in text
    assert "HW3" in text and "결정트리" in text
    assert json.dumps(result.structured_content, ensure_ascii=False).count("HW3") >= 1


async def test_missing_credentials_reach_the_model(monkeypatch):
    def missing():
        raise server.credentials.MissingCredentials("kw-mcp setup을 실행하세요")

    monkeypatch.setattr(server.credentials, "load", missing)
    server.set_service(None)
    with pytest.raises(ToolError, match="kw-mcp setup"):
        await server.mcp.call_tool("get_courses", {})


async def test_unknown_course_reaches_the_model(svc):
    server.set_service(svc)
    try:
        with pytest.raises(ToolError, match="데이터마이닝"):
            await server.mcp.call_tool("get_assignments", {"course": "없는과목"})
    finally:
        server.set_service(None)


async def test_projects_only_return_whitelisted_fields(svc):
    rows = await svc.projects()
    assert rows == [{
        "course": "데이터마이닝", "title": "팀 프로젝트 1", "purpose": "중간 발표",
        "opens": "2026-10-01 00:00", "due": "2026-11-12 23:59", "late_due": None,
        "submitted": False, "score": None, "team_no": 3,
    }]
    assert "홍길동" not in str(rows) and "2022000000" not in str(rows)
