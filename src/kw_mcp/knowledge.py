"""Academic knowledge base built from the school's public pages and regulations (scripts/knowledge/).

Data lives next to this module in knowledge/: faq.json (Q&A entries), curricula/ (one file per department and
admission year, plus index.json) and rules_tables.json (the HWP annexes as tables). Everything here is local
and read-only: no network, and search is a small in-memory index over Korean character bigrams.

    load()                                  -> the whole knowledge base (cached)
    search(query, category=None, limit=5)   -> best-matching entries for a student's question
    entry(id)                               -> one entry
    curriculum(department, admission_year)  -> that department's course list for the year

Every entry and curriculum returned carries `version` {built_at, sources} and `report` (how to flag an error).

Files are read through datasync.read(): a newer signed copy from the bridge when there is one, else the package's
own. Loads are cached per data snapshot, and every file of one load comes from the same snapshot.
"""

from __future__ import annotations

import functools
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from . import datasync

DATA = Path(__file__).with_name("knowledge")  # the package's own copy (loaders go through datasync.read)
REPORT_HINT = "틀린 정보는 디스코드 #알림-설정의 제보하기(또는 /제보)로 알려 주세요"

# Everytime shorthand -> the words the entries use. Applied to the query only.
SYNONYMS = {
    "복전": "복수전공", "부전": "부전공", "연계": "연계전공", "마전": "마이크로전공", "마이크로": "마이크로전공",
    "다전": "다전공", "심전": "심화전공", "졸유": "졸업유예 졸업연기", "졸업유예": "졸업연기", "조졸": "조기졸업",
    "드랍": "수강포기 수강철회", "드롭": "수강포기 수강철회", "수포": "수강포기", "철회": "수강포기 수강철회",
    "정정": "수강정정", "수신": "수강신청", "재수": "재수강",
    "계절": "계절학기 계절수업", "썸머": "계절학기 하계", "윈터": "계절학기 동계", "계절학기": "계절수업",
    "국장": "국가장학금", "성장": "성적장학금", "근장": "근로장학", "장학": "장학금",
    "긱사": "기숙사 생활관", "기숙사": "생활관 행복기숙사", "빛솔재": "기숙사 생활관",
    "학식": "식단 학생식당", "밥": "식단 학식", "셔틀": "셔틀버스", "도서관": "중앙도서관",
    "군휴학": "군입대휴학 휴학 입영", "군대": "입영 군휴학 병무", "예비군": "예비군 공결",
    "학고": "학사경고",
    "성적이의": "성적 이의신청", "이의신청": "성적 이의신청", "피에프": "P/F", "pf": "P/F",
    "교환": "교환학생", "학점교류": "학점교류 타대학", "전배": "전공배정",
    "증명서": "증명서 증명발급", "재학증명": "재학증명서", "분납": "분할납부 등록금",
    "등록금": "등록금 납입금", "환불": "반환", "졸업요건": "졸업 이수학점", "졸업학점": "졸업이수학점",
    "광인되": "광운인되기", "출결": "출석", "공결": "출석인정 공결", "체특": "체육특기자",
    "빼고": "수강포기", "과옮기": "전과", "그만두": "자퇴", "타과": "타학과 다른학과",
    "딴과": "타학과 다른학과", "패스": "P/F", "입대": "입영 군입대 휴학", "기계": "자동발급기", "타대": "타대학 학점교류",
    "다른대학": "타대학 학점교류", "시뮬": "시뮬레이션 다전공 플래너 Daple",
    "다플": "Daple 다전공 플래너",
}
EXPANSION_WEIGHT = 0.5  # words added from SYNONYMS count half as much as the student's own words
_WEIGHTS = {"questions": 3.0, "category": 2.0, "answer": 1.0, "conditions": 0.5, "how_to": 0.5}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[^0-9a-z가-힣/]+", " ", text).strip()


def _grams(text: str) -> Counter:
    """Character bigrams of each word (whole word if one character), so 수강포기 matches 포기 and 수강."""
    out: Counter = Counter()
    for word in _norm(text).split():
        if len(word) == 1:
            out[word] += 1
        out.update(word[i:i + 2] for i in range(len(word) - 1))
    return out


def _expand(query: str) -> str:
    """The synonyms' words for a query (not the query itself)."""
    squeezed = _norm(query).replace(" ", "")
    return " ".join(v for k, v in SYNONYMS.items() if k.replace(" ", "") in squeezed)


def _read(name: str, snap: datasync.Active | None) -> Any:
    return json.loads(datasync.read(name, snap))


def load() -> dict[str, Any]:
    """The knowledge base: {"version", "entries", "by_id", "curricula_index", "rules_tables"}."""
    return _load(datasync.snapshot())


@functools.lru_cache(maxsize=2)  # the data in use and, while calls still run on it, the one before
def _load(snap: datasync.Active | None) -> dict[str, Any]:
    faq = _read("knowledge/faq.json", snap)
    index_path, tables_path = "knowledge/curricula/index.json", "knowledge/rules_tables.json"
    return {
        "version": faq.get("version", {}),
        "entries": faq["entries"],
        "by_id": {e["id"]: e for e in faq["entries"]},
        "gaps": faq.get("gaps", {}),
        "curricula_index": (_read(index_path, snap) if datasync.path(index_path, snap).exists()
                            else {"departments": [], "unavailable": []}),
        "rules_tables": _read(tables_path, snap) if datasync.path(tables_path, snap).exists() else None,
    }


@functools.lru_cache(maxsize=2)
def _index(snap: datasync.Active | None) -> tuple[list[dict[str, Any]], dict[str, list[tuple[int, float]]],
                                                  dict[str, float]]:
    """(entries, postings, idf) for one data snapshot."""
    entries = _load(snap)["entries"]
    postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for i, e in enumerate(entries):
        fields = {
            "questions": " ".join(e["questions"]),
            "category": e["category"],
            "answer": e["answer"],
            "conditions": " ".join(e.get("conditions_exceptions") or []),
            "how_to": e.get("how_to") or "",
        }
        weights: Counter = Counter()
        for name, text in fields.items():
            for gram, n in _grams(text).items():
                weights[gram] += _WEIGHTS[name] * (1 + math.log(n))
        for gram, w in weights.items():
            postings[gram].append((i, w))
    total = len(entries) or 1
    idf = {g: math.log(1 + total / len(p)) for g, p in postings.items()}
    return entries, dict(postings), idf


def _with_meta(e: dict[str, Any]) -> dict[str, Any]:
    urls = list(dict.fromkeys(s["url"] for s in e.get("sources", []) if s.get("url")))
    return {**e, "version": {"built_at": load()["version"].get("built_at"), "sources": urls},
            "report": REPORT_HINT}


def search(query: str, category: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Entries that best match a (casual) question, best first. `category` keeps one category only."""
    if not query or not query.strip() or limit <= 0:
        return []
    entries, postings, idf = _index(datasync.snapshot())
    scores: Counter = Counter()
    wanted: Counter = Counter({g: min(n, 2) for g, n in _grams(query).items()})
    for gram, n in _grams(_expand(query)).items():
        wanted[gram] += EXPANSION_WEIGHT * min(n, 2)
    for gram, weight in wanted.items():
        for i, w in postings.get(gram, ()):
            scores[i] += idf[gram] * w * weight
    ranked = [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
              if category is None or entries[i]["category"] == category]
    return [_with_meta(entries[i]) for i in ranked[:limit]]


def entry(entry_id: str) -> dict[str, Any] | None:
    e = load()["by_id"].get(entry_id)
    return _with_meta(e) if e else None


def categories() -> list[str]:
    return list(dict.fromkeys(e["category"] for e in load()["entries"]))


def _department(name: str, kb: dict[str, Any] | None = None) -> dict[str, Any] | None:
    depts = (kb or load())["curricula_index"].get("departments", [])
    key = _norm(name).replace(" ", "")
    if not key:
        return None
    for d in depts:
        if _norm(d["department"]).replace(" ", "") == key:
            return d
    hits = [d for d in depts if key in _norm(d["department"]).replace(" ", "")]
    return hits[0] if len(hits) == 1 else None


GUIDE_NOTE = ("학교 규정·학사 안내 페이지·Daple에서 정리한 참고 안내입니다. 학번·학과에 따라 다를 수 있으니 "
              "중요한 결정 전에는 contact_office나 최신 공지로 확인하세요.")
_GUIDE_FIELDS = ("id", "category", "answer", "conditions_exceptions", "how_to", "applies_to", "contact_office",
                 "confidence", "disagreement", "last_verified")
_SOURCE_FIELDS = ("title", "regulation", "article", "effective_date", "url")


def _guide_entry(e: dict[str, Any]) -> dict[str, Any]:
    out = {k: e.get(k) for k in _GUIDE_FIELDS}
    out["question"] = e["questions"][0]
    out["sources"] = [{k: s[k] for k in _SOURCE_FIELDS if s.get(k)} for s in e.get("sources", [])]
    return out


def guide(question: str, category: str | None = None, limit: int = 3) -> dict[str, Any]:
    """What the school_guide tool returns: the best entries for a student's question, trimmed for citing,
    plus what the documents don't say for the top entry's category (so a gap is reported as a gap)."""
    kb = load()
    if category and category not in categories():
        category = None
    hits = search(question, category, max(1, min(limit, 5)))
    out: dict[str, Any] = {
        "answers": [_guide_entry(e) for e in hits],
        "version": {"built_at": kb["version"].get("built_at"),
                    "basis": "광운대 학칙·시행세칙·내규, 학사안내 페이지, Daple 다전공 플래너"},
        "note": GUIDE_NOTE,
        "report": REPORT_HINT,
    }
    if not hits:
        out["categories"] = categories()
        out["note"] = ("지식베이스에서 찾지 못했습니다. school_notices로 공지를 찾거나 학교 홈페이지를 확인하세요. "
                       + GUIDE_NOTE)
        return out
    gaps = kb["gaps"].get(hits[0]["category"]) if isinstance(kb["gaps"], dict) else None
    if gaps:
        out["not_in_documents"] = list(gaps)
    return out


NOTICE_LINKS = "knowledge/notice_links.json"
NOTICE_DAYS = 90  # without an open deadline, notices posted this many days back at most
NOTICE_LIMIT = 3
NOTICE_TEXT_CHARS = 300
NOTICES_NOTE = "최근 공지가 있으면 규정 안내보다 공지가 먼저예요. 링크를 함께 알려 주세요."


def notice_queries(category: str | None) -> list[dict[str, str]]:
    """The public-notice searches for a knowledge category (knowledge/notice_links.json): each a public-API
    "category" and/or "q". Empty for a category with no useful notices."""
    if not category:
        return []
    snap = datasync.snapshot()
    if not datasync.path(NOTICE_LINKS, snap).exists():
        return []
    links = _read(NOTICE_LINKS, snap).get("links") or {}
    return [{k: str(q[k]) for k in ("category", "q") if q.get(k)}
            for q in links.get(category) or [] if isinstance(q, dict) and (q.get("category") or q.get("q"))]


def _deadline_at(row: dict[str, Any]) -> str:
    deadline = row.get("deadline")
    return str(deadline.get("at") or "") if isinstance(deadline, dict) else ""


def _notice_view(row: dict[str, Any]) -> dict[str, Any]:
    facts = row.get("extracted") if isinstance(row.get("extracted"), dict) else {}
    out = {"title": row.get("title"), "posted": row.get("posted_date"), "url": row.get("url"),
           "deadline": _deadline_at(row)[:16] or None,
           "target": str(facts.get("target") or "")[:NOTICE_TEXT_CHARS] or None,
           "how_to_apply": str(facts.get("how_to_apply") or "")[:NOTICE_TEXT_CHARS] or None}
    return {k: v for k, v in out.items() if v}


def pick_notices(rows: list[dict[str, Any]], today: date, *, open_only: bool = False,
                 limit: int = NOTICE_LIMIT) -> list[dict[str, Any]]:
    """Up to `limit` public-notice rows for a guide answer, each as {title, posted, url, deadline, target,
    how_to_apply} (empty fields left out): those whose deadline is today or later first, soonest first;
    with open_only only those, else the newest after them. The same notice found by two searches counts once."""
    seen: set[str] = set()
    unique = []
    for r in rows:
        key = str(r.get("post_id") or r.get("url") or r.get("title") or "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    ahead = sorted((r for r in unique if _deadline_at(r)[:10] >= today.isoformat()), key=_deadline_at)
    rest = [] if open_only else sorted((r for r in unique if r not in ahead),
                                       key=lambda r: str(r.get("posted_date") or ""), reverse=True)
    return [_notice_view(r) for r in (ahead + rest)[:limit]]


def curriculum_lookup(department: str, admission_year: int) -> dict[str, Any]:
    """What the department_curriculum tool returns: the curriculum, or what the knowledge base does have."""
    found = curriculum(department, admission_year)
    if found is not None:
        return found
    index = load()["curricula_index"]
    key = _norm(department).replace(" ", "")
    names = [d for d in index.get("departments", [])
             if key and (key in _norm(d["department"]).replace(" ", "")
                         or _norm(d["department"]).replace(" ", "") in key)]
    out: dict[str, Any] = {"found": False, "report": REPORT_HINT}
    if len(names) == 1:
        out["note"] = f"{names[0]['department']}의 {admission_year}학번 교육과정은 지식베이스에 없습니다."
        out["admission_years"] = names[0].get("admission_years", [])
    elif names:
        out["note"] = "학과 이름이 여러 곳과 맞습니다. 정확한 이름으로 다시 물어보세요."
        out["candidates"] = [d["department"] for d in names][:20]
    else:
        out["note"] = "그 학과의 교육과정은 지식베이스에 없습니다. 학과 홈페이지나 학사안내 교육과정 페이지를 확인하세요."
        out["departments"] = [d["department"] for d in index.get("departments", [])]
    missing = [u for u in index.get("unavailable", []) if key and key in _norm(json.dumps(u, ensure_ascii=False))]
    if missing:
        out["unavailable"] = missing
    return out


def curriculum(department: str, admission_year: int) -> dict[str, Any] | None:
    """The department's curriculum for that admission year, or None if the knowledge base doesn't have it.

    scope "full" is the whole current course table; "required_only" lists only the required courses that the
    school's 필수과목표 gives for that admission year. When a year has both, the full table is returned and the
    required-only list is under "also".
    """
    snap = datasync.snapshot()  # the index and the file from one data version
    kb = _load(snap)
    d = _department(department, kb)
    if d is None or admission_year not in d.get("admission_years", []):
        return None
    data = _read(f"knowledge/curricula/{d['slug']}-{admission_year}.json", snap)
    urls = [s["url"] for s in data.get("sources", [])]
    return {**data, "version": {"built_at": kb["curricula_index"].get("version", {}).get("built_at"),
                                "sources": urls},
            "report": REPORT_HINT}
