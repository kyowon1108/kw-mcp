"""macOS-only agent behaviour on a fresh runner, run inside the installed tool's Python by agent-install.yml."""

import plistlib

from kw_mcp import agent

job = plistlib.loads(agent.launchd_plist())
print("launchd job:", job["Label"], job["ProgramArguments"])
assert job["ProgramArguments"][1:4] == ["-m", "kw_mcp", "agent"]
assert job["KeepAlive"] == {"SuccessfulExit": False} and job["RunAtLoad"] is True
assert agent.find_uv(), "uv must be found even with launchd's bare PATH"

lock = agent.single_instance()
try:
    agent.single_instance()
    raise AssertionError("a second lock should fail")
except agent.AlreadyRunning:
    print("single-instance lock: ok")
finally:
    lock.close()
