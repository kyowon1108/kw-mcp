"""The answering agent: claude-opus-5-5 in a manual tool loop over kw-mcp's real MCP tools.

Tools come from kw_mcp.server's own MCP server (names, descriptions and schemas exactly as Claude
sees them), called through MCPServer.call_tool so the real wrappers run (expected_errors, scrub).
- personal tools: a KlasService over the synthetic fixture (evals/fixture.py), never real KLAS
- public tools: the live kw-campus public API as kw_mcp.public_api reads it, cached per run and paced
- read_school_notice: kw_mcp.notices behind a gate of 60 school-site requests per run, 3 s per host
- pieces that exist in the tree but aren't MCP tools yet (service.scholarships, src/kw_mcp/rules,
  kw_mcp.knowledge) are offered as provisional tools until the server registers its own
The system prompt carries kw_mcp.server.INSTRUCTIONS, as the MCP server sends it.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import inspect
import json
import logging
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals import llm
from evals.fixture import FIXTURE, build_service

ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = ROOT / "src" / "kw_mcp" / "rules"
NOW_TEXT = ("2026-11-07(토)", "13:00")
SITE_CAP = 60
SITE_GAP_S = 3.0
PUBLIC_GAP_S = 0.4
PUBLIC_CAP = 600
TOOL_TIMEOUT_S = 120.0
RULES_CHARS = 12_000
SITE_CAP_MESSAGE = "평가 실행의 학교 사이트 요청 상한"

SYSTEM_TEMPLATE = """오늘은 {date}, 지금은 {time}(한국 시간)입니다.
사용자는 광운대학교 학생이고, Claude에 KW CAMPUS (광운 캠퍼스) 확장을 연결해 두었습니다.

<kw-campus 서버 안내>
{instructions}</kw-campus 서버 안내>"""


# --- isolation ---------------------------------------------------------------------------------

def isolate() -> None:
    """No real keychain, login state, update server or invite: the run touches only the fixture,
    the public API named by ~/.config/kw-campus/api-url, and (through the gate) school sites."""
    import keyring
    from keyring.backend import KeyringBackend

    from kw_mcp import klas

    class _NoKeychain(KeyringBackend):
        priority = 1

        def get_password(self, service: str, username: str) -> None:
            return None

        def set_password(self, service: str, username: str, password: str) -> None:
            raise RuntimeError("the eval never writes the keychain")

        def delete_password(self, service: str, username: str) -> None:
            raise RuntimeError("the eval never writes the keychain")

    # httpx logs every request URL at INFO, and the public API URL carries the invite token.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    keyring.set_keyring(_NoKeychain())
    klas.LOGIN_STATE_FILE = Path(tempfile.mkdtemp(prefix="kw-eval-")) / "login-state.json"
    for name in ("KW_MCP_DISTRIBUTION", "KW_CAMPUS_INVITE", "KLAS_ID", "KLAS_PASSWORD"):
        os.environ.pop(name, None)


# --- public API and school sites -----------------------------------------------------------------

def _eval_public_api(gap_s: float = PUBLIC_GAP_S, cap: int = PUBLIC_CAP) -> Any:
    from kw_mcp.public_api import PublicApi, PublicUnavailable

    class EvalPublicApi(PublicApi):
        """The live public API, asked once per distinct request in a run and at most every gap_s."""

        def __init__(self) -> None:
            super().__init__()
            self.cache: dict[str, Any] = {}
            self.requests = 0
            self._locks: dict[str, asyncio.Lock] = {}
            self._pace = asyncio.Lock()
            self._next = 0.0

        async def _get(self, path: str, params: dict[str, Any]) -> Any:
            key = json.dumps([path, {k: v for k, v in params.items() if v is not None}], sort_keys=True,
                             ensure_ascii=False, default=str)
            if key in self.cache:
                return copy.deepcopy(self.cache[key])
            async with self._locks.setdefault(key, asyncio.Lock()):
                if key in self.cache:
                    return copy.deepcopy(self.cache[key])
                async with self._pace:
                    if self.requests >= cap:
                        raise PublicUnavailable("평가 실행의 공개 API 요청 상한에 도달했습니다.")
                    wait = self._next - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._next = time.monotonic() + gap_s
                    self.requests += 1
                data = await super()._get(path, params)
                self.cache[key] = data
                return copy.deepcopy(data)

    return EvalPublicApi()


class SiteGate:
    """notices.Gate for the eval: at most `cap` school-site requests for the whole run (counted in a
    file so a resumed run keeps counting) and `interval` seconds between requests to one host."""

    def __init__(self, state: Path | None, cap: int = SITE_CAP, interval: float = SITE_GAP_S) -> None:
        from kw_mcp import notices

        self.state, self.cap = state, cap
        self.count = json.loads(state.read_text())["count"] if state and state.exists() else 0
        self._pacer = notices.Pacer(interval)
        self._lock = asyncio.Lock()
        self._refused = notices.Refused

    async def before(self, url: str) -> None:
        async with self._lock:
            if self.count >= self.cap:
                raise self._refused(f"{SITE_CAP_MESSAGE}({self.cap}건)에 도달해 학교 사이트를 읽지 않았습니다.")
            self.count += 1
            if self.state:
                self.state.write_text(json.dumps({"count": self.count}))
        await self._pacer.before(url)


# --- provisional tools ---------------------------------------------------------------------------

@dataclass
class ExtraTool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[dict[str, Any]], Awaitable[Any]]
    source: str


def _rules_view(topic: str, query: str | None) -> dict[str, Any]:
    """A slice of src/kw_mcp/rules/<topic>.json: items whose text has every query word, with the
    sources they cite. No query: the section list."""
    data = json.loads((RULES_DIR / f"{topic}.json").read_text(encoding="utf-8"))
    version = data.get("version", {})
    out: dict[str, Any] = {"topic": topic, "basis": version.get("basis"), "disclaimer": data.get("disclaimer")}
    sections = [k for k in data if k not in ("version", "disclaimer")]
    words = [w for w in (query or "").split() if w]
    if not words:
        out["sections"] = {k: json.dumps(data[k], ensure_ascii=False)[:160] for k in sections}
        out["hint"] = "query로 항목을 고르세요(예: '2024', '복수전공', '정보융합', '교양')."
        return out
    hits: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        text = json.dumps(node, ensure_ascii=False)
        if not all(w in text for w in words):
            return
        small = len(text) <= 2500
        if small or not isinstance(node, (dict, list)):
            hits.append({"path": path, "item": node})
            return
        children = node.items() if isinstance(node, dict) else enumerate(node)
        before = len(hits)
        for k, v in children:
            walk(v, f"{path}.{k}" if isinstance(node, dict) else f"{path}[{k}]")
        if len(hits) == before:  # the words only meet across children: keep the whole node
            hits.append({"path": path, "item": node})

    for k in sections:
        walk(data[k], k)
    used, items = 0, []
    for h in hits:
        size = len(json.dumps(h, ensure_ascii=False))
        if used + size > RULES_CHARS:
            out["truncated"] = f"{len(hits) - len(items)}개 항목을 더 찾았지만 길이 제한으로 뺐습니다. query를 좁히세요."
            break
        items.append(h)
        used += size
    cited = {s for h in items for s in _source_ids(h["item"])}
    out["items"] = items
    out["sources"] = [s for s in version.get("sources", []) if s.get("id") in cited]
    if not items:
        out["note"] = "이 자료에서 찾지 못했습니다."
    return out


def _source_ids(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("source_ids", "source_id"):
                found.update([v] if isinstance(v, str) else [x for x in v or [] if isinstance(x, str)])
            else:
                found |= _source_ids(v)
    elif isinstance(node, list):
        for v in node:
            found |= _source_ids(v)
    return found


PROVISIONAL = ("scholarships", "rules", "knowledge")


def provisional_tools(server_names: set[str], service: Any, wanted: tuple[str, ...] = PROVISIONAL) -> list[ExtraTool]:
    """Tools for pieces that exist in the tree but that the MCP server doesn't register yet. A piece
    is left out once the server registers a tool for it (by tool name) or imports its module."""
    extra: list[ExtraTool] = []
    lowered = {n.lower() for n in server_names}
    server_source = (ROOT / "src" / "kw_mcp" / "server.py").read_text(encoding="utf-8")
    server_uses = {m for m in ("knowledge", "simulation")
                   if re.search(rf"^(?:from|import)\b[^\n]*\b{m}\b|\b{m}\.\w+\(", server_source, re.MULTILINE)}
    if ("scholarships" in wanted and hasattr(service, "scholarships")
            and not any("scholarship" in n for n in lowered)):
        async def scholarships(_: dict[str, Any]) -> Any:
            return await service.scholarships()

        extra.append(ExtraTool(
            "get_scholarships",
            "장학 수혜 내역(KLAS 장학조회): 학기별로 받은 장학금 이름과 금액(원), 학기 합계와 전체 합계. "
            "신청 가능 여부나 중복 수혜 규정은 들어 있지 않습니다.",
            {"type": "object", "properties": {}}, scholarships, "service.scholarships"))
    topics = sorted(p.stem for p in RULES_DIR.glob("*.json")) if RULES_DIR.is_dir() else []
    if ("rules" in wanted and topics and not server_uses
            and not any(w in n for n in lowered for w in ("rule", "knowledge", "regulation", "simulat"))):
        async def rules(args: dict[str, Any]) -> Any:
            topic = args.get("topic")
            if topic not in topics:
                raise ValueError(f"topic은 {', '.join(topics)} 중 하나입니다.")
            return _rules_view(topic, args.get("query"))

        extra.append(ExtraTool(
            "school_rules",
            "광운대 졸업요건·다전공 규칙 자료(학칙·학칙 시행세칙·다전공 내규·학사안내 페이지에서 옮긴 참고용, 2026-11-07 확인). "
            "topic=graduation(입학 연도별 졸업학점·교양·전공 이수학점, 졸업 조건) 또는 multi_major(심화·복수·부·연계·"
            "마이크로·학생설계융합전공의 이수학점·자격·상호인정, 연계·마이크로전공 목록). query는 띄어쓰기로 나눈 검색어로, "
            "모두 들어간 항목만 돌려줍니다(예: '2024 정보융합', '복수전공 상호인정'). 결과의 sources에 규정 이름·조항·URL이 있습니다.",
            {"type": "object", "properties": {
                "topic": {"type": "string", "enum": topics},
                "query": {"type": "string", "description": "검색어(띄어쓰기로 여러 개)"}},
             "required": ["topic"]}, rules, "src/kw_mcp/rules/*.json"))
    knowledge = None
    if "knowledge" in wanted and "knowledge" not in server_uses:
        try:
            knowledge = importlib.import_module("kw_mcp.knowledge")
        except ImportError:
            knowledge = None
    search = next((getattr(knowledge, n) for n in ("search", "lookup", "query") if callable(getattr(knowledge, n, None))),
                  None) if knowledge else None
    if search and not any("knowledge" in n for n in lowered):
        async def kb(args: dict[str, Any]) -> Any:
            out = search(args.get("query", ""))
            return await out if inspect.isawaitable(out) else out

        extra.append(ExtraTool(
            "school_knowledge",
            (inspect.getdoc(search) or "광운대 학사·장학·생활 안내 지식 베이스 검색.").split("\n\n")[0],
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            kb, f"kw_mcp.knowledge.{search.__name__}"))
    return extra


# --- the toolset ----------------------------------------------------------------------------------

@dataclass
class ToolResult:
    blocks: list[dict[str, Any]]
    is_error: bool
    seconds: float
    site_cap_hit: bool = False

    def text(self) -> str:
        return "\n".join(b["text"] for b in self.blocks if b["type"] == "text")


@dataclass
class Toolset:
    server: Any
    definitions: list[dict[str, Any]]
    extras: dict[str, ExtraTool]
    service: Any
    public: Any
    gate: SiteGate | None
    meta: dict[str, Any] = field(default_factory=dict)

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        start = time.monotonic()
        try:
            blocks, is_error = await asyncio.wait_for(self._call(name, args or {}), TOOL_TIMEOUT_S)
        except TimeoutError:
            blocks, is_error = [{"type": "text", "text": f"도구가 {int(TOOL_TIMEOUT_S)}초 안에 끝나지 않았습니다."}], True
        result = ToolResult(blocks, is_error, round(time.monotonic() - start, 2))
        result.site_cap_hit = is_error and SITE_CAP_MESSAGE in result.text()
        return result

    async def _call(self, name: str, args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        from mcp.server.mcpserver.exceptions import ToolError

        if name in self.extras:
            try:
                out = await self.extras[name].run(args)
            except Exception as e:  # noqa: BLE001 - provisional tools report errors the way the server's wrapper would
                return [{"type": "text", "text": str(e) or e.__class__.__name__}], True
            return [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2, default=str)}], False
        if name == "klas_status":  # the real one reads the keychain; answer for the fixture instead
            return [{"type": "text", "text": json.dumps(self._status(), ensure_ascii=False, indent=2)}], False
        try:
            result = await self.server.mcp.call_tool(name, args)
        except ToolError as e:
            return [{"type": "text", "text": str(e)}], True
        except Exception as e:  # noqa: BLE001 - UnexpectedToolError and friends: what an MCP client would show
            cause = e.__cause__ or e
            return [{"type": "text", "text": f"Error executing tool {name}: {cause.__class__.__name__}: {cause}"}], True
        blocks = []
        for item in getattr(result, "content", []) or []:
            if getattr(item, "type", "") == "text":
                blocks.append({"type": "text", "text": item.text})
            elif getattr(item, "type", "") == "image":
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": item.mime_type,
                                                           "data": item.data}})
        if not blocks:
            blocks = [{"type": "text", "text": "(빈 결과)"}]
        return blocks, bool(getattr(result, "is_error", False))

    def _status(self) -> dict[str, Any]:
        from kw_mcp import klas

        return {"version": klas.package_version(), "distribution": "mcpb",
                "login": {"source": "확장 설정", "login_id": "2024****"}, "last_login": {"ok": True},
                "klas_requests_last_10_min": 3, "rejected_login": None,
                "public_api": "configured" if self.public.configured else "not configured",
                "update": "최신 버전입니다(또는 확인할 수 없음)."}

    def fingerprints(self) -> dict[str, str]:
        """sha256 of each tool's definition, to tell which tools changed between rounds."""
        return {d["name"]: hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
                for d in self.definitions}


async def build_toolset(state_dir: Path | None = None, fixture: Path = FIXTURE, live: bool = True,
                        provisional: tuple[str, ...] = PROVISIONAL) -> Toolset:
    """live=False keeps the public API unconfigured and gives read_school_notice no gate budget (tests).
    provisional: which unregistered pieces to offer as tools (see provisional_tools)."""
    isolate()
    from kw_mcp import notices
    from kw_mcp import server as srv
    from kw_mcp.public_api import PublicApi

    service, _ = build_service(fixture)
    srv.set_service(service)
    public = _eval_public_api() if live else PublicApi("")
    srv.set_public(public)
    gate = SiteGate(state_dir / "site_fetches.json" if state_dir else None, cap=SITE_CAP if live else 0)
    notices.PACER = gate  # read_notice uses notices.PACER when the server passes no gate
    if live:  # keep every page and file read in this run, so the same notice is fetched from the school once
        notices.CACHE_S, notices.CACHE_PAGES, notices.CACHE_FILES = 6 * 3600.0, 256, 64
    listed = await srv.mcp.list_tools()
    definitions = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in listed]
    extras = provisional_tools({t.name for t in listed}, service, provisional)
    definitions += [{"name": e.name, "description": e.description, "input_schema": e.schema} for e in extras]
    meta = {"server_tools": [t.name for t in listed], "provisional_tools": {e.name: e.source for e in extras},
            "instructions_sha": hashlib.sha256(srv.INSTRUCTIONS.encode()).hexdigest()[:16],
            "fixture_sha": hashlib.sha256(fixture.read_bytes()).hexdigest()[:16],
            "public_api_configured": public.configured}
    return Toolset(srv, definitions, {e.name: e for e in extras}, service, public, gate, meta)


def system_prompt() -> str:
    from kw_mcp.server import INSTRUCTIONS

    return SYSTEM_TEMPLATE.format(date=NOW_TEXT[0], time=NOW_TEXT[1], instructions=INSTRUCTIONS)


# --- the agent loop -------------------------------------------------------------------------------

async def answer(api: Any, tools: Toolset, question: str, *, case_id: str = "", effort: str = "medium",
                 max_turns: int = 12, max_tokens: int = 12000, reserve: float = 0.0) -> dict[str, Any]:
    """Run one question to a final answer. Returns the answer, a trace in the eval report's turn
    format, tool-call records, summed usage and the stop reason."""
    system = system_prompt()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    trace: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    calls: list[dict[str, Any]] = []
    usage: dict[str, int] = {}
    status, stop_reason, final, model, api_seconds = "ok", None, "", llm.MODEL, 0.0
    for turn in range(max_turns):
        started = time.monotonic()
        response = await llm.create(
            api, note=f"answer {case_id} t{turn}", reserve=reserve, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools.definitions, messages=messages, cache_control={"type": "ephemeral"},
            thinking={"type": "adaptive", "display": "summarized"}, output_config={"effort": effort})
        api_seconds += time.monotonic() - started
        model, stop_reason = response.model, response.stop_reason
        llm.add_usage(usage, response.usage)
        messages.append({"role": "assistant", "content": response.content})
        thinking = "\n".join(b.thinking for b in response.content if b.type == "thinking" and getattr(b, "thinking", ""))
        texts = [b.text for b in response.content if b.type == "text"]
        uses = [b for b in response.content if b.type == "tool_use"]
        if texts:
            trace.append({"role": "assistant", "content": "\n".join(texts), **({"thinking": thinking} if thinking else {})})
            thinking = ""
        if stop_reason == "pause_turn":
            continue
        if stop_reason != "tool_use" or not uses:
            final = "\n".join(texts)
            if stop_reason == "max_tokens":
                status = "truncated"
            elif stop_reason == "refusal":
                status = "refusal"
            break
        results = await asyncio.gather(*(tools.call(u.name, u.input) for u in uses))
        content = []
        for u, r in zip(uses, results, strict=True):
            trace.append({"role": "tool_call", "name": u.name,
                          "content": json.dumps(u.input, ensure_ascii=False, indent=2),
                          **({"thinking": thinking} if thinking else {})})
            thinking = ""
            images = sum(b["type"] == "image" for b in r.blocks)
            trace.append({"role": "tool_result", "name": u.name, "is_error": r.is_error,
                          "content": r.text() + (f"\n[이미지 {images}장]" if images else "")})
            calls.append({"name": u.name, "input": u.input, "is_error": r.is_error, "chars": len(r.text()),
                          "images": images, "seconds": r.seconds, "site_cap_hit": r.site_cap_hit})
            content.append({"type": "tool_result", "tool_use_id": u.id, "content": r.blocks,
                            **({"is_error": True} if r.is_error else {})})
        messages.append({"role": "user", "content": content})
    else:
        status = "turn_limit"
    return {"answer": final, "status": status, "stop_reason": stop_reason, "model": model, "usage": usage,
            "cost_usd": round(llm.cost(usage), 4), "api_seconds": round(api_seconds, 1), "tool_calls": calls,
            "trace": trace, "site_cap_hit": any(c["site_cap_hit"] for c in calls)}
