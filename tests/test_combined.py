from datetime import datetime

import httpx
import pytest

from kw_mcp import combined
from kw_mcp.public_api import PublicApi
from kw_mcp.service import KST, KlasService, parse_schedule

from .test_service import FakeClient


def test_parse_schedule_real_klas_format():
    assert parse_schedule("화 3교시/새빛103, 목 4교시/새빛103") == [
        {"weekday": "화", "periods": [3], "room": "새빛103"},
        {"weekday": "목", "periods": [4], "room": "새빛103"},
    ]
    assert parse_schedule("월 5,6,7교시/새빛103") == [{"weekday": "월", "periods": [5, 6, 7], "room": "새빛103"}]
    assert parse_schedule("") == [] and parse_schedule(None) == []


class FakePublic:
    """Records what the public API was asked for, to prove no personal data is sent."""

    def __init__(self):
        self.requests = []

    def transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(str(request.url))
            if request.url.path.endswith("/api/menu"):
                return httpx.Response(200, json={"date": "2026-11-05", "weekday": "목요일",
                                                 "meals": [{"name": "함지마루 자율중식", "menu": ["백미밥"]}]})
            if request.url.path.endswith("/api/calendar"):
                return httpx.Response(200, json={"events": [{"start": "2026-11-18", "end": "2026-11-20",
                                                             "title": "동계 계절수업 수강신청"}]})
            return httpx.Response(200, json={"notices": [{"title": "국가장학금 안내", "category": "등록/장학"}]})
        return httpx.MockTransport(handler)


@pytest.fixture
def svc():
    return KlasService(FakeClient(), now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=KST))  # Thursday


async def test_today_briefing_joins_on_device(svc):
    fake = FakePublic()
    api = PublicApi("https://api.example/c/token", transport=fake.transport())
    out = await combined.today_briefing(svc, api)
    assert out["weekday"] == "목"
    assert out["classes"] == [{"course": "데이터마이닝", "periods": [3], "room": "새빛101", "professor": "김교수"}]
    assert [d["title"] for d in out["due_today_or_tomorrow"]] == ["3주차 퀴즈"]
    assert out["cafeteria"]["meals"][0]["name"] == "함지마루 자율중식"
    assert out["new_school_notices"][0]["title"] == "국가장학금 안내"
    # Only generic filters left this machine: no course names, titles, or student data.
    sent = " ".join(fake.requests)
    assert "데이터마이닝" not in sent and "퀴즈" not in sent and "U2026A" not in sent


async def test_this_week_adds_calendar_and_degrades_without_public_api(svc):
    out = await combined.this_week(svc, PublicApi("https://api.example/c/token", transport=FakePublic().transport()))
    assert out["academic_events"][0]["title"] == "동계 계절수업 수강신청"
    offline = await combined.this_week(svc, PublicApi(""))
    assert offline["academic_events"] == [] and "설정되지 않아" in offline["public_data"]
    assert offline["items"], "personal deadlines still work without the public API"


async def test_my_notices(svc):
    out = await combined.my_notices(svc, PublicApi("https://api.example/c/token", transport=FakePublic().transport()), days=7)
    assert out["course_posts"][0]["title"] == "10주차 자료"
    assert out["school_scholarship"][0]["title"] == "국가장학금 안내"
