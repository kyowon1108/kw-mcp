"""Writes evals/questions.jsonl: Everytime-style questions, drafted by Claude, then reviewed by a
second Claude pass for realism, duplicates and balance (10 per category).

    uv run --frozen --with anthropic --with 'botocore[crt]' --with boto3 python evals/gen_questions.py

Both passes see the same context: the tool list, the synthetic student's data as the tools return
it (so must_include for personal questions is grounded in the fixture), and a snapshot of public
notice titles and the academic calendar (fixtures/public_snapshot.json). Drafts and review output
are kept under evals/results/questions/ for provenance.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import harness, llm
from evals.fixture import build_service, load
from evals.run import CATEGORIES

EVALS = Path(__file__).resolve().parent
OUT = EVALS / "questions.jsonl"
WORK = EVALS / "results" / "questions"
SNAPSHOT = EVALS / "fixtures" / "public_snapshot.json"
PER_CATEGORY = 10
DRAFTS_PER_CATEGORY = 13
GROUPS = [CATEGORIES[i:i + 3] for i in range(0, len(CATEGORIES), 3)]
CODES = dict(zip(CATEGORIES, ("dl", "cc", "ex", "at", "gr", "sc", "gd", "mm", "rg", "lv", "cf", "cp", "sn", "dn", "ac"),
                 strict=True))

GUIDE = {
    "마감·할 일": "이번 주·오늘·내일 할 일, 지각 제출, 특정 과제 제출 형식, 온라인 강의 진도",
    "휴강·강의실 변경": "휴강·보강, 강의실·시간 변경, 비대면 전환. 오늘은 토요일이라 '다음주 ○요일'식 질문이 자연스러움",
    "시험": "기말 날짜·범위·장소, 평가 비율, 시험 공지, 학교 기말고사 기간",
    "출석": "결석·지각 횟수, F 기준, 공결 신청, 출석 반영",
    "성적·재수강": "평점, F 재수강, 재수강 학점 상한 같은 학칙(도구에 없으면 지어내면 안 됨), 성적 공개일, 학사경고",
    "장학": "지금 신청 가능한 장학, 신청 기간, 중복 수혜, 받은 장학 내역, 국가장학금 지급일",
    "졸업요건": "졸업까지 남은 학점, 교양 영역, 졸업 가능 여부, 학과 전공 학점",
    "다전공": "복수·부·마이크로·연계전공 학점과 자격, 신청 기간, 상호인정",
    "수강신청·정정·포기": "계절학기 수강신청, 수강포기·취득학점포기 기간, 다음 학기 수강신청 일정",
    "휴학·복학": "휴학·복학 신청 기간과 방법, 군휴학, 등록금 반환. 도구에 없을 가능성이 높아 정직함을 보는 질문 포함",
    "학식": "오늘·어제·특정 요일 메뉴, 천원의 아침, 가격, 주말 운영",
    "셔틀·기숙사·도서관": "셔틀 시간, 기숙사 공지, 열람실 좌석·도서관 시간. 전용 도구가 없으니 정직하게 모른다고 하고 공식 경로를 알려 주는지가 핵심",
    "학교 공지 찾기": "특정 학교 공지 찾기(계절수업 학점교류, 세부전공 변경, 다전공 수요조사, FAQ 등). 공지 제목·링크를 주는지",
    "학과 공지": "내 학과(정보융합학부)·단과대(인공지능융합대학) 게시판 공지",
    "첨부·이미지 공지 읽기": "학교 공지의 본문·첨부·포스터 이미지 읽기(read_school_notice), KLAS 과목 게시글·과제 첨부 읽기(get_attachment_text)",
}

ITEM = {"type": "object", "properties": {
    "category": {"type": "string", "enum": list(CATEGORIES)},
    "question": {"type": "string"},
    "needs": {"type": "string", "enum": ["personal", "public", "both"]},
    "expected_tools": {"type": "array", "items": {"type": "string"}},
    "must_include": {"type": "array", "items": {"type": "string"}},
    "must_not": {"type": "array", "items": {"type": "string"}},
    "notes": {"type": "string"}},
    "required": ["category", "question", "needs", "expected_tools", "must_include", "must_not", "notes"],
    "additionalProperties": False}
DRAFT_SCHEMA = {"type": "object", "properties": {"questions": {"type": "array", "items": ITEM}},
                "required": ["questions"], "additionalProperties": False}
REVIEW_SCHEMA = {"type": "object", "properties": {
    "questions": {"type": "array", "items": ITEM},
    "dropped": {"type": "array", "items": {"type": "object", "properties": {
        "question": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["question", "reason"], "additionalProperties": False}}},
    "required": ["questions", "dropped"], "additionalProperties": False}

SYSTEM = """당신은 광운대학교 학생용 AI 도우미(Claude + KW CAMPUS MCP 도구)를 평가할 질문 세트를 만듭니다.
목표: 학생들이 에브리타임에 실제로 올리는 질문에, 도우미가 출처 있고 정확하고 바로 행동할 수 있는 답을 하는지 측정.

질문 작성 규칙
- 에브리타임 말투: 반말·줄임말·오타·ㅋㅋ/ㅠㅠ, 짧고 맥락이 빠진 질문, 막연한 질문("나 이번 학기 장학금 뭐 받을 수 있음?")도 섞기.
- 질문하는 학생은 아래 <학생 데이터>의 가상 학생 본인입니다(정보융합학부 2024학번 3학년). 개인 질문은 이 데이터로 답할 수 있게.
- 오늘은 2026-11-07(토) 13:00 KST. 날짜 표현(오늘, 내일, 다음주 화요일)은 이 기준.
- needs: personal(KLAS 개인 데이터만), public(학교 공개 정보만), both.
- expected_tools: 아래 도구 목록에 실제로 있는 이름만. 맞는 도구가 없으면 빈 배열로 두고 notes에 "도구 없음"이라고 적기.
- must_include: 좋은 답에 꼭 있어야 할 사실이나 행동. 개인 질문의 사실은 <학생 데이터>에 있는 것만 쓰기.
  학교 공개 정보는 <공개 정보 스냅숏>에 있는 것(공지 제목·날짜·URL, 학사일정)만 사실로 쓰고, 그 밖의 학교 규칙·날짜는
  사실 대신 행동("공지 원문 링크 제시", "확인하지 못했으면 그렇게 말함", "담당 부서 안내")으로 쓰기.
  학칙·규정 자료(school_rules)에 있을 내용도 수치를 지어내지 말고 "규칙 자료나 공식 출처를 인용"처럼 쓰기.
- must_not: 이 질문에서 특히 하기 쉬운 잘못(마감·날짜 추측, 학칙 지어내기, 다른 학교 정보, '못 찾음'을 '없음'으로 말하기,
  제출한 과제를 남은 일로 넣기, 개인정보 노출 등).
- notes: 이 질문이 무엇을 시험하는지 한 줄(쉬움/어려움, 도구 없음, 함정 등).
- 같은 카테고리 안에서 서로 다른 상황을 다루고, 쉬운 것·어려운 것·도구가 없는 것·애매한 것을 섞기.
- 학교 공지·첨부 질문은 스냅숏의 공지 중에서 고르되, 전체에서 서로 다른 공지는 12개 이내로(학교 사이트 요청을 아끼려고).
"""


async def context() -> str:
    tools = await harness.build_toolset(None, live=False, provisional=("scholarships", "rules"))
    catalog = "\n".join(f"- {d['name']}: {' '.join(d['description'].split())}" for d in tools.definitions)
    svc, _ = build_service()
    data = load()
    facts = {
        "courses": await svc.courses(),
        "deadlines_14_days": await svc.deadlines(14),
        "all_assignments": await svc.assignments(None, None, False),
        "class_changes": await svc.class_changes(14),
        "attendance_summary": [{"course": a["course"], "summary": a["summary"]} for a in await svc.attendance(None)],
        "grades_summary": {k: v for k, v in (await svc.grades()).items() if k in ("gpa", "credits", "summary", "standing",
                                                                                   "grade_viewing_period")},
        "graduation_progress": await svc.graduation_progress(),
        "scholarship_history": await svc.scholarships(),
        "klas_application_windows": await svc.application_windows(),
        "course_board_posts": {subj: {board: [{"title": p["title"], "posted": p["registDt"][:16],
                                               "body": re.sub(r"<[^>]+>", " ", p["content"]).strip(),
                                               "attachment": [f["fileName"] for f in data["files"].get(p["atchFileId"] or "", [])]}
                                              for p in posts] for board, posts in boards.items()}
                               for subj, boards in data["boards"].items()},
        "syllabus_grading": {s[0]["gwamokKname"]: {k: v for k, v in s[0].items() if k.endswith("Biyul") and v}
                             for s in data["per_course"]["SYLLABUS"].values()},
    }
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return (f"{SYSTEM}\n<도구 목록>\n{catalog}\n</도구 목록>\n\n"
            f"<학생 데이터>\n{json.dumps(facts, ensure_ascii=False, default=str)}\n</학생 데이터>\n\n"
            f"<공개 정보 스냅숏>\n{json.dumps(snapshot, ensure_ascii=False)}\n</공개 정보 스냅숏>")


async def ask(api: Any, ctx: str, prompt: str, schema: dict[str, Any], effort: str, note: str) -> dict[str, Any]:
    response = await llm.create(
        api, note=note, stream=True, max_tokens=32000,
        system=[{"type": "text", "text": ctx, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"{note}: stop_reason {response.stop_reason}")
    return json.loads("".join(b.text for b in response.content if b.type == "text"))


def guide(group: tuple[str, ...]) -> str:
    return "\n".join(f"- {c}: {GUIDE[c]}" for c in group)


async def draft(api: Any, ctx: str, group: tuple[str, ...], index: int) -> list[dict[str, Any]]:
    path = WORK / f"drafts_{index}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    prompt = (f"다음 카테고리마다 질문 초안 {DRAFTS_PER_CATEGORY}개씩 쓰세요.\n{guide(group)}\n"
              "카테고리 이름은 그대로 쓰세요.")
    out = (await ask(api, ctx, prompt, DRAFT_SCHEMA, "low", f"qgen draft {index}"))["questions"]
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


async def review(api: Any, ctx: str, group: tuple[str, ...], drafts: list[dict[str, Any]], index: int) -> dict[str, Any]:
    path = WORK / f"review_{index}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    prompt = (f"아래는 다른 작성자가 쓴 질문 초안입니다. 검토자로서 카테고리마다 정확히 {PER_CATEGORY}개를 골라 다듬으세요.\n"
              f"{guide(group)}\n"
              "검토 기준:\n"
              "1. 현실성: 실제 광운대 학생이 에브리타임에 쓸 법한 말투·상황인가. 어색하면 고쳐 쓰기.\n"
              "2. 중복: 같은 걸 묻는 질문은 하나만 남기기(다른 카테고리와 겹치는 것도).\n"
              "3. 균형: needs(personal/public/both), 쉬움/어려움, 도구 없는 질문, 막연한 질문을 섞기.\n"
              "4. 정답 근거: must_include의 사실이 <학생 데이터>·<공개 정보 스냅숏>에 실제로 있는지 확인하고, 없거나 틀리면 고치기.\n"
              "   학교 규칙·날짜를 지어낸 must_include는 행동 기준으로 바꾸기.\n"
              "5. expected_tools는 도구 목록에 있는 이름만.\n"
              "버린 초안은 dropped에 이유와 함께 적으세요.\n\n"
              f"<초안>\n{json.dumps(drafts, ensure_ascii=False)}\n</초안>")
    out = await ask(api, ctx, prompt, REVIEW_SCHEMA, "medium", f"qgen review {index}")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def finalize(reviewed: list[dict[str, Any]], tool_names: set[str]) -> list[dict[str, Any]]:
    rows, counts = [], {c: 0 for c in CATEGORIES}
    for q in reviewed:
        cat = q["category"]
        if cat not in counts or counts[cat] >= PER_CATEGORY:
            continue
        counts[cat] += 1
        bad = [t for t in q["expected_tools"] if t not in tool_names]
        rows.append({"id": f"{CODES[cat]}{counts[cat]:02d}", "category": cat, "question": q["question"].strip(),
                     "needs": q["needs"], "expected_tools": [t for t in q["expected_tools"] if t in tool_names],
                     "must_include": q["must_include"], "must_not": q["must_not"],
                     "notes": q["notes"] + (f" (도구 목록에 없는 이름 제거: {', '.join(bad)})" if bad else "")})
    rows.sort(key=lambda r: (CATEGORIES.index(r["category"]), r["id"]))
    return rows


async def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    ctx = await context()
    (WORK / "context.txt").write_text(ctx, encoding="utf-8")
    api = llm.client()
    first = await draft(api, ctx, GROUPS[0], 0)  # alone first, so the others read the cached context
    drafts = [first, *await asyncio.gather(*(draft(api, ctx, g, i) for i, g in enumerate(GROUPS) if i))]
    reviews = await asyncio.gather(*(review(api, ctx, g, d, i) for i, (g, d) in enumerate(zip(GROUPS, drafts, strict=True))))
    tools = await harness.build_toolset(None, live=False, provisional=("scholarships", "rules"))
    rows = finalize([q for r in reviews for q in r["questions"]], {d["name"] for d in tools.definitions})
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    counts = {c: sum(r["category"] == c for r in rows) for c in CATEGORIES}
    print(f"wrote {len(rows)} questions to {OUT}: {counts}; eval spend ${llm.spent():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
