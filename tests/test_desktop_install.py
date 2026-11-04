import argparse
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
EVENTS = ("SessionStart", "UserPromptSubmit", "Stop")


@pytest.fixture
def fixture_settings():
    return json.loads((FIX / "settings_real_like.json").read_text(encoding="utf-8"))


@pytest.fixture
def claude_dir(tmp_path, monkeypatch, cug, state_dir):
    d = tmp_path / "claude"
    d.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    monkeypatch.setattr(cug, "start_menu_shortcut_path", lambda: tmp_path / "Claude Usage Guard.lnk")
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        if "CUG_LNK" in (kw.get("env") or {}):
            Path(kw["env"]["CUG_LNK"]).write_text("lnk", encoding="utf-8")
        return argparse.Namespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cug.subprocess, "run", fake_run)
    return d


def ns(**kw):
    return argparse.Namespace(**{"force": False, **kw})


def guard_cmds(cug, settings, event):
    return [h["command"] for g in settings.get("hooks", {}).get(event, []) for h in g.get("hooks", [])
            if cug.is_guard_desktop_hook(h)]


def test_is_guard_desktop_hook(cug):
    assert cug.is_guard_desktop_hook({"type": "command", "command": '"C:/x y/claude_usage_guard.exe" desktop-hook'})
    assert not cug.is_guard_desktop_hook({"type": "command", "command": "claude_usage_guard.exe hook"})
    assert not cug.is_guard_desktop_hook({"type": "command", "command": "outro.exe desktop-hook"})
    assert not cug.is_guard_desktop_hook("texto")


def test_merge_is_idempotent_and_keeps_user_hooks(cug, fixture_settings):
    before = json.loads(json.dumps(fixture_settings))
    once = cug.merge_desktop_hooks(fixture_settings, "G/claude_usage_guard.exe desktop-hook")
    twice = cug.merge_desktop_hooks(once, "G/claude_usage_guard.exe desktop-hook")
    assert once == twice and fixture_settings == before
    for ev in EVENTS:
        assert guard_cmds(cug, once, ev) == ["G/claude_usage_guard.exe desktop-hook"]
        assert once["hooks"][ev][-1] == {"hooks": [{"type": "command", "command": "G/claude_usage_guard.exe desktop-hook",
                                                    "timeout": 5}]}
    assert [g for g in once["hooks"]["SessionStart"] if not any(cug.is_guard_desktop_hook(x) for x in g["hooks"])] \
        == fixture_settings["hooks"]["SessionStart"]
    assert once["hooks"]["PreToolUse"] == fixture_settings["hooks"]["PreToolUse"]
    moved = cug.merge_desktop_hooks(once, '"D:/novo lugar/claude_usage_guard.exe" desktop-hook')
    assert guard_cmds(cug, moved, "Stop") == ['"D:/novo lugar/claude_usage_guard.exe" desktop-hook']


def test_strip_restores_original(cug, fixture_settings):
    merged = cug.merge_desktop_hooks(fixture_settings, "G/claude_usage_guard.exe desktop-hook")
    assert cug.strip_desktop_hooks(merged) == fixture_settings
    assert cug.strip_desktop_hooks(cug.merge_desktop_hooks({}, "G/claude_usage_guard.exe desktop-hook")) == {}


def test_install_uninstall_roundtrip(cug, claude_dir, fixture_settings, capsys):
    cfg, _ = cug.load_config(None)
    path = claude_dir / "settings.json"
    path.write_text(json.dumps(fixture_settings, indent=2) + "\n", encoding="utf-8")
    assert cug.cmd_install_desktop(cfg, ns()) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    for ev in EVENTS:
        assert len(guard_cmds(cug, data, ev)) == 1
    assert data["model"] == "sonnet"
    assert list(claude_dir.glob("settings.json.bak-*"))
    skill = claude_dir / "skills" / "economia-de-cota" / "SKILL.md"
    assert skill.read_bytes() == cug.asset_path("skills/economia-de-cota/SKILL.md").read_bytes()
    out = capsys.readouterr().out
    assert str(path) in out and "sessão nova" in out
    assert cug.desktop_hooks_status() == (True, True) or not cug.IS_WINDOWS
    assert cug.cmd_install_desktop(cfg, ns()) == 0          # reinstalar não duplica
    assert len(guard_cmds(cug, json.loads(path.read_text(encoding="utf-8")), "Stop")) == 1
    assert cug.cmd_uninstall_desktop(cfg, ns()) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == fixture_settings
    assert not skill.exists()
    assert cug.desktop_hooks_status()[0] is False


def test_install_creates_settings_when_missing(cug, claude_dir):
    cfg, _ = cug.load_config(None)
    assert cug.cmd_install_desktop(cfg, ns()) == 0
    data = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert set(data["hooks"]) == set(EVENTS)
    assert not list(claude_dir.glob("settings.json.bak-*"))


def test_install_aborts_on_invalid_json(cug, claude_dir, capsys):
    cfg, _ = cug.load_config(None)
    path = claude_dir / "settings.json"
    path.write_bytes(b"{ inv\xc3\xa1lido")
    assert cug.cmd_install_desktop(cfg, ns()) == 1
    assert path.read_bytes() == b"{ inv\xc3\xa1lido"
    assert not list(claude_dir.glob("settings.json.bak-*"))
    assert not (claude_dir / "skills").exists()
    assert "settings.json" in capsys.readouterr().err


def test_install_handles_bom_and_crlf(cug, claude_dir, fixture_settings):     # Review Focus 2
    cfg, _ = cug.load_config(None)
    path = claude_dir / "settings.json"
    text = json.dumps(fixture_settings, indent=2, ensure_ascii=False).replace("\n", "\r\n") + "\r\n"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert cug.cmd_install_desktop(cfg, ns()) == 0
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"}\r\n")
    assert b"\n" not in raw.replace(b"\r\n", b"")
    data = json.loads(raw.decode("utf-8-sig"))
    assert data["hooks"]["PreToolUse"] == fixture_settings["hooks"]["PreToolUse"]
    assert cug.cmd_uninstall_desktop(cfg, ns()) == 0
    assert path.read_bytes() == b"\xef\xbb\xbf" + text.encode("utf-8")


def test_user_modified_skill_kept_without_force(cug, claude_dir, capsys):
    cfg, _ = cug.load_config(None)
    skill = claude_dir / "skills" / "economia-de-cota" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("minha versão", encoding="utf-8")
    assert cug.cmd_install_desktop(cfg, ns()) == 0
    assert skill.read_text(encoding="utf-8") == "minha versão"
    assert "--force" in capsys.readouterr().out
    assert cug.cmd_install_desktop(cfg, ns(force=True)) == 0
    assert skill.read_bytes() == cug.asset_path("skills/economia-de-cota/SKILL.md").read_bytes()
    baks = list(skill.parent.glob("SKILL.md.bak-*"))
    assert len(baks) == 1 and baks[0].read_text(encoding="utf-8") == "minha versão"
    assert cug.cmd_uninstall_desktop(cfg, ns()) == 0
    assert not skill.exists() and baks[0].exists()          # backups ficam


def test_uninstall_keeps_modified_skill(cug, claude_dir):
    cfg, _ = cug.load_config(None)
    assert cug.cmd_install_desktop(cfg, ns()) == 0
    skill = claude_dir / "skills" / "economia-de-cota" / "SKILL.md"
    skill.write_text("editada", encoding="utf-8")
    assert cug.cmd_uninstall_desktop(cfg, ns()) == 0
    assert skill.read_text(encoding="utf-8") == "editada"


def test_check_config_reports_moved_exe(cug, claude_dir):
    settings = cug.merge_desktop_hooks({}, '"C:/não existe/claude_usage_guard.exe" desktop-hook')
    (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    assert cug.desktop_hooks_status() == (True, False)
    (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
    assert cug.desktop_hooks_status() == (False, False)


def test_restore_default_model_keeps_bom_and_crlf(cug, claude_dir):
    path = claude_dir / "settings.json"
    path.write_bytes(b'\xef\xbb\xbf{\r\n  "model": "haiku"\r\n}\r\n')
    assert cug.restore_default_model("sonnet") is True
    assert path.read_bytes() == b'\xef\xbb\xbf{\r\n  "model": "sonnet"\r\n}\r\n'
    assert cug.read_default_model() == "sonnet"
