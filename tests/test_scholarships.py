"""장학 수혜 내역 (JanghakHistoryStdList.do): grouped by term, newest first, amounts summed."""

from datetime import datetime
from zoneinfo import ZoneInfo

from kw_mcp import agent
from kw_mcp.service import SCHOLARSHIP_HISTORY, KlasService


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    async def post(self, path, body=None, **_):
        self.calls.append((path, body))
        return self.answer


def service(answer) -> tuple[KlasService, FakeClient]:
    client = FakeClient(answer)
    return KlasService(client, now=lambda: datetime(2026, 11, 7, tzinfo=ZoneInfo("Asia/Seoul"))), client


async def test_terms_are_grouped_newest_first_with_totals():
    svc, client = service([
        {"yearHakgi": "2026-1", "grade": 3, "janghakName": "성적우수", "janghakAmt": 1_000_000},
        {"yearHakgi": "2026-2", "grade": 3, "janghakName": "성적우수", "janghakAmt": 1_200_000},
        {"yearHakgi": "2026-2", "grade": 3, "janghakName": "총동문회장학금", "janghakAmt": 500_000},
        {"yearHakgi": "2025-4", "grade": 2, "janghakName": "\u200b근로장학", "janghakAmt": "300000"},
    ])
    out = await svc.scholarships()
    assert client.calls == [(SCHOLARSHIP_HISTORY, {})]
    assert [t["semester"] for t in out["terms"]] == ["2026,2", "2026,1", "2025,4"]
    newest = out["terms"][0]
    assert newest["label"] == "2026학년도 2학기" and newest["total"] == 1_700_000 and newest["year_level"] == 3
    assert [s["name"] for s in newest["scholarships"]] == ["성적우수", "총동문회장학금"]
    assert out["terms"][2]["label"] == "2025학년도 겨울학기" and out["terms"][2]["scholarships"][0]["name"] == "근로장학"
    assert out["total_amount"] == 3_000_000 and "학생복지팀" in out["note"]


async def test_no_scholarships_is_an_empty_list_not_an_error():
    for empty in ([], None):
        svc, _ = service(empty)
        out = await svc.scholarships()
        assert out["terms"] == [] and out["total_amount"] == 0


def test_the_agent_can_answer_it():
    assert agent.CALLS["scholarships"] == () and hasattr(KlasService, "scholarships")
