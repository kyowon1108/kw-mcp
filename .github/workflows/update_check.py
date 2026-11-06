"""Run the agent's own self-update on a test wheel, inside the installed tool's Python (agent-install.yml).

  python update_check.py <wheel> <uv export of uv.lock>

Writes the release's constraints file next to the wheel (as scripts/release.sh does) and calls
agent.install_update, which installs with those pins and self-tests the result (on Windows, from a
detached shell after this process exits).
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

from kw_mcp import agent, release

wheel, exported = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
version = wheel.name.split("-")[1]
pins = wheel.with_name(release.constraints_name(version))
pins.write_text(release.constraints_text(exported.read_text(encoding="utf-8"), version, datetime.now(UTC)),
                encoding="utf-8")
print("uv:", agent.find_uv(), "| uv tool env:", agent.in_uv_tool())
sys.exit(0 if agent.install_update(wheel, pins, version) else 1)
