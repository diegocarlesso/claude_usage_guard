def test_desktop_defaults(cug):
    cfg, _ = cug.load_config(None)
    d = cfg["desktop"]
    assert d["enabled"] is True
    assert (d["attention_session"], d["attention_weekly"]) == (60, 70)
    assert (d["high_session"], d["high_weekly"]) == (80, 85)
    assert (d["critical_session"], d["critical_weekly"]) == (92, 95)
    assert d["context_tokens_threshold"] == 120000 and d["context_repeat_tokens"] == 30000
    assert d["session_list_hours"] == 2 and d["usage_fetch_timeout_seconds"] == 2 and d["toast"] is True


def test_desktop_env_override(cug, monkeypatch):
    monkeypatch.setenv("CUG_DESKTOP_HIGH_SESSION", "75")
    cfg, _ = cug.load_config(None)
    assert cfg["desktop"]["high_session"] == 75


def test_desktop_thresholds_out_of_order_rejected(cug):
    cfg, _ = cug.load_config(None)
    cfg["desktop"]["high_session"] = 50   # < attention 60
    try:
        errs = cug.validate_config(cfg)
    except cug.ConfigError as exc:
        errs = [str(exc)]
    assert any("desktop" in e for e in errs)


def test_desktop_threshold_out_of_range_rejected(cug):
    cfg, _ = cug.load_config(None)
    cfg["desktop"]["critical_weekly"] = 120
    try:
        errs = cug.validate_config(cfg)
    except cug.ConfigError as exc:
        errs = [str(exc)]
    assert any("desktop" in e for e in errs)


def test_config_yaml_matches_defaults(cug):
    cfg, _ = cug.load_config(str(cug.app_dir() / "config.yaml"))
    assert cfg["desktop"] == cug.DEFAULT_CONFIG["desktop"]
