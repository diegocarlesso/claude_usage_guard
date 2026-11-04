"""Spike descartável (04/11): o hook Stop com decision:block funciona na aba Code do Desktop?

Registrado só em _e2e\\proj\\.claude\\settings.json. Em cada evento grava a entrada em
stop_probe.log. No Stop, se existir proj\\.probe-pending (e stop_hook_active for falso),
apaga o arquivo e devolve {"decision": "block", "reason": ...}: o Claude deveria seguir
trabalhando com o reason como instrução.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "stop_probe.log")
FLAG = os.path.join(HERE, "proj", ".probe-pending")

raw = sys.stdin.buffer.read().decode("utf-8", "replace")
try:
    data = json.loads(raw)
except ValueError:
    data = {"_raw": raw[:500]}
out = ""
if data.get("hook_event_name") == "Stop" and os.path.exists(FLAG) and not data.get("stop_hook_active"):
    os.remove(FLAG)
    out = json.dumps({"decision": "block",
                      "reason": "[usage-guard] Pedido do usuario pelo Claude Usage Guard (teste): "
                                "responda apenas a palavra ABACAXI-STOP-OK e pare."})
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": time.strftime("%H:%M:%S"), "event": data.get("hook_event_name"),
                        "stop_hook_active": data.get("stop_hook_active"),
                        "session_id": data.get("session_id"), "keys": sorted(data), "out": out},
                       ensure_ascii=False) + "\n")
if out:
    sys.stdout.write(out)
