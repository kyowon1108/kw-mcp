"""The three HWP annexes the rules worker couldn't read, structured by Claude and checked against rules/*.json.

    학칙 [별표 6] 입학년도별/단과대학(학과)별 이수학점 안내      (FILE_SEQ 3092)
    다전공 이수에 관한 내규 [별표1] 연계전공별 이수학점 및 학위명  (FILE_SEQ 3086)
    교양교육 운영 규정 [별표2] 교양교과목 분류                   (FILE_SEQ 2708)

The HWP text comes from kw_mcp.attachments (cell by cell, one line each); Claude rebuilds the tables.

    python build_rules_tables.py --dry-run
    python build_rules_tables.py --budget 45
"""

from __future__ import annotations

import argparse
import datetime
import json

from kbcommon import KNOWLEDGE, OUT, SRC, TEXT, dump_json, load_sources

CHECKED_AT = "2026-11-07"
ANNEXES = ["annex-hakchik-6", "annex-damajor-1", "annex-gyoyang-2"]

S = {"type": "string"}
BLOCK = {"type": "object", "properties": {
    "section": S, "admission_years": S, "first_year": {"type": "integer"}, "last_year": {"type": "integer"},
    "transfer_students_included": S,
    "general_education_system": {"type": "array", "items": S},
    "columns": {"type": "array", "items": S},
    "rows": {"type": "array", "items": {"type": "array", "items": S}},
    "notes": {"type": "array", "items": S}},
    "required": ["section", "admission_years", "first_year", "last_year", "transfer_students_included",
                 "general_education_system", "columns", "rows", "notes"], "additionalProperties": False}
SCHEMA = {"type": "object", "properties": {
    "annex6": {"type": "object", "properties": {
        "title": S, "revisions": {"type": "array", "items": S},
        "blocks": {"type": "array", "items": BLOCK},
        "general_notes": {"type": "array", "items": S}},
        "required": ["title", "revisions", "blocks", "general_notes"], "additionalProperties": False},
    "linked_majors": {"type": "object", "properties": {
        "title": S, "revisions": {"type": "array", "items": S},
        "rows": {"type": "array", "items": {"type": "object", "properties": {
            "name": S, "credits": {"type": "integer"}, "degree": S, "note": S},
            "required": ["name", "credits", "degree", "note"], "additionalProperties": False}},
        "notes": {"type": "array", "items": S}},
        "required": ["title", "revisions", "rows", "notes"], "additionalProperties": False},
    "gyoyang_classification": {"type": "object", "properties": {
        "title": S, "revisions": {"type": "array", "items": S},
        "rows": {"type": "array", "items": {"type": "object", "properties": {
            "core_competency": S, "area": S, "course_group": S, "classification": S},
            "required": ["core_competency", "area", "course_group", "classification"],
            "additionalProperties": False}},
        "notes": {"type": "array", "items": S}},
        "required": ["title", "revisions", "rows", "notes"], "additionalProperties": False},
    "crosscheck": {"type": "array", "items": {"type": "object", "properties": {
        "item": S, "rules_json": S, "annex": S, "status": {"type": "string", "enum": [
            "confirms", "corrects", "adds", "conflicts"]}, "note": S},
        "required": ["item", "rules_json", "annex", "status", "note"], "additionalProperties": False}}},
    "required": ["annex6", "linked_majors", "gyoyang_classification", "crosscheck"], "additionalProperties": False}

SYSTEM = """You turn text extracted from Korean HWP regulation annexes into exact JSON tables. The extractor
printed table cells one per line, row by row, left to right; merged cells appear once. Rebuild each table
faithfully: copy every number exactly as written (keep "45(39*)", "30～51", "-", "교양이수체계 참조"); use "" for
a column the table doesn't have. Never guess a value that isn't in the text; if a cell is ambiguous, keep the
literal text and explain in note. Korean for all text values."""

ASK = """Three annexes follow (as documents), then excerpts of this project's existing rules JSON (built from
the web pages, not from these annexes).

1. annex6 ([별표 6]): one block per numbered section (1., 2., ..., 16.). first_year/last_year are admission
   years (use 0 for an open end such as "95학년도 이전" → first_year 0, last_year 1995; "2026학년도 신입생부터" →
   last_year 0). Put the 교양 이수체계 description of that block, condensed, in general_education_system, one
   string per point. columns: the credit table's column names, flattened left to right (e.g. "단과대학",
   "학과", "교양(필수포함)", "주전공 단일전공 이수시", "주전공 다전공 이수시", "심화전공", "복수전공", "부전공",
   "졸업이수학점"); rows: one array of cell strings per college/department line, same order as columns, with
   merged cells repeated into every row they cover.
2. linked_majors ([별표1]): every 연계전공 with credits and 학위명. The table is two columns side by side
   (가나다순); credits cells are merged where blank, so infer each row's credits from the table layout only
   where the layout clearly shows it, and say so in note.
3. gyoyang_classification ([별표2]): 3대 중점역량 → 4대 영역 → 12개 교과목군 → 교과목 분류.
4. crosscheck: compare the annexes with the rules JSON excerpts. One item per finding: where the annex confirms a
   rules JSON value, corrects it, adds something it lacks (e.g. degree names), or conflicts. Be specific (which
   admission year, which department, which numbers). Include: the 2016-2024 교양 change in [별표 6] section 14
   versus the JSON's 광운인되기 exemption note; linked-major credits; 2024 교양 필수/균형 split; 지능형로봇학과;
   architecture; 참빛인재대학; anything else you see."""


# Claude saw the annexes and the JSON, not the 학칙 body. Its 부칙<2025.12.17.> 제2조 waives 광운인되기 for every
# admission year up to 2025, which settles the items below.
RESOLUTIONS = {
    "2016~2024학년도 입학생 필수교양 변경(광운인되기)":
        "검토 결과: 별표 6의 14항은 '광운인되기를 뺀 나머지 필수교양'을 면제한 앞선 변경이고, 학칙 부칙<2025.12.17.> "
        "제2조(2026-03-01 적용)가 2025학년도 이전 입학자의 광운인되기까지 면제했습니다(웹 bachelor_info12도 같음). 둘을 "
        "합치면 2016~2025학번은 필수교양 없이 총 교양학점만 채우면 되므로 rules JSON의 면제 표기가 현행과 맞습니다. 별표 "
        "본문만 보면 광운인되기가 필수로 남아 보이는 점은 별표가 부칙을 반영하지 않은 것으로 봅니다.",
    "2025학년도 광운인되기":
        "검토 결과: 별표 6의 15항은 2025학년도 원래 체계(광운인되기 1 + 균형 30)입니다. 학칙 부칙<2025.12.17.> 제2조의 "
        "'2025학년도 이전 입학자'에 2025학번이 들어가므로 광운인되기는 면제되고 총 31학점만 채우면 됩니다. rules JSON이 "
        "현행과 맞습니다.",
    "2024학년도 교양 필수/균형 구분":
        "검토 결과: 별표의 13/18은 원래 체계이고, 웹의 '필수 1 + 균형 30'은 14항 변경(광운인되기 외 필수 면제)을 반영한 "
        "표기입니다. 현행 적용은 부칙까지 더해 '필수 없음, 총 31학점'입니다.",
    "2020~2023학년도 교양 이수체계":
        "검토 결과: 필수 13 + 균형 9는 원래 체계, JSON의 균형 21은 14항 변경을 반영한 현행 표기라 구조 차이는 "
        "설명됩니다. 공학 기초교양 상한(별표 27, JSON 24)과 공학 계 상한(49 대 46)은 숫자가 실제로 달라 확인이 필요합니다.",
}


def _rules_excerpt() -> str:
    rules = SRC / "kw_mcp" / "rules"
    g = json.loads((rules / "graduation.json").read_text(encoding="utf-8"))
    m = json.loads((rules / "multi_major.json").read_text(encoding="utf-8"))

    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("source_ids", "source_id", "also_source_ids",
                                                                  "articles", "listed_as_of")}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o
    part = {
        "graduation.credit_tables": strip(g.get("credit_tables")),
        "graduation.general_education": strip(g.get("general_education")),
        "graduation.uncertain": strip(g.get("uncertain")),
        "multi_major.types.연계전공": strip(m["types"].get("연계전공")),
        "multi_major.linked_tracks": [{"name": t["name"], "required_courses": t.get("required_courses"),
                                       "required_credits": t.get("required_credits"),
                                       "mutual_recognition_max": t.get("mutual_recognition_max")}
                                      for t in m["tracks"] if t["type"] == "연계전공"],
        "multi_major.uncertain": strip(m.get("uncertain")),
    }
    return json.dumps(part, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=45.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    titles = {s["id"]: s for s in load_sources()}
    texts = {a: (TEXT / f"{a}.txt").read_text(encoding="utf-8") for a in ANNEXES}
    excerpt = _rules_excerpt()
    if args.dry_run:
        print({k: len(v) for k, v in texts.items()}, "rules excerpt", len(excerpt), "chars")
        return
    from claude_client import call, doc_block
    content = [doc_block(f"[{a}] {titles[a]['title']}", texts[a]) for a in ANNEXES]
    content.append(doc_block("rules/*.json excerpts (this project's web-page-based data)", excerpt))
    content.append({"type": "text", "text": ASK})
    r = call(note="rules-tables", system=SYSTEM, content=content, schema=SCHEMA, budget=args.budget,
             effort="medium", max_tokens=64000)
    data = r["data"]
    sources = [{"id": a, "title": titles[a]["title"], "url": titles[a]["url"], "format": "HWP",
                "read_with": "kw_mcp.attachments.extract_text", "checked_at": CHECKED_AT} for a in ANNEXES]
    for c in data["crosscheck"]:  # human review, keyed by the item names this run produced (2026-11-07)
        if c["item"] in RESOLUTIONS:
            c["resolution"] = RESOLUTIONS[c["item"]]
    doc = {"version": {"built_at": datetime.date.today().isoformat(), "sources": sources,
                       "note": "HWP 별표를 표로 다시 짠 참고 자료입니다. 숫자는 원문 그대로이며, 실제 사정은 교육지원팀이 정합니다.",
                       "review_note": "crosscheck는 Claude가 별표와 rules JSON 발췌만 보고 만든 비교입니다. 학칙 부칙까지 본 "
                                      "사람 검토 결과는 resolution 필드에 따로 적었습니다(2026-11-07)."},
           **data}
    dump_json(KNOWLEDGE / "rules_tables.json", doc)
    dump_json(OUT / "rules-tables-final.json", doc)
    print("rules_tables.json written;", len(data["annex6"]["blocks"]), "blocks,",
          len(data["linked_majors"]["rows"]), "linked majors,", len(data["crosscheck"]), "crosschecks")


if __name__ == "__main__":
    main()
