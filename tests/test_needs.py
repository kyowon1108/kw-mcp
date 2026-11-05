"""Attendance, exam info and class changes: what students ask about most (everytime threads)."""

import json
from datetime import datetime
from typing import Any

from kw_mcp.service import ATTENDANCE, BOARDS, KST, SYLLABUS, KlasService, schedule_note
from tests.test_items import SYLLABUS_ROW, ItemClient

NOTICE_ID = BOARDS[0][1]
# Shape of a live KwAttendStdAttendList.do response; weeks not held yet are null.
ATTENDANCE_ROWS = [
    {"weeklyseq": 1, "attendancediv1": "AT", "attendancediv2": "LT", "attendancediv3": None, "attendancediv4": None,
     "attendancedate1": "20260902", "attendancedate2": "20260904", "registId1": "2000000000AB", "registId2": "2000000000AB"},
    {"weeklyseq": 2, "attendancediv1": "AB", "attendancediv2": "OA", "attendancedate1": "20260909",
     "attendancedate2": "20260911", "registId1": "2000000000AB"},
    None,
]
POSTS = [
    {"boardNo": 31, "title": "11/12(수) 휴강 안내", "registDt": "2026-11-04T09:00:00.000+09:00"},
    {"boardNo": 32, "title": "11/19 보강 및 휴강 공지", "registDt": "2026-11-03T09:00:00.000+09:00"},
    {"boardNo": 33, "title": "9월 휴강 안내", "registDt": "2026-09-01T09:00:00.000+09:00"},
    {"boardNo": 34, "title": "기말 시험 범위 안내", "registDt": "2026-11-01T09:00:00.000+09:00"},
]


class NeedsClient(ItemClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        body = body or {}
        if path == ATTENDANCE:
            self.calls.append((path, body))
            return ATTENDANCE_ROWS if body["subj"] == "U2026A" else []
        if path == SYLLABUS:
            self.calls.append((path, body))
            weeks = {"week8Lecture": "중간고사", "week8Bigo": "시험일시 추후 공지", "week15Lecture": "기말고사"}
            return [{**SYLLABUS_ROW, **weeks}] if body["selectSubj"] == "U2026A" else []
        if path.endswith("/BoardStdList.do"):
            self.calls.append((path, body))
            if body["selectSubj"] != "U2026A" or path.split("/")[4] != NOTICE_ID:
                return {"list": [], "page": {"totalElements": 0}}
            word = body["searchKeyword"]
            return {"list": [p for p in POSTS if word in p["title"]], "page": {"totalElements": 1}}
        return await super().post(path, body)


def service() -> tuple[KlasService, NeedsClient]:
    client = NeedsClient()
    return KlasService(client, now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=KST)), client


async def test_attendance_counts_statuses_and_drops_staff_ids():
    svc, client = service()
    data = await svc.attendance("데이터")
    assert len(data) == 1
    out = data[0]
    assert "2000000000" not in json.dumps(out, ensure_ascii=False)
    assert out["summary"] == {"출석": 1, "결석": 1, "지각": 1, "조퇴": 0, "공결": 1} and out["recorded_sessions"] == 4
    assert out["weeks"][0] == {"week": 1, "sessions": [{"session": 1, "status": "출석", "date": "2026-09-02"},
                                                       {"session": 2, "status": "지각", "date": "2026-09-04"}]}
    body = [b for p, b in client.calls if p == ATTENDANCE][0]
    assert body == {"selectYear": "2026", "selectHakgi": "2", "subj": "U2026A"}
    everyone = await svc.attendance()
    assert [c["course"] for c in everyone] == ["데이터마이닝", "확장현실"] and everyone[1]["recorded_sessions"] == 0


async def test_exam_info_combines_syllabus_weeks_and_exam_posts():
    svc, _ = service()
    out = (await svc.exam_info("데이터"))[0]
    assert [w["week"] for w in out["exam_related_weeks"]] == [8, 15]
    assert out["grading_percent"] == {"attendance": 10, "midterm": 30, "final": 40, "assignments": 20}
    assert [p["title"] for p in out["exam_posts"]] == ["기말 시험 범위 안내"]
    other = (await svc.exam_info("확장"))[0]  # no syllabus yet: still answers
    assert other["grading_percent"] is None and other["exam_related_weeks"] == []


async def test_class_changes_lists_recent_posts_once():
    svc, client = service()
    out = await svc.class_changes(14)
    titles = [p["title"] for p in out["posts"]]
    assert titles == ["11/12(수) 휴강 안내", "11/19 보강 및 휴강 공지"]  # september post too old; no duplicate
    assert out["posts"][0]["course"] == "데이터마이닝"
    searched = {(b["selectSubj"], b["searchKeyword"]) for p, b in client.calls if p.endswith("/BoardStdList.do")}
    assert searched == {("U2026A", "휴강"), ("U2026A", "보강"), ("U2026B", "휴강"), ("U2026B", "보강")}


def test_schedule_note_for_unassigned_rooms():
    assert schedule_note("토 18교시/미지정")
    assert schedule_note("") and schedule_note(None)
    assert schedule_note("화 3교시/새빛103") is None
