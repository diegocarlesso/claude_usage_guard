import time

import pytest

NOW = time.time()


def cfg_(cug):
    cfg, _ = cug.load_config(None)
    return cfg


def test_session_start_high_gives_note_and_sets_level(cug, make_snap):
    st = cug.DesktopSessionState("s1")
    notes, toasts, st2 = cug.advise(cfg_(cug), make_snap(83, 10), st, "SessionStart", "startup", NOW)
    assert len(notes) == 1 and notes[0].startswith("[usage-guard] Cota 5h em 83% (reinicia em ")
    assert st2.last_level == "high" and st.last_level is None
    assert [t.key.split(":")[-1] for t in toasts] == ["high"]
    assert toasts[0].key.startswith("five_hour:")
    assert toasts[0].title == "Claude Usage Guard" and toasts[0].message.startswith("Cota 5h alta: 83%")


def test_session_start_normal_records_level_silently(cug, make_snap):
    notes, toasts, st2 = cug.advise(cfg_(cug), make_snap(10, 10), cug.DesktopSessionState("s1"),
                                    "SessionStart", "startup", NOW)
    assert (notes, toasts, st2.last_level) == ([], [], "normal")


def test_same_level_no_repeat(cug, make_snap):
    st = cug.DesktopSessionState("s1", last_level="high")
    notes, toasts, _ = cug.advise(cfg_(cug), make_snap(85, 10), st, "UserPromptSubmit", None, NOW)
    assert notes == [] and toasts == []


def test_level_up_on_prompt(cug, make_snap):
    st = cug.DesktopSessionState("s1", last_level="attention")
    notes, toasts, st2 = cug.advise(cfg_(cug), make_snap(93, 10), st, "UserPromptSubmit", None, NOW)
    assert len(notes) == 1 and "Conclua o passo atual" in notes[0]
    assert [t.key.split(":")[-1] for t in toasts] == ["critical"] and st2.last_level == "critical"


def test_level_down_to_normal_gives_normalization(cug, make_snap):
    st = cug.DesktopSessionState("s1", last_level="high")
    notes, toasts, st2 = cug.advise(cfg_(cug), make_snap(8, 10), st, "UserPromptSubmit", None, NOW)
    assert notes == ["[usage-guard] Cota normalizada (5h em 8%). Pode trabalhar normalmente."]
    assert toasts == [] and st2.last_level == "normal"


def test_no_data_silence(cug, make_snap):
    cfg = cfg_(cug)
    st = cug.DesktopSessionState("s1", last_level="high")
    for snap in (None, make_snap(10, 10, fetched_at=NOW - cfg["max_stale_seconds"] - 1)):
        notes, toasts, st2 = cug.advise(cfg, snap, st, "UserPromptSubmit", None, NOW)
        assert (notes, toasts, st2.last_level) == ([], [], "high")


def test_context_threshold_and_repeat(cug, make_snap):
    cfg = cfg_(cug)
    st = cug.DesktopSessionState("s1", cwd="F:/Projetos/app", last_level="normal", context_tokens=125_000)
    notes, toasts, st = cug.advise(cfg, make_snap(10, 10), st, "UserPromptSubmit", None, NOW)
    assert notes == [cug.context_note(125_000)] and st.context_noted_at == 125_000
    assert [t.key for t in toasts] == ["context:s1"] and st.context_toast_done
    st = cug.dataclasses.replace(st, context_tokens=150_000)
    notes, toasts, st = cug.advise(cfg, make_snap(10, 10), st, "UserPromptSubmit", None, NOW)
    assert notes == [] and toasts == []
    st = cug.dataclasses.replace(st, context_tokens=155_000)
    notes, toasts, st = cug.advise(cfg, make_snap(10, 10), st, "UserPromptSubmit", None, NOW)
    assert notes == [cug.context_note(155_000)] and toasts == [] and st.context_noted_at == 155_000


def test_level_and_context_together(cug, make_snap):
    st = cug.DesktopSessionState("s1", last_level="normal", context_tokens=130_000)
    notes, _, _ = cug.advise(cfg_(cug), make_snap(64, 10), st, "UserPromptSubmit", None, NOW)
    assert len(notes) == 2
    assert notes[0].startswith("[usage-guard] Cota 5h em 64%") and notes[1] == cug.context_note(130_000)


def test_clear_resets_context(cug, make_snap):
    st = cug.DesktopSessionState("s1", last_level="normal", context_tokens=130_000, context_noted_at=130_000)
    for source in ("clear", "compact"):
        _, _, st2 = cug.advise(cfg_(cug), make_snap(10, 10), st, "SessionStart", source, NOW)
        assert st2.context_tokens is None and st2.context_noted_at is None
    _, _, st3 = cug.advise(cfg_(cug), make_snap(10, 10), st, "SessionStart", "resume", NOW)
    assert st3.context_tokens == 130_000


def test_missing_state_treated_as_session_start(cug, make_snap):
    notes, _, st2 = cug.advise(cfg_(cug), make_snap(64, 10), cug.DesktopSessionState("s1"),
                               "UserPromptSubmit", None, NOW)
    assert len(notes) == 1 and notes[0].startswith("[usage-guard] Cota 5h em 64%") and st2.last_level == "attention"


def test_weekly_drives_note(cug, make_snap):
    notes, toasts, _ = cug.advise(cfg_(cug), make_snap(10, 90), cug.DesktopSessionState("s1"),
                                  "SessionStart", "startup", NOW)
    assert notes[0].startswith("[usage-guard] Cota semanal em 90%")
    assert toasts[0].key.startswith("seven_day:")


def test_stop_is_silent(cug, make_snap):
    st = cug.DesktopSessionState("s1", last_level="normal", context_tokens=500_000)
    notes, toasts, st2 = cug.advise(cfg_(cug), make_snap(93, 10), st, "Stop", None, NOW)
    assert (notes, toasts, st2.last_level) == ([], [], "normal")


def test_state_roundtrip(cug):
    st = cug.DesktopSessionState("s1", cwd="F:/Projetos/Açúcar", context_tokens=5)
    assert cug.DesktopSessionState.from_json({**st.to_json(), "extra": 1}) == st


@pytest.mark.parametrize("source,economy,expected", [("compact", True, True), ("clear", True, True),
                                                     ("startup", True, False), ("resume", True, False),
                                                     ("compact", False, False)])
def test_economy_reminder_after_clear_or_compact(cug, make_snap, source, economy, expected):
    st = cug.DesktopSessionState("s1", economy_mode=economy)
    notes, _, _ = cug.advise(cfg_(cug), make_snap(10, 10), st, "SessionStart", source, NOW)
    assert (cug.ECONOMY_REMINDER in notes) is expected
