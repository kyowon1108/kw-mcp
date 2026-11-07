"""Claude API access for the evals: the key comes from SSM, every response goes into the spend ledger.

Every call checks the eval pipeline's remaining budget first (ledger.remaining(60, "eval") must stay
above 0.5 plus the reserve the caller keeps for a later round) and records its usage afterwards,
including responses that end in an error state. The key is never printed or written anywhere.
"""

from __future__ import annotations

import importlib.util
import os
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

MODEL = "claude-opus-5-5"
PIPELINE = "eval"
BUDGET_USD = 60.0  # raised from 35 for rounds 2-3 (owner: spend the expiring credits on quality)
MIN_LEFT_USD = 0.5
SSM_KEY = "/kw/collector/anthropic-api-key"
SSM_REGION = "ap-northeast-2"
LEDGER = Path(os.environ.get("KW_EVAL_LEDGER", "/Users/kapr/Projects/University/v11/claude-spend/ledger.py"))


class BudgetExhausted(RuntimeError):
    """The eval budget (minus the reserve) is spent; stop cleanly."""


class ModelMismatch(RuntimeError):
    """The response came from a different model than the one asked for."""


@cache
def ledger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("claude_spend_ledger", LEDGER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"spend ledger not found at {LEDGER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def remaining() -> float:
    return float(ledger().remaining(BUDGET_USD, PIPELINE))


def spent() -> float:
    return float(ledger().spent(PIPELINE))


def check_budget(reserve: float = 0.0) -> None:
    left = remaining()
    if left <= MIN_LEFT_USD + reserve:
        raise BudgetExhausted(f"eval budget left ${left:.2f} (reserve ${reserve:.2f}); stopping")


def _api_key() -> str:
    import boto3  # only the API path needs it; tests never import it

    ssm = boto3.client("ssm", region_name=SSM_REGION)
    return ssm.get_parameter(Name=SSM_KEY, WithDecryption=True)["Parameter"]["Value"]


def client() -> Any:
    import anthropic

    return anthropic.AsyncAnthropic(api_key=_api_key(), max_retries=4, timeout=300.0)


def usage_dict(usage: Any) -> dict[str, int]:
    get = (lambda k: usage.get(k)) if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
    return {k: int(get(k) or 0) for k in
            ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}


def add_usage(total: dict[str, int], usage: Any) -> dict[str, int]:
    for k, v in usage_dict(usage).items():
        total[k] = total.get(k, 0) + v
    return total


def cost(usage: Any) -> float:
    return float(ledger().cost(MODEL, usage_dict(usage)))


async def create(api: Any, *, note: str, reserve: float = 0.0, stream: bool = False, **params: Any) -> Any:
    """messages.create with the budget check before and the ledger record after. stream=True for
    long outputs (the SDK refuses non-streaming requests whose max_tokens could take over 10 minutes)."""
    check_budget(reserve)
    params.setdefault("model", MODEL)
    if stream:
        async with api.messages.stream(**params) as s:
            response = await s.get_final_message()
    else:
        response = await api.messages.create(**params)
    ledger().record(PIPELINE, params["model"], response.usage, note)
    if not str(response.model).startswith(params["model"]):
        raise ModelMismatch(f"asked for {params['model']}, served by {response.model}")
    return response
