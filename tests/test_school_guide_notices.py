"""school_guide adds the newest related notices (knowledge/notice_links.json) from the public API:
open deadlines first, else the last 90 days; never failing the knowledge answer. Made-up notices only."""

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from kw_mcp import knowledge, server
from kw_mcp.public_api import PublicApi
from kw_mcp.service import KST

TODAY = datetime.now(KST).date()


def row(post_id: str, title: str, posted: str, deadline: str | None = None, **facts: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"post_id": post_id, "title": title, "category": "등록/장학", "posted_date": posted,
                           "url": f"https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID={post_id}"}
    if deadline:
        out["deadline"] = {"kind": "신청마감", "at": deadline, "text": "신청 마감"}
        out["extracted"] = {"deadlines": [out["deadline"]], "target": facts.get("target", ""),
                            "how_to_apply": facts.get("how_to_apply", ""), "summary": ""}
    return out


class FakeApi:
    """The public notice API: open notices when asked for open_only, recent ones otherwise."""

    def __init__(self, open_rows: list[dict[str, Any]], recent_rows: list[dict[str, Any]], fail: bool = False) -> None:
        self.open_rows, self.recent_rows, self.fail = open_rows, recent_rows, fail
        self.requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        if self.fail:
            return httpx.Response(500)
        rows = self.open_rows if params.get("open_only") == "true" else self.recent_rows
        return httpx.Response(200, json={"notices": rows})


@pytest.fixture
def api(monkeypatch):
    def install(fake: FakeApi) -> FakeApi:
        server.set_public(PublicApi("https://bridge.example/c/token", transport=httpx.MockTransport(fake)))
        return fake

    yield install
    server.set_public(None)


SOON = (TODAY + timedelta(days=5)).isoformat()
LATER = (TODAY + timedelta(days=20)).isoformat()
PAST = (TODAY - timedelta(days=3)).isoformat()


async def test_open_notices_come_with_their_extracted_facts(api):
    fake = api(FakeApi(open_rows=[
        row("2", "2027-1 국가장학금 2차 신청", TODAY.isoformat(), f"{LATER} 18:00", target="재학생"),
        row("1", "교내 장학 신청", PAST, f"{SOON} 17:00", target="2~4학년", how_to_apply="KLAS 장학 신청"),
        row("3", "지난 장학 안내", PAST, f"{PAST} 17:00"),  # deadline passed: a server ignoring open_only
    ], recent_rows=[]))
    out = await server.school_guide("국가장학금 신청 언제야?", category="장학")
    assert out["answers"]  # the knowledge answer is still there
    assert [n["title"] for n in out["recent_notices"]] == ["교내 장학 신청", "2027-1 국가장학금 2차 신청"]  # soonest first
    first = out["recent_notices"][0]
    assert first == {"title": "교내 장학 신청", "posted": PAST, "url": first["url"], "deadline": f"{SOON} 17:00",
                     "target": "2~4학년", "how_to_apply": "KLAS 장학 신청"}
    assert out["recent_notices_note"] == knowledge.NOTICES_NOTE
    assert fake.requests == [{"category": "장학", "limit": "5", "pinned": "true", "open_only": "true"}]


async def test_without_open_deadlines_the_newest_of_90_days(api):
    fake = api(FakeApi(open_rows=[], recent_rows=[
        row("5", "휴학 신청 안내", PAST), row("6", "복학 신청 안내", TODAY.isoformat()),
        row("7", "군휴학 안내", (TODAY - timedelta(days=30)).isoformat())]))
    out = await server.school_guide("휴학하려면 어떻게 해?", category="학적변동")
    assert [n["title"] for n in out["recent_notices"]] == ["복학 신청 안내", "휴학 신청 안내", "군휴학 안내"]
    since = (TODAY - timedelta(days=90)).isoformat()
    assert {r["q"] for r in fake.requests} == {"휴학", "복학"}
    assert [r.get("since") for r in fake.requests if "open_only" not in r] == [since, since]


async def test_a_failing_api_leaves_the_knowledge_answer(api):
    api(FakeApi([], [], fail=True))
    out = await server.school_guide("국장 언제야?", category="장학")
    assert out["answers"] and out["recent_notices"] == "unavailable" and "recent_notices_note" not in out


async def test_a_category_without_links_or_an_api_adds_nothing(api):
    fake = api(FakeApi([row("1", "공지", PAST, f"{SOON} 17:00")], []))
    out = await server.school_guide("도서관 몇 시까지 해?", category="도서관")
    assert "recent_notices" not in out and fake.requests == []
    server.set_public(PublicApi(url=""))  # no public API configured
    out = await server.school_guide("국장 언제야?", category="장학")
    assert "recent_notices" not in out


async def test_nothing_recent_is_an_empty_list():
    server.set_public(PublicApi("https://bridge.example/c/token",
                                transport=httpx.MockTransport(FakeApi([], []))))
    try:
        out = await server.school_guide("계절학기 언제 신청해?", category="계절학기")
    finally:
        server.set_public(None)
    assert out["recent_notices"] == [] and "recent_notices_note" not in out


def test_notice_links_name_knowledge_categories():
    from kw_mcp import datasync

    links = __import__("json").loads(datasync.read(knowledge.NOTICE_LINKS, datasync.snapshot()))["links"]
    assert set(links) <= set(knowledge.categories())
    assert all(q.get("category") or q.get("q") for queries in links.values() for q in queries)
    assert knowledge.notice_queries("다전공") == [{"q": "다전공"}, {"q": "복수전공"}, {"q": "부전공"}, {"q": "마이크로"}]
    assert knowledge.notice_queries("학점교류·교환학생") == [{"category": "국제", "q": "교환"}]
    assert knowledge.notice_queries("도서관") == [] and knowledge.notice_queries(None) == []


def test_the_same_notice_found_twice_counts_once():
    rows = [row("1", "다전공 신청 안내", PAST, f"{SOON} 17:00"), row("1", "다전공 신청 안내", PAST, f"{SOON} 17:00")]
    assert len(knowledge.pick_notices(rows, TODAY)) == 1
    assert knowledge.pick_notices([row("2", "지난 공지", PAST)], TODAY, open_only=True) == []
