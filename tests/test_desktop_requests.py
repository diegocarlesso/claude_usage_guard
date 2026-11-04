"""Fila de pedidos dos botões da janela para as sessões do Desktop (1.4.0)."""
import json

import pytest

SID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"


def test_toggle_adds_then_cancels(cug, state_dir):
    assert cug.toggle_request(SID, "compact", 1.0) is True
    assert cug.read_pending(SID) == ["compact"]
    assert cug.toggle_request(SID, "compact", 2.0) is False
    assert cug.read_pending(SID) == [] and not cug.desktop_pending_path(SID).exists()


def test_first_click_creates_dirs(cug, state_dir):            # Review Focus 2
    assert not (state_dir / "desktop").exists()
    assert cug.toggle_request(SID, "research", 1.0) is True
    data = json.loads(cug.desktop_pending_path(SID).read_text(encoding="utf-8"))
    assert data == {"session_id": SID, "requests": [{"action": "research", "at": 1.0}]}


def test_economy_pair_cancels_each_other(cug, state_dir):
    cug.toggle_request(SID, "economy_on", 1.0)
    cug.toggle_request(SID, "economy_off", 2.0)
    assert cug.read_pending(SID) == ["economy_off"]


def test_delivery_order_is_fixed(cug, state_dir):
    for a in ("research", "compact", "tools", "economy_on"):
        cug.toggle_request(SID, a, 1.0)
    assert cug.read_pending(SID) == ["economy_on", "compact", "tools", "research"]


def test_cancel_click_after_delivery_is_noop(cug, state_dir):   # Review Focus 1
    cug.toggle_request(SID, "compact", 1.0)
    assert cug.take_requests(SID) == ["compact"]
    assert cug.toggle_request(SID, "compact", 2.0, expect_pending=True) is None   # já entregue: nada muda
    assert cug.read_pending(SID) == []


def test_take_empties_and_restore_does_not_duplicate(cug, state_dir):
    cug.toggle_request(SID, "compact", 1.0)
    cug.toggle_request(SID, "tools", 1.0)
    got = cug.take_requests(SID)
    assert got == ["compact", "tools"] and not cug.desktop_pending_path(SID).exists()
    cug.toggle_request(SID, "tools", 2.0)          # clicado de novo no meio
    cug.restore_requests(SID, got, 3.0)
    assert cug.read_pending(SID) == ["compact", "tools"]


def test_corrupted_file_reads_empty_and_is_rewritten(cug, state_dir):
    p = cug.desktop_pending_path(SID)
    p.parent.mkdir(parents=True)
    p.write_text("{oops", encoding="utf-8")
    assert cug.read_pending(SID) == [] and cug.take_requests(SID) == []
    assert cug.toggle_request(SID, "compact", 1.0) is True and cug.read_pending(SID) == ["compact"]


@pytest.mark.parametrize("bad", ["../x", r"..\..\aaaaaaaa", "", "a" * 81])
def test_invalid_session_id_rejected(cug, state_dir, bad):
    with pytest.raises(cug.GuardError):
        cug.toggle_request(bad, "compact", 1.0)


def test_unknown_action_rejected(cug, state_dir):
    with pytest.raises(ValueError):
        cug.toggle_request(SID, "rm -rf", 1.0)


def test_request_notes_by_channel(cug):
    stop = cug.request_notes(["compact", "research"], "Stop").split("\n")
    assert len(stop) == 2
    assert stop[0].startswith('[usage-guard] Pedido do usuário pelo botão "Compactar" do Claude Usage Guard '
                              '(não é erro; faça agora): grave HANDOFF.md')
    assert stop[1].startswith('[usage-guard] Pedido do usuário pelo botão "Pesquisar"')
    ups = cug.request_notes(["tools"], "UserPromptSubmit")
    assert "(faça antes do resto da mensagem dele): use a skill ferramentas-do-projeto" in ups
    assert json.dumps({"x": ups}).isascii()


def test_apply_delivery(cug):
    st = cug.apply_delivery(cug.DesktopSessionState(SID), ["economy_on", "compact"], "Stop", 50.0)
    assert (st.economy_mode, st.delivered_actions, st.delivered_at, st.delivered_via) == \
           (True, ["economy_on", "compact"], 50.0, "Stop")
    assert st.last_note == "[usage-guard] entregues: Economizar, Compactar" and st.last_note_at == 50.0   # M3
    assert cug.apply_delivery(st, ["economy_off"], "UserPromptSubmit", 60.0).economy_mode is False


def test_merge_concurrent_delivery_keeps_newer_disk_fields(cug):          # M1
    mine = cug.DesktopSessionState(SID, delivered_at=10.0, economy_mode=False)
    disk = cug.DesktopSessionState(SID, delivered_at=20.0, economy_mode=True,
                                   delivered_actions=["economy_on"], delivered_via="Stop")
    out = cug.merge_concurrent_delivery(mine, disk)
    assert (out.economy_mode, out.delivered_actions, out.delivered_at, out.delivered_via) == \
           (True, ["economy_on"], 20.0, "Stop")


def test_merge_concurrent_delivery_ignores_older_or_missing_disk(cug):    # M1
    mine = cug.DesktopSessionState(SID, delivered_at=30.0, economy_mode=True)
    older = cug.DesktopSessionState(SID, delivered_at=20.0, economy_mode=False)
    assert cug.merge_concurrent_delivery(mine, older).economy_mode is True
    assert cug.merge_concurrent_delivery(mine, None) is mine


def test_corrupted_queue_warns_once(cug, state_dir, caplog):              # M4
    import logging
    p = cug.desktop_pending_path(SID)
    p.parent.mkdir(parents=True)
    p.write_text("{oops", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert cug.read_pending(SID) == []
    assert sum("ilegível" in r.getMessage() for r in caplog.records) == 1


def test_old_state_loads_with_defaults(cug):                    # Review Focus 3
    old = {"session_id": SID, "cwd": "F:/x", "updated_at": 1.0, "last_level": "high", "context_toast_done": True}
    st = cug.DesktopSessionState.from_json(old)
    assert (st.economy_mode, st.last_event, st.delivered_actions, st.delivered_via) == (False, None, [], None)


def test_stale_queue_expires(cug, state_dir):                    # revisão I2
    import os
    import time
    cug.toggle_request(SID, "compact", time.time())
    p = cug.desktop_pending_path(SID)
    old = time.time() - cug.PENDING_MAX_AGE_SECONDS - 60
    os.utime(p, (old, old))
    assert cug.read_pending(SID) == [] and cug.take_requests(SID) == []
