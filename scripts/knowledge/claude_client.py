"""One structured Claude call, with the spend ledger in front of it and behind it.

- The API key comes from SSM SecureString /kw/collector/anthropic-api-key (ap-northeast-2), read with boto3
  WithDecryption. It is held in memory only: never printed, logged or written.
- Before every call: ledger.remaining(budget, "knowledge") must be above 0.5 USD plus what calls already in
  flight may cost. After every response: ledger.record("knowledge", model, usage, note).
- Model claude-opus-5-5, no `thinking`/`temperature` (both 400 on this model); depth via output_config.effort;
  JSON via output_config.format (structured outputs); streaming + get_final_message() for long outputs.
- stop_reason is checked before the content is read: refusal and max_tokens are errors, not data.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

from kbcommon import LEDGER, MODEL, OUT, PIPELINE

SSM_NAME = "/kw/collector/anthropic-api-key"
SSM_REGION = "ap-northeast-2"
IN_FLIGHT_RESERVE = 1.0  # USD held back per call already running

_lock = threading.Lock()
_in_flight = 0
_client = None
_ledger = None


class BudgetExhausted(RuntimeError):
    pass


class BadStop(RuntimeError):
    pass


def ledger():
    global _ledger
    if _ledger is None:
        spec = importlib.util.spec_from_file_location("kb_spend_ledger", LEDGER)
        if spec is None or spec.loader is None:
            raise SystemExit(f"spend ledger not found at {LEDGER}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ledger = mod
    return _ledger


def client():
    global _client
    if _client is None:
        import anthropic
        import boto3

        ssm = boto3.client("ssm", region_name=SSM_REGION)
        key = ssm.get_parameter(Name=SSM_NAME, WithDecryption=True)["Parameter"]["Value"]
        _client = anthropic.Anthropic(api_key=key, max_retries=4, timeout=900.0)
        del key
    return _client


def remaining(budget: float) -> float:
    return ledger().remaining(budget, PIPELINE)


def call(*, note: str, system: list[dict] | str, content: list[dict], schema: dict, budget: float,
         effort: str = "medium", max_tokens: int = 16000, out_name: str | None = None) -> dict:
    """Runs one call and returns {"data": parsed JSON, "usage": {...}, "usd": cost}. Saves it under OUT."""
    global _in_flight
    with _lock:
        left = remaining(budget)
        if left <= 0.5 + IN_FLIGHT_RESERVE * _in_flight:
            raise BudgetExhausted(f"budget left {left:.2f} USD, {_in_flight} calls in flight")
        _in_flight += 1
    t0 = time.time()
    try:
        with client().messages.stream(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        ) as stream:
            msg = stream.get_final_message()
    finally:
        with _lock:
            _in_flight -= 1
    usd = ledger().record(PIPELINE, MODEL, msg.usage, note)
    usage = {k: getattr(msg.usage, k, None) for k in
             ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
    meta = {"note": note, "stop_reason": msg.stop_reason, "usage": usage, "usd": round(usd, 4),
            "seconds": round(time.time() - t0, 1), "request_id": getattr(msg, "_request_id", None)}
    if msg.stop_reason == "refusal":
        details = getattr(msg, "stop_details", None)
        _save(out_name or note, {"meta": meta, "refusal": str(details)})
        raise BadStop(f"{note}: refusal ({details})")
    if msg.stop_reason == "max_tokens":
        _save(out_name or note, {"meta": meta, "partial": _text(msg)})
        raise BadStop(f"{note}: hit max_tokens ({max_tokens})")
    data = json.loads(_text(msg))
    result = {"meta": meta, "data": data}
    _save(out_name or note, result)
    return result


def _text(msg) -> str:
    return next((b.text for b in msg.content if b.type == "text"), "")


def _save(name: str, obj) -> Path:
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def doc_block(title: str, text: str, cache: bool = False) -> dict:
    """A source as a plain-text document block (citations off: structured outputs reject them)."""
    block = {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text},
             "title": title}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block
