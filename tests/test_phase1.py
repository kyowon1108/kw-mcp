"""Online exams, surveys, discussions, partial deadlines, course evaluation, grade periods, standing
and the academic-deadline digest. Field names come from the live KLAS pages (2026-11-06); values
are made up."""

from datetime import datetime
from typing import Any

import pytest
import respx

from kw_mcp import agent, combined
from kw_mcp.klas import BASE_URL, KlasClient, KlasError, KlasLoginError
from kw_mcp.service import (
    DISCUSSIONS,
    DROP_CREDITS_TERM,
    EVAL_COURSES,
    EVAL_TERM,
    GRADE_TERM,
    KST,
    ONLINE_TESTS,
    SCHOLARSHIP_TERM,
    SURVEYS,
    KlasService,
    grade_summary,
    is_lecture,
    parse_due,
)
from tests.test_klas import HOME, keypair, mock_login  # noqa: F401 (fixture)
from tests.test_service import FakeClient

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=KST)


class Phase1Client(FakeClient):
    term: Any = None
    fail: frozenset[str] = frozenset()

    async def post(self, path: str, body: dict[str, Any] | None = None, **_: Any) -> Any:
        if path in self.fail:
            raise KlasError(f"{path}: HTTP 500")
        subj = (body or {}).get("selectSubj")
        if path == ONLINE_TESTS:
            self.calls.append((path, body or {}))
            if subj != "U2026A":
                return []
            return [
                {"papernm": "중간 대체 시험", "examtypenm": "온라인시험", "sdt": "2026-11-06 09:00:00",
                 "edt": "2026-11-06 10:00:00", "issubmit": "N", "isretry": "N", "weeklyseq": 9},
                {"papernm": "2주차 시험", "examtypenm": "온라인시험", "sdt": "2026-10-01 09:00:00",
                 "edt": "2026-10-01 10:00:00", "issubmit": "Y", "isretry": "Y", "isresubmit": "N",
                 "rsdt": "2026-11-05 00:00:00", "redt": "2026-11-08 23:59:00", "weeklyseq": 2},
                {"papernm": "1주차 시험", "examtypenm": "온라인시험", "sdt": "2026-09-10 09:00:00",
                 "edt": "2026-09-10 10:00:00", "issubmit": "Y", "isretry": "N", "weeklyseq": 1},
            ]
        if path == SURVEYS:
            self.calls.append((path, body or {}))
            if subj != "U2026B":
                return []
            return [{"sulpapernm": "중간 강의 설문 ", "sulstart": "2026-11-01", "sulend": "2026-11-07", "appcnt": 0},
                    {"sulpapernm": "첫 주 설문", "sulstart": "2026-09-01", "sulend": "2026-11-30", "appcnt": 1}]
        if path == DISCUSSIONS:
            self.calls.append((path, body or {}))
            if subj != "U2026A":
                return []
            return [{"tpcode": 1, "title": "윤리 토론", "started": "2026-11-01 00:00:00", "ended": "2026-11-09 23:59:59",
                     "toroncnt": 4},
                    {"tpcode": 2, "title": "다음 주 토론", "started": "2026-11-10 00:00:00",
                     "ended": "2026-11-11 23:59:59", "toroncnt": 0}]
        if path == EVAL_TERM:
            return self.term
        if path == EVAL_COURSES:
            self.calls.append((path, body or {}))
            return [{"gwamokKname": "데이터마이닝", "judgeOpt": "N"}, {"gwamokKname": "확장현실", "judgeOpt": "Y"}]
        if path == SCHOLARSHIP_TERM:
            return {"stats": True, "returnMsg": "장학 신청 기간입니다", "janghakApplyTerm": {
                "fromDate": "2026.11.01", "toDate": "2026.11.15", "fromTime": "09:00:00", "toTime": "18:00:00"}}
        if path == DROP_CREDITS_TERM:
            return {"stats": "N", "returnMsg": "취득학점포기 신청 기간이 아닙니다"}
        return await super().post(path, body)


def service(client: Phase1Client | None = None, now: datetime = NOW) -> tuple[KlasService, Phase1Client]:
    client = client or Phase1Client()
    return KlasService(client, now=lambda: now), client


def test_due_times_mean_what_klas_shows():
    assert parse_due("2026-11-08 23:59").second == 59  # open through 23:59:59
    assert parse_due("2026-11-08 23:59:00").second == 0
    assert parse_due("2026-11-07").strftime("%H:%M:%S") == "23:59:59"  # survey end dates
    assert parse_due("2026.11.07").day == 7 and parse_due(None) is None


def test_only_watchable_lessons_count_as_lectures():
    assert is_lecture({"evltnSe": "lesson", "isonoff": "ON"}) and is_lecture({})
    assert not is_lecture({"evltnSe": "proj"}) and not is_lecture({"evltnSe": "lesson", "isonoff": "OFF"})
    assert not is_lecture({"evltnSe": "survey"})  # unknown kinds aren't lectures either


async def test_online_tests_keep_open_retries_pending():
    svc, _ = service()
    pending = await svc.online_tests(pending_only=True)
    assert [t["title"] for t in pending] == ["2주차 시험", "중간 대체 시험"]  # taken but retry open; not taken
    retry = pending[0]["retry"]
    assert retry == {"opens": "2026-11-05 00:00", "due": "2026-11-08 23:59", "submitted": False}


async def test_deadlines_add_tests_surveys_and_discussions():
    svc, _ = service()
    due = await svc.deadlines(days=7)
    kinds = [(d["kind"], d["title"]) for d in due["items"]]
    assert ("online_test", "중간 대체 시험") in kinds and ("online_test", "2주차 시험") in kinds
    assert ("survey", "중간 강의 설문") in kinds and ("survey", "첫 주 설문") not in kinds  # answered
    assert ("discussion", "윤리 토론") in kinds and ("discussion", "다음 주 토론") not in kinds  # not open yet
    retry = next(d for d in due["items"] if d["title"] == "2주차 시험")
    assert retry["effective_due"] == "2026-11-08 23:59"
    survey = next(d for d in due["items"] if d["kind"] == "survey")
    assert survey["due"] == "2026-11-07 23:59"
    assert "incomplete" not in due


async def test_one_unreadable_list_leaves_the_rest():
    client = Phase1Client()
    client.fail = frozenset({SURVEYS})
    svc, _ = service(client)
    due = await svc.deadlines(days=7)
    assert due["incomplete"]["missing"] == ["survey"]
    assert any(d["kind"] == "assignment" for d in due["items"])


async def test_login_trouble_is_not_hidden_as_a_partial_answer():
    class LoginFails(Phase1Client):
        async def post(self, path, body=None, **_):
            if path == SURVEYS:
                raise KlasLoginError("캡차")
            return await super().post(path, body)

    svc, _ = service(LoginFails())
    with pytest.raises(KlasLoginError):
        await svc.deadlines(days=7)


async def test_course_evaluation_window():
    svc, client = service()
    assert (await svc.course_evaluation())["open"] is False  # empty body outside the window
    client.term = {"judgeChasu": "last"}
    out = await svc.course_evaluation()
    assert out["open"] is True and out["round"] == "기말" and out["not_evaluated"] == ["데이터마이닝"]
    assert [b for p, b in client.calls if p == EVAL_COURSES][-1]["judgeChasu"] == "last"
    client.term = [{"judgeChasu": "middle"}, {"judgeChasu": "last"}]
    assert (await svc.course_evaluation())["open"] is None


async def test_grade_viewing_period_status():
    class Period(Phase1Client):
        async def post(self, path, body=None, **_):
            if path == GRADE_TERM:
                assert body == {"thisYear": "2026", "hakgi": "2"}
                return {"nowMap": {}, "termMap": {"fromDate": "20261221", "toDate": "20261228",
                                                  "fromTime": "100000", "toTime": "235959"}}
            return await super().post(path, body)

    before, _ = service(Period())
    assert (await before.grade_period()) == {"status": "before", "from": "2026-12-21 10:00", "to": "2026-12-28 23:59"}
    during, _ = service(Period(), now=datetime(2026, 12, 22, tzinfo=KST))
    assert (await during.grade_period())["status"] == "open"


async def test_application_windows_and_academic_digest():
    svc, _ = service()
    windows = await svc.application_windows()
    assert windows["scholarship_application"] == {"open": True, "from": "2026-11-01 09:00", "to": "2026-11-15 18:00"}
    assert windows["drop_earned_credits"]["open"] is False
    assert windows["course_evaluation"]["open"] is False and windows["grade_viewing"]["status"] == "not_set"

    class Calendar:
        configured = True

        async def calendar(self, start, end):
            assert (start, end) == ("2026-11-05", "2026-12-05")
            return [{"start": "2026-11-20", "end": "2026-11-26", "title": "2학기 수업평가"},
                    {"start": "2026-11-11", "end": "2026-11-11", "title": "개교기념일"},
                    {"start": "2026-12-01", "end": "2026-12-03", "title": "동계 계절학기 수강신청"}]

    digest = await combined.academic_deadlines(svc, Calendar(), 30)
    assert [e["title"] for e in digest["calendar"]] == ["2학기 수업평가", "동계 계절학기 수강신청"]
    assert digest["klas"]["scholarship_application"]["open"] is True


def test_grade_summary_counts_a_retake_once():
    semesters = [
        {"year": "2025", "term": "1", "courses": [
            {"course": "자료구조", "category": "전필", "credits": 3, "grade": "F"},
            {"course": "글쓰기", "category": "교필", "credits": 2, "grade": "B0"},
            {"course": "확률", "category": "전선", "credits": 3, "grade": "F"}]},
        {"year": "2025", "term": "2", "courses": [
            {"course": "자료구조", "category": "전필", "credits": 3, "grade": "A0"},
            {"course": "체육", "category": "교선", "credits": 1, "grade": "P"}]},
    ]
    out = grade_summary(semesters)
    assert out["major_gpa"] == round((3 * 4.0 + 3 * 0.0) / 6, 2)  # retaken 자료구조 counts as A0
    assert out["non_major_gpa"] == 3.0 and out["gpa_excluding_f"] == round((3 * 4.0 + 2 * 3.0) / 5, 2)
    assert out["f_not_retaken"] == [{"course": "확률", "year": "2025", "term": "1", "category": "전선"}]


async def test_an_empty_body_means_nothing_only_where_allowed(keypair):  # noqa: F811
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL) as router:
        mock_login(router, public_b64)
        router.post(EVAL_TERM).respond(200, content=b"")
        router.post(HOME).respond(200, content=b"")
        async with KlasClient("id", "pw") as client:
            assert await client.post(EVAL_TERM, None, allow_empty=True) is None
            with pytest.raises(KlasError, match="not JSON"):  # elsewhere it must not read as "nothing due"
                await client.post(HOME)


def test_impossible_dates_are_skipped_not_fatal():
    assert parse_due("0000-00-00") is None and parse_due("2026-02-30") is None
    assert is_lecture({"evltnSe": ""}) and not is_lecture({"evltnSe": "quiz"})


async def test_a_missed_test_with_a_retry_window_is_listed():
    class Missed(Phase1Client):
        async def post(self, path, body=None, **_):
            if path == ONLINE_TESTS:
                if (body or {}).get("selectSubj") != "U2026A":
                    return []
                return [{"papernm": "놓친 시험", "sdt": "2026-10-01 09:00:00", "edt": "2026-10-01 10:00:00",
                         "issubmit": "N", "isretry": "Y", "isresubmit": "N",
                         "rsdt": "2026-11-05 00:00:00", "redt": "2026-11-07 23:59:00"}]
            return await super().post(path, body)

    svc, _ = service(Missed())
    due = await svc.deadlines(days=7)
    assert [d["effective_due"] for d in due["items"] if d["kind"] == "online_test"] == ["2026-11-07 23:59"]


def test_grade_summary_orders_terms_itself():
    newest_first = [
        {"year": "2025", "term": "2", "courses": [{"course": "확률", "category": "전선", "credits": 3, "grade": "B0"}]},
        {"year": "2025", "term": "3", "courses": [{"course": "확률", "category": "전선", "credits": 3, "grade": "F"}]},
    ]
    out = grade_summary(newest_first)  # summer F, then retaken in the fall
    assert out["f_not_retaken"] == [] and out["major_gpa"] == 3.0


async def test_briefing_uses_the_retry_due_and_passes_incomplete_on():
    client = Phase1Client()
    client.fail = frozenset({SURVEYS})
    svc, _ = service(client, now=datetime(2026, 11, 7, 12, 0, tzinfo=KST))

    class NoPublic:
        configured = False

        async def notices(self, **kw):
            return []

        async def menu(self, day):
            return None

    out = await combined.today_briefing(svc, NoPublic())
    titles = [i["title"] for i in out["due_today_or_tomorrow"]]
    assert "2주차 시험" in titles  # retry due 11-08 23:59 is tomorrow
    assert out["deadlines_incomplete"]["missing"] == ["survey"]


async def test_bridge_can_ask_the_agent_for_the_new_reads():
    svc, _ = service()

    class Holder:
        async def service(self):
            return svc

    out = await agent.build_result(Holder(), "deadlines", {"days": "7"})
    assert out["result"]["days"] == 7 and any(i["kind"] == "online_test" for i in out["result"]["items"])
    for op in ("online_tests", "surveys", "discussions", "course_evaluation", "application_windows"):
        assert "result" in await agent.build_result(Holder(), op, {})
