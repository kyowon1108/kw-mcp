"""The shipped knowledge base: every entry well-formed and sourced, no personal names, search finds the
right entry for casual student questions, curricula and annex tables load."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from kw_mcp import knowledge

DATA = Path(knowledge.__file__).with_name("knowledge")
CATEGORIES = {"수강신청", "재수강·성적", "계절학기", "수업·출석", "학적변동", "졸업", "다전공", "전과·전공배정",
              "학점교류·교환학생", "장학", "등록·등록금", "증명서·학생증", "기숙사", "셔틀·교통", "도서관",
              "학식·편의시설", "병무·예비군", "IT·계정", "상담·학생지원", "진로·취업", "동아리·학생자치", "기타"}
ENTRIES = knowledge.load()["entries"]


def test_loads_and_has_enough_entries():
    kb = knowledge.load()
    assert kb["version"]["built_at"]
    assert 150 <= len(ENTRIES) <= 400
    assert len({e["id"] for e in ENTRIES}) == len(ENTRIES)


@pytest.mark.parametrize("e", ENTRIES, ids=[e["id"] for e in ENTRIES])
def test_entry_schema(e):
    assert re.fullmatch(r"[a-z]+-[a-z0-9-]+", e["id"])
    assert e["category"] in CATEGORIES
    assert 3 <= len(e["questions"]) <= 6 and all(isinstance(q, str) and q.strip() for q in e["questions"])
    assert isinstance(e["answer"], str) and len(e["answer"]) >= 10
    assert isinstance(e["conditions_exceptions"], list)
    assert isinstance(e["how_to"], str)
    assert set(e["contact_office"]) == {"name", "phone"}
    assert e["confidence"] in {"high", "medium", "low"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["last_verified"])
    assert isinstance(e["applies_to"], str) and e["applies_to"]
    assert e["disagreement"] is None or isinstance(e["disagreement"], str)
    for s in e["sources"]:
        assert {"title", "url", "regulation", "article", "effective_date", "checked_at"} <= set(s)


@pytest.mark.parametrize("e", ENTRIES, ids=[e["id"] for e in ENTRIES])
def test_every_entry_has_a_source_url(e):
    assert e["sources"]
    # https everywhere, except the library's seat page, which the school serves over plain http only
    assert all(s["url"].startswith(("https://", "http://mobileid.kw.ac.kr/seatweb/")) for s in e["sources"])
    # never KLAS; Daple only as the cited planner (facts came from the owner's snapshot, never fetched here)
    assert not any("klas.kw.ac.kr" in s["url"] for s in e["sources"])
    assert all(s["url"] == "https://daple.kwuniv.com" for s in e["sources"] if "daple" in s["url"])
    if any("daple" in s["url"] for s in e["sources"]):
        assert any("daple" not in s["url"] for s in e["sources"]), "Daple next to the official sources, not alone"


def test_quotes_are_short_and_at_most_one_per_entry():
    for e in ENTRIES:
        quotes = [s["quote"] for s in e["sources"] if s.get("quote")]
        assert len(quotes) <= 1, e["id"]
        assert all(len(q.split()) < 15 for q in quotes), e["id"]


PERSON = [
    re.compile(r"(?<![가-힣])[가-힣]{2,3}\s?(교수님|선생님|팀장님|과장님)"),  # a 2-3 syllable name before a title
    re.compile(r"(담당자|담당)\s?[:：]\s?[가-힣]{2,4}"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # e-mail addresses point at people
]


def test_no_personal_name_patterns():
    for e in ENTRIES:
        text = json.dumps({k: e[k] for k in ("questions", "answer", "conditions_exceptions", "how_to",
                                             "contact_office", "applies_to", "disagreement")}, ensure_ascii=False)
        for pat in PERSON:
            assert not pat.search(text), (e["id"], pat.search(text).group(0))


def test_disagreements_lower_confidence():
    for e in ENTRIES:
        if e["disagreement"]:
            assert e["confidence"] in {"medium", "low"}, e["id"]


@pytest.mark.parametrize("query, category, word", [
    ("재수강하면 성적 몇까지 나옴?", "재수강·성적", "재수강"),
    ("계절학기 최대 몇 학점까지 들을 수 있어?", "계절학기", "학점"),
    ("휴학 최대 몇 학기까지 가능함?", "학적변동", "휴학"),
    ("자퇴하려면 어떻게 해야 돼", "학적변동", "자퇴"),
    ("복전 신청 언제 하나요", "다전공", "복수전공"),
    ("마이크로전공 몇 학점 들어야 돼?", "다전공", "마이크로"),
    ("조기졸업 조건이 뭐야", "졸업", "조기졸업"),
    ("졸업유예 하면 등록금 내야 함?", "졸업", "졸업"),
    ("수강신청 최대 학점 몇이야", "수강신청", "학점"),
    ("국장 신청 언제야", "장학", "장학"),
    ("긱사 신청 어떻게 해", "기숙사", "기숙사"),
    ("재학증명서 인터넷으로 뽑을 수 있어?", "증명서·학생증", "증명"),
    ("전과 하려면 평점 몇 돼야 해", "전과·전공배정", "전과"),
    ("교환학생 지원 자격", "학점교류·교환학생", "교환"),
    ("유고결석 며칠까지 인정돼?", "수업·출석", "결석"),
    ("폐강 기준 몇 명이야", "수강신청", "폐강"),
    ("자율전공 전공 언제 정함", "전과·전공배정", "자율전공"),
    ("장학금 중복으로 받을 수 있어?", "장학", "중복"),
    ("셔틀 몇시까지 다녀", "셔틀·교통", "셔틀"),
    ("도서관 몇시까지 열어", "도서관", "도서관"),
    ("휴학하면 국가장학금 토해내야 돼?", "장학", "국가장학금"),
    ("공결 서류 어디에 내?", "수업·출석", "공결"),
    ("소프트웨어학부 과사 전화번호 뭐야", "기타", "소프트웨어학부"),
    ("열람실 남은 자리 어디서 봐?", "도서관", "좌석"),
    ("군대 제대하고 복학하려면 뭐 내야 돼", "학적변동", "복학"),
    ("오피스 365 학생도 공짜로 써?", "IT·계정", "Office 365"),
    ("해외에서 클라스 로그인 2차 인증", "IT·계정", "2차 인증"),
    ("취업 상담 예약 어떻게 해?", "진로·취업", "상담"),
    ("채용공고 어디서 봐? 인스타?", "진로·취업", "인스타그램"),
    ("동아리 가입하려면 어떻게 해", "동아리·학생자치", "동아리"),
    ("성희롱 상담 어디서 받아?", "상담·학생지원", "성희롱"),
    ("풋살장 예약 어떻게 해?", "학식·편의시설", "풋살"),
    ("선수과목 안 들었는데 후수과목 들어도 돼?", "수강신청", "선수"),
    ("졸업하려면 토익 필요해?", "졸업", "토익"),
    # round 6: Everytime gaps (docs/campus-sites/gaps-2026-11-07.md)
    ("총동문회 장학금 어떻게 신청해?", "장학", "총동문회"),
    ("총동문회비 냈는지 어디서 확인해?", "장학", "총동문회비"),
    ("튜터링 어떻게 신청해?", "상담·학생지원", "튜터"),
    ("단과대 학생회 인스타 어디서 찾아?", "동아리·학생자치", "인스타그램"),
    ("예비군 셔틀버스 있어?", "병무·예비군", "셔틀버스"),
    ("교내 토익 특강 어디서 신청해?", "기타", "국제교육원"),
    ("교환학생 어학점수 꼭 있어야 돼?", "학점교류·교환학생", "어학점수"),
    ("KLAS 졸업사정에 어학 대상이라고 뜨는데 뭐야", "졸업", "어학"),
    ("함지마루 저녁도 팔아?", "학식·편의시설", "함지마루"),
    ("분실물 어디서 찾아?", "학식·편의시설", "분실물"),
    ("학생상담실 예약 어떻게 해?", "상담·학생지원", "상담"),
    ("다음 학기 수강신청 언제야?", "수강신청", "수강신청"),
    ("부전공 포기하면 들은 과목 어떻게 돼?", "다전공", "일반선택"),
    ("학생회비 냈는지 어디서 확인해?", "동아리·학생자치", "자율적학생경비"),
])

def test_search_finds_the_right_entry(query, category, word):
    hits = knowledge.search(query, limit=3)
    assert hits, query
    assert any(h["category"] == category for h in hits), [(h["id"], h["category"]) for h in hits]
    top = hits[0]
    blob = " ".join(top["questions"]) + top["answer"]
    assert word in blob, (query, top["id"])


def test_link_entries_carry_official_urls():
    assert "mobileid.kw.ac.kr/seatweb" in knowledge.entry("library-seat-status-live")["how_to"]
    assert "kw.happydorm.or.kr" in knowledge.entry("dorm-apply-how")["how_to"]
    assert "www.kw.ac.kr/ko/tour/directions.jsp" in knowledge.entry("shuttle-route-schedule")["how_to"]
    # robots-disallowed or outside sites: links only, never fetched
    assert "www.kwuaa.com/bbs/board.php?bo_table=notice" in knowledge.entry("scholar-alumni-apply")["how_to"]
    assert "ontl.kw.ac.kr" in knowledge.entry("support-kw-major-tutoring")["how_to"]
    assert "kwu.ttceducation.net" in knowledge.entry("etc-iie-english-toeic")["how_to"]
    assert "reading.kw.ac.kr" in knowledge.entry("library-contact")["how_to"]


def _validate_module():
    import importlib.util

    root = Path(__file__).resolve().parents[1] / "scripts" / "knowledge"
    sys.path.insert(0, str(root))
    try:
        spec = importlib.util.spec_from_file_location("kb_validate", root / "validate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(root))
    return mod


def test_links_only_go_to_allowed_hosts():
    v = _validate_module()
    assert v.link_problems("바로가기 https://vvd.bz/bhjy") and v.link_problems("m.site.naver.com/2iMoN")
    assert v.link_problems("https://aback-shirt-867.notion.site/x") and v.link_problems("https://instagram.com/x")
    assert not v.link_problems("https://www.instagram.com/kwu_career https://daple.kwuniv.com www.kosaf.go.kr")
    for e in ENTRIES:
        blob = json.dumps({k: e[k] for k in ("questions", "answer", "conditions_exceptions", "how_to",
                                             "disagreement", "sources")}, ensure_ascii=False)
        assert not v.link_problems(blob), (e["id"], v.link_problems(blob))


def test_curricula_notes_read_as_plain_notes():
    index = json.loads((DATA / "curricula" / "index.json").read_text(encoding="utf-8"))
    for d in index["departments"]:
        for note in d["notes"]:
            assert not re.search(r"지시에 따라|요청에 따라|required_only|\(A\)|\(B\)", note), (d["slug"], note)


def test_office_phone_entries_have_no_people():
    offices = [e for e in ENTRIES if e["id"].startswith("etc-office-phone-")]
    assert len(offices) >= 8
    for e in offices:
        assert re.search(r"02-9\d{2}-\d{4}", e["answer"]) and "@" not in e["answer"]


def test_search_results_carry_version_and_report_hint():
    hit = knowledge.search("재수강 성적 상한")[0]
    assert hit["version"]["built_at"] and hit["version"]["sources"]
    assert all(u.startswith(("https://", "http://mobileid.kw.ac.kr/")) for u in hit["version"]["sources"])
    assert "제보" in hit["report"]


def test_search_category_filter_and_edges():
    assert knowledge.search("") == []
    assert knowledge.search("휴학", limit=0) == []
    hits = knowledge.search("학점", category="계절학기", limit=10)
    assert hits and all(h["category"] == "계절학기" for h in hits)


def test_entry_lookup():
    first = ENTRIES[0]
    e = knowledge.entry(first["id"])
    assert e["id"] == first["id"] and "report" in e and "version" in e
    assert knowledge.entry("no-such-entry") is None


def test_curricula_index_and_files():
    index = json.loads((DATA / "curricula" / "index.json").read_text(encoding="utf-8"))
    assert index["departments"]
    for d in index["departments"]:
        for year in d["admission_years"]:
            c = json.loads((DATA / "curricula" / f"{d['slug']}-{year}.json").read_text(encoding="utf-8"))
            assert c["department"] == d["department"] and c["admission_year"] == year
            assert c["scope"] in {"full", "required_only"}
            assert c["sources"] and all(s["url"].startswith("https://") for s in c["sources"])
            for course in c["courses"]:
                assert course["name"]
                assert course["credits"] is None or isinstance(course["credits"], (int, float))
                assert course["year_level"] is None or 1 <= course["year_level"] <= 5
                assert course["term"] in (None, 1, 2)


def test_curriculum_lookup():
    d = knowledge.load()["curricula_index"]["departments"][0]
    year = d["admission_years"][-1]
    c = knowledge.curriculum(d["department"], year)
    assert c and c["courses"] and c["report"] and c["version"]["sources"]
    assert knowledge.curriculum(d["department"], 1900) is None
    assert knowledge.curriculum("없는학과", year) is None


def test_multi_major_planning_points_to_daple():
    hits = knowledge.search("다전공 시뮬레이션 어디서 해볼 수 있어?", limit=3)
    assert any("daple.kwuniv.com" in (h["answer"] + h["how_to"]) for h in hits)


def test_rules_tables():
    tables = knowledge.load()["rules_tables"]
    assert tables["annex6"]["blocks"]
    assert tables["linked_majors"]["rows"]
    assert tables["gyoyang_classification"]["rows"]
    assert all(s["url"].startswith("https://rule.kw.ac.kr/") for s in tables["version"]["sources"])


def test_guide_trims_entries_for_citing():
    out = knowledge.guide("복전 몇 학점 들어야 돼?")
    assert out["answers"] and len(out["answers"]) <= 3
    top = out["answers"][0]
    assert top["category"] == "다전공" and top["question"] and top["answer"]
    assert top["sources"] and all(s.get("url", "").startswith("http") for s in top["sources"])
    assert all("source_id" not in s and "checked_at" not in s for s in top["sources"])
    assert "questions" not in top
    assert out["version"]["built_at"] and out["report"] == knowledge.REPORT_HINT and out["note"]
    assert isinstance(out.get("not_in_documents", []), list)


def test_guide_limits_and_unknown_category():
    assert len(knowledge.guide("장학금", limit=50)["answers"]) == 5
    assert len(knowledge.guide("장학금", limit=0)["answers"]) == 1
    # an unknown category is ignored rather than returning nothing
    assert knowledge.guide("국장 신청", category="없는분류")["answers"]
    only = knowledge.guide("신청 언제", category="장학")["answers"]
    assert only and {a["category"] for a in only} == {"장학"}


def test_guide_without_a_match_lists_categories():
    out = knowledge.guide("   ")
    assert out["answers"] == [] and set(out["categories"]) == CATEGORIES
    assert "school_notices" in out["note"]


def test_round5_curricula_cover_the_robot_and_global_korea_majors():
    robot = knowledge.curriculum("지능형로봇학과", 2026)
    assert robot and robot["courses"] and robot["scope"] == "full"
    assert all(s["url"].startswith("https://share.kw.ac.kr/") for s in robot["sources"])
    assert "이미지" in robot["basis"]  # credits read from the 교육과정체계 image are said so
    korea = knowledge.curriculum("글로벌코리아전공", 2026)
    assert korea and any(c["name"] == "한국의 대중문화" for c in korea["courses"])


def test_curriculum_lookup_explains_what_is_missing():
    dept = knowledge.load()["curricula_index"]["departments"][0]
    year = dept["admission_years"][-1]
    assert knowledge.curriculum_lookup(dept["department"], year)["courses"]
    missing_year = knowledge.curriculum_lookup(dept["department"], 1990)
    assert missing_year["found"] is False and missing_year["admission_years"] == dept["admission_years"]
    vague = knowledge.curriculum_lookup("공학", 2024)
    assert vague["found"] is False and len(vague["candidates"]) > 1
    unknown = knowledge.curriculum_lookup("없는학과", 2024)
    assert unknown["found"] is False and unknown["departments"]


async def test_knowledge_tools_need_no_klas_login():
    from kw_mcp import server

    def text(result) -> str:
        return "".join(getattr(b, "text", "") for b in result.content)

    server.set_service(None)
    guide = text(await server.mcp.call_tool("school_guide", {"question": "재수강하면 성적 최대 몇?"}))
    assert "재수강" in guide and '"sources"' in guide
    missing = text(await server.mcp.call_tool("department_curriculum", {"department": "없는학과", "admission_year": 2024}))
    assert '"found": false' in missing
