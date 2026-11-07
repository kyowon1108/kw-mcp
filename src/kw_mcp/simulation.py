"""Reference-only graduation and multi-major (다전공) simulation on the school's published rules.

rules/graduation.json and rules/multi_major.json were built from the 학칙, 학칙 시행세칙, the 다전공
내규 and the 학사안내 pages (docs/rules-sources.md; every rule carries its source ids). Nothing here is
an official verdict. Every answer carries the data's version, the open questions (uncertain) that
touch this student, a disclaimer and where to report a wrong rule. A requirement that KLAS's data
can't show is "확인 필요" with the reason, never a guessed pass or fail.

The inputs are what KlasService already reads: the 학적 record (only the admission year, department,
year, status and transfer credits are used; the student id never leaves this module), the grade
totals, the transcript (semesters of _grade_row courses) and the 교양 이수현황 summary. Where the
knowledge base (kw_mcp.knowledge.curriculum) has a department's curriculum, course names are matched
against it and the result is marked estimated.
"""

from __future__ import annotations

import difflib
import functools
import json
import re
import unicodedata
from importlib import resources
from typing import Any

MET, NOT_MET, CHECK, NOT_APPLICABLE = "충족", "미충족", "확인 필요", "해당 없음"
# 다전공 answers follow Daple; the graduation outlook (교양, 졸업학점) follows the 학칙 and keeps its own wording.
DISCLAIMER = "Daple(다전공 플래너)과 같은 기준으로 계산한 참고 결과입니다. 공식 판정과 신청은 Daple과 학과사무실에서 확인하세요."
GRADUATION_DISCLAIMER = "참고용 계산입니다. 공식 판정은 학교 다전공 플래너(Daple)나 학과사무실에서 확인하세요."
REPORT = "규정이 바뀌었거나 틀린 곳은 디스코드 #알림-설정의 '제보하기'(또는 /제보)로 알려 주세요."
DAPLE_BASIS = "Daple 과정 과목 목록(2026-11-07) 기준"
COURSE_MATCHING = ("Daple 과정 과목 목록(2026-11-07) 기준으로 성적표 학정번호(과목번호 4자리 + 개설 학과 코드)를 맞춥니다. "
                   "개설 학과 코드를 두 자료로 확인한 과정만 계산하고, 나머지는 course_matching.reasons에 이유가 있습니다.")
# Daple's snapshot shows one version of each 복수·부전공 target (basis admission, version_year): the one for
# the snapshot's own cohort. That cohort is 2024학번 or earlier (it shows the 전정대 targets' 2017 version, 54,
# where the 2025 table has 45), so a target's Daple value is used from its version_year to this admission
# year; other years use the official table's row of the target department (multi_major.json uncertain).
DAPLE_COHORT_MAX = 2024
_HAKJUNG = re.compile(r"^([0-9A-Za-z]{4})-\d+-(\d{4})(?:-|$)")  # KLAS 학정번호: 학과코드-학년-과목번호-분반
TYPES = ("심화전공", "복수전공", "부전공", "연계전공", "마이크로전공", "학생설계융합전공")
# Departments by college, as the 2017~2026 credit tables (graduation.json credit_tables) and the
# micro-major list name them. Old names stay so older admission years still find their row.
COLLEGES = {
    "전자정보공과대학": ("전자공학과", "전자통신공학과", "전자융합공학과", "전기공학과", "전자재료공학과",
                        "반도체시스템공학부", "지능형로봇학과"),
    "인공지능융합대학": ("컴퓨터정보공학부", "소프트웨어학부", "정보융합학부", "로봇학부"),
    "공과대학": ("건축공학과", "화학공학과", "환경공학과", "건축학과"),
    "자연과학대학": ("수학과", "전자바이오물리학과", "화학과", "스포츠융합과학과", "생활체육학과", "정보콘텐츠학과"),
    "인문사회과학대학": ("국어국문학과", "영어산업학과", "영어영문학과", "산업심리학과", "미디어커뮤니케이션학부",
                        "미디어영상학부", "동북아문화산업학부"),
    "정책법학대학": ("행정학과", "법학부", "국제학부", "자산관리학과"),
    "경영대학": ("경영학부", "국제통상학부"),
    "참빛인재대학": ("금융부동산법무학과", "게임콘텐츠학과", "스마트전기전자학과", "스포츠상담재활학과"),
    "인제니움대학": ("자율전공학부",),
}
# A department whose older credit tables list it under another college (로봇학부: 전자정보공과대학 until 2023).
FORMER_COLLEGES = {"로봇학부": ("전자정보공과대학",)}
# 2016~2023 교양 totals are given per 계열 (인문/자연/공학).
GROUPS = {"인문": ("인문사회과학대학", "정책법학대학", "경영대학"), "자연": ("자연과학대학",),
          "공학": ("전자정보공과대학", "인공지능융합대학", "공과대학")}
# 야간 (120학점제) departments: their 2020~2023 교양 isn't the 계열 total (2019's table says 30).
NIGHT = ("정보콘텐츠학과", "자산관리학과")
# Names the credit tables shorten.
_DEPARTMENT_SHORT = {"건축공": "건축공학과", "화공": "화학공학과", "환경": "환경공학과"}
_COLLEGE_SHORT = {"소프트웨어융합대학": "인공지능융합대학", "전정공대": "전자정보공과대학", "공과대": "공과대학",
                  "자연대": "자연과학대학", "경영대": "경영대학"}
# Transcript 이수구분 of each multi-major (web-info01).
TRANSCRIPT_CODES = {"복수전공": ("복필", "복선"), "부전공": ("부필", "부선"), "연계전공": ("연필", "연선"),
                    "마이크로전공": ("MD",)}
_TYPE_WORDS = (("학생설계", "학생설계융합전공"), ("심화", "심화전공"), ("복수", "복수전공"), ("부전공", "부전공"),
               ("연계", "연계전공"), ("마이크로", "마이크로전공"), ("md", "마이크로전공"), ("부", "부전공"))
_NOT_PASSED = {"F", "NP"}
WAIVER = "광운인되기는 이수하지 않아도 됩니다(2026-03-01부터). 빈 학점은 균형교양 영역의 교양선택으로 채웁니다."
WAIVER_SOURCE = {"source_ids": ["reg-hakchik", "web-info12"], "articles": {"reg-hakchik": "부칙<2025.12.17.> 제1조 단서·제2조"}}


@functools.cache
def rules(name: str) -> dict[str, Any]:
    """rules/<name>.json from the installed package, read once."""
    return json.loads(resources.files("kw_mcp").joinpath("rules", f"{name}.json").read_text(encoding="utf-8"))


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _key(text: Any) -> str:
    """A name compared leniently: NFKC, case-folded, without spaces or punctuation."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(text or "")).casefold())


def _plain(name: str) -> str:
    """'정보콘텐츠학과(야간)' -> '정보콘텐츠학과', '국제학부*' -> '국제학부'."""
    return re.sub(r"\(.*?\)|\*", "", name).strip()


def _span(spec: str) -> tuple[int, int]:
    """'2020-2023', '2026', '-2016', '2017-' or 'all' as an inclusive range of admission years."""
    if spec == "all":
        return 0, 9999
    low, dash, high = spec.partition("-")
    if not dash:
        return int(low), int(low)
    return int(low) if low else 0, int(high) if high else 9999


def _covers(spec: str, year: int | None) -> bool:
    low, high = _span(spec)
    return year is not None and low <= year <= high


def college_of(department: str | None) -> str | None:
    key = _key(_plain(department or ""))
    return next((college for college, names in COLLEGES.items() if key and key in map(_key, names)), None)


def student(record: dict[str, Any]) -> dict[str, Any]:
    """What the simulation uses from the 학적. The student id is read for its first four digits only."""
    hakbun = str(record.get("hakbun") or "")
    words = str(record.get("hakgwa") or "").split()
    department = words[0] if words else None
    transfer = any((_int(record.get(k)) or 0) > 0 for k in ("prevHakjumNum", "cultureHakjum", "majorHakjum",
                                                              "generalHakjum"))
    return {"admission_year": int(hakbun[:4]) if hakbun[:4].isdigit() else None, "college": college_of(department),
            "department": department, "year": record.get("grade"), "status": record.get("hakjukStatu"),
            "transfer": transfer}


# --- credit tables ------------------------------------------------------------------------

def _row_departments(row: dict[str, Any]) -> list[str]:
    """Departments a credit-table row covers: its department column, spelled out, or the departments
    its college column names ('건축학과(5년제)', '사과대(행정학과, 산업심리학과)')."""
    if row.get("department"):
        parts = re.split(r"[,.]", row["department"])
    else:
        parts = re.findall(r"[가-힣A-Za-z]+(?:학과|학부)", row.get("college") or "")
    return [_DEPARTMENT_SHORT.get(p, p) for p in (_plain(p) for p in parts) if p]


def _row_colleges(row: dict[str, Any]) -> list[str]:
    text = re.sub(r"\(.*?\)", "", row.get("college") or "")
    return [_COLLEGE_SHORT.get(_key(p), _key(p)) for p in text.split(",") if _key(p)]


def _cohort_fits(row: dict[str, Any], year: int) -> bool:
    cohort = re.match(r"(\d{4})학번\s*([~∼])?", row.get("cohort") or "")
    return not cohort or (year >= int(cohort[1]) if cohort[2] else year == int(cohort[1]))


def credit_table(year: int | None) -> dict[str, Any] | None:
    return next((t for t in rules("graduation")["credit_tables"] if _covers(t["admission_years"], year)), None)


def credit_row(year: int | None, college: str | None, department: str | None) -> dict[str, Any] | None:
    """The row of the admission year's credit table for this department, else for its whole college."""
    table = credit_table(year)
    if table is None or year is None:
        return None
    rows = [r for r in table.get("rows", []) if _cohort_fits(r, year)]
    key = _key(_plain(department or ""))
    for row in rows:
        if key and key in map(_key, _row_departments(row)):
            return row
    for name in (college, *FORMER_COLLEGES.get(department or "", ())):
        if name and (row := next((r for r in rows if not _row_departments(r) and _key(name) in _row_colleges(r)),
                                 None)):
            return row
    return None


def _row_label(year: int | None, row: dict[str, Any] | None) -> str | None:
    table = credit_table(year)
    if not table or not row:
        return None
    return f"{table['label']} · {row['college']}" + (f" {row['department']}" if row.get("department") else "")


# --- small helpers ------------------------------------------------------------------------

def _item(requirement: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"requirement": requirement, "status": status, **{k: v for k, v in extra.items() if v is not None}}


def _at_least(have: int, need: int | dict[str, int]) -> str:
    if isinstance(need, dict):
        return MET if have >= need["max"] else NOT_MET if have < need["min"] else CHECK
    return MET if have >= need else NOT_MET


def _short(have: int, need: int | dict[str, int]) -> int:
    return max(0, (need["min"] if isinstance(need, dict) else need) - have)


def _overall(items: list[dict[str, Any]]) -> bool | None:
    statuses = [i["status"] for i in items if i["status"] != NOT_APPLICABLE]
    if NOT_MET in statuses:
        return False
    return True if statuses and all(s == MET for s in statuses) else None


def _shown(need: int | dict[str, int] | None) -> str:
    return f"{need['min']}~{need['max']}" if isinstance(need, dict) else str(need)


def _passed(course: dict[str, Any]) -> bool:
    return not course.get("deleted") and bool(course.get("grade")) and course["grade"] not in _NOT_PASSED


def _semesters(grades: list[dict[str, Any]] | None) -> dict[str, int] | None:
    """Regular semesters (1·2학기) on the transcript: all of them, and those whose grades are all in."""
    if grades is None:
        return None
    regular = [s for s in grades if str(s.get("term")) in ("1", "2")
               and any(not c.get("deleted") for c in s.get("courses") or [])]
    done = [s for s in regular if all(c.get("grade") for c in s["courses"] if not c.get("deleted"))]
    return {"on_transcript": len(regular), "graded": len(done)}


def _group(college: str | None) -> str | None:
    return next((g for g, colleges in GROUPS.items() if college in colleges), None)


def _version(*names: str) -> dict[str, Any]:
    first = rules(names[0])["version"]
    sources: dict[str, dict[str, str]] = {}
    for name in names:
        for s in rules(name)["version"]["sources"]:
            sources.setdefault(s["id"], {"title": s["title"], "url": s["url"]})
    return {"built_at": first["built_at"], "basis": first["basis"], "sources": list(sources.values())}


def _years_in(text: str) -> set[int]:
    years: set[int] = set()
    for low, high in re.findall(r"(\d{4})\s*[~\-]\s*(\d{4})", text):
        years.update(range(int(low), int(high) + 1))
    rest = re.sub(r"\d{4}\s*[~\-]\s*\d{4}", " ", text)
    years.update(int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", rest) if 1990 <= int(y) <= 2100)
    return years


def _uncertain(name: str, year: int | None, departments: set[str], colleges: set[str],
               types: tuple[str, ...] = TYPES, tracks: set[str] | None = None) -> list[dict[str, Any]]:
    """The data's open questions that touch this student: an item naming admission years, departments,
    multi-major types or one 연계·마이크로전공 counts only when one of them is this student's (or what
    was asked: `types` shown, `tracks` found)."""
    known = {d for names in COLLEGES.values() for d in names}
    mine = {_key(d) for d in departments if d} | {_key(c) for c in colleges if c}
    out = []
    for entry in rules(name)["uncertain"]:
        item = entry["item"]
        years = _years_in(item)
        named = {d for d in known if d in item}
        if "명칭" in item:  # a renaming: the departments are in what was seen
            named = {d for d in known | set(COLLEGES) if d in entry.get("seen", "")}
        kinds = {kind for word, kind in _TYPE_WORDS if word != "부" and word in item.casefold()}
        about = [t for t in rules("multi_major")["tracks"] if any(n in item for n in (t["name"], *t.get("aliases", [])))]
        if (years and year not in years or named and not {_key(d) for d in named} & mine
                or kinds and not kinds & set(types)
                or about and not any(t["type"] in types and (tracks is None or t["name"] in tracks) for t in about)):
            continue
        out.append(entry)
    return out


def _curriculum(department: str | None, year: int | None) -> dict[str, Any] | None:
    """The knowledge base's course list (kw_mcp.knowledge.curriculum) for a department and admission
    year, or None when it has none or can't be read (it is built separately and may be missing)."""
    if not department or year is None:
        return None
    try:
        from . import knowledge

        return knowledge.curriculum(department, year)
    except (ImportError, AttributeError, OSError, ValueError, KeyError, TypeError):
        return None


def _course_keys(course: dict[str, Any]) -> set[str]:
    """A curriculum course's name and its former names (the note's '구,조직론')."""
    names = [course.get("name") or "", *re.findall(r"구\s*[,.]\s*([^;,]+)", course.get("note") or "")]
    return {_key(n) for n in names if _key(n)}


def _curriculum_ref(table: dict[str, Any]) -> dict[str, Any]:
    return {"department": table.get("department"), "admission_year": table.get("admission_year"),
            "scope": table.get("scope"), "sources": (table.get("version") or {}).get("sources")}


def _required_estimate(department: str | None, year: int | None,
                       grades: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """전필 of my department's curriculum (knowledge base) not found among my passed courses, by name."""
    table = _curriculum(department, year)
    required = [c for c in (table or {}).get("courses") or [] if c.get("type") == "전필" and c.get("name")]
    if not required or grades is None:
        return None
    passed = {_key(c.get("course")) for s in grades for c in s.get("courses") or [] if _passed(c)}
    return {"estimated": True, "required": [c["name"] for c in required],
            "not_passed": [c["name"] for c in required if not _course_keys(c) & passed],
            "curriculum": _curriculum_ref(table or {}),
            "note": "학과 교육과정 자료의 전필 과목을 성적표 과목명과 맞춰 본 추정입니다. 학년별 공식 전공필수 목록은 "
                    "학과 사무실에서 확인하세요."}


def daple_track(program_code: str | None = None, kind: str | None = None,
                department: str | None = None) -> dict[str, Any] | None:
    """A Daple course list (rules/track_courses.json) by its program code, or a 복수·부전공 by target department."""
    for track in rules("track_courses")["tracks"]:
        if program_code and track["program_code"] == program_code:
            return track
        if kind and track["type"] == kind and track.get("target_department") == department:
            return track
    return None


def course_matching(entry: dict[str, Any] | None, required: int | None,
                    grades: list[dict[str, Any]] | None) -> dict[str, Any]:
    """My transcript against one Daple course list. A course is (과목번호, 개설 학과); a KLAS row is
    'PPPP-학년-NNNN-분반' with PPPP the offering department's code. Only lists whose departments' codes two
    sources agree on are matched (track_courses.json matching); a row whose number is listed but whose
    code isn't known is shown as unconfirmed, never counted. Estimated, Daple's list as the basis."""
    if entry is None or not entry["matching"]["reliable"]:
        reasons = entry["matching"]["reasons"] if entry else ["Daple 과정 과목 목록에 이 과정이 없습니다."]
        return {"reliable": False, "reasons": reasons, "basis": DAPLE_BASIS}
    if grades is None:
        return {"reliable": True, "computed": False, "reason": "성적표를 읽지 못해 맞춰 보지 못했습니다.", "basis": DAPLE_BASIS}
    codes = rules("track_courses")["department_codes"]
    owner = {prefix: dept for dept, v in codes.items() for prefix in v["course_code_prefixes"]}
    listed = {number: dept for number, dept in entry["courses"]}  # a number appears once per list
    found: dict[str, list[dict[str, Any]]] = {"recognized": [], "in_progress": [], "unconfirmed": []}
    seen: set[str] = set()
    without_code = 0
    for semester in grades:
        for c in semester.get("courses") or []:
            if c.get("deleted") or c.get("grade") and not _passed(c):
                continue
            m = _HAKJUNG.match(str(c.get("code") or ""))
            if not m:
                without_code += 1
                continue
            prefix, number = m[1].upper(), m[2]
            if number not in listed or f"{prefix}-{number}" in seen:
                continue  # not on the list, or the same course again (a retake counts once)
            if prefix in codes[listed[number]]["course_code_prefixes"]:
                kind = "recognized" if c.get("grade") else "in_progress"
            elif prefix in owner:
                continue  # the same course number offered by another department
            else:
                kind = "unconfirmed"
            seen.add(f"{prefix}-{number}")
            found[kind].append({"course": c.get("course"), "code": c.get("code"), "credits": c.get("credits") or 0,
                                **({"in_progress": True} if not c.get("grade") else {})})
    credits = {k: sum(c["credits"] for c in v) for k, v in found.items()}
    out: dict[str, Any] = {"reliable": True, "estimated": True, "basis": DAPLE_BASIS, "required_credits": required,
                           "recognized_credits": credits["recognized"],
                           "remaining_credits": None if required is None else max(0, required - credits["recognized"]),
                           "recognized_courses": found["recognized"]}
    if found["in_progress"]:
        out["in_progress_courses"] = found["in_progress"]
        if required is not None:
            out["remaining_if_in_progress_passed"] = max(0, required - credits["recognized"] - credits["in_progress"])
    if found["unconfirmed"]:
        out["unconfirmed_courses"] = found["unconfirmed"]
        out["unconfirmed_note"] = (f"과목번호는 목록에 있지만 학정번호 앞자리(개설 학과 코드)를 확인하지 못한 과목입니다. 인정되면 남은 학점이 "
                                   f"최대 {credits['unconfirmed']}학점 줄어듭니다. Daple에서 확인하세요.")
    if without_code:
        out["rows_without_code"] = without_code
    out["note"] = ("같은 학정번호는 한 번만 셉니다. 필수과목, 과목별 인정 한도, 주전공과의 상호인정, 성적 조건은 반영하지 않았습니다."
                   + (f" 학정번호가 없는 성적표 행 {without_code}개는 비교하지 못했습니다." if without_code else ""))
    return out


def _wrap(name: str | tuple[str, ...], answer: dict[str, Any], uncertain: list[dict[str, Any]],
          disclaimer: str = DISCLAIMER) -> dict[str, Any]:
    names = (name,) if isinstance(name, str) else name
    return {**answer, "uncertain": uncertain, "version": _version(*names), "disclaimer": disclaimer, "report": REPORT}


# --- 교양 --------------------------------------------------------------------------------

def general_education_check(me: dict[str, Any], gen_ed: dict[str, Any],
                            grades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The 교양 rule of this student's admission year, checked against KLAS's 교양 이수현황 (gen_ed:
    {"required": 필수교양 칸, "balanced_by_area": {영역: 학점}}). With the transcript, a passed course
    named AI리터러시 also counts for the 2026 rule."""
    year, college = me["admission_year"], me["college"]
    areas, required = gen_ed["balanced_by_area"], gen_ed["required"]
    total = required + sum(areas.values())
    data = rules("graduation")["general_education"]
    notes = [r["rule"] for r in data["common_rules"][:2]]
    if me["transfer"]:
        reason = ("편입생은 교양이수체계·교양필수가 면제되고 교양 30학점을 이수합니다. 편입 인정 교양학점이 KLAS 교양 "
                  "이수현황 합계에 들어가는지 알 수 없어 판정하지 않습니다.")
        return {"rule": "편입생 교양 이수 기준(신입학 기준은 적용하지 않음)", "met": None,
                "items": [_item("편입생 교양 30학점", CHECK, have=total, need=30, reason=reason)],
                "note": "편입생은 교양 이수 기준이 다릅니다. 편입 인정학점을 포함한 기준은 학과·학사지원팀 졸업기준표를 확인하세요.",
                "source_ids": ["web-info12"]}
    entry = next((e for e in data["by_admission_year"] if _covers(e["admission_years"], year)), None)
    if entry is None:
        why = ("학번에서 입학 연도를 읽지 못했습니다." if year is None else
               f"{year}학번의 교양 기준표는 아직 공개 자료에 없습니다(규칙 데이터 {rules('graduation')['version']['built_at']} 기준).")
        return {"rule": "입학 연도별 교양 기준(확인하지 못함)", "met": None,
                "items": [_item("입학 연도별 총 교양학점", CHECK, have=total, reason=why)], "notes": notes}
    row_ge = (credit_row(year, college, me["department"]) or {}).get("general_education") or {}
    source = {"source_ids": entry["source_ids"], **({"articles": entry["articles"]} if entry.get("articles") else {})}
    balanced_rule = entry.get("balanced") or {}
    if balanced_rule.get("min_areas") and row_ge.get("required") is None and isinstance(row_ge.get("total"), int):
        # 참빛인재대학: the college table has 교양 30 with no 필수·균형 split.
        need = row_ge["total"]
        items = [_item(f"교양 {need}학점", _at_least(total, need), have=total, need=need, short=_short(total, need) or None),
                 _item("필수·균형교양 영역 기준", CHECK, reason=f"{college} 표에는 교양 {need}학점만 있고 필수·균형 구분이 없어 "
                                                         "영역 기준이 적용되는지 확인하지 못했습니다.")]
        return {"rule": f"교양 {need}학점({college} 표 기준)", "met": _overall(items), "items": items,
                "credits_needed": _short(total, need), "notes": notes, **source}
    if balanced_rule.get("min_areas"):
        return _structured(entry, me, required, areas, grades, notes, source)
    return _total_only(entry, me, row_ge, total, notes, source)


def _structured(entry: dict[str, Any], me: dict[str, Any], required: int, areas: dict[str, int],
                grades: list[dict[str, Any]] | None, notes: list[str], source: dict[str, Any]) -> dict[str, Any]:
    """2025·2026: balanced credits over a minimum of areas, plus the year's required part."""
    college = me["college"]
    rule, need_total = entry["balanced"], entry["total"]
    balanced, total = sum(areas.values()), required + sum(areas.values())
    taken = sum(1 for v in areas.values() if v > 0)
    unseen = [a for a in rule["areas"] if a not in areas]  # areas KLAS's table has no column for (기초학문융합)
    # Below a threshold, an area or credits KLAS can't show might still make it up: that is 확인 필요, not 미충족.
    below = NOT_MET if not unseen else CHECK
    why_unseen = (f"{'·'.join(unseen)} 영역은 KLAS 교양 이수현황의 어느 칸인지 공개 자료로 확인하지 못해 세지 않았습니다."
                  if unseen else None)
    new_required = [c["course"] for c in entry["required"] if not c.get("waived")]
    why_total = (f"{'·'.join(unseen)} 영역" + "".join(f"·{c}" for c in new_required)
                 + " 학점이 KLAS 교양 이수현황의 어느 칸에 잡히는지 확인하지 못해 합계가 실제보다 적을 수 있습니다."
                 if unseen else None)
    items = []
    for course in entry["required"]:
        name, credits = course["course"], course["credits"]
        if course.get("waived"):
            continue
        found = [c for s in grades or [] for c in s.get("courses") or [] if _passed(c) and _key(name) in _key(c.get("course"))]
        if found:
            items.append(_item(f"{name} {credits}학점(필수)", MET, have=sum(c.get("credits") or 0 for c in found),
                               basis="성적표 과목명"))
        else:
            items.append(_item(f"{name} {credits}학점(필수)", CHECK, reason=(
                f"{name}가 KLAS 교양 이수현황의 어느 칸에 잡히는지 공개 자료로 확인하지 못했습니다(필수교양 칸 {required}학점)"
                + (". 성적표에도 이 이름의 이수 과목이 없습니다." if grades is not None else ". 성적표에서 이수 여부를 확인하세요."))))
    n_areas = len(rule["areas"])
    items.append(_item(f"균형교양 {n_areas}개 영역 중 {rule['min_areas']}개 영역 이상", MET if taken >= rule["min_areas"] else below,
                       have=taken, need=rule["min_areas"], reason=why_unseen if taken < rule["min_areas"] else None))
    for label, options in (rule.get("must_include") or {}).items():
        colleges = re.search(r"\((.*?)\)", label)
        if colleges and college in [c.strip() for c in colleges[1].split(",")]:
            have = [a for a in options if areas.get(a, 0) > 0]
            items.append(_item(f"{label.split('(')[0]} 지정 영역({' 또는 '.join(options)}) 포함", MET if have else NOT_MET,
                               have=have or None))
            break
    else:
        if rule.get("must_include"):
            items.append(_item("계열별 지정 영역 포함", CHECK, reason=(
                "단과대학 계열을 알 수 없습니다(자율전공학부는 선택한 주전공 계열을 따릅니다)." if college != "인제니움대학"
                else "자율전공학부는 본인이 선택한 주전공 계열의 지정 영역을 따릅니다.")))
    items.append(_item(f"균형교양 {rule['credits']}학점", MET if balanced >= rule["credits"] else below, have=balanced,
                       need=rule["credits"], reason=why_unseen if balanced < rule["credits"] else None))
    items.append(_item(f"총 교양 {need_total}학점", MET if total >= need_total else below, have=total, need=need_total,
                       reason=why_total if total < need_total else None))
    waived = [c for c in entry["required"] if c.get("waived")]
    required_text = " + ".join(f"{c['course']} {c['credits']}학점" for c in entry["required"] if not c.get("waived"))
    text = (f"{required_text}(필수) + " if required_text else "") + (
        f"균형교양 {rule['credits']}학점({n_areas}개 영역 중 {rule['min_areas']}개 영역 이상"
        + (", 계열별 지정 영역 포함" if rule.get("must_include") else "") + ")"
        + (f" + {sum(c['credits'] for c in waived)}학점(폐지된 {waived[0]['course']} 몫, 균형교양 선택으로)" if waived else "")
        + f" = 교양 {need_total}학점")
    out = {"rule": text, "met": _overall(items), "items": items,
           "areas_needed": max(0, rule["min_areas"] - taken), "credits_needed": max(0, need_total - total),
           "balanced_credits_needed": max(0, rule["credits"] - balanced), "notes": notes, **source}
    if waived:
        out["note"] = WAIVER
        out["source_ids"] = sorted({*out["source_ids"], *WAIVER_SOURCE["source_ids"]})
        out["articles"] = {**out.get("articles", {}), **WAIVER_SOURCE["articles"]}
    if unseen:
        out["note"] = why_total
    return out


def _total_only(entry: dict[str, Any], me: dict[str, Any], row_ge: dict[str, Any], total: int, notes: list[str],
                source: dict[str, Any]) -> dict[str, Any]:
    """2024 and earlier: 광운인되기 no longer required, only the year's total 교양 credits (학칙 부칙<2025.12.17.>)."""
    year, college = me["admission_year"], me["college"]
    need: int | dict[str, int] | None = None
    basic: Any = None
    label = "총 교양"
    if row_ge.get("required_plus_balanced") is not None:  # 2016~2019: the department's 필수+균형 and 기초
        need, basic, label = row_ge["required_plus_balanced"], row_ge.get("basic"), "필수+균형 교양"
    elif isinstance(row_ge.get("total"), int):
        need = row_ge["total"]
    elif isinstance(entry.get("total"), int):
        need = entry["total"]
    elif isinstance(entry.get("total"), dict) and me["department"] not in NIGHT and (group := _group(college)):
        by_group = next((v for k, v in entry["total"].items() if k.startswith(group)), None)
        part = sum(c["credits"] for c in entry.get("required") or []) + (entry.get("balanced") or {}).get("credits", 0)
        if isinstance(by_group, int):
            need = by_group
        elif isinstance(by_group, dict) and part:  # 2020~2023 자연·공학: 필수+균형 22 + the department's 기초
            need, basic, label = part, "학과별", "필수+균형 교양"
    items = []
    if need is None:
        items.append(_item("입학 연도별 총 교양학점", CHECK, have=total, reason=(
            f"야간(120학점제) 학과의 {year}학번 교양 학점은 공개 표에 없습니다." if me["department"] in NIGHT else
            f"{year}학번 {college or '이 학과'}의 교양 학점을 공개 표에서 정하지 못했습니다(학과 졸업기준표를 확인하세요).")))
    else:
        status = _at_least(total, need)
        items.append(_item(f"{label} {_shown(need)}학점", status, have=total, need=need,
                           short=_short(total, need) if status == NOT_MET else None,
                           reason="대학영어 이수 면제(신입생 영어레벨테스트) 여부에 따라 기준이 다릅니다." if status == CHECK else None))
    if basic is not None:
        items.append(_item(f"기초교양(학과 지정) {_shown(basic)}학점" if basic != "학과별" else "기초교양(학과 지정)", CHECK,
                           need=basic if basic != "학과별" else None,
                           reason="KLAS 교양 이수현황 표(필수교양·균형교양 영역)에는 기초교양 칸이 없어 확인하지 못했습니다. "
                                  "학과 졸업기준표의 기초교양(MSC) 학점을 확인하세요."))
    text = (f"{year}학번 {label} {_shown(need)}학점" if need is not None else f"{year}학번 입학 연도별 총 교양학점") + (
        " + 학과 지정 기초교양" if basic is not None else "") + "(광운인되기는 이수하지 않아도 됨)"
    sources = sorted({*source["source_ids"], *WAIVER_SOURCE["source_ids"]})
    return {"rule": text, "met": _overall(items), "items": items,
            "credits_needed": _short(total, need) if need is not None else None,
            "note": WAIVER, "notes": notes, "source_ids": sources,
            "articles": {**source.get("articles", {}), **WAIVER_SOURCE["articles"]}}


# --- graduation outlook -------------------------------------------------------------------

def _major_paths(year: int | None, row: dict[str, Any] | None) -> list[tuple[str, Any, str | None]]:
    """(path, 주전공 학점, why it doesn't apply) for the admission year's table row."""
    major = (row or {}).get("major")
    if not isinstance(major, dict):
        return []
    advanced = row.get("advanced_major_total")
    no_advanced = "이 학과(단과대학)는 심화전공을 운영하지 않습니다(표에 '-')." if advanced is None else None
    if "without_advanced" in major:  # 2025~
        return [("다전공 하나 이수 시 주전공", major["with_multi_major"], None),
                ("심화전공(주전공 심화, 다전공 의무 충족)", advanced, no_advanced),
                ("주전공만(다전공 의무 예외자: 외국인전형·특성화고 재직자전형·체육특기자·편입생·건축학과)",
                 major["without_advanced"], None)]
    paths = [("단일전공", major["single"], None)]
    if "with_multi_major" in major:
        paths.append(("복수전공·연계전공 이수 시(부·마이크로·학생설계융합전공은 단일전공 학점)", major["with_multi_major"], None))
    if "advanced_major_total" in row:
        paths.append(("심화전공", advanced, no_advanced))
    return paths


def _other_conditions(me: dict[str, Any], grades: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    year, department, college = me["admission_year"], me["department"], me["college"]
    semesters = _semesters(grades)
    by_id = {c["id"]: c for c in rules("graduation")["other_conditions"]}
    out = []

    def add(cid: str, status: str, **extra: Any) -> None:
        c = by_id[cid]
        out.append({"id": cid, "rule": c["rule"], "status": status, **{k: v for k, v in extra.items() if v is not None},
                    "source_ids": c["source_ids"], **({"articles": c["articles"]} if c.get("articles") else {})})

    need = 10 if department == "건축학과" else 8
    if me["transfer"]:
        add("semesters", CHECK, reason="편입생은 편입 학년에 따라 4학기 또는 6학기 이상 등록입니다. 편입 학년은 KLAS 자료로 알 수 없습니다.")
    elif semesters is None:
        add("semesters", CHECK, reason="성적표를 읽지 못해 등록 학기 수를 세지 못했습니다.")
    else:
        have = semesters["on_transcript"]
        add("semesters", MET if have >= need else NOT_MET, have=have, need=need,
            basis="성적표에 있는 정규학기 수(이번 학기 포함). 교환학생·학점교류 학기가 따로 있으면 다를 수 있습니다.")
    estimate = _required_estimate(department, year, grades)
    add("required_courses", CHECK, reason=(
        "학과별·학년별 전공필수 공식 목록이 KLAS 자료에 없습니다. estimate는 학과 교육과정 자료로 추정한 것이니 학과 사무실에서 "
        "확인하세요." if estimate else
        "학과별·학년별 전공필수 목록이 KLAS 자료와 공개 자료에 없어 확인하지 못했습니다. 학과 사무실에서 확인하세요."),
        estimate=estimate)
    add("thesis", CHECK, reason="졸업논문(또는 학과가 정한 대체 요건) 통과 여부는 KLAS 자료에 없습니다.")
    if year is None:
        add("multi_major_mandatory", CHECK, reason="입학 연도를 알 수 없습니다.")
    elif year < 2025:
        add("multi_major_mandatory", NOT_APPLICABLE, reason="2025학번부터의 졸업요건입니다.")
    elif department == "건축학과" or me["transfer"]:
        add("multi_major_mandatory", NOT_APPLICABLE, reason="건축학과·편입생은 다전공 의무 예외입니다.")
    else:
        add("multi_major_mandatory", CHECK, reason="다전공 신청·이수 현황은 KLAS 학적 자료에 없습니다. 외국인전형·특성화고 "
                                                   "재직자전형·체육특기자도 예외입니다. explore_multi_major로 선택지를 보세요.")
    if college in GROUPS["공학"]:
        add("engineering_accreditation", CHECK, reason="공학인증 프로그램 이수 여부와 학과 기준은 KLAS 자료에 없습니다.")
    add("english_certification", NOT_APPLICABLE, reason="영어졸업인증제는 폐지돼 졸업요건이 아닙니다.")
    return out


def graduation_outlook(record: dict[str, Any], totals: dict[str, Any], grades: list[dict[str, Any]] | None,
                       gen_ed: dict[str, Any]) -> dict[str, Any]:
    """Where this student stands on every graduation requirement the published rules give: total and
    major credits for the admission year and department, 교양 by the corrected rules, and the other
    conditions. Reference only."""
    me = student(record)
    year, college, department = me["admission_year"], me["college"], me["department"]
    row = credit_row(year, college, department)
    earned = _int(totals.get("chidukHakjum"))
    in_progress = sum(c.get("credits") or 0 for s in grades or [] for c in s.get("courses") or []
                      if not c.get("deleted") and not c.get("grade"))
    need = (row or {}).get("graduation_total")
    if need is None:
        credits = _item("졸업학점", CHECK, earned=earned, reason=(
            "입학 연도·학과에 맞는 졸업학점 표를 찾지 못했습니다." if row is None else "이 학과는 표에 졸업학점이 따로 없습니다."))
    elif earned is None:
        credits = _item("졸업학점", CHECK, required=need, reason="KLAS 취득 학점을 읽지 못했습니다.")
    elif me["transfer"]:
        credits = _item("졸업학점", CHECK, required=need, earned=earned, reason=(
            "편입 인정학점이 KLAS 취득 학점에 들어가는지 KLAS 자료로 알 수 없습니다. 학과 사무실에서 확인하세요."))
    else:
        credits = _item("졸업학점", MET if earned >= need else NOT_MET, required=need, earned=earned,
                        remaining=max(0, need - earned))
    if in_progress:
        credits["in_progress"] = in_progress
    credits["note"] = "성적 처리가 끝난 과목만 합산했습니다(F·NP·삭제 제외). in_progress는 이번 학기 성적이 아직 없는 학점입니다."
    credits["source_ids"] = ["reg-hakchik", "reg-sihaeng", "web-info12"]

    major_earned = _int(totals.get("majorChidukHakjum"))
    paths = []
    for path, required, why in _major_paths(year, row):
        if required is None:
            paths.append(_item(path, NOT_APPLICABLE, reason=why))
        elif major_earned is None:
            paths.append(_item(path, CHECK, required=required, reason="KLAS 전공 취득 학점을 읽지 못했습니다."))
        else:
            paths.append(_item(path, MET if major_earned >= required else NOT_MET, required=required,
                               remaining=max(0, required - major_earned)))
    if not paths:
        reason = ("자율전공학부는 본인이 선택한 주전공 기준을 따릅니다." if department == "자율전공학부"
                  else "입학 연도·학과에 맞는 주전공 학점 표를 찾지 못했습니다.")
        paths.append(_item("주전공 학점", CHECK, reason=reason))
    major = {"earned": major_earned, "paths": paths, "source_ids": ["web-info12", "web-info11", "reg-damajor-isu"],
             "note": "KLAS 전공 취득 학점 기준입니다. 다전공 과목이 여기에 섞여 잡히는지는 KLAS 자료로 구분되지 않을 수 있고, "
                     "학과 전공필수 이수 여부는 other_conditions의 required_courses를 보세요."}
    ge = general_education_check(me, gen_ed, grades)
    others = _other_conditions(me, grades)
    summary: dict[str, list[str]] = {MET: [], NOT_MET: [], CHECK: []}
    for label, status in [("졸업학점", credits["status"]),
                          ("교양", MET if ge["met"] else NOT_MET if ge["met"] is False else CHECK),
                          *((o["id"], o["status"]) for o in others)]:
        if status in summary:
            summary[status].append(label)
    answer = {
        "student": {**{k: me[k] for k in ("admission_year", "college", "year", "status", "transfer")},
                    "department": record.get("hakgwa")},
        "table": _row_label(year, row),
        "total_credits": credits,
        "major_credits": major,
        "general_education": {**gen_ed, "total": gen_ed["required"] + sum(gen_ed["balanced_by_area"].values()),
                              "check": ge},
        "other_conditions": others,
        "summary": summary,
    }
    return _wrap("graduation", answer, _uncertain("graduation", year, {department or ""}, {college or ""}),
                 GRADUATION_DISCLAIMER)


# --- multi-major --------------------------------------------------------------------------

def _type_of(text: str | None) -> str | None:
    key = _key(text)
    if not key:
        return None
    return next((kind for word, kind in _TYPE_WORDS if (key == word if word == "부" else word in key)), None)


def _track_key(name: str) -> str:
    key = _key(re.sub(r"\(.*?\)", "", name))
    for suffix in ("연계전공", "마이크로전공", "전공"):
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)]
    return key


def _bucket(value: Any, year: int | None) -> Any:
    """A per-period text ({"2017-2024": …, "2025-2026": …}) for this admission year."""
    if not isinstance(value, dict):
        return value
    return next((v for k, v in value.items() if _covers(k, year)), None)


def _completed_major(kind: str, year: int | None, row: dict[str, Any] | None) -> tuple[Any, str | None]:
    """주전공 학점 that applies when this multi-major is completed, and why it is unknown."""
    major = (row or {}).get("major")
    if not isinstance(major, dict):
        return None, ("자율전공학부는 본인이 선택한 주전공 기준을 따릅니다." if row else
                      "입학 연도·학과에 맞는 주전공 학점 표를 찾지 못했습니다.")
    if kind == "심화전공":
        return row.get("advanced_major_total"), (None if "advanced_major_total" in row else
                                                 "이 입학 연도 표에는 심화전공 학점이 없습니다.")
    if "without_advanced" in major or kind in ("복수전공", "연계전공") and "with_multi_major" in major:
        return major["with_multi_major"], None
    if "with_multi_major" in major:
        return major["single"], None
    return major.get("single"), "이 입학 연도 표에는 다전공 이수 시 주전공 학점이 따로 없어 전공 학점을 그대로 보였습니다."


def target_credits(kind: str, department: str, year: int | None) -> dict[str, Any]:
    """복수·부전공 이수학점 with `department` as the target, as Daple counts it: the target department's
    row (not mine), in the version for my admission year. Daple's value for the years its version is
    known to cover (version_year .. DAPLE_COHORT_MAX), else the official table's row of the target."""
    daple = next((t for t in rules("multi_major")["targets"] if t["type"] == kind and t["department"] == department), None)
    row = credit_row(year, college_of(department), department)
    official = (row or {}).get({"복수전공": "double_major", "부전공": "minor"}[kind])
    if daple and year is not None and daple["version_year"] <= year <= DAPLE_COHORT_MAX:
        out = {"required_credits": daple["required_credits"],
               "basis": f"Daple 대상 학과 기준(입학연도 버전 {daple['version_year']})", "source_ids": daple["source_ids"]}
        if official is not None and official != daple["required_credits"]:
            out["official_table"] = {"required_credits": official, "table": _row_label(year, row)}
        return out
    if official is not None:
        out = {"required_credits": official, "basis": f"{_row_label(year, row)} · 대상 학과 행",
               "source_ids": ["web-info12", "web-info11"]}
        if daple and daple["required_credits"] != official:
            out["daple"] = {"required_credits": daple["required_credits"], "version_year": daple["version_year"],
                            "note": "Daple 스냅샷에 나온 버전의 값입니다. 이 입학 연도에도 같은 버전인지는 확인하지 못했습니다."}
        return out
    if daple:
        return {"required_credits": daple["required_credits"], "source_ids": daple["source_ids"],
                "basis": f"Daple 대상 학과 기준(버전 {daple['version_year']}). 입학 연도 표에는 이 학과 행이 없습니다."}
    return {"required_credits": None, "basis": "Daple 대상 학과 목록과 입학 연도 표에서 이 학과를 찾지 못했습니다."}


def _type_credits(kind: str, data: dict[str, Any], year: int | None, row: dict[str, Any] | None) -> tuple[Any, str]:
    column = {"심화전공": "advanced_major_total", "복수전공": "double_major", "부전공": "minor", "연계전공": "linked_major",
              "마이크로전공": "micro_major", "학생설계융합전공": "student_designed_major"}[kind]
    if row is not None and column in row:
        return row[column], "입학 연도 표의 내 학과(단과대학) 행"
    rc = data["required_credits"]
    if year is not None and year < 2017 and rc.get("before_2017"):
        return rc["before_2017"], "2016학번 이전 기준"
    return rc.get("default", rc.get("range")), "다전공 내규 기본값"


def _earned_codes(kind: str, grades: list[dict[str, Any]] | None) -> dict[str, int] | None:
    codes = TRANSCRIPT_CODES.get(kind)
    if not codes or grades is None:
        return None
    courses = [c for s in grades for c in s.get("courses") or [] if not c.get("deleted") and c.get("category") in codes]
    return {"earned": sum(c.get("credits") or 0 for c in courses if _passed(c)),
            "in_progress": sum(c.get("credits") or 0 for c in courses if not c.get("grade"))}


def _type_summary(kind: str, me: dict[str, Any], row: dict[str, Any] | None,
                  grades: list[dict[str, Any]] | None) -> dict[str, Any]:
    data = rules("multi_major")["types"][kind]
    year = me["admission_year"]
    by_department = None
    if kind in ("복수전공", "부전공"):  # the target department's row (Daple), never mine
        by_department = {t["department"]: target_credits(kind, t["department"], year)["required_credits"]
                         for t in rules("multi_major")["targets"]
                         if t["type"] == kind and _key(t["department"]) != _key(me["department"])}
        values = [v for v in by_department.values() if isinstance(v, int)]
        credits = {"min": min(values), "max": max(values)} if values else None
        basis = "대상 학과(복수·부전공으로 이수하는 학과)에 따라 다릅니다(Daple 기준). by_department 또는 track에 학과 이름을 주세요."
    else:
        credits, basis = _type_credits(kind, data, year, row)
    major, major_why = _completed_major(kind, year, row)
    out: dict[str, Any] = {
        "definition": data["definition"], "degree": data["degree"],
        "required_credits": credits, "required_credits_basis": basis,
        "major_credits_if_completed": major,
        **({"major_credits_note": major_why} if major_why else {}),
        "major_credit_reduction": _bucket(data.get("major_credit_reduction"), year),
        "mutual_recognition": data["mutual_recognition"],
        "eligibility": data.get("eligibility", []), "other": data.get("other", []),
        "source_ids": data["source_ids"], "articles": data.get("articles", {}),
    }
    if by_department is not None:
        out["by_department"] = by_department
    if notes := data["required_credits"].get("notes"):
        out["notes"] = notes
    if exceptions := data["required_credits"].get("exceptions"):
        out["exceptions"] = exceptions
    if kind == "심화전공" and (me["department"] == "자율전공학부" or row is not None and credits is None):
        out["available"] = False
        out["unavailable_reason"] = ("자율전공학부는 심화전공을 고를 수 없습니다(학과 진입 후 그 학과 심화전공)."
                                     if me["department"] == "자율전공학부" else "이 학과(단과대학)는 심화전공을 운영하지 않습니다(표에 '-').")
    if (earned := _earned_codes(kind, grades)) is not None:
        out["on_transcript"] = {**earned, "codes": list(TRANSCRIPT_CODES[kind]),
                                "note": "성적표 이수구분으로 더한 값입니다. 신청 전에 일반선택으로 들은 과목은 신청 후 다전공 학점으로 "
                                        "인정될 수 있어 여기 빠져 있을 수 있습니다."}
    return out


def _department_track(name: str, me: dict[str, Any], grades: list[dict[str, Any]] | None) -> dict[str, Any]:
    """복수·부전공(및 내 학과면 심화전공) as a department the student named."""
    year = me["admission_year"]
    college = college_of(name)
    out: dict[str, Any] = {"name": name, "type": "학과(복수전공·부전공 대상)", "college": college}
    if _key(name) == _key(me["department"]):
        out["available"] = False
        out["unavailable_reason"] = "본인 소속 학과는 복수·부전공으로 이수할 수 없습니다. 주전공을 더 이수하려면 심화전공입니다."
        out["advanced_major"] = (credit_row(year, college, name) or {}).get("advanced_major_total")
        return out
    types = rules("multi_major")["types"]
    for kind, label in (("복수전공", "double_major"), ("부전공", "minor")):
        credits = target_credits(kind, name, year)
        entry = daple_track(kind=kind, department=name)
        out[label] = {**credits, "mutual_recognition_max": types[kind]["mutual_recognition"]["max_credits"],
                      **({"program_code": entry["program_code"]} if entry else {}),
                      "course_matching": course_matching(entry, credits["required_credits"], grades)}
    return out


def _linked_credits(track: dict[str, Any], year: int | None) -> Any:
    if track.get("required_credits") is not None:
        return track["required_credits"]
    detail = (track.get("credits_detail") or {}).get("by_admission_year") or []
    return next((d["credits"] for d in detail if _covers(d["admission_years"], year)), None)


def _track_detail(track: dict[str, Any], me: dict[str, Any], row: dict[str, Any] | None,
                  grades: list[dict[str, Any]] | None) -> dict[str, Any]:
    kind, year = track["type"], me["admission_year"]
    sources = {s["id"]: s for s in rules("multi_major")["version"]["sources"]}
    operator_department = (track.get("operator") or "").split()[0] if track.get("operator") else ""
    out: dict[str, Any] = {"name": track["name"], "type": kind, "operator": track.get("operator"),
                           "program_code": track.get("program_code")}
    if track.get("aliases"):
        out["aliases"] = track["aliases"]
    if kind == "연계전공":
        participants = track.get("participants") or ""
        out.update({"participants": participants, "required_credits": _linked_credits(track, year),
                    "required_courses": track.get("required_courses"),
                    "mutual_recognition_max": track.get("mutual_recognition_max"),
                    "mutual_recognition_condition": rules("multi_major")["types"][kind]["mutual_recognition"]["condition"],
                    "my_department_participates": bool(me["department"]) and me["department"] in participants})
        if detail := track.get("credits_detail"):
            out["credits_detail"] = detail
    else:
        out.update({"college": track.get("college"), "required_credits": track.get("required_credits"),
                    "offered_credits": track.get("offered_credits"), "mutual_recognition_max": 0})
        if track.get("offered_credits_note"):
            out["offered_credits_note"] = track["offered_credits_note"]
        if me["department"] and _key(operator_department) == _key(me["department"]):
            out["available"] = False
            out["unavailable_reason"] = "본인이 소속한 학과(부)의 마이크로전공은 이수할 수 없습니다."
    out["major_credits_if_completed"] = _completed_major(kind, year, row)[0]
    if track.get("notes"):
        out["notes"] = track["notes"]
    source = sources.get(track.get("source_id"))
    out["source"] = {"title": source["title"], "url": source["url"]} if source else None
    out["listed_as_of"] = track.get("listed_as_of")
    out["course_matching"] = course_matching(daple_track(program_code=track.get("program_code")),
                                             out["required_credits"], grades)
    return out


def find_tracks(query: str, kind: str | None = None) -> tuple[list[dict[str, Any]], list[str], str | None]:
    """Tracks (연계·마이크로) or departments (복수·부·심화) named by `query`, leniently: spaces,
    punctuation and a '연계전공'/'전공' suffix don't matter, and a track's former names (aliases) count.
    Returns (exact or single matches as {"track": …} or {"department": …}, other candidates' names, the
    type the query itself says)."""
    said = _type_of(query) if _key(query).endswith(("연계전공", "마이크로전공")) else None
    kind = kind or said
    q = _track_key(query)
    if not q:
        return [], [], kind
    tracks = [t for t in rules("multi_major")["tracks"] if kind in (None, t["type"])]
    keys = {id(t): {_track_key(n) for n in (t["name"], *t.get("aliases", []))} for t in tracks}
    departments = [] if kind in ("연계전공", "마이크로전공", "학생설계융합전공") else sorted(
        {d for names in COLLEGES.values() for d in names})
    exact = [{"track": t} for t in tracks if q in keys[id(t)]]
    exact += [{"department": d} for d in departments if _key(d) == q or _track_key(d) == q]
    if exact:
        return exact, [], kind
    partial = [{"track": t} for t in tracks if any(q in k or len(q) >= 2 and k in q for k in keys[id(t)])]
    partial += [{"department": d} for d in departments if len(q) >= 2 and q in _key(d)]
    if len(partial) == 1:
        return partial, [], kind
    if partial:
        return [], [p["track"]["name"] if "track" in p else p["department"] for p in partial], kind
    names = {k: t["name"] for t in tracks for k in keys[id(t)]} | {_key(d): d for d in departments}
    close = difflib.get_close_matches(q, list(names), n=5, cutoff=0.5)
    return [], [names[c] for c in close], kind


def _eligibility(me: dict[str, Any], semesters: dict[str, int] | None) -> list[dict[str, Any]]:
    """The two application conditions, checked against the 학적 status and the transcript's semesters."""
    out = []
    for rule in rules("multi_major")["common_rules"]:
        if rule["rule"].startswith("신청 자격"):  # 내규 제4조: 2개 학기 이상 이수
            if me["transfer"]:
                status, extra = MET, {"reason": "편입생은 편입학기부터 신청할 수 있습니다."}
            elif semesters is None:
                status, extra = CHECK, {"reason": "성적표를 읽지 못해 이수 학기를 세지 못했습니다."}
            else:
                status = MET if semesters["graded"] >= 2 else NOT_MET
                extra = {"have": semesters["graded"], "need": 2, "basis": "성적이 모두 나온 정규학기 수"}
        elif rule["rule"].startswith("신청 대상"):  # 학사안내·공지: 재학생, 총 재학 8학기 이하
            state = str(me.get("status") or "")
            if "휴학" in state:
                status, extra = NOT_MET, {"reason": "휴학생은 신청할 수 없습니다."}
            elif semesters is None or not state:
                status, extra = CHECK, {"reason": "학적 상태나 재학 학기를 읽지 못했습니다."}
            elif semesters["on_transcript"] > 8:
                status, extra = CHECK, {"have": semesters["on_transcript"], "reason": (
                    "'총 재학 8학기 이하'는 학사안내·공지에만 있고 다전공 내규에는 없습니다. 교육지원팀에 확인하세요.")}
            else:
                status = MET if semesters["graded"] >= 2 or me["transfer"] else NOT_MET
                extra = {"have": semesters["on_transcript"], "basis": "학적 상태와 성적표 정규학기 수(이번 학기 포함)"}
        else:
            continue
        out.append({"rule": rule["rule"], "status": status, **extra, "source_ids": rule["source_ids"],
                    **({"articles": rule["articles"]} if rule.get("articles") else {})})
    return out


def multi_major_options(record: dict[str, Any], grades: list[dict[str, Any]] | None = None,
                        track: str | None = None, track_type: str | None = None) -> dict[str, Any]:
    """다전공 types this student could take, as Daple counts them: 복수·부전공 credits from the target
    department's row, the 주전공 학점 that would then apply, eligibility and limits; with `track`, that
    연계·마이크로전공 or department, with my transcript matched against its Daple course list where the
    departments' course codes are confirmed (course_matching; estimated). Reference only."""
    me = student(record)
    year, department, college = me["admission_year"], me["department"], me["college"]
    row = credit_row(year, college, department)
    data = rules("multi_major")
    notes = []
    kind = _type_of(track_type) if track_type else None
    if track_type and kind is None:
        notes.append(f"'{track_type}'은(는) 다전공 유형으로 알아보지 못해 모든 유형을 보여 줍니다({'·'.join(TYPES)}).")
    asked = (track or "").strip()
    found, candidates, said = find_tracks(asked, kind) if asked else ([], [], kind)
    kind = kind or said
    mandatory = next(c for c in rules("graduation")["other_conditions"] if c["id"] == "multi_major_mandatory")
    answer: dict[str, Any] = {
        "student": {**{k: me[k] for k in ("admission_year", "college", "year", "status", "transfer")},
                    "department": record.get("hakgwa")},
        "table": _row_label(year, row),
        "mandatory": {
            "applies": None if year is None else year >= 2025 and department != "건축학과" and not me["transfer"],
            "rule": mandatory["rule"], "exceptions": mandatory["exceptions"],
            "note": "심화전공 70학점(참빛인재대학 60)도 다전공 의무를 채웁니다. 다전공 신청·이수 현황은 KLAS 학적 자료에 없습니다.",
            "source_ids": mandatory["source_ids"], "articles": mandatory["articles"]},
        "eligibility": _eligibility(me, _semesters(grades)),
        "limits": [{"rule": r["rule"], "source_ids": r["source_ids"], **({"articles": r["articles"]} if r.get("articles")
                                                                         else {})}
                   for r in data["common_rules"] if not r["rule"].startswith(("신청 자격", "신청 대상", "다전공 종류"))],
    }
    # Types shown: the asked type, else the types of the tracks found, else all six.
    kinds: list[str] = [kind] if kind else []
    track_departments: set[str] = set()
    if asked:
        answer["track_query"] = asked
        details = []
        for match in found:
            if "track" in match:
                details.append(_track_detail(match["track"], me, row, grades))
                track_departments.add(str(match["track"].get("operator") or "").split(" ")[0])
                matched = [match["track"]["type"]]
            else:
                details.append(_department_track(match["department"], me, grades))
                track_departments.add(match["department"])
                own = _key(match["department"]) == _key(department)
                matched = ["심화전공"] if own else ["복수전공", "부전공"]
            kinds += [k for k in matched if not kind and k not in kinds]
        answer["track_matches"] = details
        if not details:
            answer["track_candidates"] = candidates
            answer["track_note"] = ("이 이름이 여러 전공에 걸립니다. track_candidates 중 하나로 다시 물어보세요."
                                    if candidates and any(_track_key(asked) in _track_key(c) for c in candidates) else
                                    "다전공 목록(연계전공·마이크로전공, 학과)에서 이 이름을 찾지 못했습니다."
                                    + (" track_candidates는 비슷한 이름입니다." if candidates else ""))
    elif kind in ("연계전공", "마이크로전공"):
        answer["tracks"] = [{"name": t["name"], "operator": t.get("operator"),
                             "required_credits": _linked_credits(t, year) if kind == "연계전공" else t.get("required_credits"),
                             "courses_matchable": bool((daple_track(program_code=t.get("program_code")) or {})
                                                       .get("matching", {}).get("reliable"))}
                            for t in data["tracks"] if t["type"] == kind]
        answer["tracks_note"] = (f"{kind} {len(answer['tracks'])}개(목록 {data['tracks'][0]['listed_as_of']} 기준). "
                                 "track에 이름을 주면 자세히 봅니다.")
    shown = tuple(k for k in TYPES if k in kinds) or TYPES
    answer["types"] = {t: _type_summary(t, me, row, grades) for t in shown}
    answer["course_matching"] = COURSE_MATCHING + ("" if asked else " track에 과정이나 학과 이름을 주면 내 성적표와 맞춰 봅니다.")
    if notes:
        answer["notes"] = notes
    named = {m["track"]["name"] for m in found if "track" in m} if asked else None
    uncertain = _uncertain("multi_major", year, {department or "", *track_departments}, {college or ""}, shown, named)
    return _wrap(("multi_major", "graduation"), answer, uncertain)
