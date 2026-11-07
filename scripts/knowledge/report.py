"""Markdown source table for docs/knowledge-sources.md, from sources.json and the fetch log.

    python report.py > /tmp/sources-table.md
"""

from __future__ import annotations

import json

from kbcommon import FETCH_LOG, KNOWLEDGE, RAW, load_sources

FEEDS = {"faq": "Q&A", "curricula": "교육과정", "rules_tables": "별표 표", "contacts": "연락처"}


def main() -> None:
    log = {}
    if FETCH_LOG.exists():
        for line in FETCH_LOG.read_text(encoding="utf-8").splitlines():
            _n, ts, status, size, _ctype, url = line.split("\t")
            log[url] = (ts[:10], status, int(size))
    cited = set()
    faq = KNOWLEDGE / "faq.json"
    if faq.exists():
        for e in json.loads(faq.read_text(encoding="utf-8"))["entries"]:
            cited.update(s.get("source_id") for s in e["sources"])
    print("| id | 자료 | 확인일 | 상태 | 쓰인 곳 |")
    print("|---|---|---|---|---|")
    for s in load_sources():
        meta_path = RAW / f"{s['id']}.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        date, status, _size = log.get(s["url"], (str(meta.get("fetched_at", ""))[:10] or "-", meta.get("status", "-"), 0))
        if meta.get("reused_from"):
            status = "재사용"
        feeds = ", ".join(FEEDS.get(f, f) for f in s["feeds"])
        if "faq" in s["feeds"] and s["id"] in cited:
            feeds += " (인용됨)"
        title = s["title"].replace("|", "/")
        print(f"| {s['id']} | [{title}]({s['url']}) | {date} | {status} | {feeds} |")


if __name__ == "__main__":
    main()
