"""Token do CLI vencido: o Desktop não renova o ~/.claude/.credentials.json,
então o guard pede ao `claude` oficial uma chamada mínima que o renova."""
import argparse
import json
import time

import pytest


@pytest.fixture
def expired_creds(tmp_path, monkeypatch, state_dir):
    d = tmp_path / "claude"
    d.mkdir()
    (d / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "velho", "expiresAt": int((time.time() - 3600) * 1000)}}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    return d


def test_hook_spawns_refresh_when_token_expired(cug, expired_creds, monkeypatch):
    spawned = []
    monkeypatch.setattr(cug, "spawn_auth_refresh", lambda cfg: spawned.append(1) or True)
    cfg, _ = cug.load_config(None)
    assert cug.load_snapshot_for_hook(cfg) is None
    assert spawned == [1]


def test_hook_does_not_spawn_when_disabled(cug, expired_creds, monkeypatch):
    spawned = []
    monkeypatch.setattr(cug, "spawn_auth_refresh", lambda cfg: spawned.append(1) or True)
    cfg, _ = cug.load_config(None)
    cfg["desktop"]["refresh_auth_with_cli"] = False
    cug.load_snapshot_for_hook(cfg)
    assert spawned == []


def test_refresh_auth_runs_minimal_cli_call(cug, expired_creds, monkeypatch, state_dir):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return argparse.Namespace(returncode=0, stdout='{"result": "ok"}', stderr="")

    monkeypatch.setattr(cug.subprocess, "run", fake_run)
    monkeypatch.setattr(cug, "resolve_claude_binary", lambda cfg: r"C:\bin\claude.exe")
    warmed = []
    monkeypatch.setattr(cug.UsageClient, "get", lambda self, max_age, lock_timeout=120.0: warmed.append(max_age))
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "claude-desktop")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    cfg, _ = cug.load_config(None)
    assert cug.cmd_refresh_auth(cfg, argparse.Namespace()) == 0
    cmd, kw = calls[0]
    assert cmd[0] == r"C:\bin\claude.exe" and "-p" in cmd
    assert cmd[cmd.index("--model") + 1] == "haiku" and cmd[cmd.index("--tools") + 1] == ""
    assert "--no-session-persistence" in cmd and "--setting-sources" in cmd
    assert "CLAUDE_CODE_ENTRYPOINT" not in kw["env"] and "ANTHROPIC_BASE_URL" not in kw["env"]
    assert "CLAUDE_CODE_SIMPLE" not in kw["env"]           # desligaria o login OAuth
    assert kw["env"]["CLAUDE_CONFIG_DIR"] == str(expired_creds)
    assert warmed == [0]                                      # já deixa o cache de uso pronto
    # segunda chamada logo depois: não gasta cota de novo
    assert cug.cmd_refresh_auth(cfg, argparse.Namespace()) == 0
    assert len(calls) == 1


def test_refresh_auth_skips_when_token_valid(cug, expired_creds, monkeypatch):
    (expired_creds / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "novo", "expiresAt": int((time.time() + 3600) * 1000)}}), encoding="utf-8")
    monkeypatch.setattr(cug.subprocess, "run", lambda *a, **k: pytest.fail("não devia chamar o claude"))
    monkeypatch.setattr(cug.UsageClient, "get", lambda self, max_age, lock_timeout=120.0: None)
    cfg, _ = cug.load_config(None)
    assert cug.cmd_refresh_auth(cfg, argparse.Namespace()) == 0


def test_spawn_auth_refresh_flags(cug, state_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(cug, "IS_WINDOWS", True)
    monkeypatch.setattr(cug.subprocess, "Popen", lambda *a, **k: calls.append((a, k)) or object())
    cfg, _ = cug.load_config(None)
    assert cug.spawn_auth_refresh(cfg) is True
    (args,), kw = calls[0]
    assert args[-1] == "refresh-auth"
    assert not kw["creationflags"] & 0x00000008 and kw["creationflags"] & 0x08000000
    assert cug.spawn_auth_refresh(cfg) is False             # já pedido há pouco
    assert len(calls) == 1
