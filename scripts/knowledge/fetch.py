"""Polite GET fetcher for the knowledge base.

Honest User-Agent, one request at a time, at least GAP_SECONDS between two requests to the same server
(keyed by IP, so the department hosts that share one machine share one clock), robots.txt checked first,
GET only, a hard cap on the number of requests, and every request logged to fetch_log.tsv.

    python fetch.py URL NAME              # one page -> raw/NAME.<ext>
    python fetch.py --sources             # everything in sources.json not downloaded yet
    python fetch.py --sources --dry-run   # list what would be fetched
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from kbcommon import (
    FETCH_LOG,
    FORBIDDEN_HOSTS,
    GAP_SECONDS,
    MAX_FETCHES,
    RAW,
    ROBOTS,
    UA,
    WORK,
    load_sources,
)

STAMPS = WORK / "host_stamps.json"
try:
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except OSError:
    CTX = ssl.create_default_context()


def fetch_count() -> int:
    return sum(1 for _ in FETCH_LOG.open(encoding="utf-8")) if FETCH_LOG.exists() else 0


def _server_key(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return host


def _crawl_delay(host: str) -> float:
    """robots.txt Crawl-delay for this host, if the cached file gives one (job.kw.ac.kr asks for 10 s)."""
    for cache in ROBOTS.glob(f"robots_{host}*.txt"):
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(cache.read_text(encoding="utf-8", errors="replace").splitlines())
        delay = rp.crawl_delay(UA)
        if delay:
            return float(delay)
    return 0.0


def _wait(host: str) -> None:
    stamps = json.loads(STAMPS.read_text()) if STAMPS.exists() else {}
    key = _server_key(host)
    gap = max(GAP_SECONDS, _crawl_delay(host))
    delta = time.time() - stamps.get(key, 0)
    if delta < gap:
        time.sleep(gap - delta)
    stamps[key] = time.time()
    STAMPS.write_text(json.dumps(stamps))


def _get(url: str, limit: int) -> tuple[object, bytes, str, str]:
    host = urllib.parse.urlsplit(url).hostname or ""
    if any(host == h or host.endswith("." + h) for h in FORBIDDEN_HOSTS):
        sys.exit(f"refused: {host} is off limits")
    if fetch_count() >= limit:
        sys.exit(f"fetch budget reached ({limit})")
    _wait(host)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.5"})
    status, data, ctype, final = None, b"", "", url
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            status, data, ctype, final = r.status, r.read(), r.headers.get("Content-Type", ""), r.geturl()
    except urllib.error.HTTPError as e:
        status, data, ctype = e.code, e.read() or b"", e.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001 - network trouble is logged, not fatal
        status = f"ERR:{type(e).__name__}:{str(e)[:80]}"
    n = fetch_count() + 1
    with FETCH_LOG.open("a", encoding="utf-8") as f:
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        f.write(f"{n}\t{stamp}\t{status}\t{len(data)}\t{ctype}\t{url}\n")
    return status, data, ctype, final


def robots_ok(url: str, limit: int) -> bool:
    parts = urllib.parse.urlsplit(url)
    cache = ROBOTS / f"robots_{parts.netloc}.txt"
    if not cache.exists():
        status, data, _, _ = _get(f"{parts.scheme}://{parts.netloc}/robots.txt", limit)
        cache.write_bytes(data if status == 200 else b"")
    text = cache.read_text(encoding="utf-8", errors="replace")
    if "<html" in text.lower()[:500]:  # some hosts answer robots.txt with an HTML page: no rules
        return True
    return _allowed(text, parts.path + (f"?{parts.query}" if parts.query else ""))


def _allowed(text: str, path: str) -> bool:
    """RFC 9309: in the group for our agent (else "*"), the longest matching rule wins; Allow wins a tie.
    (urllib.robotparser takes the first match instead, which reads "Disallow: / then Allow: /index.do" as
    disallowing /index.do.)"""
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key in ("allow", "disallow"):
            rules.append((key, value))
    if agents or rules:
        groups.append((agents, rules))
    token = UA.split()[0].lower()
    mine = [r for a, r in groups if any(x != "*" and x in token for x in a)]
    chosen = mine[0] if mine else next((r for a, r in groups if "*" in a), [])
    best = ("allow", -1)
    for kind, rule in chosen:
        if not rule:
            continue
        pattern = re.escape(rule).replace(r"\*", ".*")
        if pattern.endswith(r"\$"):
            pattern = pattern[:-2] + "$"
        if re.match(pattern, path) and (len(rule) > best[1] or (len(rule) == best[1] and kind == "allow")):
            best = (kind, len(rule))
    return best[0] == "allow"


def _ext(data: bytes, ctype: str, url: str) -> str:
    head = data[:8]
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\xd0\xcf\x11\xe0"):  # OLE: old Excel or HWP
        return ".xls" if ".xls" in url.lower() else ".hwp"
    if head.startswith(b"PK"):
        low = url.lower()
        for e in (".hwpx", ".docx", ".xlsx", ".pptx"):
            if e in low:
                return e
        return ".zip"
    if b"<" in data[:300] or "html" in ctype:
        return ".html"
    if "javascript" in ctype:
        return ".js"
    return ".bin"


def fetch(url: str, name: str, limit: int = MAX_FETCHES, dry_run: bool = False) -> dict | None:
    if dry_run:
        print("would fetch", name, url)
        return None
    if not robots_ok(url, limit):
        print("robots.txt disallows", url)
        return None
    status, data, ctype, final = _get(url, limit)
    ext = _ext(data, ctype, url)
    out = RAW / f"{name}{ext}"
    out.write_bytes(data)
    meta = {"name": name, "url": url, "final_url": final, "status": status, "content_type": ctype,
            "bytes": len(data), "file": out.name,
            "fetched_at": datetime.datetime.now().isoformat(timespec="seconds")}
    (RAW / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(fetch_count(), status, len(data), ctype, out.name)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--sources", action="store_true", help="fetch every source in sources.json not yet in raw/")
    ap.add_argument("--only", nargs="*", help="with --sources: just these ids")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-fetches", type=int, default=MAX_FETCHES)
    args = ap.parse_args()
    if args.sources:
        for s in load_sources():
            if not s.get("fetch", True) or (args.only and s["id"] not in args.only):
                continue
            if any(RAW.glob(f"{s['id']}.meta.json")):
                continue
            fetch(s["url"], s["id"], args.max_fetches, args.dry_run)
        return
    if not (args.url and args.name):
        ap.error("give URL NAME, or --sources")
    fetch(args.url, args.name, args.max_fetches, args.dry_run)


if __name__ == "__main__":
    main()
