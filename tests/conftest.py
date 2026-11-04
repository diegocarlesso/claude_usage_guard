"""Fixtures dos testes do Claude Usage Guard (só pytest; o produto não depende disto)."""
import datetime as dt
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD_PY = ROOT / "ClaudeCodeSessionLimits" / "claude_usage_guard.py"

# O módulo calcula STATE_DIR na importação: nunca deixe os testes tocarem o
# ~/.claude-usage-guard real.
os.environ["CUG_STATE_DIR"] = tempfile.mkdtemp(prefix="cug-tests-")
for _k in [k for k in os.environ if k.startswith("CUG_") and k != "CUG_STATE_DIR"]:
    del os.environ[_k]


@pytest.fixture(scope="session")
def cug():
    if "cug" in sys.modules:
        return sys.modules["cug"]
    spec = importlib.util.spec_from_file_location("cug", GUARD_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cug"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _defaults_only(cug, monkeypatch):
    """load_config(None) usa só os padrões (ignora config.yaml da pasta e do estado)."""
    real = cug.find_config_path
    monkeypatch.setattr(cug, "find_config_path", lambda explicit: real(explicit) if explicit else None)


@pytest.fixture
def state_dir(tmp_path, monkeypatch, cug):
    monkeypatch.setattr(cug, "STATE_DIR", tmp_path)
    monkeypatch.setattr(cug, "INSTANCES_DIR", tmp_path / "instances")
    monkeypatch.setattr(cug, "ACTIONS_LOG", tmp_path / "actions.jsonl")
    monkeypatch.setattr(cug, "GUI_PID_FILE", tmp_path / "gui.pid")
    return tmp_path


@pytest.fixture
def make_snap(cug):
    def make(s5=None, s7=None, resets_in=3600, fetched_at=None):
        now = time.time()
        r = dt.datetime.fromtimestamp(now + resets_in, dt.timezone.utc).isoformat()
        data = {}
        if s5 is not None:
            data["five_hour"] = {"utilization": s5, "resets_at": r}
        if s7 is not None:
            data["seven_day"] = {"utilization": s7, "resets_at": r}
        return cug.UsageSnapshot.from_api(data, now if fetched_at is None else fetched_at)
    return make
