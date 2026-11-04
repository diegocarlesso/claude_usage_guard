"""Abre a GuardWindow com dados falsos e salva uma captura em gui_snapshot.png."""
import ctypes
import datetime as dt
import importlib.util
import sys
import time
from pathlib import Path

from PIL import ImageGrab

spec = importlib.util.spec_from_file_location("cug", sys.argv[1])
cug = importlib.util.module_from_spec(spec)
sys.modules["cug"] = cug
spec.loader.exec_module(cug)

ctypes.windll.shcore.SetProcessDpiAwareness(1)
cfg, _ = cug.load_config(None)
now = time.time()
resets = dt.datetime.fromtimestamp(now + 2 * 3600, dt.timezone.utc).isoformat()
snap = cug.UsageSnapshot.from_api({
    "five_hour": {"utilization": 83.0, "resets_at": resets},
    "seven_day": {"utilization": 31.0, "resets_at": resets},
    "iguana_necktie": {"utilization": 100.0, "resets_at": resets},
    "extra_usage": {"utilization": None, "resets_at": None}}, now - 40)
insts = [
    {"instance": "a1b2c3d4e5f6", "state": "ocioso", "model_override": "haiku", "context_tokens": 84_300,
     "hooks_ok": True, "cwd": r"F:\Projetos\Origo"},
    {"instance": "0f9e8d7c6b5a", "state": "aguardando permissão", "model_override": None,
     "context_tokens": 152_000, "hooks_ok": True, "clear_requested": True, "cwd": r"F:\Projetos\ClaudeCodeSessionLimits"},
    {"instance": "77aa88bb99cc", "state": "desconhecido", "context_tokens": None, "hooks_ok": False,
     "cwd": r"C:\Users\Diego\Documents\outro"},
]
acts = [
    {"ts": now - 600, "instance": "a1b2c3d4e5f6", "action": "compact", "reason": "sessão em 61% (limiar 60%)"},
    {"ts": now - 120, "instance": "a1b2c3d4e5f6", "action": "switch_model", "reason": "uso 5h 72% / 7d 31% → haiku"},
    {"ts": now - 30, "instance": "0f9e8d7c6b5a", "action": "failover", "reason": "proxy indisponível", "ok": False},
]
desk = [
    cug.DesktopSessionState("5f1e2d3c-aaaa", cwd="F:/Projetos/Açúcar", updated_at=now - 600, context_tokens=132_400,
                            last_level="high", last_note=cug.context_note(132_400)),
    cug.DesktopSessionState("9a8b7c6d-bbbb", cwd="F:/Projetos/Origo", updated_at=now - 3000, context_tokens=41_000,
                            last_level="attention"),
]
win = cug.GuardWindow(cfg, lambda: (snap, None, insts[:1], acts, desk))
win.refresh(reschedule=False)
win.root.update()
time.sleep(0.5)
win.root.update()
r = win.root
x, y = r.winfo_rootx(), r.winfo_rooty()
img = ImageGrab.grab(bbox=(x, y, x + r.winfo_width(), y + r.winfo_height()), all_screens=True)
out = Path(__file__).with_name("gui_snapshot.png")
img.save(out)
print(out, img.size)
r.destroy()
