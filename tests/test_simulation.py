"""졸업·다전공 시뮬레이션 (kw_mcp.simulation) and the graduation-check fixes the official rules data
brought: synthetic 2019, 2024, 2025 and 2026 students in different colleges, read through KlasService
with a fake KLAS client. Made-up numbers and names only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import agent, release, server, simulation
from kw_mcp.klas import KlasError
from kw_mcp.service import (
    GEN_ED,
    GRADE_TOTALS,
    GRADES,
    KST,
    LANGUAGE_REQUIREMENT,
    LEAVE_STATUS,
    LEAVE_WINDOWS,
    LINKED_APPLIED,
    MAJOR_APPLIED,
    MICRO_APPLIED,
    STUDENT_RECORD,
    KlasService,
)

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=KST)
# 교양 이수현황 columns (service.BALANCED_AREAS; 과학과기술 is aa63 + aa76, here all in aa63).
AREA_FIELDS = {"대학실용영어": "aa62", "언어와표현": "aa64", "과학과기술": "aa63", "인간과철학": "aa65", "사회와경제": "aa66",
               "글로벌문화와제2외국어": "aa67", "예술과체육": "aa68", "수리와자연": "aa7881"}
FAKE_NAME, FAKE_MAIL = "가상학생", "student@example.invalid"
# A made-up curriculum in kw_mcp.knowledge.curriculum's shape.
CURRICULUM = {"department": "경영학부", "admission_year": 2024, "scope": "full", "basis": "테스트용",
              "courses": [{"name": "회계원리", "type": "전필", "credits": 3, "note": None},
                          {"name": "조직행동", "type": "전필", "credits": 3, "note": "구,조직론"},
                          {"name": "경영통계", "type": "전선", "credits": 3, "note": None},
                          {"name": "데이터베이스", "type": "전선", "credits": 3, "note": None}],
              "version": {"built_at": "2026-11-07", "sources": ["https://www.kw.ac.kr/ko/univ/example.jsp"]}}


@pytest.fixture(autouse=True)
def no_curriculum(monkeypatch):
    """The knowledge base is built elsewhere: these tests decide what curriculum, if any, it has."""
    known: dict[tuple[str, int], dict[str, Any]] = {}
    monkeypatch.setattr(simulation, "_curriculum", lambda department, year: known.get((department, year)))
    return known


def course(name: str, category: str, credits: int = 3, grade: str = "A0") -> dict[str, Any]:
    return {"gwamokKname": name, "codeName1": category, "hakjumNum": credits, "getGrade": grade, "retakeOpt": "N"}


def transcript(graded: int, start: int, first: tuple[dict[str, Any], ...] = ()) -> list[dict[str, Any]]:
    """`graded` regular semesters with grades from `start`, then this term with no grades yet."""
    rows, year, term = [], start, 1
    for i in range(graded):
        rows.append({"thisYear": str(year), "hakgi": str(term), "sungjukList": [course(f"전공과목{i}", "전선"),
                                                                              *(first if i == 0 else ())]})
        year, term = (year, 2) if term == 1 else (year + 1, 1)
    rows.append({"thisYear": str(year), "hakgi": str(term), "sungjukList": [course("이번학기과목", "전선", grade="")]})
    return rows


class SimClient:
    """KLAS for one made-up student: 학적, 교양 이수현황, grade totals and transcript. Anything else
    (the graduation review list) answers with an empty body: not on the list."""

    def __init__(self, admitted: int, department: str, *, required: int = 0, areas: dict[str, int] | None = None,
                 earned: int = 60, major: int = 30, semesters: list[dict[str, Any]] | None = None, **record: Any):
        self.record = {"hakgwa": department, "hakbun": f"{admitted}000000", "kname": FAKE_NAME, "email": FAKE_MAIL,
                       "grade": 2, "hakjukStatu": "재학", **record}
        self.gen = {"aa8128": required, **{AREA_FIELDS[a]: v for a, v in (areas or {}).items()}}
        self.totals = {"chidukHakjum": earned, "majorChidukHakjum": major, "cultureChidukHakjum": 30,
                       "etcChidukHakjum": 0, "hwakinScoresum": 3.5, "jaechulScoresum": 3.5}
        self.semesters = transcript(2, admitted) if semesters is None else semesters
        self.calls: list[str] = []

    async def post(self, path: str, body: dict[str, Any] | None = None, **_: Any) -> Any:
        self.calls.append(path)
        return {STUDENT_RECORD: self.record, GEN_ED: self.gen, GRADE_TOTALS: self.totals, GRADES: self.semesters}.get(path)


def service(client: SimClient) -> KlasService:
    return KlasService(client, now=lambda: NOW)


def statuses(items: list[dict[str, Any]]) -> dict[str, str]:
    return {i["requirement"]: i["status"] for i in items}


def uncertain(out: dict[str, Any]) -> list[str]:
    return [u["item"] for u in out["uncertain"]]


# Five areas, 30 balanced credits, 인간과철학 and 과학과기술 among them.
FULL_AREAS = {"대학실용영어": 3, "언어와표현": 6, "과학과기술": 6, "인간과철학": 6, "수리와자연": 9}
STUDENTS = {
    "2019 인공지능융합대학": lambda: SimClient(2019, "컴퓨터정보공학부", required=1, earned=120, major=57,
                                         areas={"대학실용영어": 3, "언어와표현": 3, "과학과기술": 6, "인간과철학": 3,
                                                "사회와경제": 3, "예술과체육": 3}, semesters=transcript(7, 2019)),
    "2024 경영대학": lambda: SimClient(2024, "경영학부", required=1, earned=95, major=50,
                                   areas={"대학실용영어": 6, "언어와표현": 6, "사회와경제": 9, "인간과철학": 9},
                                   semesters=transcript(5, 2024, (course("경영통계", "복선"),))),
    "2025 정책법학대학": lambda: SimClient(2025, "행정학과", areas=FULL_AREAS, semesters=transcript(3, 2025)),
    "2026 전자정보공과대학": lambda: SimClient(2026, "전자공학과", required=3, areas=FULL_AREAS, earned=33, major=6,
                                       semesters=transcript(1, 2026)),
}


# --- graduation_progress: the 교양 fixes ----------------------------------------------------------

async def test_2024_and_earlier_need_only_the_years_total_not_kwangwoonin():
    # 2024 경영학부: 31 = 31 without 광운인되기 (학칙 부칙<2025.12.17.> 제2조, from 2026-03-01).
    out = await service(SimClient(2024, "경영학부", required=0,
                                  areas={"대학실용영어": 6, "언어와표현": 6, "사회와경제": 9, "인간과철학": 10})).graduation_progress()
    check = out["check"]
    assert "kwangwoonin_done" not in check and check["met"] is True and "31" in out["rule"]
    assert statuses(check["items"]) == {"총 교양 31학점": "충족"}
    assert "광운인되기" in check["note"] and check["articles"]["reg-hakchik"] == "부칙<2025.12.17.> 제1조 단서·제2조"
    # 2019 인문 (국어국문학과): 필수+균형 22 from the department's row, one course short.
    old = await service(SimClient(2019, "국어국문학과", areas={"대학실용영어": 9, "언어와표현": 6, "인간과철학": 4})).graduation_progress()
    assert statuses(old["check"]["items"]) == {"필수+균형 교양 22학점": "미충족"} and old["check"]["credits_needed"] == 3


async def test_2025_needs_31_not_30():
    # 균형교양 30 over five areas, no 광운인되기: the 1 credit that replaced it is still missing.
    out = await service(SimClient(2025, "행정학과", areas=FULL_AREAS)).graduation_progress()
    check = out["check"]
    assert statuses(check["items"]) == {"균형교양 8개 영역 중 4개 영역 이상": "충족", "균형교양 30학점": "충족",
                                        "총 교양 31학점": "미충족"}
    assert check["met"] is False and check["credits_needed"] == 1 and check["balanced_credits_needed"] == 0
    done = await service(SimClient(2025, "행정학과", required=1, areas=FULL_AREAS)).graduation_progress()
    assert done["check"]["met"] is True


async def test_2026_reports_what_klas_cannot_show_as_unknown():
    out = await service(SimClient(2026, "전자공학과", required=3, areas=FULL_AREAS)).graduation_progress()
    check = out["check"]
    assert "AI리터러시 3학점" in out["rule"] and "33" in out["rule"] and "9개 영역" in out["rule"]
    items = statuses(check["items"])
    # Which KLAS column holds AI리터러시 is not public: 확인 필요 with the reason, never a pass.
    assert items["AI리터러시 3학점(필수)"] == "확인 필요"
    ai = next(i for i in check["items"] if i["requirement"].startswith("AI리터러시"))
    assert "공개 자료" in ai["reason"]
    assert items["이공계열 지정 영역(인간과철학 또는 사회와경제) 포함"] == "충족"
    assert items["균형교양 30학점"] == items["총 교양 33학점"] == "충족"
    assert check["met"] is None  # one item unknown: no verdict either way

    # Below 4 areas or 30 credits, the unseen 기초학문융합 area might make it up: 확인 필요, not 미충족.
    short = await service(SimClient(2026, "미디어커뮤니케이션학부", required=3,
                                    areas={"인간과철학": 6, "언어와표현": 6})).graduation_progress()
    items = {i["requirement"]: i for i in short["check"]["items"]}
    assert items["균형교양 9개 영역 중 4개 영역 이상"]["status"] == "확인 필요"
    assert "기초학문융합" in items["균형교양 9개 영역 중 4개 영역 이상"]["reason"]
    assert items["균형교양 30학점"]["status"] == items["총 교양 33학점"]["status"] == "확인 필요"
    # The 인문사회 must-include areas are both KLAS columns: that one is a firm 미충족.
    assert items["인문사회계열 지정 영역(과학과기술 또는 수리와자연) 포함"]["status"] == "미충족"
    assert short["check"]["met"] is False


async def test_unknown_years_and_transfer_students_get_no_verdict():
    later = await service(SimClient(2027, "전자공학과", areas=FULL_AREAS)).graduation_progress()
    assert later["check"]["met"] is None and later["check"]["items"][0]["status"] == "확인 필요"
    moved = await service(SimClient(2025, "행정학과", areas=FULL_AREAS, prevHakjumNum=65,
                                    cultureHakjum=20)).graduation_progress()
    assert moved["check"]["met"] is None and moved["check"]["transfer_credits"]["total"] == 65
    free = await service(SimClient(2026, "자율전공학부", required=3, areas=FULL_AREAS)).graduation_progress()
    assert statuses(free["check"]["items"])["계열별 지정 영역 포함"] == "확인 필요"


def test_what_matches_the_code_is_kept():
    # The 8 area names and 과학과기술 = aa63 + aa76 (rules code_crosscheck says "agrees").
    from kw_mcp.service import BALANCED_AREAS

    areas = dict(BALANCED_AREAS)
    official = simulation.rules("graduation")["general_education"]["by_admission_year"]
    assert list(areas) == next(e for e in official if e["admission_years"] == "2025")["balanced"]["areas"]
    assert areas["과학과기술"] == ("aa63", "aa76")
    notes = " ".join(r["rule"] for r in simulation.rules("graduation")["general_education"]["common_rules"][:2])
    assert "3·4학점" in notes and "K-MOOC" in notes


# --- simulate_graduation ------------------------------------------------------------------------

async def test_outlook_2019_engineering():
    out = await service(STUDENTS["2019 인공지능융합대학"]()).graduation_outlook()
    assert out["student"]["admission_year"] == 2019 and out["student"]["college"] == "인공지능융합대학"
    total = out["total_credits"]
    assert (total["required"], total["earned"], total["remaining"], total["status"]) == (133, 120, 13, "미충족")
    assert total["in_progress"] == 3
    paths = {p["requirement"]: p for p in out["major_credits"]["paths"]}
    assert paths["단일전공"]["required"] == 60 and paths["단일전공"]["remaining"] == 3
    double = next(p for p in paths.values() if p["requirement"].startswith("복수전공·연계전공"))
    assert double["required"] == 54 and double["status"] == "충족"
    assert paths["심화전공"]["status"] == "해당 없음"  # 전정·소융대: no 심화전공 ('-')
    ge = out["general_education"]["check"]
    # 2019: the department's 필수+균형 22 and 기초 24 (KLAS's 교양 table has no 기초 column).
    assert statuses(ge["items"]) == {"필수+균형 교양 22학점": "충족", "기초교양(학과 지정) 24학점": "확인 필요"}
    assert ge["met"] is None
    others = {o["id"]: o for o in out["other_conditions"]}
    assert others["semesters"]["status"] == "충족" and others["semesters"]["have"] == 8
    assert others["multi_major_mandatory"]["status"] == "해당 없음"
    assert others["engineering_accreditation"]["status"] == "확인 필요"
    assert others["required_courses"]["status"] == others["thesis"]["status"] == "확인 필요"
    assert others["english_certification"]["status"] == "해당 없음"
    assert "졸업학점" in out["summary"]["미충족"] and "교양" in out["summary"]["확인 필요"]


async def test_outlook_2024_humanities():
    out = await service(STUDENTS["2024 경영대학"]()).graduation_outlook()
    assert out["student"]["college"] == "경영대학" and out["total_credits"]["required"] == 130
    paths = [(p["requirement"], p.get("required")) for p in out["major_credits"]["paths"]]
    assert paths == [("단일전공", 54), ("복수전공·연계전공 이수 시(부·마이크로·학생설계융합전공은 단일전공 학점)", 45), ("심화전공", 70)]
    assert out["general_education"]["check"]["met"] is True and out["general_education"]["total"] == 31
    assert {o["id"]: o["status"] for o in out["other_conditions"]}["semesters"] == "미충족"
    assert "engineering_accreditation" not in {o["id"] for o in out["other_conditions"]}
    assert "2024학년도 교양 필수/균형 구분" in uncertain(out)
    assert "2026학년도 AI리터러시 면제 여부와 KLAS 표시" not in uncertain(out)


async def test_outlook_2025_multi_major_is_mandatory_but_unknown():
    out = await service(STUDENTS["2025 정책법학대학"]()).graduation_outlook()
    assert out["table"].startswith("2025학년도") and out["total_credits"]["required"] == 130
    paths = {p["requirement"]: p.get("required") for p in out["major_credits"]["paths"]}
    assert paths["다전공 하나 이수 시 주전공"] == 45 and paths["심화전공(주전공 심화, 다전공 의무 충족)"] == 70
    others = {o["id"]: o for o in out["other_conditions"]}
    assert others["multi_major_mandatory"]["status"] == "확인 필요" and "explore_multi_major" in others[
        "multi_major_mandatory"]["reason"]
    assert out["general_education"]["check"]["credits_needed"] == 1


async def test_outlook_2026_uses_the_transcript_for_ai_literacy():
    client = STUDENTS["2026 전자정보공과대학"]()
    out = await service(client).graduation_outlook()
    ge = out["general_education"]["check"]
    assert statuses(ge["items"])["AI리터러시 3학점(필수)"] == "확인 필요" and ge["met"] is None
    assert "성적표에도" in next(i for i in ge["items"] if i["requirement"].startswith("AI"))["reason"]
    assert "2026학년도 AI리터러시 면제 여부와 KLAS 표시" in uncertain(out)
    # A passed course named AI리터러시 on the transcript is evidence for that item.
    client.semesters = transcript(1, 2026, (course("AI 리터러시", "교필"),))
    passed = await service(client).graduation_outlook()
    item = next(i for i in passed["general_education"]["check"]["items"] if i["requirement"].startswith("AI"))
    assert item["status"] == "충족" and item["basis"] == "성적표 과목명"
    assert passed["general_education"]["check"]["met"] is True


async def test_outlook_without_a_table_says_check_needed():
    out = await service(SimClient(2027, "전자공학과", areas=FULL_AREAS)).graduation_outlook()
    assert out["table"] is None and out["total_credits"]["status"] == "확인 필요"
    assert out["major_credits"]["paths"][0]["status"] == "확인 필요"
    assert out["general_education"]["check"]["met"] is None
    moved = await service(SimClient(2024, "경영학부", prevHakjumNum=70, majorHakjum=30)).graduation_outlook()
    assert moved["total_credits"]["status"] == "확인 필요" and "편입" in moved["total_credits"]["reason"]
    assert {o["id"]: o["status"] for o in moved["other_conditions"]}["semesters"] == "확인 필요"


@pytest.mark.parametrize("name", sorted(STUDENTS))
async def test_every_answer_carries_version_uncertain_disclaimer_and_report(name):
    client = STUDENTS[name]()
    svc = service(client)
    outlook = await svc.graduation_outlook()
    assert outlook["disclaimer"] == "참고용 계산입니다. 공식 판정은 학교 다전공 플래너(Daple)나 학과사무실에서 확인하세요."
    for out in (outlook, await svc.multi_major_options(), await svc.multi_major_options(track="빅데이터")):
        if out is not outlook:
            assert out["disclaimer"] == ("Daple(다전공 플래너)과 같은 기준으로 계산한 참고 결과입니다. "
                                         "공식 판정과 신청은 Daple과 학과사무실에서 확인하세요.")
            assert any(s["url"] == "https://daple.kwuniv.com" for s in out["version"]["sources"])
        assert out["report"] == "규정이 바뀌었거나 틀린 곳은 디스코드 #알림-설정의 '제보하기'(또는 /제보)로 알려 주세요."
        version = out["version"]
        assert version["built_at"] == "2026-11-07" and version["basis"]
        assert version["sources"] and all(s["title"] and s["url"].startswith("https://") for s in version["sources"])
        assert isinstance(out["uncertain"], list) and all({"item", "seen"} <= set(u) for u in out["uncertain"])
        text = json.dumps(out, ensure_ascii=False)
        assert FAKE_NAME not in text and FAKE_MAIL not in text and client.record["hakbun"] not in text


async def test_the_reads_are_shared_between_the_graduation_tools():
    client = STUDENTS["2025 정책법학대학"]()
    svc = service(client)
    await svc.graduation_outlook()
    await svc.multi_major_options(track_type="연계")
    await svc.graduation_progress()
    for path in (STUDENT_RECORD, GEN_ED, GRADE_TOTALS, GRADES):
        assert client.calls.count(path) == 1, path


# --- explore_multi_major ------------------------------------------------------------------------

async def test_each_type_for_a_2025_student():
    out = await service(STUDENTS["2025 정책법학대학"]()).multi_major_options()
    assert list(out["types"]) == list(simulation.TYPES)
    t = out["types"]
    assert (t["심화전공"]["required_credits"], t["심화전공"]["major_credits_if_completed"]) == (70, 70)
    # 복수·부전공: the target department's credits (Daple), not my own row; 2025학번 → the 2025 table.
    assert t["복수전공"]["required_credits"] == {"min": 45, "max": 99} and t["복수전공"]["major_credits_if_completed"] == 45
    assert t["복수전공"]["by_department"]["건축학과"] == 99 and "행정학과" not in t["복수전공"]["by_department"]
    assert t["부전공"]["required_credits"] == {"min": 21, "max": 45} and t["마이크로전공"]["required_credits"] == 15
    assert t["연계전공"]["required_credits"] == {"min": 30, "max": 51} and t["학생설계융합전공"]["required_credits"] == 24
    assert t["복수전공"]["mutual_recognition"]["max_credits"] == 9 and t["마이크로전공"]["mutual_recognition"]["max_credits"] == 0
    assert out["mandatory"]["applies"] is True and "건축학과" in out["mandatory"]["exceptions"]
    eligibility = {e["rule"][:5]: e for e in out["eligibility"]}
    assert eligibility["신청 자격"]["status"] == "충족" and eligibility["신청 자격"]["have"] == 3
    assert any("최대 2개" in r["rule"] for r in out["limits"])
    assert out["course_matching"].startswith(simulation.COURSE_MATCHING)


async def test_major_credit_reduction_follows_the_year_and_type():
    out = await service(STUDENTS["2024 경영대학"]()).multi_major_options()
    t = out["types"]
    # 2017~2024: 복수·연계 lower the major to the '다전공 이수시' column, 부·마이크로·학생설계 don't.
    assert t["복수전공"]["major_credits_if_completed"] == t["연계전공"]["major_credits_if_completed"] == 45
    assert t["부전공"]["major_credits_if_completed"] == t["마이크로전공"]["major_credits_if_completed"] == 54
    assert t["복수전공"]["on_transcript"]["earned"] == 3  # the 복선 course on the transcript
    assert out["mandatory"]["applies"] is False
    # 2025~ 참빛인재대학: every multi-major lowers the major to 39; 심화 is 60.
    night = await service(SimClient(2025, "게임콘텐츠학과")).multi_major_options()
    assert night["types"]["부전공"]["major_credits_if_completed"] == 39
    assert night["types"]["심화전공"]["required_credits"] == 60
    # 2019 전정·소융대: no 심화전공.
    old = await service(STUDENTS["2019 인공지능융합대학"]()).multi_major_options(track_type="심화")
    assert list(old["types"]) == ["심화전공"] and old["types"]["심화전공"]["available"] is False


async def test_eligibility_checks_the_semesters_and_status():
    fresh = await service(SimClient(2026, "전자공학과", semesters=transcript(0, 2026))).multi_major_options()
    assert {e["status"] for e in fresh["eligibility"]} == {"미충족"}
    away = await service(SimClient(2024, "경영학부", hakjukStatu="휴학")).multi_major_options()
    assert [e["status"] for e in away["eligibility"]] == ["충족", "미충족"]
    late = await service(SimClient(2019, "경영학부", semesters=transcript(9, 2019))).multi_major_options()
    assert late["eligibility"][1]["status"] == "확인 필요" and "8학기" in late["eligibility"][1]["reason"]


@pytest.mark.parametrize("query", ["빅데이터", "빅데이터 연계전공", " 빅 데이터 "])
async def test_a_linked_major_is_found_leniently(query):
    out = await service(STUDENTS["2025 정책법학대학"]()).multi_major_options(track=query)
    [match] = out["track_matches"]
    assert match["name"] == "빅데이터" and match["aliases"] == ["빅데이터 연계전공"]  # Daple's name, ours kept
    assert match["type"] == "연계전공" and match["operator"] == "정보융합학부" and match["program_code"] == (
        "interdisciplinary_major:big-data")
    assert match["required_credits"] == 30 and match["mutual_recognition_max"] == 9
    assert match["course_matching"]["reliable"] is True and match["source"]["url"].startswith("https://")
    assert list(out["types"]) == ["연계전공"]


async def test_track_names_case_spaces_and_suffixes_do_not_matter():
    svc = service(STUDENTS["2025 정책법학대학"]())
    for query in ("AI 융합 연계전공", "ai융합", "AI융합"):
        assert [m["name"] for m in (await svc.multi_major_options(track=query))["track_matches"]] == ["AI융합"]
    assert [m["name"] for m in (await svc.multi_major_options(track="VR AR"))["track_matches"]] == ["VR/AR"]
    assert [m["name"] for m in (await svc.multi_major_options(track="지속가능ESG"))["track_matches"]] == ["지속가능ESG전공"]


@pytest.mark.parametrize(("old", "daple"), [("바이오헬스케어", "바이오헬스케어전공"),
                                            ("문학기반K-콘텐츠개발전공", "문학기반K-콘텐츠전공"),
                                            ("로봇기초전공", "기초전공"),
                                            ("에너지‧환경지속가능성전공", "에너지·환경지속가능성전공")])
async def test_our_old_track_names_resolve_to_daples(old, daple):
    out = await service(STUDENTS["2025 정책법학대학"]()).multi_major_options(track=old)
    [match] = out["track_matches"]
    assert match["name"] == daple and old in match["aliases"]


async def test_linked_major_credits_follow_daple():
    # 사회복지학: Daple 51 (교육과정 기준); the 학사안내's 45 for 2019학번 and earlier stays as detail and an open question.
    old = await service(STUDENTS["2019 인공지능융합대학"]()).multi_major_options(track="사회복지학")
    new = await service(STUDENTS["2024 경영대학"]()).multi_major_options(track="사회복지학 연계전공")
    assert old["track_matches"][0]["required_credits"] == new["track_matches"][0]["required_credits"] == 51
    assert old["track_matches"][0]["credits_detail"]["by_admission_year"][0]["credits"] == 45
    assert "사회복지학 연계전공 2019학번 이전 이수학점" in uncertain(old)
    assert "사회복지학 연계전공 2019학번 이전 이수학점" not in uncertain(new)


async def test_a_micro_major_of_my_own_department_is_not_open_to_me():
    out = await service(SimClient(2026, "수학과")).multi_major_options(track="데이터분석")
    [match] = out["track_matches"]
    assert match["type"] == "마이크로전공" and match["available"] is False and match["required_credits"] == 15
    other = await service(SimClient(2026, "경영학부")).multi_major_options(track="데이터분석")
    assert "available" not in other["track_matches"][0]
    assert "데이터분석전공 편성학점" in uncertain(out)  # the open question about this very track
    assert "동북아지역전문가전공 편성학점" not in uncertain(out)


async def test_ambiguous_and_unknown_names_list_candidates():
    svc = service(STUDENTS["2026 전자정보공과대학"]())
    both = await svc.multi_major_options(track="미디어콘텐츠")
    assert sorted(m["type"] for m in both["track_matches"]) == ["마이크로전공", "연계전공"]
    micro = await svc.multi_major_options(track="미디어콘텐츠", track_type="마이크로")
    assert [m["name"] for m in micro["track_matches"]] == ["미디어콘텐츠전공"] and list(micro["types"]) == ["마이크로전공"]
    many = await svc.multi_major_options(track="인공지능")
    assert many["track_matches"] == [] and {"인공지능반도체", "인공지능융합시스템전공"} <= set(many["track_candidates"])
    typo = await svc.multi_major_options(track="빅데이타")
    assert typo["track_matches"] == [] and "빅데이터" in typo["track_candidates"]
    assert "찾지 못했습니다" in typo["track_note"]


async def test_a_department_target_uses_the_target_departments_credits():
    # 2019 컴퓨터정보공학부 → 경영학부: Daple's target row (45, version 2003), not my own row (54).
    out = await service(STUDENTS["2019 인공지능융합대학"]()).multi_major_options(track="경영학부")
    [match] = out["track_matches"]
    double, minor = match["double_major"], match["minor"]
    assert match["college"] == "경영대학" and double["required_credits"] == 45 and minor["required_credits"] == 21
    assert "Daple" in double["basis"] and double["source_ids"] == ["daple-2026-11-07"]
    assert double["program_code"] == "double_major:5080" and minor["program_code"] == "minor:5080"
    assert list(out["types"]) == ["복수전공", "부전공"]
    assert "복수·부전공 학점 표의 적용 기준" not in uncertain(out)  # resolved by Daple
    resolved = {r["item"] for r in simulation.rules("multi_major")["resolved"]}
    assert "복수·부전공 학점 표의 적용 기준" in resolved
    own = await service(STUDENTS["2019 인공지능융합대학"]()).multi_major_options(track="컴퓨터정보공학부")
    assert own["track_matches"][0]["available"] is False and list(own["types"]) == ["심화전공"]


def test_the_targets_table_by_admission_year():
    targets = simulation.rules("multi_major")["targets"]
    assert len(targets) == 56 and {t["type"] for t in targets} == {"복수전공", "부전공"}
    assert all(t["source_ids"] == ["daple-2026-11-07"] and t["basis"] == "admission" for t in targets)
    # Inside the version Daple showed: Daple's value, and the official table's when they differ.
    robot = simulation.target_credits("부전공", "지능형로봇학과", 2022)
    assert robot["required_credits"] == 21 and robot["official_table"]["required_credits"] == 24
    # 2025학번 and later: the official table's target row, with Daple's snapshot value beside it.
    later = simulation.target_credits("복수전공", "전자공학과", 2025)
    assert later["required_credits"] == 45 and later["daple"] == {
        "required_credits": 54, "version_year": 2017, "note": later["daple"]["note"]}
    # Before the version Daple showed (행정학과 2020): the official table of that year.
    assert simulation.target_credits("부전공", "행정학과", 2019)["basis"].startswith("2019학년도")


# A transcript built from course numbers in Daple's lists (rules/track_courses.json, from the snapshot).
MARKETING = transcript(0, 2025) + [
    {"thisYear": "2025", "hakgi": "1", "sungjukList": [
        {**course("마케팅원론", "일선"), "hakjungNo": "5080-2-0508-01"},  # 경영학부 0508: counts
        {**course("마케팅원론", "일선"), "hakjungNo": "5080-2-0508-02"},  # the same course again: once
        {**course("소비자행동", "일선", grade="F"), "hakjungNo": "5080-2-8557-01"},  # failed: no
        {**course("광고론", "일선"), "hakjungNo": "6050-2-7704-01"},  # 화학과's code: another department's course
        {**course("브랜드관리", "일선"), "hakjungNo": "Z999-3-4127-01"},  # unknown department code: unconfirmed
        course("코드없는과목", "일선")]},
    {"thisYear": "2025", "hakgi": "2", "sungjukList": [
        {**course("마케팅조사", "일선", grade=""), "hakjungNo": "5080-3-3303-01"}]},  # this term, no grade yet
]


async def test_course_matching_on_a_daple_list():
    out = await service(SimClient(2025, "행정학과", semesters=MARKETING)).multi_major_options(track="마케팅")
    [match] = out["track_matches"]
    result = match["course_matching"]
    assert match["name"] == "마케팅전공" and result["reliable"] is True and result["estimated"] is True
    assert result["basis"] == "Daple 과정 과목 목록(2026-11-07) 기준"
    assert [c["code"] for c in result["recognized_courses"]] == ["5080-2-0508-01"]
    assert (result["required_credits"], result["recognized_credits"], result["remaining_credits"]) == (15, 3, 12)
    assert [c["code"] for c in result["in_progress_courses"]] == ["5080-3-3303-01"]
    assert result["remaining_if_in_progress_passed"] == 9
    assert [c["code"] for c in result["unconfirmed_courses"]] == ["Z999-3-4127-01"] and "최대 3학점" in result[
        "unconfirmed_note"]
    assert result["rows_without_code"] == 2  # this term's placeholder course and the one without 학정번호


async def test_course_matching_for_a_target_department_and_a_linked_major():
    student = SimClient(2024, "컴퓨터정보공학부", semesters=MARKETING)
    chem = await service(student).multi_major_options(track="화학과")
    double = chem["track_matches"][0]["double_major"]["course_matching"]
    assert double["reliable"] is True and double["recognized_credits"] == 0 and double["remaining_credits"] == 54
    analysis = await service(student).multi_major_options(track="경영분석")
    assert analysis["track_matches"][0]["course_matching"]["recognized_credits"] == 3  # 0508 is on that list too


async def test_unreliable_lists_say_why_instead_of_guessing():
    svc = service(SimClient(2024, "컴퓨터정보공학부", semesters=MARKETING))
    robot = (await svc.multi_major_options(track="로봇기구전공"))["track_matches"][0]["course_matching"]
    assert robot["reliable"] is False and "recognized_credits" not in robot
    assert "교육과정보다 3과목 적어요" in robot["reasons"][0]  # Daple's own list is short
    welfare = (await svc.multi_major_options(track="사회복지학"))["track_matches"][0]
    reasons = " ".join(welfare["course_matching"]["reasons"])
    assert "과목번호가 없는 과목 4개" in reasons and "학과를 정하지 못한 과목이 6개" in reasons


def test_track_courses_data():
    data = simulation.rules("track_courses")
    tracks = data["tracks"]
    assert len(tracks) == 146 and data["version"]["sources"][0]["id"] == "daple-2026-11-07"
    assert {t["type"] for t in tracks} == {"복수전공", "부전공", "연계전공", "마이크로전공"}
    assert sum(t["matching"]["reliable"] for t in tracks) == 113
    assert all(t["matching"]["reliable"] for t in tracks if t["type"] in ("복수전공", "부전공"))
    # Names, numbers, codes and department names only: no Daple prose.
    allowed = {"program_code", "name", "type", "required_credits", "basis", "version_year", "target_department",
               "course_count", "curriculum_gap_count", "matching", "courses"}
    assert all(set(t) <= allowed for t in tracks)
    assert all(len(c) == 2 and (c[0] is None or len(c[0]) == 4) for t in tracks for c in t["courses"])
    # Every 연계·마이크로전공 links to its course list; every department code is one KLAS lists, owned once.
    codes = {t["program_code"] for t in tracks}
    assert all(t["program_code"] in codes for t in simulation.rules("multi_major")["tracks"])
    klas = {c["code"]: c["name"] for c in simulation.rules("department_codes")["codes"]}
    owned = [p for v in data["department_codes"].values() for p in v["course_code_prefixes"]]
    assert len(owned) == len(set(owned)) and set(owned) <= set(klas)
    for dept, v in data["department_codes"].items():
        assert all(klas[p] == dept for p in v["klas_codes"]), dept
        assert all(klas[p] == name for p, name in v.get("older_names", {}).items()), dept
    assert data["department_codes"]["컴퓨터정보공학부"]["older_names"] == {"7220": "컴퓨터공학과"}


async def test_required_courses_are_estimated_from_my_curriculum(no_curriculum):
    no_curriculum[("경영학부", 2024)] = CURRICULUM
    out = await service(SimClient(2024, "경영학부", semesters=[{"thisYear": "2024", "hakgi": "1", "sungjukList": [
        course("회계원리", "전필"), course("조직론", "전필")]}])).graduation_outlook()
    required = next(o for o in out["other_conditions"] if o["id"] == "required_courses")
    assert required["status"] == "확인 필요"  # an estimate, not a verdict
    assert required["estimate"]["required"] == ["회계원리", "조직행동"] and required["estimate"]["not_passed"] == []
    assert required["estimate"]["estimated"] is True and "추정" in required["reason"]


def test_a_knowledge_base_that_cannot_be_read_is_no_curriculum(monkeypatch):
    from kw_mcp import knowledge

    def unreadable(department: str, admission_year: int) -> dict[str, Any]:
        raise FileNotFoundError("knowledge/faq.json")

    monkeypatch.undo()  # back to the real lookup (the autouse fixture replaced it)
    monkeypatch.setattr(knowledge, "curriculum", unreadable)
    assert simulation._curriculum("경영학부", 2024) is None
    assert simulation._curriculum(None, 2024) is None


async def test_a_type_alone_lists_its_tracks():
    out = await service(STUDENTS["2026 전자정보공과대학"]()).multi_major_options(track_type="마이크로")
    assert len(out["tracks"]) == 64 and list(out["types"]) == ["마이크로전공"]
    assert {"name": "기초전공", "operator": "지능형로봇학과 (지능형로봇혁신융합대학사업단)", "required_credits": 12,
            "courses_matchable": False} in out["tracks"]
    assert sum(t["courses_matchable"] for t in out["tracks"]) == 41
    exceptions = out["types"]["마이크로전공"]["exceptions"]
    assert {e["credits"] for e in exceptions} == {12, 9} and all("2개 이상" in e["note"] for e in exceptions)
    odd = await service(STUDENTS["2026 전자정보공과대학"]()).multi_major_options(track_type="이상한 유형")
    assert list(odd["types"]) == list(simulation.TYPES) and "알아보지 못해" in odd["notes"][0]


# --- KLAS department codes (rules/department_codes.json) ------------------------------------------

def test_department_codes_come_from_klas():
    data = simulation.rules("department_codes")
    assert {s["id"] for s in data["version"]["sources"]} == {"klas-lectureplan-2026", "klas-department-lists"}
    codes = {c["code"]: c for c in data["codes"]}
    assert len(codes) == len(data["codes"]) == 72
    # The prefixes the owner's transcript showed: 7450 and H040 are older codes of the same departments.
    assert (codes["7450"]["name"], codes["7450"]["college"], codes["7450"]["last"]) == ("지능형로봇학과", "전자정보공과대학", "2023,2")
    assert codes["H040"]["name"] == codes["I040"]["name"] == "정보융합학부" and codes["I060"]["name"] == "지능형로봇학과"
    # 2026 course lists: only the code, number and name of each course, under its own department's code.
    assert len(data["departments"]) == 44
    for d in data["departments"]:
        assert set(d) == {"name", "college", "class_code", "semesters", "course_code_prefixes", "courses"}
        assert d["course_code_prefixes"] == [d["class_code"]] and all(len(c) == 3 for c in d["courses"])
    text = json.dumps(data, ensure_ascii=False)
    assert "memberName" not in text and "telNo" not in text


async def test_an_older_department_code_still_counts():
    # 7220 was 컴퓨터공학과; the 필수과목표 lists 컴퓨터정보공학부 courses under it.
    number = simulation.daple_track(kind="복수전공", department="컴퓨터정보공학부")["courses"][0][0]
    rows = [{"thisYear": "2019", "hakgi": "1", "sungjukList": [{**course("옛 과목", "일선"), "hakjungNo": f"7220-2-{number}-01"}]}]
    out = await service(SimClient(2024, "경영학부", semesters=rows)).multi_major_options(track="컴퓨터정보공학부")
    matched = out["track_matches"][0]["double_major"]["course_matching"]
    assert [c["code"] for c in matched["recognized_courses"]] == [f"7220-2-{number}-01"]


# --- the 다전공 I applied for, in simulate_graduation ----------------------------------------------

def result_list(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"stats": True, "hakjukMap": {"kname": FAKE_NAME}, "resultList": list(rows)}


class AppliedClient(SimClient):
    """SimClient plus the 학적 reads academic_status makes and the 어학 요건."""

    def __init__(self, *args: Any, applied: Any = (), micro: Any = (), linked: Any = (), language: Any = None,
                 **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.extra = {MAJOR_APPLIED: result_list(*applied), MICRO_APPLIED: micro if isinstance(micro, Exception)
                      else result_list(*micro), LINKED_APPLIED: result_list(*linked), LEAVE_STATUS: {"statu": []},
                      LEAVE_WINDOWS: {}, LANGUAGE_REQUIREMENT: language or []}

    async def post(self, path: str, body: dict[str, Any] | None = None, **kw: Any) -> Any:
        if path in self.extra:
            self.calls.append(path)
            if isinstance(self.extra[path], Exception):
                raise self.extra[path]
            return self.extra[path]
        return await super().post(path, body, **kw)


ROBOT_MINOR = {"submajor": "부전공", "applyDate": "20261015", "organName": "인공지능융합대학", "className": "지능형로봇학과",
               "majorName": "지능형로봇학과", "finishOpt": "N"}


def coded(name: str, code: str, category: str = "일선", grade: str = "A0") -> dict[str, Any]:
    return {**course(name, category, grade=grade), "hakjungNo": code}


OWNER_LIKE = [  # 2022학번 정보융합학부 with 지능형로봇학과 courses under its old (7450) and new (I060) code
    {"thisYear": "2022", "hakgi": "1", "sungjukList": [coded("전공과목", "H040-1-3687-01", "전선")]},
    {"thisYear": "2024", "hakgi": "1", "sungjukList": [coded("로봇과목1", "7450-1-4024-01")]},
    {"thisYear": "2024", "hakgi": "2", "sungjukList": [coded("로봇과목2", "I060-2-4025-01")]},
    {"thisYear": "2026", "hakgi": "2", "sungjukList": [coded("로봇과목3", "I060-3-4026-01", grade="")]},
]


async def test_the_outlook_puts_in_my_applied_minor():
    client = AppliedClient(2022, "정보융합학부", earned=110, major=42, semesters=OWNER_LIKE, applied=[ROBOT_MINOR])
    out = await service(client).graduation_outlook()
    assert out["summary"]["plan"] == {"line": "주전공 60 + 부전공 21(지능형로봇학과)",
                                      "remaining": "주전공 18학점, 부전공 15학점 남았어요.",
                                      "note": "부전공(지능형로봇학과)은 아직 확정 전이에요."}
    [minor] = out["applied_multi_major"]
    assert (minor["type"], minor["name"], minor["status"], minor["applies_from"]) == (
        "부전공", "지능형로봇학과", "신청함(확정 전)", "2027-03-01")
    assert minor["required_credits"] == 21 and minor["recognized"]["recognized_credits"] == 6
    assert [c["code"] for c in minor["recognized"]["recognized_courses"]] == ["7450-1-4024-01", "I060-2-4025-01"]
    assert [c["code"] for c in minor["recognized"]["in_progress_courses"]] == ["I060-3-4026-01"]
    # 부전공 doesn't lower the 주전공 (2017~2024학번): 60, not the '다전공 이수시' 54.
    assert out["major_credits"]["applies"]["required"] == 60 and "부전공" in out["major_credits"]["applies"]["path"]
    assert out["disclaimer"] == simulation.GRADUATION_DISCLAIMER


async def test_double_and_linked_majors_lower_the_major_but_minors_do_not():
    double = {**ROBOT_MINOR, "submajor": "복수전공", "className": "경영학부", "majorName": "경영학전공"}
    out = await service(AppliedClient(2022, "정보융합학부", semesters=OWNER_LIKE, applied=[double])).graduation_outlook()
    assert out["summary"]["plan"]["line"] == "주전공 54 + 복수전공 45(경영학부)"
    linked = await service(AppliedClient(2022, "정보융합학부", semesters=OWNER_LIKE,
                                         linked=[{"linkmajorName": "빅데이터", "applyDate": "20250601"}])).graduation_outlook()
    assert linked["summary"]["plan"]["line"] == "주전공 54 + 연계전공 30(빅데이터)"
    # 2025학번~: any 다전공 means the 45 of '다전공 하나 이수 시'.
    later = await service(AppliedClient(2025, "행정학과", applied=[ROBOT_MINOR])).graduation_outlook()
    assert later["major_credits"]["applies"] == {"path": "다전공 하나 이수 시 주전공", "required": 45,
                                                 "status": "미충족", "remaining": 15}


async def test_confirmation_shows_once_klas_files_my_courses_under_it():
    earlier = {**ROBOT_MINOR, "applyDate": "20260210"}  # applies from 2026-03-01, already started
    rows = [{"thisYear": "2026", "hakgi": "1", "sungjukList": [coded("로봇과목1", "I060-1-4024-01", "부선")]}]
    confirmed = await service(AppliedClient(2022, "정보융합학부", semesters=rows, applied=[earlier])).graduation_outlook()
    assert confirmed["applied_multi_major"][0]["status"] == "확정"
    assert confirmed["applied_multi_major"][0]["on_transcript"]["earned"] == 3
    unclear = await service(AppliedClient(2022, "정보융합학부", applied=[earlier])).graduation_outlook()
    assert unclear["applied_multi_major"][0]["status"] == "신청함(확정 여부는 KLAS 학적에서 확인)"
    assert "plan" in unclear["summary"] and "note" not in unclear["summary"]["plan"]


async def test_micro_and_linked_rows_use_their_own_field_names():
    micro = {"micromajorName": "데이터분석전공", "micromajorOrganname": "자연과학대학", "micromajorClassname": "수학과",
             "applyDate": "20260601"}
    client = AppliedClient(2024, "경영학부", micro=[micro], linked=[{"linkmajorName": "빅데이터", "applyDate": "20260601"}])
    status = await service(client).academic_status()
    names = {(r["kind"], r["track_type"], r["name"], r.get("department")) for r in status["multi_major"]}
    assert names == {("마이크로", "마이크로전공", "데이터분석전공", "수학과"), ("연계", "연계전공", "빅데이터", None)}
    out = await service(client).graduation_outlook()
    assert [(t["type"], t["name"], t["required_credits"]) for t in out["applied_multi_major"]] == [
        ("마이크로전공", "데이터분석전공", 15), ("연계전공", "빅데이터", 30)]
    # 2024 경영학부: 54 alone, 45 with the 연계전공 (the 마이크로전공 alone wouldn't lower it).
    assert out["summary"]["plan"]["line"] == "주전공 45 + 마이크로전공 15(데이터분석전공) + 연계전공 30(빅데이터)"


async def test_unread_applications_are_said_not_hidden():
    partly = await service(AppliedClient(2024, "경영학부", applied=[ROBOT_MINOR],
                                         micro=KlasError("down"))).graduation_outlook()
    assert partly["applied_multi_major_note"] == "마이크로 신청 내역은 KLAS에서 못 읽었어요."
    assert [t["type"] for t in partly["applied_multi_major"]] == ["부전공"]
    none = await service(SimClient(2024, "경영학부")).graduation_outlook()  # every 학적 read fails
    assert none["applied_multi_major"] == "unavailable" and "plan" not in none["summary"]


@pytest.mark.parametrize(("language", "noted"), [
    ([{"daesangOpt": "Y", "passOpt": "N", "langName": "TOEIC"}], True),
    ([{"daesangOpt": "Y", "passOpt": "Y"}], False),
    ([{"daesangOpt": "N", "passOpt": "N"}], False),
    ([], False),
])
async def test_language_note_when_klas_says_target_without_a_pass(language, noted):
    client = AppliedClient(2022, "정보융합학부", language=language)
    for out in (await service(client).graduation_outlook(), await service(client).graduation_progress()):
        assert ("language_note" in out) is noted
        if noted:
            note = out["language_note"]["note"]
            assert note == simulation.LANGUAGE_NOTE and note.count("요.") <= 2
            assert "2014년" in note and "TOPIK" in note and "학과" in note
            assert set(out["language_note"]["source_ids"]) <= {"reg-hakchik", "reg-sihaeng", "web-info07"}


# --- agent, tools ---------------------------------------------------------------------------------

@pytest.mark.parametrize(("applied", "start"), [
    ("2026-10-15", "2027-03-01"), ("2026-02-10", "2026-03-01"), ("2026-04-20", "2026-09-01"),
    ("9999-12-31", None), ("99991231", None), ("1899-12-31", None), ("", None), (None, None), ("2026-13-01", None),
])
def test_applies_from_survives_sentinel_dates(applied, start):
    found = simulation._applies_from(applied)
    assert (found.isoformat() if found else None) == start


async def test_a_sentinel_apply_date_does_not_break_the_outlook():
    sentinel = {**ROBOT_MINOR, "applyDate": "99991231"}
    out = await service(AppliedClient(2022, "정보융합학부", applied=[sentinel])).graduation_outlook()
    [minor] = out["applied_multi_major"]
    assert "applies_from" not in minor and minor["status"].startswith("신청함")


def test_the_agent_knows_both_calls_with_optional_arguments():
    assert agent.CALLS["graduation_outlook"] == () and agent.CALLS["multi_major_options"] == ("track", "track_type")
    assert {"track", "track_type"} <= agent.OPTIONAL_ARGS
    assert agent.call_args("multi_major_options", {}) == {"track": None, "track_type": None}
    assert agent.call_args("multi_major_options", {"track": "빅데이터"}) == {"track": "빅데이터", "track_type": None}


async def test_the_agent_answers_both_calls():
    class Holder:
        def __init__(self, svc: KlasService) -> None:
            self._svc = svc

        async def service(self) -> KlasService:
            return self._svc

    holder = Holder(service(STUDENTS["2025 정책법학대학"]()))
    found = await agent.build_result(holder, "multi_major_options", {"track": "빅데이터", "track_type": ""})
    assert found["result"]["track_matches"][0]["name"] == "빅데이터" and found["result"]["disclaimer"] == simulation.DISCLAIMER
    outlook = await agent.build_result(holder, "graduation_outlook", {})
    assert outlook["result"]["disclaimer"] == simulation.GRADUATION_DISCLAIMER


async def test_extension_tools_answer_and_say_they_are_reference_only():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    for name in ("simulate_graduation", "explore_multi_major"):
        assert "참고용" in tools[name].description and tools[name].annotations.read_only_hint
    server.set_service(service(STUDENTS["2024 경영대학"]()))
    try:
        result = await server.mcp.call_tool("explore_multi_major", {"track": "경영분석"})
        outlook = await server.mcp.call_tool("simulate_graduation", {})
    finally:
        server.set_service(None)
    assert not result.is_error and result.structured_content["track_matches"][0]["name"] == "경영분석"
    assert not outlook.is_error and outlook.structured_content["total_credits"]["required"] == 130


# --- packaging: the rules data travels with the code ---------------------------------------------

RULES_FILES = ("rules/graduation.json", "rules/multi_major.json", "rules/track_courses.json",
               "rules/department_codes.json")


def test_rules_load_as_package_data():
    simulation.rules.cache_clear()
    assert simulation.rules("graduation")["version"]["built_at"] == "2026-11-07"
    assert len(simulation.rules("multi_major")["tracks"]) == 90 and len(simulation.rules("track_courses")["tracks"]) == 146
    # Package data ships in every wheel and .mcpb: keep each rules file small.
    for name in RULES_FILES:
        assert (ROOT / "src" / "kw_mcp" / name).stat().st_size < 256 * 1024, name


@pytest.mark.parametrize(("name", "allowed"), [
    ("src/kw_mcp/rules/graduation.json", True),
    ("src/kw_mcp/rules/multi_major.json", True),
    ("src/kw_mcp/rules/track_courses.json", True),
    ("src/kw_mcp/knowledge/index.json", True),
    ("src/kw_mcp/knowledge/curricula/2026/컴퓨터정보공학부.json", True),
    ("src/kw_mcp/rules/notes.md", False),
    ("src/kw_mcp/rules/old/graduation.json", False),
    ("src/kw_mcp/knowledge/raw/page.html", False),
    ("src/kw_mcp/knowledge/../../secrets.json", False),
    ("src/kw_mcp/other/data.json", False),
])
def test_the_bundle_allow_list_takes_the_data_files(name, allowed):
    assert (release.bundle_extras([name]) == []) is allowed


def test_staging_copies_the_rules_data(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import release as release_script
    finally:
        sys.path.pop(0)
    copied = release_script.stage_bundle(ROOT, tmp_path / "stage")
    for name in RULES_FILES:
        name = f"src/kw_mcp/{name}"
        assert name in copied and (tmp_path / "stage" / name).read_bytes() == (ROOT / name).read_bytes()


def test_signing_compares_the_data_files_with_the_wheel(tmp_path):
    key = Ed25519PrivateKey.generate()  # throwaway: never the release key
    files = {"kw_mcp/server.py": b"print('v')", "kw_mcp/rules/graduation.json": b'{"version": {}}'}

    def wheel(rules: bytes) -> Path:
        path = tmp_path / "kw_mcp-1.1.0-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as z:
            for name, data in {**files, "kw_mcp/rules/graduation.json": rules}.items():
                z.writestr(name, data)
            z.writestr("kw_mcp-1.1.0.dist-info/METADATA", "Metadata-Version: 2.4\nName: kw-mcp\nVersion: 1.1.0\n")
        return path

    bundle = tmp_path / "kw-campus.mcpb"
    with zipfile.ZipFile(bundle, "w") as z:
        z.writestr("pyproject.toml", '[project]\nname = "kw-mcp"\nversion = "1.1.0"\n')
        z.writestr("manifest.json", json.dumps({"version": "1.1.0"}))
        for name, data in files.items():
            z.writestr(f"src/{name}", data)
    assert release.sign_mcpb(bundle, key, wheel_path=wheel(files["kw_mcp/rules/graduation.json"]))["version"] == "1.1.0"
    with pytest.raises(ValueError, match="not packed from the same code"):
        release.sign_mcpb(bundle, key, wheel_path=wheel(b'{"version": {"built_at": "older"}}'))


def test_the_built_wheel_carries_the_rules_data(tmp_path):
    # uv_build packs every file under src/kw_mcp; build a copy of the project so the tree stays clean.
    project = tmp_path / "project"
    shutil.copytree(ROOT / "src" / "kw_mcp", project / "src" / "kw_mcp", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, project / name)
    env = {k: v for k, v in os.environ.items() if not k.startswith("VIRTUAL_ENV")}
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist"), "--quiet"], cwd=project, env=env,
                   check=True, capture_output=True, timeout=300)
    [built] = (tmp_path / "dist").glob("kw_mcp-*.whl")
    with zipfile.ZipFile(built) as wheel:
        for name in RULES_FILES:
            assert wheel.read(f"kw_mcp/{name}") == (ROOT / "src" / "kw_mcp" / name).read_bytes()
