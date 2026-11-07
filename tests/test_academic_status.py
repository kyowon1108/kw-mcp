"""휴·복학 and 다전공 신청 현황 (get_academic_status), 어학 졸업요건 and the 수강포기 window.

Field names come from the KLAS page templates (checked 2026-11-07); every value here is made up."""

import json
from datetime import datetime
from typing import Any

import httpx
import pytest

from kw_mcp import agent, server
from kw_mcp.klas import LOGIN_FORM, KlasError, KlasLoginError
from kw_mcp.service import (
    COURSE_DROP_PAGE,
    DROP_CREDITS_TERM,
    EVAL_TERM,
    GEN_ED,
    GRADE_TERM,
    GRADE_TOTALS,
    GRADUATION_CHECK,
    KST,
    LANGUAGE_REQUIREMENT,
    LEAVE_STATUS,
    LEAVE_WINDOWS,
    LINKED_APPLIED,
    MAJOR_APPLIED,
    MICRO_APPLIED,
    SCHOLARSHIP_TERM,
    STUDENT_RECORD,
    KlasService,
    leave_window,
    leave_windows,
)
from tests.test_core_klas import Klas, client
from tests.test_klas import keypair  # noqa: F401 (fixture)

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=KST)
# What hakjukMap and the 어학 row carry about me and my advisor: none of it may leave.
ME = {"kname": "홍길동", "hakbun": "2022000000", "jidoName": "김지도", "jidoEmail": "advisor@kw.ac.kr"}


def applied(**row: Any) -> dict[str, Any]:
    return {"stats": True, "returnMsg": "", "hakjukMap": ME, "resultList": [row] if row else []}


class Fake:
    """KLAS answers by path; an exception in `answers` is raised for that path."""

    def __init__(self, **overrides: Any) -> None:
        self.answers: dict[str, Any] = {
            LEAVE_WINDOWS: {"commitStr01": "<b>일반휴학</b><br>(신청불가)",
                            "commentStr01": "신청기간이 아닙니다! <br>기간 : 2027.01.04부터 2027.02.19까지시간 : 09:00~17:00",
                            "commitStr02": "<b>군입휴학</b><br>(신청가능)",
                            "commentStr02": "기간 : 2026.09.01부터 2026.12.31까지"},
            LEAVE_STATUS: {"stats": True, "returnMsg": "", "applyCnt": 1, "hakjukName": "휴학", "hakjukDate": "20260302",
                           "combackDate": "2027.03.02",
                           "statu": [{"gubun": "일반휴학", "applyDate": "20260215", "processName": "승인",
                                      "processDate": "2026.02.20", "bigo": "", "processOpt": "Y", "gubunCode": "1"}]},
            MAJOR_APPLIED: applied(submajor="복수전공", applyDate="20260520", organName="경영대학", className="경영학부",
                                   majorName="경영학전공", dayName="주간", finishOpt="N", submajorOpt="2",
                                   organCode="10", classCode="11", majorCode="12"),
            MICRO_APPLIED: applied(),
            LINKED_APPLIED: applied(submajor="연계전공", applyDate="2026.06.01", organName="인공지능융합대학",
                                    className="연계전공", majorName="빅데이터", finishOpt="Y"),
            LANGUAGE_REQUIREMENT: [{"daesangOpt": "Y", "passOpt": "N", "langName": "TOEIC", "langScore": "700",
                                    "langDate": "20260412", "codeName1": "졸업인증", "dayOpt": "주간",
                                    "graduateDate": None, "경고여부": "N", "졸업여부": "N", **ME}],
            SCHOLARSHIP_TERM: {"stats": False, "janghakApplyTerm": None},
            DROP_CREDITS_TERM: {"stats": "N"},
            GRADE_TERM: {"termMap": None},
            EVAL_TERM: None,
            STUDENT_RECORD: {"hakgwa": "정보융합학부", "grade": 3, "hakjukStatu": "재학", **ME, "hakbun": "2024000000"},
            GEN_ED: {"aa8128": 3},
            GRADE_TOTALS: {"chidukHakjum": 60},
            GRADUATION_CHECK: None,
        }
        self.answers.update(overrides)
        self.drop_page: Any = "<div>수강포기 기간이 아닙니다.</div>"
        self.calls: list[str] = []

    async def post(self, path: str, body: dict[str, Any] | None = None, **_: Any) -> Any:
        self.calls.append(path)
        answer = self.answers.get(path)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    async def page(self, path: str) -> str:
        assert path == COURSE_DROP_PAGE
        if isinstance(self.drop_page, BaseException):
            raise self.drop_page
        return self.drop_page


def svc(fake: Fake) -> KlasService:
    return KlasService(fake, now=lambda: NOW)


def leaks(out: Any) -> list[str]:
    text = json.dumps(out, ensure_ascii=False)
    return [s for s in (*ME, *ME.values(), "hakjukMap", "2024000000") if s in text]


# -- parsing the 휴·복학 칸 ---------------------------------------------------------------------------

def test_a_closed_window_with_its_period_and_time():
    row = leave_window("<b>일반휴학</b><br>(신청불가)",
                       "신청기간이 아닙니다! <br>기간 : 2027.01.04부터 2027.02.19까지시간 : 09:00부터 17:00까지")
    assert row == {"type": "일반휴학", "can_apply": False, "period": {"from": "2027-01-04", "to": "2027-02-19"},
                   "time": "09:00부터 17:00까지", "note": None}


def test_an_open_window_and_one_without_a_mark():
    assert leave_window("<b>군입휴학</b><br>(신청가능)", "기간 : 2026.9.1부터 2026.12.31까지")["can_apply"] is True
    assert leave_window("<b>일반복학</b><br>(신청불가능)", "")["can_apply"] is False  # 불가능 holds 가능
    unmarked = leave_window("<b>월반복학</b>", None)
    assert unmarked == {"type": "월반복학", "can_apply": None, "period": None, "time": None, "note": None}


def test_a_notice_instead_of_a_period_is_wrapped_and_cut():
    long = "입영 일자가 바뀐 경우에만 신청합니다. " * 20
    row = leave_window("<b>군입휴학연기</b><br>(신청불가)", f"<p>{long}</p><p>시간 : 상시</p>")
    assert row["period"] is None and row["time"] is None
    assert row["note"].startswith("<<<KLAS_CONTENT\n입영 일자가") and row["note"].endswith("…\nKLAS_CONTENT>>>")
    assert len(row["note"]) < 200 + 40


@pytest.mark.parametrize("commit, comment", [(None, None), ("", ""), ("<br>", "  ")])
def test_an_empty_pair_is_no_row(commit, comment):
    assert leave_window(commit, comment) is None


def test_odd_dates_and_keys():
    row = leave_window("일반휴학 신청불가", "기간 : 2027.13.40부터 2027.02.19까지")
    assert row["type"] == "일반휴학" and row["can_apply"] is False
    assert row["period"] == {"from": None, "to": "2027-02-19"}  # an impossible date is not guessed
    data = {"commitStr10": "<b>열째</b>", "commitStr02": "<b>둘째</b><br>(신청가능)", "commentStr02": None,
            "commitStr03": "", "commentStr03": "", "commentStr04": "짝 없는 안내", "stats": True}
    assert [r["type"] for r in leave_windows(data)] == ["둘째", "열째"]
    assert leave_windows({}) == []


# -- get_academic_status --------------------------------------------------------------------------

async def test_status_applications_windows_and_majors():
    out = await svc(Fake()).academic_status()
    leave = out["leave"]
    assert leave["status"] == {"state": "휴학", "state_date": "2026-03-02", "return_date": "2027-03-02"}
    assert leave["applications"] == [{"type": "일반휴학", "applied": "2026-02-15", "status": "승인",
                                      "processed": "2026-02-20", "note": None}]
    assert [(w["type"], w["can_apply"]) for w in leave["windows"]] == [("일반휴학", False), ("군입휴학", True)]
    assert leave["windows"][0]["time"] == "09:00~17:00"
    assert out["multi_major"] == [
        {"kind": "복수·부·심화", "track_type": "복수전공", "name": "경영학전공", "college": "경영대학",
         "department": "경영학부", "applied": "2026-05-20", "finished": "N"},
        {"kind": "연계", "track_type": "연계전공", "name": "빅데이터", "college": "인공지능융합대학",
         "department": "연계전공", "applied": "2026-06-01", "finished": "Y"}]
    assert out["note"] == "신청은 KLAS에서 직접 해야 해요."


async def test_multi_major_never_passes_on_hakjuk_map():
    fake = Fake()
    for path in (MAJOR_APPLIED, MICRO_APPLIED, LINKED_APPLIED):
        fake.answers[path]["hakjukMap"] = {**ME, "hakbun": "2024000000", "email": "me@kw.ac.kr"}
    out = await svc(fake).academic_status()
    assert leaks(out) == [] and "me@kw.ac.kr" not in json.dumps(out, ensure_ascii=False)
    assert not any(set(row) - {"kind", "track_type", "name", "college", "department", "applied", "finished"}
                   for row in out["multi_major"])


async def test_a_failing_endpoint_is_unavailable_not_empty():
    fake = Fake(**{LEAVE_STATUS: KlasError("HTTP 500"), MICRO_APPLIED: KlasError("HTTP 500")})
    out = await svc(fake).academic_status()
    assert out["leave"]["status"] == "unavailable" and out["leave"]["applications"] == "unavailable"
    assert out["leave"]["windows"][0]["type"] == "일반휴학"
    assert {"kind": "마이크로", "status": "unavailable"} in out["multi_major"]
    assert [m["kind"] for m in out["multi_major"]] == ["복수·부·심화", "마이크로", "연계"]
    assert "unavailable" in out["note"]
    odd = await svc(Fake(**{LEAVE_WINDOWS: ["not", "a", "dict"]})).academic_status()
    assert odd["leave"]["windows"] == "unavailable"


async def test_every_read_failing_or_a_login_problem_raises():
    down = {p: KlasError("HTTP 500") for p in (LEAVE_WINDOWS, LEAVE_STATUS, MAJOR_APPLIED, MICRO_APPLIED, LINKED_APPLIED)}
    with pytest.raises(KlasError):
        await svc(Fake(**down)).academic_status()
    with pytest.raises(KlasLoginError):
        await svc(Fake(**{MICRO_APPLIED: KlasLoginError("login")})).academic_status()


async def test_the_reads_are_shared_with_explore_multi_major():
    fake = Fake()
    service = svc(fake)
    await service.academic_status()
    assert (await service._majors_applied("복수·부·심화", MAJOR_APPLIED))[0]["name"] == "경영학전공"
    assert fake.calls.count(MAJOR_APPLIED) == 1


async def test_explore_multi_major_mentions_my_applications_without_a_track():
    fake = Fake()
    out = await svc(fake).multi_major_options()
    assert [a["name"] for a in out["my_applications"]] == ["경영학전공", "빅데이터"]
    assert not leaks(out["my_applications"])
    tracked = await svc(Fake()).multi_major_options(track="빅데이터")
    assert "my_applications" not in tracked
    down = Fake(**{p: KlasError("HTTP 500") for p in (MAJOR_APPLIED, MICRO_APPLIED, LINKED_APPLIED)})
    assert "my_applications" not in await svc(down).multi_major_options()  # an extra: never fails the tool


async def test_the_tool_and_the_bridge_op():
    server.set_service(svc(Fake()))
    try:
        result = await server.mcp.call_tool("get_academic_status", {})
    finally:
        server.set_service(None)
    assert not result.is_error and "경영학전공" in json.dumps(result.structured_content, ensure_ascii=False)
    assert agent.CALLS["academic_status"] == ()


# -- 어학 졸업요건 ---------------------------------------------------------------------------------

async def test_language_requirement_passes_the_klas_codes_through():
    out = await svc(Fake()).graduation_progress()
    assert out["language_requirement"] == {"target": "Y", "passed": "N", "test": "TOEIC", "score": "700",
                                           "date": "2026-04-12"}
    assert not leaks(out["language_requirement"])
    assert await svc(Fake(**{LANGUAGE_REQUIREMENT: []})).language_requirement() is None
    failed = await svc(Fake(**{LANGUAGE_REQUIREMENT: KlasError("HTTP 500")})).graduation_progress()
    assert failed["language_requirement"] == "unavailable" and failed["earned_credits"]["total"] == 60


# -- 수강포기 ----------------------------------------------------------------------------------------

async def test_course_drop_closed_unknown_and_error():
    fake = Fake()
    assert (await svc(fake).application_windows())["course_drop"] == {"open": False}
    fake.drop_page = "<p>수강포기&nbsp;기간이\n아닙니다</p>"
    assert (await svc(fake).application_windows())["course_drop"] == {"open": False}
    fake.drop_page = "<table><tr><td>과목</td></tr></table>"
    assert (await svc(fake).application_windows())["course_drop"] == {
        "open": None, "note": "KLAS 수강포기 신청 메뉴에서 확인해 주세요"}
    fake.drop_page = KlasError("HTTP 500")
    out = await svc(fake).application_windows()
    assert "course_drop" not in out and out["incomplete"] == ["course_drop"]
    assert out["drop_earned_credits"] == {"open": False}  # the rest still answers


async def test_page_fetches_only_student_pages_and_logs_in_again_on_a_redirect(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    pages = iter([httpx.Response(302, headers={"location": f"{LOGIN_FORM}?x=1"}),
                  httpx.Response(200, text="<p>수강포기 기간이 아닙니다</p>")])
    fake.data = lambda request: (next(pages) if request.url.path == COURSE_DROP_PAGE
                                 else httpx.Response(200, json=[{"ok": True}]))
    async with client(fake) as c:
        await c.post("/std/lis/evltn/TaskStdList.do")  # a session that later expires
        assert "수강포기" in await c.page(COURSE_DROP_PAGE)
        with pytest.raises(KlasError, match="refusing"):
            await c.page("/common/file/DownloadFile/F1/1")
    assert fake.counts[COURSE_DROP_PAGE] == 2 and fake.counts[LOGIN_FORM] == 2  # logged in again once


async def test_a_login_form_as_the_page_is_an_error_not_another_login(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, text='<form><input name="loginId"><input id="loginPwd"></form>')
    async with client(fake) as c:
        with pytest.raises(KlasError, match="로그인 화면"):
            await c.page(COURSE_DROP_PAGE)
    assert fake.counts[LOGIN_FORM] == 1
