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


# ---- botões que mandam pedidos às sessões (1.4.0) ----------------------------

SID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"


def _buttons(widget):
    out = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            out.append(child)
        out.extend(_buttons(child))
    return out


def test_status_line_texts(cug):
    st = cug.DesktopSessionState(SID, last_event="UserPromptSubmit")
    assert cug.desktop_status_line(["compact", "research"], st, 100.0, False) == \
        "pendente: Compactar, Pesquisar · vai no fim do turno atual (ou com a sua próxima mensagem)"
    st.last_event = "Stop"
    assert cug.desktop_status_line(["tools"], st, 100.0, False) == \
        "pendente: Skills/MCPs · vai junto com a sua próxima mensagem (até um 'ok' serve)"
    st2 = cug.DesktopSessionState(SID, delivered_actions=["compact"], delivered_at=1000.0, delivered_via="Stop")
    assert cug.desktop_status_line([], st2, 1120.0, False) == "entregue há 2m: Compactar (fim do turno)"
    assert cug.desktop_status_line([], st2, 1700.0, False) is None
    assert cug.desktop_status_line([], st2, 1700.0, True) == "pesquisa e skills pausadas: cota crítica"
    assert cug.desktop_status_line([], cug.DesktopSessionState(SID), 1120.0, False) is None


@pytest.mark.parametrize("pending,mode,expected", [
    (["economy_on"], False, ("✓ Economizar", "economy_on")),
    (["economy_off"], True, ("✓ Desligar economia", "economy_off")),
    ([], True, ("Economizar: ligado", "economy_off")),
    ([], False, ("Economizar", "economy_on"))])
def test_economy_button(cug, pending, mode, expected):
    assert cug.economy_button(pending, mode) == expected


def test_buttons_toggle_request(cug, state_dir, window, monkeypatch):
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    # Como no uso real: o redesenho depois do clique lê as sessões do disco.
    monkeypatch.setattr(window, "data", lambda: (None, None, [], [], cug.list_desktop_sessions(2)))
    window.draw(*window.data())
    btn = {b.cget("text"): b for b in _buttons(window.body)}
    assert {"Compactar", "Economizar", "Skills/MCPs", "Pesquisar"} <= set(btn)
    btn["Compactar"].invoke()
    assert cug.read_pending(SID) == ["compact"]
    btn = {b.cget("text"): b for b in _buttons(window.body)}
    assert "✓ Compactar" in btn and any(t.startswith("pendente: Compactar") for t in _texts(window.body))
    btn["✓ Compactar"].invoke()
    assert cug.read_pending(SID) == []


def test_critical_disables_research_and_tools(cug, state_dir, make_snap, window):
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    window.draw(make_snap(96, 10), None, [], [], cug.list_desktop_sessions(2))
    state = {b.cget("text"): str(b.cget("state")) for b in _buttons(window.body)}
    assert state["Pesquisar"] == state["Skills/MCPs"] == "disabled"
    assert state["Compactar"] == state["Economizar"] == "normal"


def test_desktop_disabled_turns_buttons_off(cug, state_dir, window):
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    window.cfg["desktop"]["enabled"] = False
    try:
        window.draw(None, None, [], [], cug.list_desktop_sessions(2))
    finally:
        window.cfg["desktop"]["enabled"] = True
    assert all(str(b.cget("state")) == "disabled" for b in _buttons(window.body) if b.cget("text") != "Abrir log")
    assert any("modo Desktop desligado no config" in t for t in _texts(window.body))


def test_old_pending_files_deleted(cug, state_dir):
    cug.toggle_request(SID, "compact", 1.0)
    p = cug.desktop_pending_path(SID)
    t = time.time() - 8 * 86400
    os.utime(p, (t, t))
    cug.list_desktop_sessions(2)
    assert not p.exists()


def test_at_most_four_cards(cug, state_dir, window):
    for i in range(6):
        _write_state(cug, f"{i:08d}-aaaa", 60 + i, cwd=f"F:/P/p{i}")
    window.draw(None, None, [], [], cug.list_desktop_sessions(2))
    assert "+ 2 outras" in _texts(window.body)
    assert sum(1 for b in _buttons(window.body) if b.cget("text") == "Compactar") == 4


def test_cancel_after_delivery_says_delivered(cug, state_dir, window, monkeypatch):   # revisão I1
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    monkeypatch.setattr(window, "data", lambda: (None, None, [], [], cug.list_desktop_sessions(2)))
    cug.toggle_request(SID, "research", time.time())
    window.draw(*window.data())
    btn = {b.cget("text"): b for b in _buttons(window.body)}["✓ Pesquisar"]
    cug.take_requests(SID)                       # o hook entregou antes do clique
    btn.invoke()
    assert "já tinha sido entregue" in window.footer_note.cget("text")
    assert cug.read_pending(SID) == []


def test_session_with_pending_stays_listed(cug, state_dir):              # revisão I2
    _write_state(cug, SID, 3 * 3600, cwd="F:/Projetos/App")
    assert cug.list_desktop_sessions(2) == []
    cug.toggle_request(SID, "compact", time.time())
    assert [s.session_id for s in cug.list_desktop_sessions(2)] == [SID]


def test_body_scrolls_when_content_is_tall(cug, state_dir, window):
    for i in range(4):
        _write_state(cug, f"{i:08d}-bbbb", 60 + i, cwd=f"F:/P/p{i}", last_note="nota " * 40)
    acts = [{"ts": time.time(), "instance": "abcdef123456", "action": "compact", "reason": "teste"}] * 15
    window.draw(None, None, [], acts, cug.list_desktop_sessions(2))
    window.root.update()
    window.canvas.yview_moveto(0)
    window.root.update()
    window.canvas.yview_scroll(10, "units")
    window.root.update()
    assert window.canvas.yview()[0] > 0          # desceu: há conteúdo além da janela
    assert window.scrollbar.winfo_ismapped()


def test_refresh_keeps_scroll_position(cug, state_dir, window):
    for i in range(4):
        _write_state(cug, f"{i:08d}-dddd", 60 + i, cwd=f"F:/P/p{i}", last_note="nota " * 40)
    acts = [{"ts": time.time(), "instance": "abcdef123456", "action": "compact", "reason": "teste"}] * 15
    data = (None, None, [], acts, cug.list_desktop_sessions(2))
    window.draw(*data)
    window.root.update()
    window.canvas.yview_scroll(3, "units")
    window.root.update()
    before = window.canvas.yview()[0]
    assert before > 0
    window.draw(*data)                       # a atualização periódica redesenha tudo
    window.root.update()
    assert abs(window.canvas.yview()[0] - before) < 0.01
