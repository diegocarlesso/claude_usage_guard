import http.server
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import GUARD_PY

FIX = Path(__file__).parent / "fixtures"
SID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"


def payload(name, **over):
    data = json.loads((FIX / name).read_text(encoding="utf-8"))
    data.update(over)
    return data


@pytest.fixture
def hook_env(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CUG_", "CLAUDE"))}
    env.update(CUG_STATE_DIR=str(tmp_path), CUG_USAGE_URL="http://127.0.0.1:9/",
               CLAUDE_CODE_OAUTH_TOKEN="token-de-teste", CLAUDE_CONFIG_DIR=str(tmp_path / "claude"),
               CUG_DESKTOP_TOAST="false")
    return env


def write_cache(tmp_path, make_snap, s5, s7=10, fetched_at=None):
    snap = make_snap(s5, s7, fetched_at=fetched_at)
    (tmp_path / "usage_cache.json").write_text(json.dumps({"snapshot": snap.to_json(), "cooldown_until": 0}),
                                               encoding="utf-8")


def run_hook(env, data, timeout=20):
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(GUARD_PY), "desktop-hook"], input=raw.encode("utf-8"),
                       capture_output=True, env=env, timeout=timeout)
    return r, time.time() - t0


def test_session_start_high_outputs_note(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 83)
    r, _ = run_hook(hook_env, payload("hook_session_start.json"))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert list(out) == ["hookSpecificOutput"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert out["hookSpecificOutput"]["additionalContext"].startswith("[usage-guard] Cota 5h em 83%")
    st = json.loads((tmp_path / "desktop" / f"{SID}.json").read_text(encoding="utf-8"))
    assert st["last_level"] == "high" and st["cwd"] == r"F:\Projetos\Açúcar"
    alerts = json.loads((tmp_path / "desktop" / "alerts.json").read_text(encoding="utf-8"))
    assert len(alerts) == 1 and next(iter(alerts)).endswith(":high")


def test_normal_outputs_nothing(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    r, _ = run_hook(hook_env, payload("hook_session_start.json"))
    assert (r.returncode, r.stdout) == (0, b"")


def _transcript(tmp_path):
    t = tmp_path / "t.jsonl"
    lines = [{"type": "user", "message": {"content": "oi"}},
             {"type": "assistant", "message": {"usage": {"input_tokens": 100_000, "cache_read_input_tokens": 30_000}}}]
    t.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return str(t)


def test_stop_measures_context_then_prompt_gets_note(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    tr = _transcript(tmp_path)
    r, _ = run_hook(hook_env, payload("hook_stop.json", transcript_path=tr))
    assert (r.returncode, r.stdout) == (0, b"")
    st = json.loads((tmp_path / "desktop" / f"{SID}.json").read_text(encoding="utf-8"))
    assert st["context_tokens"] == 130_000
    r, _ = run_hook(hook_env, payload("hook_user_prompt.json", transcript_path=tr))
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit" and "Contexto com 130k tokens" in out["additionalContext"]


def test_toast_not_repeated_across_sessions(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 83)
    run_hook(hook_env, payload("hook_session_start.json"))
    run_hook(hook_env, payload("hook_session_start.json", session_id="11111111-2222-3333-4444-555555555555"))
    alerts = json.loads((tmp_path / "desktop" / "alerts.json").read_text(encoding="utf-8"))
    assert len([k for k in alerts if not k.startswith("context:")]) == 1


@pytest.mark.parametrize("raw", ["não é json", "", "[1, 2]",
                                 json.dumps({"hook_event_name": "SessionStart", "session_id": "../x"}),
                                 json.dumps({"hook_event_name": "SessionStart", "session_id": r"..\..\aaaaaaaa"})])
def test_garbage_input_is_silent(tmp_path, hook_env, make_snap, raw):
    write_cache(tmp_path, make_snap, 95)
    r, _ = run_hook(hook_env, raw)
    assert (r.returncode, r.stdout) == (0, b"")
    assert not (tmp_path / "x.json").exists()


class _Slow(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(10)

    def log_message(self, *a):
        pass


def test_hung_endpoint_returns_fast(tmp_path, hook_env):           # Review Focus 3
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Slow)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        hook_env["CUG_USAGE_URL"] = f"http://127.0.0.1:{srv.server_port}/"
        r, secs = run_hook(hook_env, payload("hook_user_prompt.json"))
    finally:
        srv.shutdown()
    assert (r.returncode, r.stdout) == (0, b"")
    assert secs < 4


def test_fast_with_fresh_cache(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    times = [run_hook(hook_env, payload("hook_user_prompt.json"))[1] for _ in range(5)]
    assert statistics.median(times) < 1.0


def test_desktop_hook_command_with_spaces_and_accents(cug):   # Review Focus 1
    cmd = cug.hook_command([r"C:\Users\José\Meus Apps\claude_usage_guard.exe"], windows=True, sub="desktop-hook")
    assert cmd == '"C:/Users/José/Meus Apps/claude_usage_guard.exe" desktop-hook'
    assert cug.hook_command(["g.exe"], windows=True) == "g.exe hook"


def test_state_path_validation(cug, state_dir):
    assert cug.desktop_state_path(SID).parent == state_dir / "desktop"
    for bad in ("../x", "abc", "a" * 81, "aaaaaaaa/../b"):
        with pytest.raises(cug.GuardError):
            cug.desktop_state_path(bad)
