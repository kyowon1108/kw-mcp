"""Aligns the 다전공 entries with Daple, the school's official 다전공 플래너, from a snapshot the owner took in their
own session (this pipeline never opens daple.kwuniv.com; fetch.py refuses the host).

Only facts are taken from the snapshot: track type, name, required credits, operator/target department, the
credit-table basis and year, and course counts. Nothing else (no prose, no course lists) is sent or stored.
Where the public sources say something else, the entry follows Daple and says so in `disagreement`.

    python apply_daple.py --snapshot /path/snapshot-2026-11-07.json --dry-run
    python apply_daple.py --snapshot /path/snapshot-2026-11-07.json --budget 45
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from build_faq import CATEGORIES, SYSTEM, _schema
from kbcommon import OUT, dump_json

DAPLE_ID = "daple-snapshot"
DAPLE_SOURCE = {"id": DAPLE_ID, "url": "https://daple.kwuniv.com", "title": "다전공 플래너(Daple) 2026-11-07 확인"}
POINTER = "공식 다전공 계획·시뮬레이션은 Daple(https://daple.kwuniv.com)에서 할 수 있습니다."
TERMS = re.compile(r"(복수전공|부전공|연계전공|마이크로|다전공|심화전공|학생설계)")
CREDIT_NEAR = re.compile(r"(복수전공|부전공|연계전공|마이크로전공)[^.]{0,30}\d+\s*학점|\d+\s*학점[^.]{0,30}"
                         r"(복수전공|부전공|연계전공|마이크로전공)")


def facts(snapshot: Path) -> list[dict]:
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    f = {name: i for i, name in enumerate(snap["fields"])}
    out = []
    for t in snap["tracks"]:
        out.append({"type": t[f["type"]], "name": t[f["name"]], "credits": t[f["requiredCredits"]],
                    "operator": t[f["operator"]], "target_department": t[f["targetDepartment"]],
                    "basis": t[f["basis"]], "year": t[f["versionYear"]], "course_count": t[f["courseCount"]]})
    return out


def _files() -> dict[Path, dict]:
    paths = [OUT / f"faq-{p}{s}.json" for _, p in CATEGORIES for s in ("", "-extra")]
    return {p: json.loads(p.read_text(encoding="utf-8")) for p in paths if p.exists()}


def affected(data: dict[Path, dict]) -> list[dict]:
    out = []
    for d in data.values():
        for e in d["entries"]:
            text = json.dumps({k: e[k] for k in ("questions", "answer", "conditions_exceptions", "how_to")},
                              ensure_ascii=False)
            if d["category"] == "다전공" or (TERMS.search(text) and CREDIT_NEAR.search(text)):
                out.append({**e, "category": d["category"]})
    return out


ASK = """The school's official 다전공 planner, Daple (https://daple.kwuniv.com, run by 기획처 대학혁신사업단), is the
standard the owner wants for 다전공 and 졸업 credit questions. Below are (1) facts from a 2026-11-07 Daple
snapshot: every track's type, name, required credits, operator, target department, which credit table it uses
(basis "admission" = the target department's table for that admission year; "curriculum" = the track's own
curriculum) and course count; (2) the knowledge-base entries that touch 다전공 credits, track names or which
credit table applies. The entries were written from public pages and regulations.

Return in `entries` every entry that needs a change, in full (same id, same fields):
- Credits, track names and the rule for which table applies must agree with Daple. Where the public sources
  said something else, keep the answer on Daple's value and say in `disagreement` what the public source says
  (e.g. "학칙 [별표 6]은 21학점, Daple은 30학점"), confidence medium.
- 복수·부전공 credits depend on the target department in Daple (e.g. 복수 법학부 36, 건축학과 99, 공학계열 54,
  인문사회 45; 부전공 21, 건축학과 45, 행정학과 30). Say that the target department's credit counts, and give
  the main values; don't list all 28 departments.
- Any answer about planning, checking or simulating a 다전공 should point to Daple with this sentence in how_to
  (or answer if it fits): "{pointer}" Use the URL only; say nothing about how Daple works inside.
- Add the source {{"source_id": "{sid}", "article": "<track or table you used>", "quote": ""}} to every entry
  whose numbers or names now rest on Daple or that points to Daple. Keep the existing sources.
- Copy only facts (names, numbers) from Daple. Keep the rest of each entry as it is (style, casual questions).
- Also add ONE new entry with id "multi-planner-daple" (category 다전공) for "다전공 시뮬레이션/계획 어디서 해?",
  unless an entry already covers it.
List each change briefly in `changes` ("<id>: before -> after"). Leave gaps and dropped empty.

(1) Daple facts:
{facts}

(2) Entries:
{entries}"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--budget", type=float, default=45.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    data = _files()
    targets = affected(data)
    fx = facts(args.snapshot)
    ask = ASK.format(pointer=POINTER, sid=DAPLE_ID, facts=json.dumps(fx, ensure_ascii=False),
                     entries=json.dumps(targets, ensure_ascii=False))
    if args.dry_run:
        print(len(targets), "entries,", len(fx), "Daple tracks,", len(ask), "chars")
        return
    from claude_client import call
    r = call(note="faq-daple-align", system=SYSTEM, content=[{"type": "text", "text": ask}], schema=_schema(),
             budget=args.budget, effort="medium", max_tokens=48000)
    fixed = {e["id"]: e for e in r["data"]["entries"]}
    for e in fixed.values():  # the Daple source is never optional on an entry that now rests on it
        if not any(s["source_id"] == DAPLE_ID for s in e["sources"]):
            e["sources"].append({"source_id": DAPLE_ID, "article": "다전공 플래너", "quote": ""})
    applied = []
    for d in data.values():
        for i, e in enumerate(d["entries"]):
            if e["id"] in fixed:
                d["entries"][i] = fixed.pop(e["id"])
                applied.append(e["id"])
    added = list(fixed.values())  # new entries (the planner pointer) go with the 다전공 extras
    multi = OUT / "faq-multi-extra.json"
    data.setdefault(multi, {"category": "다전공", "entries": [], "gaps": [], "dropped": [], "changes": []})
    data[multi]["entries"] += added
    for p, d in data.items():
        dump_json(p, d)
    dump_json(OUT / "faq-daple-result.json", {"applied": applied, "added": [e["id"] for e in added],
                                              "changes": r["data"]["changes"]})
    print("Daple: updated", len(applied), "entries, added", len(added))


if __name__ == "__main__":
    main()
