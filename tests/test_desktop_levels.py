def test_levels(cug, make_snap):
    cfg, _ = cug.load_config(None)
    assert cug.quota_level(cfg, make_snap(10, 10)) == ("normal", None)
    assert cug.quota_level(cfg, make_snap(60, 10)) == ("attention", "five_hour")
    assert cug.quota_level(cfg, make_snap(50, 86)) == ("high", "seven_day")
    assert cug.quota_level(cfg, make_snap(92, 96)) == ("critical", "five_hour")
    assert cug.quota_level(cfg, None) == ("normal", None)


def test_missing_window(cug, make_snap):                      # Review Focus 4
    cfg, _ = cug.load_config(None)
    assert cug.quota_level(cfg, make_snap(s7=90)) == ("high", "seven_day")
    assert cug.quota_level(cfg, make_snap(s5=93)) == ("critical", "five_hour")


def test_note_texts(cug):
    assert cug.level_note("attention", "five_hour", 64, 2 * 3600 + 600) == (
        "[usage-guard] Cota 5h em 64% (reinicia em 2h10m). Modo econômico: respostas diretas, delegue buscas "
        "e leituras longas a subagentes com model haiku, evite reler arquivos grandes. Detalhes: skill economia-de-cota.")
    assert cug.level_note("high", "five_hour", 83, 3900) == (
        "[usage-guard] Cota 5h em 83% (reinicia em 1h05m). Economia forte: só o essencial; subagentes haiku/sonnet "
        "para o que não exige raciocínio difícil; antes de tarefas longas, confirme com o usuário e sugira "
        "/model sonnet para trabalho rotineiro.")
    assert cug.level_note("critical", "seven_day", 93, 1500) == (
        "[usage-guard] Cota semanal em 93% (reinicia em 25m). Conclua o passo atual, grave um resumo de passagem "
        "em HANDOFF.md e diga ao usuário quando a cota reinicia. Não comece tarefas novas.")
    assert cug.level_note("normal", "five_hour", 8, 0) == "[usage-guard] Cota normalizada (5h em 8%). Pode trabalhar normalmente."
    assert cug.level_note("normal", "seven_day", 40, 0) == "[usage-guard] Cota normalizada (semanal em 40%). Pode trabalhar normalmente."
    assert cug.context_note(132_400) == ("[usage-guard] Contexto com 132k tokens. Ao terminar a tarefa atual, sugira ao "
                                         "usuário /compact (mesmo assunto) ou /clear com resumo de passagem (assunto novo).")
