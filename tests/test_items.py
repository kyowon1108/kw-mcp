import json
from datetime import datetime
from typing import Any

import pytest

from kw_mcp.service import BOARDS, FILE_LIST, KST, SYLLABUS, TASK_VIEW, KlasService
from kw_mcp.text import html_to_text
from tests.test_service import FakeClient

# Field names from live TaskStdView.do / LectrePlanData.do responses; values made up.
TASK_VIEW_RESPONSE = {
    "rpt": {"title": "HW3", "contents": "<p>Naive Bayes&nbsp;구현</p><ul><li>코드</li><li>보고서</li></ul>",
            "submitfiletype": "PDF", "filelimit": "20", "reptype": "P", "submityn": "Y", "indate": "N",
            "adddate": "N", "isopenscore": "N", "attachopen": "Y", "atchFileId": "F1", "ordseq": 3},
    "smt": {"registDt": "2026-11-06T14:00:00.000+00:00", "finalscore": 9, "tutordate": "2026-11-08",
            "tutorcontents": "<p>잘했음</p>", "projid": "2022000000AB", "name": "홍길동", "userNm": "홍길동",
            "hakgwanm": "컴퓨터정보공학부"},
}
SYLLABUS_ROW = {
    "gwamokKname": "데이터마이닝", "codeName1": "전선", "hakjumNum": 3, "memberName": "김교수",
    "jikgeubName": "교수", "email": "prof@kw.ac.kr", "telNo": "02-000-0000", "hpNo": "010-0000-0000",
    "jogyoName": "조교", "jogyoEmail": "ta@kw.ac.kr", "summary": "데이터에서 패턴을 찾는다.\n",
    "purpose": "분류·군집", "week1Lecture": "소개", "week2Lecture": "결정트리", "week2Bigo": "실습",
    "attendBiyul": 10, "middleBiyul": 30, "lastBiyul": 40, "reportBiyul": 20, "quizBiyul": None,
    "bookName": "Data Mining", "writeName": "Han", "companyName": "MK", "printYear": "2022",
}


NOTICE_ID, MATERIALS_ID = BOARDS[0][1], BOARDS[1][1]
BOARD_LISTS = {
    NOTICE_ID: [{"boardNo": 11, "masterNo": 1, "title": "휴강 안내", "userNm": "김교수", "registerId": "2000000000AB"}],
    MATERIALS_ID: [{"boardNo": 21, "masterNo": 3, "title": "<b>10주차</b> 자료"},
                   {"boardNo": 22, "masterNo": 3, "title": "10주차 자료 (수정)"}],
}
POSTS = {
    "11": {"title": "휴강 안내", "content": "<p>11/12 휴강</p>", "registDt": "2026-11-05T09:00:00.000+09:00",
           "updtDt": None, "atchFileId": None, "userNm": "김교수", "registerId": "2000000000AB", "registerIp": "10.0.0.1"},
    "21": {"title": "<b>10주차</b> 자료", "content": "<p>슬라이드</p>", "registDt": "2026-11-04T13:00:00.000+09:00",
           "atchFileId": "B1", "userNm": "김교수"},
}


class ItemClient(FakeClient):
    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path.endswith("/BoardStdList.do"):
            self.calls.append((path, body or {}))
            rows = BOARD_LISTS[path.split("/")[4]]
            key = (body or {}).get("searchKeyword", "")
            return {"list": [r for r in rows if key in r["title"].replace("<b>", "").replace("</b>", "")],
                    "page": {"totalElements": len(rows)}}
        if path.endswith("/BoardStdView.do"):
            self.calls.append((path, body or {}))
            assert body and body["masterNo"] in ("1", "3")
            return {"board": POSTS.get(body["boardNo"])}
        if path == TASK_VIEW:
            self.calls.append((path, body or {}))
            return TASK_VIEW_RESPONSE
        if path == FILE_LIST:
            self.calls.append((path, body or {}))
            return [{"fileName": "hw3.pdf", "fileSize": 204800, "download": "/common/file/DownloadFile/F1/1"}]
        if path == SYLLABUS:
            self.calls.append((path, body or {}))
            return [SYLLABUS_ROW]
        return await super().post(path, body)


def service() -> tuple[KlasService, ItemClient]:
    client = ItemClient()
    return KlasService(client, now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=KST)), client


async def test_assignment_detail_reads_one_task_and_leaves_out_my_identity():
    svc, client = service()
    out = await svc.assignment_detail("데이터", "HW3")
    text = json.dumps(out, ensure_ascii=False)
    assert "2022000000" not in text and "홍길동" not in text and "컴퓨터정보공학부" not in text
    assert out["instructions"] == "Naive Bayes 구현\n\n- 코드\n- 보고서"
    assert out["attachments"] == [{"name": "hw3.pdf", "size_kb": 200}] and "download" not in text
    assert out["due"] == "2026-11-07 23:59" and out["submit_format"] == "PDF" and out["file_limit_mb"] == 20
    sub = out["my_submission"]
    assert sub["score"] is None and sub["score_status"] == "비공개" and sub["feedback"] == "잘했음"
    view = [b for p, b in client.calls if p == TASK_VIEW][0]
    assert view["selectSubj"] == "U2026A" and view["selectYearhakgi"] == "2026,2"


async def test_assignment_detail_asks_for_a_clearer_title():
    svc, _ = service()
    with pytest.raises(LookupError, match="여러 개"):
        await svc.assignment_detail("데이터", "HW")
    with pytest.raises(LookupError, match="없습니다"):
        await svc.assignment_detail("데이터", "기말 보고서")


async def test_syllabus_keeps_course_content_and_work_contact_only():
    svc, client = service()
    out = await svc.syllabus("데이터마이닝")
    text = json.dumps(out, ensure_ascii=False)
    assert "010-0000-0000" not in text and "ta@kw.ac.kr" not in text and "조교" not in text
    assert out["professor_email"] == "prof@kw.ac.kr" and out["overview"] == "데이터에서 패턴을 찾는다."
    assert out["weekly_plan"] == [{"week": 1, "topic": "소개", "note": None},
                                  {"week": 2, "topic": "결정트리", "note": "실습"}]
    assert out["grading_percent"] == {"attendance": 10, "midterm": 30, "final": 40, "assignments": 20}
    assert out["textbooks"] == [{"title": "Data Mining", "author": "Han", "publisher": "MK", "year": "2022"}]
    assert [b for p, b in client.calls if p == SYLLABUS] == [{"selectSubj": "U2026A"}]


async def test_syllabus_needs_one_course():
    svc, _ = service()
    with pytest.raises(LookupError, match="하나로"):
        await svc.syllabus("")


def test_html_to_text():
    assert html_to_text("<div>a<br>b</div><table><tr><td>x</td><td>y</td></tr></table>") == "a\nb\n\n| x | y"
    assert html_to_text("<script>alert(1)</script><p>&lt;ok&gt;</p>") == "<ok>"
    assert html_to_text("<p>" + "가" * 50 + "</p>", limit=10).endswith("…(이하 생략)")
    assert html_to_text(None) == ""


async def test_course_post_opens_one_post_without_author_details():
    svc, client = service()
    out = await svc.course_post("데이터", "휴강")
    text = json.dumps(out, ensure_ascii=False)
    assert "김교수" not in text and "2000000000" not in text and "10.0.0.1" not in text
    assert out == {"course": "데이터마이닝", "board": "강의 공지사항", "title": "휴강 안내", "posted": "2026-11-05 09:00",
                   "updated": None, "body": "11/12 휴강", "attachments": []}
    lists = [b for p, b in client.calls if p.endswith("/BoardStdList.do")]
    assert len(lists) == 2 and lists[0]["searchCondition"] == "TLE" and lists[0]["searchKeyword"] == "휴강"


async def test_course_post_prefers_the_exact_title_and_lists_attachments():
    svc, _ = service()
    out = await svc.course_post("데이터", "10주차 자료")
    assert out["board"] == "강의 자료실" and out["body"] == "슬라이드"
    assert out["attachments"] == [{"name": "hw3.pdf", "size_kb": 200}]
    with pytest.raises(LookupError, match="여러 개"):
        await svc.course_post("데이터", "10주차")
    with pytest.raises(LookupError, match="찾지 못했습니다"):
        await svc.course_post("데이터", "기말고사")


async def test_search_course_posts_covers_both_boards_newest_first():
    svc, client = service()
    out = await svc.search_course_posts("데이터", "")
    assert out["course"] == "데이터마이닝" and out["keyword"] is None
    assert [(p["board"], p["title"]) for p in out["posts"]] == [
        ("강의 공지사항", "휴강 안내"), ("강의 자료실", "10주차 자료"), ("강의 자료실", "10주차 자료 (수정)")]
    assert "김교수" not in json.dumps(out, ensure_ascii=False)
    lists = [b for p, b in client.calls if p.endswith("/BoardStdList.do")]
    assert {b["searchCondition"] for b in lists} == {"ALL"} and len(lists) == 2
    hit = await svc.search_course_posts("데이터", "휴강")
    assert [p["title"] for p in hit["posts"]] == ["휴강 안내"]
