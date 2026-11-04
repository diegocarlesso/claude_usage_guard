import json
import os
import time

import pytest

tk = pytest.importorskip("tkinter")


def _write_state(cug, sid, age_s, **kw):
    st = cug.DesktopSessionState(sid, updated_at=time.time() - age_s, **kw)
    path = cug.desktop_state_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st.to_json(), ensure_ascii=False), encoding="utf-8")
    return path


def _texts(widget):
    out = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            out.append(child.cget("text"))
        out.extend(_texts(child))
    return out


@pytest.fixture(scope="module")
def window(cug):
    # Uma janela por módulo: criar vários Tk() no mesmo processo falha às vezes
    # no Windows ("invalid command name tcl_findLibrary").
    cfg = cug._deep_merge(cug.json.loads(cug.json.dumps(cug.DEFAULT_CONFIG)), {})
    try:
        win = cug.GuardWindow(cfg, lambda: (None, None, [], [], []))
    except tk.TclError as exc:
        pytest.skip(f"sem display: {exc}")
    yield win
    win.root.destroy()


def test_list_desktop_sessions(cug, state_dir):
    _write_state(cug, "aaaaaaaa-1111", 600, cwd="F:/Projetos/Açúcar")
    _write_state(cug, "bbbbbbbb-2222", 60, cwd="F:/Projetos/Outro")
    _write_state(cug, "cccccccc-3333", 3 * 3600, cwd="F:/Projetos/Velho")
    (cug.desktop_dir() / "alerts.json").write_text("{}", encoding="utf-8")
    got = cug.list_desktop_sessions(2)
    assert [s.session_id for s in got] == ["bbbbbbbb-2222", "aaaaaaaa-1111"]


def test_old_state_files_deleted(cug, state_dir):
    old = _write_state(cug, "dddddddd-4444", 8 * 86400)
    t = time.time() - 8 * 86400
    os.utime(old, (t, t))
    keep = _write_state(cug, "eeeeeeee-5555", 3 * 3600)
    assert cug.list_desktop_sessions(2) == []
    assert not old.exists() and keep.exists()


def test_desktop_section_lists_recent_sessions(cug, state_dir, window):   # Review Focus 5
    _write_state(cug, "aaaaaaaa-1111", 600, cwd="F:/Projetos/Açúcar", context_tokens=84_300,
                 last_level="attention")
    _write_state(cug, "cccccccc-3333", 3 * 3600, cwd="F:/Projetos/Velho")
    window.draw(None, None, [], [], cug.list_desktop_sessions(2))
    texts = _texts(window.body)
    assert "Sessões do Desktop" in texts and "Açúcar" in texts
    assert any("contexto 84k tokens" in t and "há 10m" in t for t in texts)
    assert not any("Velho" in t for t in texts)


def test_desktop_section_empty_hint(cug, state_dir, window):
    window.draw(None, None, [], [], [])
    assert any("install-desktop" in t for t in _texts(window.body))


def test_banner_only_when_high_or_critical(cug, make_snap, window):
    window.draw(make_snap(83, 10), None, [], [], [])
    assert any(t.startswith("Cota 5h alta: 83%") for t in _texts(window.body))
    window.draw(make_snap(10, 96), None, [], [], [])
    assert any(t.startswith("Cota semanal crítica: 96%") for t in _texts(window.body))
    window.draw(make_snap(64, 10), None, [], [], [])
    assert not any(t.startswith("Cota ") for t in _texts(window.body))


def test_old_four_item_data_still_draws(cug, window):
    window.draw(None, "erro", [], [])
    assert "Sessões do Desktop" in _texts(window.body)
