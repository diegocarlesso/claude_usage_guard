"""Espera a sessão entrar num turno (last_event == UserPromptSubmit, depois de agora) e grava o pedido.

Uso: py queue_when_busy.py <session_id> <ação> [espera_máx_s]
"""
import json, os, subprocess, sys, time
sid, action = sys.argv[1], sys.argv[2]
limit = float(sys.argv[3]) if len(sys.argv) > 3 else 60
path = os.path.expanduser(rf"~\.claude-usage-guard\desktop\{sid}.json")
t0 = time.time()
while time.time() - t0 < limit:
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if d.get("last_event") == "UserPromptSubmit" and d.get("updated_at", 0) > t0:
        here = os.path.dirname(os.path.abspath(__file__))
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(here, "queue_request.py"), sid, action],
                           capture_output=True, text=True, encoding="utf-8")
        print(f"turno começou há {time.time() - d['updated_at']:.1f}s; {r.stdout.strip()}")
        sys.exit(0)
    time.sleep(0.1)
print("a sessão não começou um turno a tempo")
