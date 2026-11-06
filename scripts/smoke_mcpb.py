"""Start an unpacked .mcpb the way Claude Desktop does and check it lists the manifest's tools.

  python scripts/smoke_mcpb.py <unpacked bundle dir>             manifest's mcp_config command
  python scripts/smoke_mcpb.py <unpacked bundle dir> --entry-point   `uv run ... python <entry_point>`

Runs the command with the manifest env (user_config left empty, as on a first launch without an
invite), speaks MCP over stdio (initialize, then tools/list) and fails unless the tools equal the
manifest's list. KLAS is never contacted.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

TIMEOUT_S = 600  # the first launch downloads Python and every dependency


def command(bundle: Path, manifest: dict, entry_point: bool) -> tuple[list[str], dict[str, str]]:
    config = manifest["server"]["mcp_config"]
    env = {k: re.sub(r"\$\{user_config\.\w+\}", "", v) for k, v in config.get("env", {}).items()}
    args = [a.replace("${__dirname}", str(bundle)) for a in config["args"]]
    if entry_point:  # what a host that runs the uv entry_point itself would do
        args = ["run", "--frozen", "--no-dev", "--directory", str(bundle), "python", manifest["server"]["entry_point"]]
    return [config["command"], *args], {**os.environ, **env}


def main(argv: list[str]) -> int:
    bundle = Path(argv[0]).resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    argv_, env = command(bundle, manifest, "--entry-point" in argv)
    print("starting:", " ".join(argv_), flush=True)
    proc = subprocess.Popen(argv_, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, env=env,
                            cwd=bundle)
    lines: queue.Queue[bytes] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()

    def send(message: dict) -> None:
        proc.stdin.write((json.dumps(message) + "\n").encode())
        proc.stdin.flush()

    def reply(request_id: int) -> dict:
        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                message = json.loads(lines.get(timeout=max(0.1, deadline - time.monotonic())))
            except queue.Empty:
                break
            if message.get("id") == request_id:
                if "error" in message:
                    raise SystemExit(f"server error: {message['error']}")
                return message["result"]
        raise SystemExit(f"no answer to request {request_id} within {TIMEOUT_S}s (exit code {proc.poll()})")

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}})
        info = reply(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"] for t in reply(2)["tools"]}
    finally:
        proc.stdin.close()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    expected = {t["name"] for t in manifest["tools"]}
    print(f"server {info['serverInfo']}; {len(tools)} tools")
    if tools != expected:
        print(f"manifest only: {sorted(expected - tools)}; server only: {sorted(tools - expected)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
