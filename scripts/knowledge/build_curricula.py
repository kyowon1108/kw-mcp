"""Department curricula: the www 교육과정 tab (current course table) + the 필수과목표 (required courses by
calendar year and grade, with 학정번호), structured by Claude per department and then checked locally.

Every course code Claude returns must appear in that department's 필수과목표 text and every course name in one of
the two documents; anything else is dropped and counted in `validation`.

    python build_curricula.py --dry-run
    python build_curricula.py --budget 45 [--only 소프트웨어학부] [--workers 4]
    python build_curricula.py --assemble     # out/curr-*.json -> src/kw_mcp/knowledge/curricula/
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import datetime
import json
import re

from extract import decode_html
from kbcommon import KNOWLEDGE, OUT, RAW, TEXT, dump_json, load_sources

CHECKED_AT = "2026-11-07"
FIRST_ADMISSION = 2019
CURRENT_YEAR = 2026

# department -> ascii slug for file names
SLUGS = {
    "전자공학과": "electronic-engineering", "전자통신공학과": "electronics-communication",
    "전자융합공학과": "electronic-convergence", "전기공학과": "electrical-engineering",
    "전자재료공학과": "electronic-materials", "반도체시스템공학부": "semiconductor-systems",
    "컴퓨터정보공학부": "computer-information", "소프트웨어학부": "software", "정보융합학부": "information-convergence",
    "로봇학부": "robotics", "정보제어·지능시스템전공": "info-control-intelligent-systems",
    "지능형로봇학과": "intelligent-robot", "건축공학과": "architectural-engineering",
    "화학공학과": "chemical-engineering", "환경공학과": "environmental-engineering", "건축학과": "architecture",
    "수학과": "mathematics", "전자바이오물리학과": "electronic-bio-physics", "화학과": "chemistry",
    "스포츠융합과학과": "sports-convergence-science", "정보콘텐츠학과": "information-contents",
    "국어국문학과": "korean-language-literature", "영어산업학과": "english-industry",
    "미디어커뮤니케이션학부": "media-communication", "산업심리학과": "industrial-psychology",
    "동북아문화산업학부": "northeast-asian-culture-industry", "행정학과": "public-administration", "법학부": "law",
    "국제학부": "international-studies", "자산관리학과": "asset-management", "경영학부": "business-administration",
    "국제통상학부": "international-trade", "금융부동산법무학과": "finance-real-estate-law",
    "게임콘텐츠학과": "game-contents", "스마트전기전자학과": "smart-electrical-electronics",
    "스포츠상담재활학과": "sports-counseling-rehabilitation",
    "지능시스템전공": "intelligent-systems-major", "인터랙티브미디어커뮤니케이션전공": "interactive-media-major",
    "전략커뮤니케이션전공": "strategic-communication-major", "문화콘텐츠개발전공": "culture-contents-major",
    "기업법무전공": "corporate-law-major", "과학기술법무전공": "science-technology-law-major",
    "국제법무전공": "international-law-major", "빅데이터경영전공": "big-data-business-major",
    "국제금융전공": "international-finance-major", "글로벌비즈니스전공": "global-business-major",
    "글로벌코리아전공": "global-korea-major",
}

# majors with their own www course table; their 필수과목표 is the parent 학부's, used for codes only
PARENTS = {
    "지능시스템전공": "로봇학부", "인터랙티브미디어커뮤니케이션전공": "미디어커뮤니케이션학부",
    "전략커뮤니케이션전공": "미디어커뮤니케이션학부", "문화콘텐츠개발전공": "동북아문화산업학부",
    "기업법무전공": "법학부", "과학기술법무전공": "법학부", "국제법무전공": "법학부", "빅데이터경영전공": "경영학부",
    "국제금융전공": "국제통상학부", "글로벌비즈니스전공": "국제통상학부",
}

# Departments whose course table is not on a www 교육과정 tab the discovery step links (round 5): the (A) source
# to use, further documents shown to Claude and searched by the local name check, images shown to Claude only,
# and what to ask for instead of the usual items 1-2.
EXTRA_A = {"글로벌코리아전공": "web-law06-4", "지능형로봇학과": "robot-courses-2026"}
EXTRA_DOCS = {"지능형로봇학과": ["robot-courses-2025", "robot-admission"]}
IMAGES = {"지능형로봇학과": [("robot-edu-image", "robot-edu-system")]}  # (raw image id, source id cited)
EXTRA_ASK = {
    "글로벌코리아전공": """(A) is the 국제학부 글로벌코리아전공 page's 교육과정 tab. Its table has rows for two majors;
use only the 글로벌코리아 전공 rows. The table gives 학년 and 1학기/2학기 course names only: no 학정번호, credits or
이수구분, and no year. Return one curriculum, admission_year 2026, scope "full", every course in those rows
(a cell with two names separated by "/" is two courses; keep each name as written). code "", credits "",
type "", year_level from 학년, term from the column. In basis say the page has no year, so it is taken as the
current curriculum, and that credits and 이수구분 are not given. Note in notes that the page's 국제지역학전공 rows
differ from the 국제학부 교육과정 page, so the page may not be up to date.""",
    "지능형로봇학과": """(A) is the 2026학년도 지능형로봇학과 교과목 표 and (A2) the 2025학년도 one, from the
department's site (share.kw.ac.kr). The department has no freshman intake: students enter by 전공선택/전과 or
take its courses for 마이크로전공 modules. The tables list 과정 (초급/중급/고급), 모듈, 표준교과목명,
개설교과목명 and 개설 학기, by 학년도 (the year the table applies to), not by admission year. The image is the
department's 교육과정체계 diagram (no year on it): credits per course and the semesters each 과정 is meant for.
Return two curricula, both scope "full": admission_year 2026 from (A) and admission_year 2025 from (A2).
List each 개설교과목명 once (it repeats across modules). code "" (no 학정번호 anywhere). credits: from the table
when it says (n학점), else from the image when the same course name is there, else "". type "".
year_level "". term "1" or "2" when the table gives one semester, "" when it says 1,2학기 or adds a winter
term. note: 과정, the modules it counts for, and the 개설 학기 as written (e.g. "중급 · 로봇기구/로봇전장 ·
1,2학기"). In basis say: the 학년도 table is used for that admission year because the department publishes
tables by 학년도 only; credits not in the table were read from the 교육과정체계 image (undated). In notes,
record the 전과 rule from the 진학안내 page (60 credits: 초급·중급·고급 12 each plus two more 중급/고급 modules),
the 마이크로전공 completion rule printed under (A2), and that the image shows course names not in the tables.""",
}

SCHEMA = {"type": "object", "properties": {
    "department": {"type": "string"}, "college": {"type": "string"},
    "curricula": {"type": "array", "items": {"type": "object", "properties": {
        "admission_year": {"type": "integer"},
        "scope": {"type": "string", "enum": ["full", "required_only"]},
        "basis": {"type": "string"},
        "courses": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
        "required": ["admission_year", "scope", "basis", "courses"], "additionalProperties": False}},
    "notes": {"type": "array", "items": {"type": "string"}}},
    "required": ["department", "college", "curricula", "notes"], "additionalProperties": False}

SYSTEM = """You structure a Korean university department's curriculum documents into exact JSON. Use only the
documents. Never invent a course, a 학정번호 (course code) or a credit value. Copy course names as written,
without the "(구, ...)" old-name note (put that note in the course's note field instead)."""

ASK = """Department: {dept} ({college}). Documents above:
(A) the department's 교육과정 page on www.kw.ac.kr - the current course table (학년, 학기, 이수구분, 교과목명, 시수,
    학점, 비고). {a_status}
(B) the department's 필수과목표 - required courses by CALENDAR year (rows) and grade (column blocks: 학정번호,
    과목명, 이수구분, 1학기 학점, 2학기 학점). The row for year Y lists what a student in grade g had to take in
    year Y, so a student admitted in year A took grade g's required courses from row A+g-1. {b_status}

Return `curricula` with:
1. admission_year {cur}, scope "full" - only if (A) exists: every course in (A). Treat (A) as the current
   curriculum and say so in basis. Fill the code from (B) when the same course (same name, ignoring old-name
   notes) appears there; otherwise code "".
2. admission years {first}..{last}, scope "required_only" - from (B) with the diagonal rule: grade g from row
   A+g-1, only rows up to {cur}; say in basis which grades are missing because their year is in the future,
   and if (B) has no rows for some years. Include 전필 and any 교필/기필/필수 rows (B) lists for this
   department. If (B) covers several departments or majors, use only this department's rows and say so.
   Skip an admission year entirely if (B) gives nothing for it.
Each course is an array of 7 strings: [code, name, credits, type, year_level, term, note] - credits like "3",
type as written (전필/전선/교필/기필/...), year_level "1"-"5" or "" , term "1" or "2" or "" (계절/unknown),
note: 비고, old names, track notes, or "".
In notes, record anomalies: one code used for two courses, years missing from (B), names in (B) not in (A),
majors/tracks inside the department, required courses whose credits differ between (A) and (B)."""


def _xls_map() -> dict[str, str]:
    """department name (before any parenthesis) -> must-2026-NN source id, from the 필수과목 page table."""
    h = decode_html((RAW / "web-info02.html").read_bytes())
    out = {}
    for m in re.finditer(r'<td>([^<]+)</td>\s*<td><a href="/ko/life/(must_2026_\d+)\.xlsx?', h):
        name = re.sub(r"\(.*", "", m.group(1)).strip()
        out[name] = m.group(2).replace("_", "-")
    # The page links two departments to one file (금융부동산법무학과 -> the 국제학부 sheet). Keep a shared file
    # only for the department its text actually names.
    for sid in {v for v in out.values() if list(out.values()).count(v) > 1}:
        text = _text(sid)
        names = [k for k, v in out.items() if v == sid]
        best = max(names, key=text.count)
        for k in names:
            if k != best:
                del out[k]
    return out


def departments() -> list[dict]:
    xls = _xls_map()
    curr = {s["department"]: s["id"] for s in load_sources() if s["id"].startswith("curr-")}
    names = list(dict.fromkeys(list(curr) + list(xls) + list(EXTRA_A)))
    out = []
    for name in names:
        base = re.sub(r"\(.*", "", name).strip()
        parent = PARENTS.get(base)
        out.append({"department": base, "curr": curr.get(name) or EXTRA_A.get(base), "must": xls.get(parent or base),
                    "parent": parent,
                    "slug": SLUGS.get(base, re.sub(r"[^a-z0-9]+", "-", base.encode("ascii", "ignore").decode()))})
    return out


def load_meta(sid: str) -> dict:
    return next(s for s in load_sources() if s["id"] == sid)


def _text(sid: str | None) -> str:
    if not sid:
        return ""
    p = TEXT / f"{sid}.txt"
    return p.read_text(encoding="utf-8").replace('id="jwxe_main_content">', "").strip() if p.exists() else ""


def run_dept(d: dict, budget: float) -> dict:
    from claude_client import call, doc_block
    a, b = _text(d["curr"]), _text(d["must"])
    if "[표]" not in a:
        a = ""
    content = []
    if a:
        content.append(doc_block(f"(A) {d['department']} 교육과정 (www)", a))
    if b:
        content.append(doc_block(f"(B) {d.get('parent') or d['department']} 필수과목표", b[:60000]))
    for i, sid in enumerate(EXTRA_DOCS.get(d["department"], [])):
        label = "(A2)" if i == 0 else f"({sid})"
        content.append(doc_block(f"{label} {load_meta(sid)['title']}", _text(sid)))
    for raw_id, _cited in IMAGES.get(d["department"], []):
        path = next(p for p in RAW.glob(f"{raw_id}.*") if p.suffix in (".png", ".jpg"))
        media = "image/png" if path.suffix == ".png" else "image/jpeg"
        content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                    "data": base64.b64encode(path.read_bytes()).decode()}})
    if d["department"] in EXTRA_ASK:
        content.append({"type": "text", "text": f"Department: {d['department']}.\n\n{EXTRA_ASK[d['department']]}\n\n"
                        "Each course is an array of 7 strings: [code, name, credits, type, year_level, term, note]."})
        r = call(note=f"curr-{d['slug']}", system=SYSTEM, content=content, schema=SCHEMA, budget=budget,
                 effort="low", max_tokens=32000)
        return r["data"]
    ask = ASK.format(dept=d["department"], college="", cur=CURRENT_YEAR, first=FIRST_ADMISSION, last=CURRENT_YEAR,
                     a_status="" if a else "(A) is not available for this department.",
                     b_status="" if b else "(B) is not available for this department.")
    if d.get("parent"):
        ask += (f"\n\nThis is a major inside {d['parent']}, and (B) is {d['parent']}'s table. Return only item 1 "
                f"(scope full from (A)); use (B) only to fill codes. Skip item 2.")
    content.append({"type": "text", "text": ask})
    r = call(note=f"curr-{d['slug']}", system=SYSTEM, content=content, schema=SCHEMA, budget=budget,
             effort="low", max_tokens=32000)
    return r["data"]


def _norm(s: str) -> str:
    s = re.sub(r"\(\s*구\s*[,.].*?\)", "", s)
    return re.sub(r"[\s·・\-_,.()（）]", "", s).lower()


def validate(d: dict, data: dict) -> tuple[list[dict], dict]:
    a, b = _text(d["curr"]), _text(d["must"])
    hay = _norm(a + b + "".join(_text(sid) for sid in EXTRA_DOCS.get(d["department"], [])))
    codes_in_b = set(re.findall(r"[A-Z0-9]{3,5}-\d-\d{4}|\d{3}\(\d\)\d{2}|\d{4,5}", b))
    stats = {"dropped_unknown_name": 0, "cleared_unknown_code": 0, "courses": 0}
    curricula = []
    for c in data["curricula"]:
        courses = []
        for row in c["courses"]:
            row = (row + [""] * 7)[:7]
            code, name, credits, ctype, year_level, term, note = (x.strip() for x in row)
            if not name or _norm(name) not in hay:
                stats["dropped_unknown_name"] += 1
                continue
            if code and code not in b:
                stats["cleared_unknown_code"] += 1
                code = ""
            courses.append({"code": code or None, "name": name, "credits": _num(credits), "type": ctype,
                            "year_level": _int(year_level), "term": _int(term), "note": note or None})
        stats["courses"] += len(courses)
        if courses:
            curricula.append({"admission_year": c["admission_year"], "scope": c["scope"], "basis": c["basis"],
                              "courses": courses})
    stats["codes_in_source"] = len(codes_in_b)
    return curricula, stats


def _num(s: str):
    try:
        v = float(s)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def _int(s: str):
    try:
        return int(s)
    except ValueError:
        return None


KO_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"key": {"type": "string"}, "ko": {"type": "string"}},
    "required": ["key", "ko"], "additionalProperties": False}}}, "required": ["items"], "additionalProperties": False}


def _english(text: str) -> bool:
    """Mostly English prose (Korean course names inside it are fine), not a Korean note with a code or two."""
    words = [w for w in re.findall(r"[A-Za-z]{3,}", text) if w not in ("required_only", "full", "scope", "ECTS")]
    return len(words) >= 4


def korean(budget: float) -> None:
    """One call that turns every basis/notes string the per-department calls wrote in English into Korean."""
    from claude_client import call
    texts = {}
    for d in departments():
        p = OUT / f"curr-{d['slug']}.json"
        data = json.loads(p.read_text(encoding="utf-8")).get("data") if p.exists() else None
        if not data:
            continue
        for c in data["curricula"]:
            texts[f"{d['slug']}|basis|{c['admission_year']}|{c['scope']}"] = c["basis"]
        for i, n in enumerate(data.get("notes", [])):
            texts[f"{d['slug']}|note|{i}"] = n
    map_path = OUT / "curr-ko-map.json"
    done = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {}
    todo = {k: v for k, v in texts.items() if k not in done and _english(v)}
    if not todo:
        return
    ask = ("Translate each text into natural Korean (합니다체 not needed; short declarative notes). Keep course "
           "names, codes and numbers exactly. Write (A) as '교육과정 표' and (B) as '필수과목표'. Return every key.\n\n"
           + json.dumps(todo, ensure_ascii=False))
    r = call(note="curr-korean", system="You translate curriculum notes into Korean precisely.",
             content=[{"type": "text", "text": ask}], schema=KO_SCHEMA, budget=budget, effort="low",
             max_tokens=32000)
    dump_json(map_path, {**done, **{i["key"]: i["ko"] for i in r["data"]["items"]}})


# The per-department calls wrote basis/notes in the prompt's own terms ((A)/(B), required_only, "지시에 따라 …
# 생략함"). Shipped text uses plain words instead.
PLAIN = [
    (re.compile(r"(요청|지시)에 따라\s*"), ""),
    (re.compile(r"\s*\(항목 ?2\)"), ""),
    (re.compile(r"(\d{4})학번 required_only는 ?(.*?)생략함"), r"\1학번은 \2필수과목 목록을 따로 두지 않음"),
    (re.compile(r"\(A\)의 (scope-)?full 교육과정만 반환함\.?"), "2026 현행 전체 표만 둠."),
    (re.compile(r"\(A\)의 (scope-)?full 교육과정만 반환하고,?"), "2026 현행 전체 표만 두고,"),
    (re.compile(r"\(A\) 기반 2026 full 교육과정만 작성하고"), "2026 현행 전체 표만 두고"),
    (re.compile(r"\(B\)의 required_only 교육과정은"), "입학연도별 필수과목 목록은"),
    (re.compile(r"required_only (교육과정|항목)"), "입학연도별 필수과목 목록"),
    (re.compile(r"required_only는"), "필수과목 목록은"),
    (re.compile(r"required_only를"), "필수과목 목록을"),
    (re.compile(r"required_only"), "필수과목 목록"),
    (re.compile(r"필수과목 목록(은|을) (모두 )?(생략함|작성하지 않음)"), "필수과목 목록은 따로 두지 않음"),
    (re.compile(r"(학번|입학생)은 생략함"), r"\1은 필수과목 목록을 따로 두지 않음"),
    (re.compile(r"(\d{4}) full 교육과정"), r"\1 현행 전체 표"),
    (re.compile(r"\(B\) 필수과목표"), "필수과목표"),
    (re.compile(r"\(A2\)"), "2025학년도 표"),
    (re.compile(r"\(A\)"), "교육과정 표"),
    (re.compile(r"\(B\)"), "필수과목표"),
]


def plain(text: str) -> str:
    for pat, rep in PLAIN:
        text = pat.sub(rep, text)
    return re.sub(r"\s{2,}", " ", text).strip()


def assemble() -> None:
    meta = {s["id"]: s for s in load_sources()}
    ko_path = OUT / "curr-ko-map.json"
    ko = json.loads(ko_path.read_text(encoding="utf-8")) if ko_path.exists() else {}
    target = KNOWLEDGE / "curricula"
    index = {"version": {"built_at": datetime.date.today().isoformat(), "checked_at": CHECKED_AT},
             "departments": [], "unavailable": []}
    for d in departments():
        p = OUT / f"curr-{d['slug']}.json"
        if not p.exists():
            index["unavailable"].append({"department": d["department"], "reason": "자료 없음 또는 구조화 실패"})
            continue
        data = json.loads(p.read_text(encoding="utf-8")).get("data")
        if not data:
            index["unavailable"].append({"department": d["department"], "reason": "구조화 실패"})
            continue
        for c in data["curricula"]:
            c["basis"] = plain(ko.get(f"{d['slug']}|basis|{c['admission_year']}|{c['scope']}", c["basis"]))
        data["notes"] = [plain(ko.get(f"{d['slug']}|note|{i}", n)) for i, n in enumerate(data.get("notes", []))]
        curricula, stats = validate(d, data)
        sources = []
        cited = [d["curr"], d["must"], *EXTRA_DOCS.get(d["department"], []),
                 *(c for _, c in IMAGES.get(d["department"], []))]
        for sid in cited:
            if sid and sid in meta:
                sources.append({"title": meta[sid]["title"], "url": meta[sid]["url"], "checked_at": CHECKED_AT})
        by_year: dict[int, list[dict]] = {}
        for c in curricula:
            by_year.setdefault(c["admission_year"], []).append(c)
        for year, group in by_year.items():
            # One file per year: the full course table if there is one, the required-only list attached to it.
            group.sort(key=lambda c: c["scope"] != "full")
            main, rest = group[0], group[1:]
            dump_json(target / f"{d['slug']}-{year}.json", {
                "department": d["department"], "admission_year": year, "scope": main["scope"],
                "basis": main["basis"], "courses": main["courses"],
                **({"also": [{"scope": c["scope"], "basis": c["basis"], "courses": c["courses"]} for c in rest]}
                   if rest else {}),
                "sources": sources, "checked_at": CHECKED_AT})
        index["departments"].append({"department": d["department"], "slug": d["slug"],
                                     "admission_years": sorted(by_year),
                                     "scopes": {str(y): [c["scope"] for c in g] for y, g in sorted(by_year.items())},
                                     "notes": data.get("notes", []),
                                     "validation": stats, "sources": sources})
        if not curricula:
            index["unavailable"].append({"department": d["department"], "reason": "검증을 통과한 과목 없음"})
    dump_json(target / "index.json", index)
    print(len(index["departments"]), "departments,", len(index["unavailable"]), "unavailable")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=45.0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--korean", action="store_true", help="translate English basis/notes to Korean (one call)")
    args = ap.parse_args()
    if args.korean:
        korean(args.budget)
        return
    if args.assemble:
        assemble()
        return
    depts = [d for d in departments() if not args.only or d["department"] in args.only]
    if args.dry_run:
        for d in depts:
            a, b = _text(d["curr"]), _text(d["must"])
            print(f"{d['department']}\t{d['slug']}\tA={d['curr']}({len(a)}, table={'[표]' in a})\t"
                  f"B={d['must']}({len(b)})")
        return
    todo = [d for d in depts if (_text(d["curr"]) or _text(d["must"])) and not (OUT / f"curr-{d['slug']}.json").exists()]
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_dept, d, args.budget): d for d in todo}
        for f in cf.as_completed(futs):
            d = futs[f]
            try:
                data = f.result()
                print(d["department"], sum(len(c["courses"]) for c in data["curricula"]), "courses", flush=True)
            except Exception as e:  # noqa: BLE001 - one failed department must not stop the rest
                print(d["department"], "FAILED", type(e).__name__, str(e)[:200], flush=True)


if __name__ == "__main__":
    main()
