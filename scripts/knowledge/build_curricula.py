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
}

# majors with their own www course table; their 필수과목표 is the parent 학부's, used for codes only
PARENTS = {
    "지능시스템전공": "로봇학부", "인터랙티브미디어커뮤니케이션전공": "미디어커뮤니케이션학부",
    "전략커뮤니케이션전공": "미디어커뮤니케이션학부", "문화콘텐츠개발전공": "동북아문화산업학부",
    "기업법무전공": "법학부", "과학기술법무전공": "법학부", "국제법무전공": "법학부", "빅데이터경영전공": "경영학부",
    "국제금융전공": "국제통상학부", "글로벌비즈니스전공": "국제통상학부",
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
    names = list(dict.fromkeys(list(curr) + list(xls)))
    out = []
    for name in names:
        base = re.sub(r"\(.*", "", name).strip()
        parent = PARENTS.get(base)
        out.append({"department": base, "curr": curr.get(name), "must": xls.get(parent or base), "parent": parent,
                    "slug": SLUGS.get(base, re.sub(r"[^a-z0-9]+", "-", base.encode("ascii", "ignore").decode()))})
    return out


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
    hay = _norm(a + b)
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
    todo = {k: v for k, v in texts.items() if k not in done and re.search(r"[A-Za-z]{4,}", v)
            and not re.search(r"[가-힣]{6,}.*[가-힣]{6,}", v)}
    if not todo:
        return
    ask = ("Translate each text into natural Korean (합니다체 not needed; short declarative notes). Keep course "
           "names, codes and numbers exactly. (A) = www 교육과정 페이지, (B) = 필수과목표. Return every key.\n\n"
           + json.dumps(todo, ensure_ascii=False))
    r = call(note="curr-korean", system="You translate curriculum notes into Korean precisely.",
             content=[{"type": "text", "text": ask}], schema=KO_SCHEMA, budget=budget, effort="low",
             max_tokens=32000)
    dump_json(map_path, {**done, **{i["key"]: i["ko"] for i in r["data"]["items"]}})


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
            c["basis"] = ko.get(f"{d['slug']}|basis|{c['admission_year']}|{c['scope']}", c["basis"])
        data["notes"] = [ko.get(f"{d['slug']}|note|{i}", n) for i, n in enumerate(data.get("notes", []))]
        curricula, stats = validate(d, data)
        sources = []
        for sid in (d["curr"], d["must"]):
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
