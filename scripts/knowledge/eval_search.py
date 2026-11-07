"""Search check with fresh student phrasings: Claude writes new casual questions for each entry's topic (not
copied from the entry), then kw_mcp.knowledge.search must rank the right entry in the top 3.

    python eval_search.py --budget 45            # one call writes out/search-eval-questions.json, then scores it
    python eval_search.py --score                # score again without a call
    python eval_search.py --score --augment      # add each missed question to its entry (up to 6 per entry)
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from kbcommon import KNOWLEDGE, OUT, dump_json

QUESTIONS = OUT / "search-eval-questions.json"
SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "question": {"type": "string"}},
    "required": ["id", "question"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False}


def write_questions(budget: float) -> None:
    from claude_client import call
    faq = json.loads((KNOWLEDGE / "faq.json").read_text(encoding="utf-8"))
    compact = [{"id": e["id"], "category": e["category"], "answer": e["answer"][:160], "existing": e["questions"]}
               for e in faq["entries"]]
    ask = ("Below is a Korean university FAQ: each entry's id, category, the start of its answer, and the questions "
           "it already lists. For every entry, write ONE new question a student would actually type on Everytime "
           "to get that answer - casual, short, typos and 줄임말 welcome, and NOT reusing the existing questions' "
           "wording (use different keywords where a student naturally would). Return one item per entry with its id.\n\n"
           + json.dumps(compact, ensure_ascii=False))
    r = call(note="search-eval-questions", system="You write realistic Korean student questions.",
             content=[{"type": "text", "text": ask}], schema=SCHEMA, budget=budget, effort="low", max_tokens=32000)
    dump_json(QUESTIONS, r["data"]["items"])


def score(augment: bool = False) -> dict:
    import sys

    from kbcommon import SRC
    sys.path.insert(0, str(SRC))
    from kw_mcp import knowledge

    items = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    ids = {e["id"] for e in knowledge.load()["entries"]}
    items = [i for i in items if i["id"] in ids]
    hit1 = hit3 = 0
    missed = []
    by_cat: Counter = Counter()
    miss_cat: Counter = Counter()
    for it in items:
        got = [h["id"] for h in knowledge.search(it["question"], limit=3)]
        cat = knowledge.entry(it["id"])["category"]
        by_cat[cat] += 1
        hit1 += bool(got) and got[0] == it["id"]
        if it["id"] in got:
            hit3 += 1
        else:
            missed.append({**it, "got": got})
            miss_cat[cat] += 1
    result = {"questions": len(items), "hit@1": round(hit1 / len(items), 3), "hit@3": round(hit3 / len(items), 3),
              "missed_by_category": dict(miss_cat), "missed": missed}
    if augment and missed:
        path = KNOWLEDGE / "faq.json"
        faq = json.loads(path.read_text(encoding="utf-8"))
        by_id = {e["id"]: e for e in faq["entries"]}
        added = 0
        extra_path = OUT / "faq-question-additions.json"  # build_faq.py --assemble re-applies these
        extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {}
        for m in missed:
            e = by_id[m["id"]]
            if len(e["questions"]) < 6 and m["question"] not in e["questions"]:
                e["questions"].append(m["question"])
                extra.setdefault(m["id"], []).append(m["question"])
                added += 1
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")  # atomic: readers never see half a file
        dump_json(tmp, faq)
        os.replace(tmp, path)
        dump_json(extra_path, extra)
        result["augmented"] = added
    dump_json(OUT / "search-eval-result.json", result)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=45.0)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--augment", action="store_true")
    args = ap.parse_args()
    if not args.score:
        write_questions(args.budget)
    r = score(args.augment)
    print(json.dumps({k: v for k, v in r.items() if k != "missed"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
