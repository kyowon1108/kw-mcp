"""The Everytime-question eval (evals/): offline only. The fixture builds and shapes through the real
KlasService, tools dispatch through the real MCP server, the agent loop runs on a scripted API, and
the judge's output parsing survives malformed text. No Claude API, KLAS, keychain or network."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from evals import harness, judge, llm, run
from evals.fixture import FIXTURE, build_service
from evals.fixtures import build_student
from kw_mcp import notices
from kw_mcp import server as srv


class FakeLedger:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, Any, str]] = []

    def record(self, pipeline, model, usage, note=""):
        self.rows.append((pipeline, model, usage, note))
        return 0.0

    def remaining(self, budget, pipeline):
        return 30.0

    def spent(self, pipeline=None):
        return 0.0

    def cost(self, model, usage):
        return 0.0


@pytest.fixture
def no_api(monkeypatch):
    ledger = FakeLedger()
    monkeypatch.setattr(llm, "ledger", lambda: ledger)
    monkeypatch.setattr(llm, "client", lambda: pytest.fail("tests must not build an API client"))
    return ledger


@pytest.fixture
async def toolset(monkeypatch):
    """The eval toolset with the public API unconfigured and no school-site budget. Server globals,
    the notice pacer and the environment are put back afterwards."""
    monkeypatch.setattr(srv, "_service", None)
    monkeypatch.setattr(srv, "_public", None)
    monkeypatch.setattr(notices, "PACER", notices.PACER)
    for name in ("KW_MCP_DISTRIBUTION", "KW_CAMPUS_INVITE", "KLAS_ID", "KLAS_PASSWORD"):
        monkeypatch.delenv(name, raising=False)  # isolate() drops them; this puts them back afterwards
    tools = await harness.build_toolset(None, live=False, provisional=("scholarships", "rules"))
    yield tools
    await tools.public.aclose()


# --- fixture ----------------------------------------------------------------------------------------

def test_fixture_file_is_what_the_builder_writes():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == json.loads(json.dumps(build_student.build(), ensure_ascii=False))


async def test_fixture_runs_through_the_real_shaping_code():
    svc, client = build_service()
    due = await svc.deadlines(7)
    titles = {(i["course"], i.get("title")) for i in due["items"]}
    assert ("데이터베이스", "과제 2: 도서관 대출 시스템 ERD 설계") in titles
    assert not due.get("incomplete")
    late = [i for i in due["items"] if i.get("late_submission")]
    assert [i["course"] for i in late] == ["운영체제"]
    attendance = {a["course"]: a["summary"] for a in await svc.attendance(None)}
    assert attendance["운영체제"]["결석"] == 2 and attendance["확률과통계"]["결석"] == 3
    grades = await svc.grades()
    assert [f["course"] for f in grades["summary"]["f_not_retaken"]] == ["일반물리학2"]
    assert (await svc.department()) == "정보융합학부"
    assert client.calls and all(not path.startswith("http") for path, _ in client.calls)


async def test_fixture_attachments_are_readable():
    svc, _ = build_service()
    out = await svc.read_attachment("머신러닝", "10주차", "", "1", "post", None, None)
    assert out["kind"] == "PowerPoint" and "엔트로피" in out["text"]


# --- tools ------------------------------------------------------------------------------------------

async def test_tools_come_from_the_server_plus_provisional_ones(toolset):
    names = [d["name"] for d in toolset.definitions]
    for name in ("this_week", "get_deadlines", "get_class_changes", "school_notices", "read_school_notice"):
        assert name in names
    assert set(toolset.meta["provisional_tools"]) <= set(names)
    assert len(names) == len(set(names))
    assert all(d["input_schema"].get("type") == "object" for d in toolset.definitions)
    assert set(toolset.fingerprints()) == set(names)


async def test_personal_tools_dispatch_to_the_fixture(toolset):
    result = await toolset.call("get_class_changes", {"days": 14})
    assert not result.is_error and "휴강" in result.text()
    post = await toolset.call("get_course_post", {"course": "운영체제", "title": "휴강"})
    assert "11월 24일" in post.text()


async def test_combined_tool_without_public_api_still_answers(toolset):
    result = await toolset.call("this_week", {})
    data = json.loads(result.text())
    assert not result.is_error and data["items"]


async def test_errors_come_back_as_tool_errors(toolset):
    unknown = await toolset.call("no_such_tool", {})
    assert unknown.is_error
    if "school_rules" in toolset.extras:  # offered until the server registers its own rules tool
        bad_topic = await toolset.call("school_rules", {"topic": "nope"})
        assert bad_topic.is_error and "graduation" in bad_topic.text()
    off_list = await toolset.call("read_school_notice", {"url": "https://example.com/x"})
    assert off_list.is_error and not off_list.site_cap_hit


async def test_school_site_gate_refuses_before_any_request(toolset):
    result = await toolset.call("read_school_notice", {"url": "https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=1"})
    assert result.is_error and result.site_cap_hit


async def test_klas_status_never_reads_the_keychain(toolset):
    result = await toolset.call("klas_status", {})
    assert not result.is_error and json.loads(result.text())["login"]["source"] == "확장 설정"


async def test_rules_view_filters_and_cites_sources():
    out = harness._rules_view("multi_major", "복수전공 상호인정")
    assert out["items"] and out["sources"]
    assert all("복수전공" in json.dumps(i, ensure_ascii=False) for i in out["items"])
    assert "sections" in harness._rules_view("graduation", None)


# --- agent loop on a scripted API -----------------------------------------------------------------

def _usage(**kw):
    return SimpleNamespace(input_tokens=kw.get("i", 10), output_tokens=kw.get("o", 5), cache_read_input_tokens=0,
                           cache_creation_input_tokens=0)


class ScriptedApi:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.messages = self

    async def create(self, **params):
        self.requests.append(params)
        return self.responses.pop(0)


def _response(content, stop_reason, model=llm.MODEL):
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=_usage(), model=model)


async def test_agent_loop_runs_tools_and_returns_the_answer(toolset, no_api):
    api = ScriptedApi([
        _response([SimpleNamespace(type="tool_use", id="t1", name="get_class_changes", input={"days": 14})], "tool_use"),
        _response([SimpleNamespace(type="text", text="11/10 휴강, 보강은 11/24 18:00")], "end_turn"),
    ])
    out = await harness.answer(api, toolset, "운영체제 화요일 휴강임?", case_id="t")
    assert out["status"] == "ok" and "휴강" in out["answer"]
    assert [c["name"] for c in out["tool_calls"]] == ["get_class_changes"]
    assert [t["role"] for t in out["trace"]] == ["system", "user", "tool_call", "tool_result", "assistant"]
    first = api.requests[0]
    assert first["output_config"] == {"effort": "medium"} and "temperature" not in first and "tool_choice" not in first
    assert "budget_tokens" not in json.dumps(first.get("thinking"))
    tool_turn = api.requests[1]["messages"][2]["content"][0]  # user q, assistant tool_use, user tool_result
    assert tool_turn["type"] == "tool_result" and tool_turn["tool_use_id"] == "t1"
    assert len(no_api.rows) == 2 and out["usage"]["input_tokens"] == 20


async def test_agent_loop_marks_truncation_and_wrong_model(toolset, no_api):
    api = ScriptedApi([_response([SimpleNamespace(type="text", text="잘린")], "max_tokens")])
    assert (await harness.answer(api, toolset, "q"))["status"] == "truncated"
    api = ScriptedApi([_response([SimpleNamespace(type="text", text="x")], "end_turn", model="claude-other")])
    with pytest.raises(llm.ModelMismatch):
        await harness.answer(api, toolset, "q")
    assert len(no_api.rows) == 2  # the mismatched response is still billed and recorded


async def test_budget_check_stops_before_calling(monkeypatch, no_api):
    monkeypatch.setattr(no_api, "remaining", lambda budget, pipeline: 0.4)
    with pytest.raises(llm.BudgetExhausted):
        await llm.create(ScriptedApi([]), note="x", max_tokens=10, messages=[])


# --- judge parsing ----------------------------------------------------------------------------------

GOOD = {"scores": {c: {"score": 2, "reason": "ok"} for c in judge.CRITERIA}, "must_include": [{"item": "a", "met": True}],
        "must_not_violations": [], "capability_missing": False, "missing_what": "", "model_misused_tools": False,
        "misuse_what": "", "primary_gap": "none", "fix": "", "summary": "좋음"}


def test_parse_verdict_reads_plain_fenced_and_wrapped_json():
    text = json.dumps(GOOD, ensure_ascii=False)
    for raw in (text, f"```json\n{text}\n```", f"채점 결과입니다.\n{text}\n끝."):
        v = judge.parse_verdict(raw)
        assert not v["parse_error"] and judge.total(v) == 1.0 and not judge.failing(v)


@pytest.mark.parametrize("raw", ["", "모르겠어요", "{not json", "[1, 2, 3]", '{"scores": "high"}'])
def test_unreadable_judge_output_is_a_parse_error_not_a_zero(raw):
    v = judge.parse_verdict(raw)
    assert v["parse_error"] and judge.total(v) is None and judge.failing(v)


def test_parse_verdict_normalizes_odd_values():
    odd = json.loads(json.dumps(GOOD))
    odd["scores"]["correct"] = {"score": "1", "reason": "부분"}
    odd["scores"]["sourced"] = {"score": 7}
    odd["scores"]["scope"] = 0
    odd["primary_gap"] = "who-knows"
    odd["must_include"] = ["not a dict", {"item": "b", "met": 0}]
    v = judge.parse_verdict(json.dumps(odd))
    assert v["scores"]["correct"] == 1 and v["scores"]["sourced"] == 2 and v["scores"]["scope"] == 0
    assert v["primary_gap"] == "other" and v["must_include"] == [{"item": "b", "met": False}]
    assert judge.failing(v)  # a criterion at 0 fails the case


def test_missing_criterion_and_boolean_scores_are_parse_errors():
    partial = json.loads(json.dumps(GOOD))
    del partial["scores"]["honest"]
    v = judge.parse_verdict(json.dumps(partial))
    assert v["parse_error"] and v["missing_criteria"] == ["honest"]
    boolean = json.loads(json.dumps(GOOD))
    boolean["scores"]["correct"] = {"score": True}
    assert judge.parse_verdict(json.dumps(boolean))["parse_error"]


def test_failing_rules():
    v = judge.parse_verdict(json.dumps(GOOD))
    assert not judge.failing(v)
    assert judge.failing({**v, "must_not_violations": ["날짜 추측"]})
    assert judge.failing({**v, "primary_gap": "missing_tool"})


def test_judge_trace_is_cut_for_the_judge_only():
    trace = [{"role": "tool_call", "name": "x", "content": "{}"},
             {"role": "tool_result", "content": "가" * 5000, "is_error": False}]
    text = judge.render_trace(trace, budget=10_000, per_result=100)
    assert "채점용 생략" in text and len(text) < 400
    assert judge.render_trace([]) == "(도구를 쓰지 않음)"


# --- round 2 selection ------------------------------------------------------------------------------

def test_round2_reruns_failures_and_changed_categories():
    questions = [{"id": "a1", "category": "장학", "expected_tools": ["get_scholarships"]},
                 {"id": "a2", "category": "장학", "expected_tools": []},
                 {"id": "b1", "category": "학식", "expected_tools": ["cafeteria_menu"]},
                 {"id": "c1", "category": "출석", "expected_tools": ["get_attendance"]}]
    ok = {"failing": False, "tools_used": [], "verdict": {"primary_gap": "none"}}
    prev = {"a1": ok, "a2": ok, "b1": {**ok, "failing": True}, "c1": ok}
    old = {"get_scholarships": "1", "cafeteria_menu": "2", "get_attendance": "3"}
    new = {"get_scholarships": "9", "cafeteria_menu": "2", "get_attendance": "3"}
    ids, why = run.select_round2(questions, prev, {"tool_fingerprints": old}, new)
    assert ids == ["b1", "a1", "a2"] and why["changed_categories"] == ["장학"]
    ids, why = run.select_round2(questions, prev, {"tool_fingerprints": old}, old)
    assert ids == ["b1"] and not why["changed_tools"]


def test_round2_new_tool_reopens_categories_that_lacked_one():
    questions = [{"id": "d1", "category": "휴학·복학", "expected_tools": []},
                 {"id": "e1", "category": "학식", "expected_tools": ["cafeteria_menu"]}]
    prev = {"d1": {"failing": False, "tools_used": [], "verdict": {"primary_gap": "missing_data"}},
            "e1": {"failing": False, "tools_used": ["cafeteria_menu"], "verdict": {"primary_gap": "none"}}}
    ids, why = run.select_round2(questions, prev, {"tool_fingerprints": {"cafeteria_menu": "1"}},
                                 {"cafeteria_menu": "1", "school_knowledge": "2"})
    assert ids == ["d1"] and why["new_tools"] == ["school_knowledge"]


def test_questions_file_is_well_formed():
    rows = run.load_questions()
    if not rows:
        pytest.skip("questions.jsonl not generated yet")
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["category"] in run.CATEGORIES and r["needs"] in ("personal", "public", "both")
        assert r["question"].strip() and isinstance(r["must_include"], list) and isinstance(r["must_not"], list)
