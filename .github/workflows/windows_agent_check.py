"""Windows-only agent behaviour, run inside the installed tool's Python by windows-agent.yml."""

import time
import winreg

from kw_mcp import agent

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

command = agent.agent_command()
print("agent command:", command)
assert command[0].lower().endswith("pythonw.exe"), "expected pythonw so no console window opens"

lock = agent.single_instance()
try:
    agent.single_instance()
    raise AssertionError("a second lock should fail")
except agent.AlreadyRunning:
    print("single-instance lock: ok")
finally:
    lock.close()

print(agent.install_autostart())
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
    value = winreg.QueryValueEx(key, agent.WINDOWS_RUN_VALUE)[0]
print("Run key:", value)
assert "kw_mcp" in value and "agent" in value
assert agent.autostart_installed()

# The spawned agent is not linked, so it should log that and exit on its own.
log = agent.default_log_file()
for _ in range(30):
    if log.exists() and "연결되지 않았습니다" in log.read_text(encoding="utf-8"):
        break
    time.sleep(1)
print("agent log:", log.read_text(encoding="utf-8") if log.exists() else "(missing)")
assert log.exists() and "연결되지 않았습니다" in log.read_text(encoding="utf-8"), "spawned agent did not run"

agent.uninstall_autostart()
assert not agent.autostart_installed()
print("autostart removed: ok")
