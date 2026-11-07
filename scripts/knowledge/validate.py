"""Checks the shipped knowledge data: schema, sources, quotes, personal-name patterns, link hosts (no URL
shorteners; only the allow-list below), curricula files.

    python validate.py          # exit 1 and a list of problems if anything is off
"""

from __future__ import annotations

import json
import re
import sys

from kbcommon import KNOWLEDGE

CATEGORIES = {"수강신청", "재수강·성적", "계절학기", "수업·출석", "학적변동", "졸업", "다전공", "전과·전공배정",
              "학점교류·교환학생", "장학", "등록·등록금", "증명서·학생증", "기숙사", "셔틀·교통", "도서관",
              "학식·편의시설", "병무·예비군", "IT·계정", "상담·학생지원", "진로·취업", "동아리·학생자치", "기타"}
PERSON = [
    re.compile(r"[가-힣]{2,4}\s?(교수님?|선생님|팀장님?|과장님?|계장|주임|조교|대리)(?![가-힣])"),
    re.compile(r"담당자\s?[:：]?\s?[가-힣]{2,4}\s?(\(|0\d)"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
]
# office/role words that the first pattern would otherwise flag ("교육지원팀 과장" is not a name)
ROLE_OK = re.compile(r"(지도|책임|담당|학과|전임|겸임|초빙|명예|객원|교육|지원|주임|분반주임|학부|소속|해당|전공)\s?(교수|조교)")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")
# https everywhere, except the library's seat page, which the school serves over plain http only
URL_OK = ("https://", "http://mobileid.kw.ac.kr/seatweb/")

# Where the data may send a student. School hosts and government hosts by suffix; a few official services the
# school's own pages point to, by exact host; social accounts only by their path. Anything else - a URL shortener,
# a form service, a page whose owner is not known - is refused.
LINK_SUFFIXES = ("kw.ac.kr", "go.kr")
LINK_HOSTS = {
    "kwuniv.com", "daple.kwuniv.com",            # Daple, the school's 다전공 planner
    "kw.happydorm.or.kr",                        # 행복기숙사 (the dormitory's own site)
    "www.kwu-studentcouncil.co.kr",              # 총학생회
    "webminwon.com", "www.webminwon.com",        # 인터넷 증명발급 (the school's certificate service)
    "www.isic.co.kr",                            # 국제학생증
    "www.selc.or.kr",                            # 서울권역 e-러닝
}
LINK_PATHS = {  # host (without www.) -> allowed account paths
    "instagram.com": ("/kwu_career", "/kwu_studentcouncil", "/kw_club_union"),
    "cafe.naver.com": ("/kwexchange", "/kwucdy"),
    "pf.kakao.com": ("/_Cxldyn",),               # 총학생회 카카오톡 채널
}
SHORTENERS = ("vvd.bz", "bit.ly", "han.gl", "me2.do", "naver.me", "m.site.naver.com", "url.kr", "tinyurl.com",
              "goo.gl", "forms.gle", "t.ly", "buly.kr", "linktr.ee", "notion.site")
LINK = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s\"'<>)\]，,]*)?", re.IGNORECASE)


def link_problems(text: str) -> list[str]:
    out = []
    for m in LINK.finditer(text):
        host, path = m.group(1).lower(), m.group(2) or ""
        bare = host.removeprefix("www.")
        school = host in LINK_HOSTS or any(host == s or host.endswith("." + s) for s in LINK_SUFFIXES)
        account = any(path == p or path.startswith(p + "/") for p in LINK_PATHS.get(bare, ()))
        if any(host == s or host.endswith("." + s) for s in SHORTENERS):
            out.append(f"shortener or unknown-owner link: {m.group(0)}")
        elif not (school or account):
            out.append(f"link host not allowed: {m.group(0)}")
    return out


def entry_problems(e: dict) -> list[str]:
    p = []
    for key, typ in (("id", str), ("category", str), ("questions", list), ("answer", str),
                     ("conditions_exceptions", list), ("how_to", str), ("contact_office", dict), ("sources", list),
                     ("applies_to", str), ("confidence", str), ("last_verified", str)):
        if not isinstance(e.get(key), typ):
            p.append(f"{key} missing or not {typ.__name__}")
    if p:
        return p
    if e["category"] not in CATEGORIES:
        p.append(f"category {e['category']}")
    if not 3 <= len(e["questions"]) <= 6:
        p.append(f"{len(e['questions'])} questions")
    if e["confidence"] not in ("high", "medium", "low"):
        p.append("confidence")
    if not DATE.match(e["last_verified"]):
        p.append("last_verified")
    if set(e["contact_office"]) != {"name", "phone"}:
        p.append("contact_office keys")
    if not e["sources"] or not all(str(s.get("url", "")).startswith(URL_OK) for s in e["sources"]):
        p.append("source url")
    for s in e["sources"]:
        p += link_problems(str(s.get("url", "")))
    quotes = [s["quote"] for s in e["sources"] if s.get("quote")]
    if len(quotes) > 1 or any(len(q.split()) >= 15 for q in quotes):
        p.append("quotes")
    text = json.dumps({k: e[k] for k in ("questions", "answer", "conditions_exceptions", "how_to",
                                         "contact_office", "applies_to")}, ensure_ascii=False)
    p += link_problems(text + json.dumps(e.get("disagreement") or "", ensure_ascii=False))
    for pat in PERSON:
        for m in pat.finditer(text):
            if not ROLE_OK.search(text[max(0, m.start() - 4):m.end()]):
                p.append(f"person-like text: {m.group(0)}")
    return p


def main() -> int:
    problems = []
    faq = json.loads((KNOWLEDGE / "faq.json").read_text(encoding="utf-8"))
    ids = [e["id"] for e in faq["entries"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate ids")
    for e in faq["entries"]:
        problems += [f"{e.get('id')}: {x}" for x in entry_problems(e)]
    index = json.loads((KNOWLEDGE / "curricula" / "index.json").read_text(encoding="utf-8"))
    for d in index["departments"]:
        for y in d["admission_years"]:
            c = json.loads((KNOWLEDGE / "curricula" / f"{d['slug']}-{y}.json").read_text(encoding="utf-8"))
            if not c["courses"] or not c["sources"]:
                problems.append(f"curriculum {d['slug']}-{y}: empty")
            blob = json.dumps({k: c.get(k) for k in ("basis", "also", "courses", "sources")}, ensure_ascii=False)
            problems += [f"curriculum {d['slug']}-{y}: {x}" for x in link_problems(blob)]
            for course in c["courses"]:
                if not course["name"] or course.get("type") is None:
                    problems.append(f"curriculum {d['slug']}-{y}: bad course {course}")
    problems += [f"curricula index: {x}" for x in link_problems(json.dumps(index, ensure_ascii=False))]
    tables = json.loads((KNOWLEDGE / "rules_tables.json").read_text(encoding="utf-8"))
    if not tables["annex6"]["blocks"]:
        problems.append("rules_tables: no annex6 blocks")
    urls = re.findall(r"https?://[^\s\"'<>)\]]+", json.dumps(tables, ensure_ascii=False))  # its prose names code paths
    problems += [f"rules_tables: {x}" for u in urls for x in link_problems(u)]
    by_cat: dict[str, int] = {}
    for e in faq["entries"]:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    print(json.dumps({"entries": len(ids), "by_category": by_cat,
                      "curricula": sum(len(d["admission_years"]) for d in index["departments"]),
                      "problems": len(problems)}, ensure_ascii=False))
    for x in problems:
        print("-", x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
