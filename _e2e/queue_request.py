"""Grava (ou cancela) um pedido de botão na fila de uma sessão do Desktop, como o clique na janela.

Uso: py queue_request.py <session_id> <ação>   (ações: economy_on, economy_off, compact, tools, research)
"""
import importlib.util
import sys
import time
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "ClaudeCodeSessionLimits" / "claude_usage_guard.py"
spec = importlib.util.spec_from_file_location("cug", GUARD)
cug = importlib.util.module_from_spec(spec)
sys.modules["cug"] = cug
spec.loader.exec_module(cug)

sid, action = sys.argv[1], sys.argv[2]
pending = cug.toggle_request(sid, action, time.time())
print(f"{action}: {'pendente' if pending else 'cancelado'}; fila = {cug.read_pending(sid)}")
