def _fake_popen(calls, fail_times=0):
    state = {"n": 0}

    def fake(*a, **k):
        calls.append((a, k))
        state["n"] += 1
        if state["n"] <= fail_times:
            raise OSError("negado")
        return object()
    return fake


def test_toast_command_and_env(cug, monkeypatch):
    calls = []
    monkeypatch.setattr(cug, "IS_WINDOWS", True)
    monkeypatch.setattr(cug.subprocess, "Popen", _fake_popen(calls))
    assert cug.notify_toast("Claude Usage Guard", 'Cota 5h em 83% "aspas" $x') is True
    (args,), kw = calls[0]
    assert args[0] == "powershell" and "-NoProfile" in args
    script = args[-1]
    assert "ToastNotificationManager" in script and "1AC14E77-02E7-4E5D-B744-2EB1AE5198B7" in script
    assert "CreateTextNode($env:CUG_NOTIFY_MSG)" in script and "NotifyIcon" in script
    assert "83%" not in script                     # texto só pela env
    assert kw["env"]["CUG_NOTIFY_MSG"] == 'Cota 5h em 83% "aspas" $x'
    assert kw["env"]["CUG_NOTIFY_TITLE"] == "Claude Usage Guard"
    assert kw["creationflags"] & 0x01000000        # CREATE_BREAKAWAY_FROM_JOB
    assert kw["creationflags"] & 0x08000000        # CREATE_NO_WINDOW
    # DETACHED_PROCESS: o PowerShell sem console é criado mas não mostra o toast
    # (medido no registro do Windows em 04/11)
    assert not kw["creationflags"] & 0x00000008


def test_toast_retries_without_breakaway(cug, monkeypatch):
    calls = []
    monkeypatch.setattr(cug, "IS_WINDOWS", True)
    monkeypatch.setattr(cug.subprocess, "Popen", _fake_popen(calls, fail_times=1))
    assert cug.notify_toast("t", "m") is True
    assert len(calls) == 2
    assert calls[0][1]["creationflags"] & 0x01000000
    assert not calls[1][1]["creationflags"] & 0x01000000
    assert not calls[1][1]["creationflags"] & 0x00000008


def test_toast_never_raises(cug, monkeypatch):
    calls = []
    monkeypatch.setattr(cug, "IS_WINDOWS", True)
    monkeypatch.setattr(cug.subprocess, "Popen", _fake_popen(calls, fail_times=99))
    assert cug.notify_toast("t", "m") is False


def test_desktop_notify_uses_toast(cug, monkeypatch):
    seen = []
    monkeypatch.setattr(cug, "notify_toast", lambda t, m: seen.append((t, m)) or True)
    cfg, _ = cug.load_config(None)
    cug.desktop_notify(cfg, "T", "M")
    cfg["notifications"]["desktop"] = False
    cug.desktop_notify(cfg, "T2", "M2")
    assert seen == [("T", "M")]
