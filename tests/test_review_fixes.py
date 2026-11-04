"""Testes dos achados da revisão final (cada um falhava antes da correção)."""
import io
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import GUARD_PY
from test_desktop_hook import hook_env, payload, run_hook  # noqa: F401  (fixture reaproveitada)

NOW = time.time()


def _drip_server():
    """Responde 200 e depois uma linha de cabeçalho por segundo (rede lenta)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return

            def drip(c=conn):
                try:
                    c.recv(4096)
                    c.sendall(b"HTTP/1.1 200 OK\r\n")
                    for i in range(40):
                        time.sleep(1)
                        c.sendall(f"X-Drip-{i}: a\r\n".encode())
                except OSError:
                    pass
                finally:
                    c.close()
            threading.Thread(target=drip, daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()
    return srv


def test_slow_drip_endpoint_hits_hard_deadline(tmp_path, hook_env):    # Important 1
    srv = _drip_server()
    try:
        hook_env["CUG_USAGE_URL"] = f"http://127.0.0.1:{srv.getsockname()[1]}/"
        r, secs = run_hook(hook_env, payload("hook_user_prompt.json"), timeout=60)
    finally:
        srv.close()
    assert (r.returncode, r.stdout) == (0, b"")
    assert secs < 5.0


def test_failed_fetch_backs_off(tmp_path, hook_env):                    # endpoint fora do ar
    srv = _drip_server()
    try:
        hook_env["CUG_USAGE_URL"] = f"http://127.0.0.1:{srv.getsockname()[1]}/"
        run_hook(hook_env, payload("hook_user_prompt.json"), timeout=60)
        _, secs = run_hook(hook_env, payload("hook_user_prompt.json"), timeout=60)
    finally:
        srv.close()
    assert secs < 1.5


def test_hook_command_quotes_shell_metacharacters(cug):                 # Important 2
    cmd = cug.hook_command([r"C:\Users\O'Neil(x)&y\claude_usage_guard.exe"], windows=True, sub="desktop-hook")
    assert cmd.endswith(" desktop-hook")
    exe = cmd[: -len(" desktop-hook")]
    assert (exe.startswith('"') and exe.endswith('"')) or not any(c in exe for c in "'()& ")


BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


@pytest.mark.skipif(not BASH.exists() or sys.platform != "win32", reason="precisa do Git Bash")
@pytest.mark.parametrize("folder", ["a b", "O'Neil(x)&y", "José Açúcar", "O'x (1) & y"])
def test_registered_command_runs_in_git_bash(cug, tmp_path, folder):
    d = tmp_path / folder
    d.mkdir()
    exe = d / "claude_usage_guard.exe"
    shutil.copy(r"C:\Windows\System32\whoami.exe", exe)
    cmd = cug.hook_command([str(exe)], windows=True, sub="desktop-hook")
    r = subprocess.run([str(BASH), "-c", cmd], capture_output=True, timeout=30)
    # whoami recusa o argumento (código 1): o importante é ter sido executado
    assert r.returncode not in (2, 126, 127), (cmd, r.stderr)
    assert b"unexpected EOF" not in r.stderr and b"syntax error" not in r.stderr


def test_normalization_without_usable_window_does_not_raise(cug):      # Important 3
    cfg, _ = cug.load_config(None)
    snap = cug.UsageSnapshot.from_api({"five_hour": {"utilization": None}}, NOW)
    st = cug.DesktopSessionState("s1", last_level="high")
    notes, toasts, st2 = cug.advise(cfg, snap, st, "UserPromptSubmit", None, NOW)
    assert toasts == [] and st2.last_level == "normal"
    assert all("?" not in n for n in notes)


def test_note_printed_even_if_alerts_fail(cug, state_dir, make_snap, monkeypatch, capsysbinary):  # Important 4
    cfg, _ = cug.load_config(None)
    cug.atomic_write_json(state_dir / "usage_cache.json", {"snapshot": make_snap(83, 10).to_json(),
                                                          "cooldown_until": 0})
    data = json.loads((Path(__file__).parent / "fixtures" / "hook_session_start.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(data).encode())))

    def boom(*a, **k):
        raise cug.GuardError("trava ocupada")
    monkeypatch.setattr(cug, "filter_new_toasts", boom)
    assert cug.cmd_desktop_hook(cfg, None) == 0
    out = json.loads(capsysbinary.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"].startswith("[usage-guard] Cota 5h em 83%")


def test_zero_threshold_disables_level(cug, make_snap):                 # Important 5
    cfg, _ = cug.load_config(None)
    cfg["desktop"]["high_session"] = 0
    cfg["desktop"]["critical_session"] = 0
    cug.validate_config(cfg)                                            # não levanta
    assert cug.quota_level(cfg, make_snap(97, 10)) == ("attention", "five_hour")
    cfg["desktop"]["critical_session"] = 70                             # liga critical abaixo de attention
    cfg["desktop"]["attention_session"] = 75
    with pytest.raises(cug.ConfigError):
        cug.validate_config(cfg)
