"""Regression tests for the issues an independent review found (2026-11-05)."""

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
import respx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from kw_mcp import agent
from kw_mcp.service import FILE_LIST, HOME, KST, PROJECTS, SEMESTERS, TASK_VIEW, TASKS, KlasService, term_in_session
from tests.test_attachments import MINI_PDF
from tests.test_items import ItemClient

SERVER = "https://bridge.example"
LINK = agent.Link(server=SERVER, ws_url="wss://ws.example/prod", uid="u_old")


def at(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


# --- semester and term windows ----------------------------------------------------------

def test_term_windows_cover_regular_and_winter_terms():
    assert term_in_session("2026,2", at(2026, 11, 5)) and not term_in_session("2026,2", at(2027, 1, 11))
    assert not term_in_session("2026,1", at(2026, 2, 20)) and term_in_session("2026,1", at(2026, 3, 2))
    assert term_in_session("2026,4", at(2027, 1, 11))  # winter term runs into the next year
    assert term_in_session("bogus", at(2027, 1, 1))  # unknown format hides nothing


class SeasonalClient(ItemClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == SEMESTERS:
            return [{"value": "2026,4", "label": "2026 동계"}, {"value": "2026,2", "label": "2026 2학기"}]
        return await super().post(path, body)


async def test_seasonal_registration_does_not_hide_the_running_semester():
    during = KlasService(SeasonalClient(), now=lambda: at(2026, 12, 1))
    assert await during.current_semester() == "2026,2"
    after = KlasService(SeasonalClient(), now=lambda: at(2027, 1, 5))
    assert await after.current_semester() == "2026,4"


# --- names: courses, tasks, files --------------------------------------------------------

TWO_COURSES = [
    {"subj": "U1", "yearhakgi": "2026,2", "subjNm": "자료구조", "profNm": "가"},
    {"subj": "U2", "yearhakgi": "2026,2", "subjNm": "자료구조실습", "profNm": "나"},
]


class NamesClient(ItemClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        body = body or {}
        if path == HOME:
            return {"atnlcSbjectList": TWO_COURSES, "subjNotiList": [
                {"subjNm": "자료구조", "typeNm": "공지", "title": "A&amp;B 안내", "registDt": "2026-11-04T10:00:00+09:00"}]}
        if path == TASKS:
            return [{"title": "과제1", "ordseq": 1 if body["selectSubj"] == "U1" else 2, "expiredate": "2026-11-20 23:59:59"}]
        if path == TASK_VIEW:
            self.calls.append((path, body))
            return {"rpt": {"title": "과제1", "atchFileId": "F", "attachopen": "Y"}, "smt": None}
        if path == FILE_LIST:
            return [{"fileName": "1주차.pdf", "fileSize": 10, "download": "/common/file/DownloadFile/F/1"},
                    {"fileName": "11주차.pdf", "fileSize": 10, "download": "/common/file/DownloadFile/F/2"}]
        return await super().post(path, body)

    downloads: list[str]

    async def download(self, path: str, max_bytes: int) -> bytes:
        self.downloads.append(path)
        return MINI_PDF


def names_service() -> tuple[KlasService, NamesClient]:
    client = NamesClient()
    client.downloads = []
    return KlasService(client, now=lambda: at(2026, 11, 5, 12)), client


async def test_exact_course_name_settles_the_course():
    svc, client = names_service()
    out = await svc.assignment_detail("자료구조", "과제1")
    assert out["course"] == "자료구조"
    assert [b["selectSubj"] for p, b in client.calls if p == TASK_VIEW] == ["U1"]
    assert (await svc.assignment_detail("자료구조 실습", "과제1"))["course"] == "자료구조실습"  # spaces ignored


async def test_exact_file_name_wins_and_text_is_reused_for_later_parts():
    svc, client = names_service()
    first = await svc.read_attachment("자료구조", "과제1", "1주차.pdf", "1", "assignment")
    assert first["file"] == "1주차.pdf" and client.downloads == ["/common/file/DownloadFile/F/1"]
    await svc.read_attachment("자료구조", "과제1", "1주차.pdf", "2", "assignment")
    assert client.downloads == ["/common/file/DownloadFile/F/1"]  # cached, not downloaded again
    with pytest.raises(LookupError, match="post"):
        await svc.read_attachment("자료구조", "과제1", source="assignments")


async def test_home_post_titles_are_plain_text():
    svc, _ = names_service()
    assert (await svc.notices())[0]["title"] == "A&B 안내"


# --- deadlines: team projects in their late window ----------------------------------------

class LateProjectClient(ItemClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == PROJECTS:
            if (body or {}).get("selectSubj") != "U2026A":
                return []
            return [{"title": "팀플", "startdate": "2026-10-01 00:00:00", "expiredate": "2026-11-04 23:59:59",
                     "reexpiredate": "2026-11-07 23:59:59", "submityn": "N", "teamno": 1}]
        return await super().post(path, body)


async def test_team_project_in_late_window_is_listed():
    svc = KlasService(LateProjectClient(), now=lambda: at(2026, 11, 5, 12))
    items = [i for i in (await svc.deadlines(7))["items"] if i["kind"] == "team_project"]
    assert len(items) == 1 and items[0]["late_submission"] is True


# --- agent: always answer, never lose the link on a flaky network ---------------------------

class Boom:
    async def snapshot(self):
        raise ZeroDivisionError


class BoomHolder:
    async def service(self):
        return Boom()


async def test_unexpected_errors_still_answer():
    out = await agent.build_result(BoomHolder())
    assert out["error"] == "klas_error" and "예상하지 못한" in out["message"]


@respx.mock
async def test_too_large_results_are_reported(monkeypatch):
    route = respx.post(f"{SERVER}/device/result").mock(return_value=httpx.Response(202))
    monkeypatch.setattr(agent, "MAX_RESULT_CHARS", 100)

    class Big:
        async def snapshot(self):
            return {"courses": ["x" * 500]}

    class BigHolder:
        async def service(self):
            return Big()

    key = AESGCM.generate_key(bit_length=256)
    message = {"type": "snapshot", "request_id": "r", "key": agent.b64u(key), "result_url": f"{SERVER}/device/result"}
    async with httpx.AsyncClient() as http:
        await agent.answer(BigHolder(), LINK, message, http)
    body = json.loads(route.calls[0].request.content)
    plain = json.loads(AESGCM(key).decrypt(agent.b64u_decode(body["iv"]), agent.b64u_decode(body["ct"]), b"r"))
    assert plain["error"] == "too_large"


def test_linked_to_raises_on_network_errors_and_is_false_when_unknown(monkeypatch):
    monkeypatch.setattr(agent, "load_link", lambda: LINK)

    def offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(agent, "pair_code", offline)
    with pytest.raises(httpx.ConnectError):
        agent.linked_to(SERVER)

    def unknown():
        raise agent.NotLinked("gone")

    monkeypatch.setattr(agent, "pair_code", unknown)
    assert agent.linked_to(SERVER) is False
    assert agent.linked_to("https://other.example") is False


@respx.mock
def test_failed_registration_keeps_the_current_link(monkeypatch):
    respx.post(f"{SERVER}/device/register").mock(return_value=httpx.Response(502))
    touched = []
    monkeypatch.setattr(agent, "_forget_previous_device", lambda: touched.append("forget"))
    monkeypatch.setattr(agent, "save_link", lambda link: touched.append("save"))
    with pytest.raises(httpx.HTTPStatusError):
        agent.register(agent.make_invite(SERVER, "tok"))
    assert touched == []


# --- deadlines: an online-list link to a quiz must not show up twice ------------------------

class QuizLinkClient(ItemClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        from kw_mcp.service import ONLINE, QUIZZES

        subj = (body or {}).get("selectSubj")
        if path == ONLINE and subj == "U2026A":
            # KLAS can list other coursework in the online-content list; this row is the quiz below.
            return [{"evltnSe": "quiz", "sbjt": "11주차 퀴즈", "startDate": "2026-11-05 00:00",
                     "endDate": "2026-11-07 23:59", "prog": 0}]
        if path == QUIZZES and subj == "U2026A":
            return [{"papernm": "11주차 퀴즈", "sdt": "2026-11-05 00:00:00", "edt": "2026-11-07 23:59:00",
                     "issubmit": "N"}]
        if path in (ONLINE, QUIZZES):
            return []
        return await super().post(path, body)


async def test_a_quiz_linked_from_the_online_list_is_listed_once():
    svc = KlasService(QuizLinkClient(), now=lambda: at(2026, 11, 5, 12))
    items = [(i["kind"], i["title"]) for i in (await svc.deadlines(7))["items"] if "퀴즈" in (i["title"] or "")]
    assert items == [("quiz", "11주차 퀴즈")]
