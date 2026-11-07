"""Shared paths and settings for the knowledge-base pipeline (scripts/knowledge/).

The pipeline keeps everything it downloads or generates in a work directory outside the repo
(KB_WORK, default: <system temp>/kw-knowledge). Only the final JSON lands in src/kw_mcp/knowledge/.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
KNOWLEDGE = SRC / "kw_mcp" / "knowledge"
HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.json"

WORK = Path(os.environ.get("KB_WORK") or Path(tempfile.gettempdir()) / "kw-knowledge")
RAW = WORK / "raw"          # bytes as downloaded
TEXT = WORK / "text"        # text extracted from RAW
OUT = WORK / "out"          # Claude's structured answers, one file per call
ROBOTS = WORK / "robots"
FETCH_LOG = WORK / "fetch_log.tsv"

UA = "kw-campus-research (contact kyowon1108@gmail.com)"
GAP_SECONDS = 3.5           # between two requests to the same server
MAX_FETCHES = 400           # per build, robots.txt included (rounds 1-2: 250, round 3: +120, round 5: +50)

MODEL = "claude-opus-5-5"
PIPELINE = "knowledge"      # name in the shared spend ledger
LEDGER = Path(os.environ.get("KB_LEDGER") or ROOT.parent / "claude-spend" / "ledger.py")

FORBIDDEN_HOSTS = ("daple.kwuniv.com", "klas.kw.ac.kr")
REPORT_HINT = "틀린 정보는 디스코드 #알림-설정의 제보하기(또는 /제보)로 알려 주세요"

for d in (RAW, TEXT, OUT, ROBOTS):
    d.mkdir(parents=True, exist_ok=True)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_sources() -> list[dict]:
    return json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else []


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
