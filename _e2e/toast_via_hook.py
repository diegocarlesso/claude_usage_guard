"""Roda o desktop-hook do .exe com cota alta (cache falso) e toast ligado, e
confere no registro do Windows se a notificação chegou."""
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import winreg
from pathlib import Path

exe, guard_py = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("cug", guard_py)
cug = importlib.util.module_from_spec(spec)
sys.modules["cug"] = cug
spec.loader.exec_module(cug)
KEY = (r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
       r"\{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe")


def last_added():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        return winreg.QueryValueEx(k, "LastNotificationAddedTime")[0]


tmp = Path(tempfile.mkdtemp(prefix="cug-toast-"))
now = time.time()
r = dt.datetime.fromtimestamp(now + 3900, dt.timezone.utc).isoformat()
snap = cug.UsageSnapshot.from_api({"five_hour": {"utilization": 84, "resets_at": r},
                                   "seven_day": {"utilization": 20, "resets_at": r}}, now)
(tmp / "usage_cache.json").write_text(json.dumps({"snapshot": snap.to_json(), "cooldown_until": 0}), encoding="utf-8")
env = {k: v for k, v in os.environ.items() if not k.startswith("CUG_")}
env.update(CUG_STATE_DIR=str(tmp))
payload = {"session_id": str(uuid.uuid4()), "transcript_path": "", "cwd": r"F:\Projetos\Teste do toast",
           "hook_event_name": "SessionStart", "source": "startup"}
before = last_added()
t0 = time.time()
p = subprocess.run([exe, "desktop-hook"], input=json.dumps(payload).encode(), capture_output=True, env=env)
print("hook rc", p.returncode, f"{time.time() - t0:.2f}s", "nota:", bool(p.stdout))
while time.time() - t0 < 12 and last_added() == before:
    time.sleep(0.5)
print("NOTIFICAÇÃO CHEGOU AO WINDOWS" if last_added() != before else "nada chegou", f"({time.time() - t0:.1f}s)")
