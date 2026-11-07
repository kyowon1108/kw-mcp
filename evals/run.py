"""Run the Everytime-question eval: answer each question with the tool-using agent, grade it, and
write results under evals/results/round<N>/.

    uv run --frozen --with anthropic --with 'botocore[crt]' --with boto3 python evals/run.py --round 1
    ... python evals/run.py --round 2 --dry-run      # what round 2 would re-run, and its estimated cost
    ... python evals/run.py --round 2                # re-run failing cases and changed categories
    ... python evals/run.py --round 1 --summary      # rebuild summary.md from results.jsonl only

Round 1 runs every question and keeps a reserve of the budget for round 2. Round 2 re-runs the
round-1 failures plus every case in a category whose tools changed (a new tool, or a tool whose
name/description/schema changed, among the tools that category expects or used), cheapest-first
within the remaining budget, and carries the other round-1 rows over unchanged.

Per (case, round): traces/<id>_rep0.json (the conversation), answers/<id>.json (the agent run, so a
crash after answering re-grades without re-answering), one results.jsonl row once graded, and an
errors.jsonl row per failed attempt (failure class, usage if billed). Resume skips graded ids.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import harness, judge, llm

EVALS = Path(__file__).resolve().parent
QUESTIONS = EVALS / "questions.jsonl"
RESULTS = EVALS / "results"
CASE_TIMEOUT_S = 900.0
ROUND1_RESERVE_USD = 10.0
SITE_FIRST = ("첨부·이미지 공지 읽기", "학교 공지 찾기", "학과 공지", "장학")
CATEGORIES = ("마감·할 일", "휴강·강의실 변경", "시험", "출석", "성적·재수강", "장학", "졸업요건", "다전공",
              "수강신청·정정·포기", "휴학·복학", "학식", "셔틀·기숙사·도서관", "학교 공지 찾기", "학과 공지", "첨부·이미지 공지 읽기")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_questions(path: Path = QUESTIONS) -> list[dict[str, Any]]:
    return read_jsonl(path)


# --- one case -----------------------------------------------------------------------------------

async def run_case(api: Any, tools: harness.Toolset, case: dict[str, Any], out: Path, catalog: str,
                   args: argparse.Namespace, round_no: int) -> dict[str, Any] | None:
    cid = case["id"]
    answer_file = out / "answers" / f"{cid}.json"
    started = time.monotonic()
    if answer_file.exists():
        run = json.loads(answer_file.read_text(encoding="utf-8"))
    else:
        try:
            run = await asyncio.wait_for(
                harness.answer(api, tools, case["question"], case_id=cid, effort=args.effort, reserve=args.reserve),
                CASE_TIMEOUT_S)
        except llm.BudgetExhausted:
            raise
        except TimeoutError:
            append_jsonl(out / "errors.jsonl", {"prompt_id": cid, "rep": 0, "failure_class": "timeout", "phase": "answer"})
            return None
        except Exception as e:  # noqa: BLE001 - serving/harness error after the SDK's own retries
            append_jsonl(out / "errors.jsonl", {"prompt_id": cid, "rep": 0, "phase": "answer",
                                                 "failure_class": _failure_class(e), "error": f"{e.__class__.__name__}: {e}"[:500]})
            return None
        run["latency_s"] = round(time.monotonic() - started, 1)
        (out / "traces" / f"{cid}_rep0.json").write_text(json.dumps(run["trace"], ensure_ascii=False, indent=1), encoding="utf-8")
        answer_file.write_text(json.dumps(run, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    try:
        verdict, judge_usage, judge_model = await judge.judge(api, case, run, catalog, effort=args.judge_effort,
                                                              reserve=args.reserve)
    except llm.BudgetExhausted:
        raise
    except Exception as e:  # noqa: BLE001 - a grader crash is an error row, not a zero
        append_jsonl(out / "errors.jsonl", {"prompt_id": cid, "rep": 0, "phase": "judge",
                                             "failure_class": "grader_error", "error": f"{e.__class__.__name__}: {e}"[:500]})
        return None
    if verdict.get("parse_error"):
        append_jsonl(out / "errors.jsonl", {"prompt_id": cid, "rep": 0, "phase": "judge", "failure_class": "grader_parse",
                                             "verdict": verdict, "judge_usage": judge_usage})
        return None
    row = make_row(case, run, verdict, judge_usage, judge_model, round_no)
    append_jsonl(out / "results.jsonl", row)
    return row


def _failure_class(e: Exception) -> str:
    name = e.__class__.__name__
    if isinstance(e, llm.ModelMismatch):
        return "served_model_mismatch"
    if any(k in name for k in ("RateLimit", "Overloaded", "InternalServer", "APIConnection", "APITimeout")):
        return "serving_error"
    return "harness_error"


def make_row(case: dict[str, Any], run: dict[str, Any], verdict: dict[str, Any], judge_usage: dict[str, int],
             judge_model: str, round_no: int) -> dict[str, Any]:
    grade = {c: verdict["scores"][c] for c in judge.CRITERIA}
    grade["total"] = judge.total(verdict)
    return {
        "prompt_id": case["id"], "prompt": case["question"], "tags": [case["category"], case.get("needs", "")],
        "round": round_no, "status": "truncated" if run.get("status") == "truncated" else run.get("status", "ok"),
        "stop_reason": run.get("stop_reason"), "grade": grade, "explanation": verdict.get("reasons", {}),
        "failing": judge.failing(verdict), "verdict": verdict, "answer": run.get("answer", ""),
        "model": run.get("model"), "usage": run.get("usage"), "cost_usd": run.get("cost_usd"),
        "judge_model": judge_model, "judge_usage": judge_usage, "judge_cost_usd": round(llm.cost(judge_usage), 4),
        "tool_calls": len(run.get("tool_calls", [])), "tools_used": sorted({c["name"] for c in run.get("tool_calls", [])}),
        "tool_errors": sum(c["is_error"] for c in run.get("tool_calls", [])),
        "site_cap_hit": run.get("site_cap_hit", False), "latency_s": run.get("latency_s"),
        "api_seconds": run.get("api_seconds"),
    }


# --- selection for round 2 ------------------------------------------------------------------------

def changed_tools(old: dict[str, str], new: dict[str, str]) -> set[str]:
    return {n for n in set(old) | set(new) if old.get(n) != new.get(n)}


def select_round2(questions: list[dict[str, Any]], prev_rows: dict[str, dict[str, Any]], prev_meta: dict[str, Any],
                  tool_fp: dict[str, str]) -> tuple[list[str], dict[str, Any]]:
    """Ids to re-run, failing first, then the cases of changed categories; and why."""
    changed = changed_tools(prev_meta.get("tool_fingerprints", {}), tool_fp)
    new_tools = set(tool_fp) - set(prev_meta.get("tool_fingerprints", {}))
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        by_cat[q["category"]].append(q)
    changed_cats = set()
    for cat, qs in by_cat.items():
        touched = set()
        for q in qs:
            touched |= set(q.get("expected_tools") or [])
            touched |= set((prev_rows.get(q["id"]) or {}).get("tools_used") or [])
        gaps = {(prev_rows.get(q["id"]) or {}).get("verdict", {}).get("primary_gap") for q in qs}
        if touched & changed or (new_tools and gaps & {"missing_tool", "missing_data"}):
            changed_cats.add(cat)
    failing = [q["id"] for q in questions if q["id"] not in prev_rows or prev_rows[q["id"]].get("failing")]
    rest = [q["id"] for q in questions if q["category"] in changed_cats and q["id"] not in failing]
    why = {"changed_tools": sorted(changed), "new_tools": sorted(new_tools), "changed_categories": sorted(changed_cats),
           "failing": len(failing), "changed_category_cases": len(rest)}
    return failing + rest, why


# --- summary --------------------------------------------------------------------------------------

def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def summarize(rows: list[dict[str, Any]], errors: list[dict[str, Any]], meta: dict[str, Any],
              prev: dict[str, dict[str, Any]] | None = None) -> str:
    """summary.md: per-category scores, the worst 20, the judge's gap tallies. Raw material for report.md."""
    ok = [r for r in rows if r.get("status") != "truncated" and r["grade"].get("total") is not None]
    totals = [r["grade"]["total"] for r in ok]
    n = len(totals)
    half = 1.96 * statistics.pstdev(totals) / math.sqrt(n) if n > 1 else 0.0
    lines = [f"# Eval summary: round {meta.get('round')}", "",
             f"- cases graded: {len(rows)} (ok {n}, truncated {len(rows) - n}), errors: {len(errors)}",
             f"- mean total: {statistics.fmean(totals):.3f} ± {half:.3f} (95% CI)" if n else "- no graded cases",
             f"- failing: {sum(r['failing'] for r in rows)}",
             (f"- answer cost: ${sum(r.get('cost_usd') or 0 for r in rows):.2f}, judge cost: "
              f"${sum(r.get('judge_cost_usd') or 0 for r in rows):.2f}, ledger eval total: ${meta.get('ledger_eval_usd', 0):.2f}"),
             f"- model: {meta.get('model')}, effort answer/judge: {meta.get('effort')}/{meta.get('judge_effort')}",
             f"- provisional tools: {meta.get('provisional_tools')}", ""]
    lines += ["## Per category", "",
              "| category | n | total | " + " | ".join(judge.CRITERIA) + " | failing | top gap |" + (" Δ vs prev |" if prev else ""),
              "|---|---|---|" + "---|" * len(judge.CRITERIA) + "---|---|" + ("---|" if prev else "")]
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ok:
        by_cat[r["tags"][0]].append(r)
    order = [c for c in CATEGORIES if c in by_cat] + sorted(set(by_cat) - set(CATEGORIES))
    for cat in order:
        rs = by_cat[cat]
        crit = [f"{_mean([r['grade'][c] for r in rs]):.2f}" for c in judge.CRITERIA]
        gaps = Counter(r["verdict"]["primary_gap"] for r in rs if r["verdict"]["primary_gap"] != "none")
        top = ", ".join(f"{g} {k}" for g, k in gaps.most_common(2)) or "-"
        mean = _mean([r["grade"]["total"] for r in rs])
        row = f"| {cat} | {len(rs)} | {mean:.2f} | " + " | ".join(crit) + f" | {sum(r['failing'] for r in rs)} | {top} |"
        if prev:
            before = [prev[r["prompt_id"]]["grade"]["total"] for r in rs if r["prompt_id"] in prev]
            row += f" {mean - statistics.fmean(before):+.2f} |" if before else " - |"
        lines.append(row)
    lines += ["", "## Worst 20", ""]
    for r in sorted(ok, key=lambda r: (r["grade"]["total"], r["prompt_id"]))[:20]:
        v = r["verdict"]
        zeros = [f"{c}: {v['reasons'].get(c, '')}" for c in judge.CRITERIA if r["grade"][c] == 0]
        lines += [f"### {r['prompt_id']} ({r['tags'][0]}) total {r['grade']['total']:.2f}, gap {v['primary_gap']}",
                  f"- Q: {r['prompt']}", f"- tools: {', '.join(r['tools_used']) or '(none)'}",
                  f"- judge: {v.get('summary', '')}"]
        lines += [f"- 0점 {z}" for z in zeros]
        if v.get("missing_what"):
            lines.append(f"- missing: {v['missing_what']}")
        if v.get("misuse_what"):
            lines.append(f"- misuse: {v['misuse_what']}")
        if v.get("fix"):
            lines.append(f"- fix: {v['fix']}")
        lines.append("")
    lines += ["## Gap tallies (primary_gap)", ""]
    gaps = Counter(r["verdict"]["primary_gap"] for r in ok)
    lines += [f"- {g}: {k}" for g, k in gaps.most_common()]
    lines += ["", (f"- capability_missing: {sum(r['verdict']['capability_missing'] for r in ok)}, "
                   f"model_misused_tools: {sum(r['verdict']['model_misused_tools'] for r in ok)}"), ""]
    lines += ["## Gap details", ""]
    for g in ("missing_tool", "missing_data", "bad_description", "wrong_shaping", "model_misuse", "harness", "other"):
        rs = [r for r in ok if r["verdict"]["primary_gap"] == g]
        if not rs:
            continue
        lines.append(f"### {g} ({len(rs)})")
        for r in rs:
            v = r["verdict"]
            what = v.get("missing_what") or v.get("misuse_what") or v.get("summary")
            lines.append(f"- {r['prompt_id']} [{r['tags'][0]}] {what} → {v.get('fix', '')}")
        lines.append("")
    tools = Counter(t for r in rows for t in r.get("tools_used", []))
    lines += ["## Tool use", "", ", ".join(f"{t} {k}" for t, k in tools.most_common()), ""]
    if errors:
        lines += ["## Errors", ""] + [f"- {e.get('prompt_id')} {e.get('phase')} {e.get('failure_class')}: "
                                       f"{str(e.get('error', ''))[:160]}" for e in errors]
    return "\n".join(lines) + "\n"


# --- main -------------------------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> int:
    logging.getLogger().setLevel(logging.WARNING)  # no per-request INFO lines from the HTTP clients
    questions = load_questions(Path(args.questions))
    if not questions:
        print(f"no questions in {args.questions}")
        return 1
    out = Path(args.out) if args.out else RESULTS / f"round{args.round}"
    for sub in ("traces", "answers"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    if args.summary:
        return write_summary(out, args)
    if args.rejudge:
        return await rejudge(out, questions, args)
    tools = await harness.build_toolset(out, provisional=args.provisional)
    catalog = judge.tool_catalog(tools.definitions)
    meta_file = out / "run_meta.json"
    meta = {"round": args.round, "model": llm.MODEL, "effort": args.effort, "judge_effort": args.judge_effort,
            "questions_file": str(Path(args.questions).name), "now": " ".join(harness.NOW_TEXT),
            "tool_fingerprints": tools.fingerprints(), **tools.meta}
    selected = [q["id"] for q in questions]
    if args.round > 1:
        prev_dir = RESULTS / f"round{args.round - 1}"
        prev_rows = {r["prompt_id"]: r for r in read_jsonl(prev_dir / "results.jsonl")}
        prev_meta = json.loads((prev_dir / "run_meta.json").read_text()) if (prev_dir / "run_meta.json").exists() else {}
        selected, why = select_round2(questions, prev_rows, prev_meta, meta["tool_fingerprints"])
        why["instructions_changed"] = prev_meta.get("instructions_sha") != meta["instructions_sha"]
        why["fixture_changed"] = prev_meta.get("fixture_sha") != meta["fixture_sha"]
        per_case = statistics.fmean([(r.get("cost_usd") or 0) + (r.get("judge_cost_usd") or 0)
                                     for r in prev_rows.values()]) if prev_rows else 0.15
        budget = llm.remaining() - llm.MIN_LEFT_USD - args.reserve
        fit = max(0, int(budget // per_case)) if per_case else len(selected)
        why.update({"per_case_usd": round(per_case, 3), "selected": len(selected), "fits_budget": fit,
                    "estimated_usd": round(per_case * min(len(selected), fit), 2)})
        selected = selected[:fit]
        meta["selection"] = why
        print(json.dumps(why, ensure_ascii=False, indent=1))
        if args.dry_run:
            return 0
        carried = [r | {"carried_from": args.round - 1} for pid, r in prev_rows.items() if pid not in selected]
        done = {r["prompt_id"] for r in read_jsonl(out / "results.jsonl")}
        for r in carried:
            if r["prompt_id"] not in done:
                append_jsonl(out / "results.jsonl", r)
    if args.ids:
        wanted = set(args.ids.split(","))
        selected = [i for i in selected if i in wanted]
    if args.categories:
        cats = set(args.categories.split(","))
        selected = [q["id"] for q in questions if q["id"] in selected and q["category"] in cats]
    if args.limit:
        selected = selected[:args.limit]
    done = {r["prompt_id"] for r in read_jsonl(out / "results.jsonl") if not r.get("carried_from")}
    todo = [q for q in questions if q["id"] in selected and q["id"] not in done]
    # The 60 school-site requests go first to the categories that need them most.
    todo.sort(key=lambda q: (SITE_FIRST.index(q["category"]) if q["category"] in SITE_FIRST else len(SITE_FIRST)))
    print(f"round {args.round}: {len(todo)} to run ({len(done)} already graded), budget left ${llm.remaining():.2f}, "
          f"reserve ${args.reserve:.2f}")
    if args.dry_run:
        return 0
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    api = llm.client()
    gate = asyncio.Semaphore(args.concurrency)
    stop = asyncio.Event()

    async def one(case: dict[str, Any]) -> None:
        async with gate:
            if stop.is_set():
                return
            try:
                row = await run_case(api, tools, case, out, catalog, args, args.round)
            except llm.BudgetExhausted as e:
                print(f"stop: {e}")
                stop.set()
                return
            if row:
                g = row["grade"]
                print(f"{case['id']:>8} {case['category']:<14} total {g['total']:.2f} gap {row['verdict']['primary_gap']:<15} "
                      f"${(row['cost_usd'] or 0) + row['judge_cost_usd']:.3f} tools {','.join(row['tools_used'])}", flush=True)

    await asyncio.gather(*(one(q) for q in todo))
    await tools.public.aclose()
    return write_summary(out, args)


async def rejudge(out: Path, questions: list[dict[str, Any]], args: argparse.Namespace) -> int:
    """Grade saved answers again with the current judge (no re-answering); the old verdict's total
    and gap stay on the row as previous_grade. For a grader change, re-grade every case whose judge
    input changed, not only the failing ones, so scores only move for grader reasons."""
    rows = read_jsonl(out / "results.jsonl")
    wanted = {r["prompt_id"] for r in rows} if args.rejudge == "all" else set(args.rejudge.split(","))
    cases = {q["id"]: q for q in questions}
    tools = await harness.build_toolset(None, live=False, provisional=args.provisional)
    meta = json.loads((out / "run_meta.json").read_text()) if (out / "run_meta.json").exists() else {}
    # the judge must see the tool list the answers were made with
    names = set(meta.get("tool_fingerprints") or [d["name"] for d in tools.definitions])
    catalog = judge.tool_catalog([d for d in tools.definitions if d["name"] in names])
    api = llm.client()
    gate = asyncio.Semaphore(args.concurrency)
    new: dict[str, dict[str, Any]] = {}

    async def one(row: dict[str, Any]) -> None:
        pid = row["prompt_id"]
        run_file = out / "answers" / f"{pid}.json"
        if pid not in wanted or not run_file.exists() or pid not in cases:
            return
        async with gate:
            run = json.loads(run_file.read_text(encoding="utf-8"))
            try:
                verdict, usage, model = await judge.judge(api, cases[pid], run, catalog, effort=args.judge_effort,
                                                          reserve=args.reserve)
            except llm.BudgetExhausted as e:
                print(f"stop: {e}")
                return
            if verdict.get("parse_error"):
                append_jsonl(out / "errors.jsonl", {"prompt_id": pid, "phase": "rejudge", "failure_class": "grader_parse"})
                return
            fresh = make_row(cases[pid], run, verdict, usage, model, row.get("round", args.round))
            fresh["previous_grade"] = {"total": row["grade"]["total"], "gap": row["verdict"]["primary_gap"],
                                       "judge_cost_usd": row.get("judge_cost_usd")}
            new[pid] = fresh
            print(f"{pid:>8} {row['grade']['total']:.2f} -> {fresh['grade']['total']:.2f} "
                  f"gap {fresh['verdict']['primary_gap']}", flush=True)

    await asyncio.gather(*(one(r) for r in rows))
    tmp = out / "results.jsonl.tmp"
    tmp.write_text("".join(json.dumps(new.get(r["prompt_id"], r), ensure_ascii=False, default=str) + "\n"
                           for r in rows), encoding="utf-8")
    tmp.replace(out / "results.jsonl")
    print(f"re-graded {len(new)} of {len(wanted)}")
    return write_summary(out, args)


def write_summary(out: Path, args: argparse.Namespace) -> int:
    rows = read_jsonl(out / "results.jsonl")
    graded = {r["prompt_id"] for r in rows}
    errors = [e for e in read_jsonl(out / "errors.jsonl") if e.get("prompt_id") not in graded]
    meta = json.loads((out / "run_meta.json").read_text()) if (out / "run_meta.json").exists() else {"round": args.round}
    meta["ledger_eval_usd"] = llm.spent()
    prev = None
    if args.round > 1:
        prev = {r["prompt_id"]: r for r in read_jsonl(RESULTS / f"round{args.round - 1}" / "results.jsonl")}
    (out / "summary.md").write_text(summarize(rows, errors, meta, prev), encoding="utf-8")
    print(f"wrote {out / 'summary.md'}; ledger eval spend ${meta['ledger_eval_usd']:.2f}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--round", type=int, default=1)
    p.add_argument("--questions", default=str(QUESTIONS))
    p.add_argument("--ids", help="comma-separated case ids")
    p.add_argument("--categories", help="comma-separated categories")
    p.add_argument("--limit", type=int)
    p.add_argument("--out", help="results directory (default evals/results/round<N>)")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--judge-effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--reserve", type=float, help="USD of the eval budget to leave unspent "
                   f"(default {ROUND1_RESERVE_USD} in round 1, 0 later)")
    p.add_argument("--provisional", help="pieces not yet registered as MCP tools to offer anyway, comma-separated "
                   f"from {','.join(harness.PROVISIONAL)} or 'none' (default: scholarships,rules in round 1, all later)")
    p.add_argument("--dry-run", action="store_true", help="print the selection and cost estimate; no API calls")
    p.add_argument("--summary", action="store_true", help="only rebuild summary.md from results.jsonl")
    p.add_argument("--rejudge", help="grade saved answers again with the current judge: comma-separated ids or 'all'")
    args = p.parse_args(argv)
    if args.reserve is None:
        args.reserve = ROUND1_RESERVE_USD if args.round == 1 else 0.0
    if args.provisional is None:  # round 1 ran before the knowledge base was built (faq.json missing)
        args.provisional = "scholarships,rules" if args.round == 1 else ",".join(harness.PROVISIONAL)
    args.provisional = tuple(p for p in args.provisional.split(",") if p in harness.PROVISIONAL)
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
