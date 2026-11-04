DESCRIPTION = ('Use ao ver uma nota "[usage-guard]" no contexto, quando a cota de uso (5h/semanal) estiver alta '
               'ou o contexto da sessão estiver grande, ou quando o usuário pedir para economizar tokens. Diz como '
               'reduzir consumo, que modelo usar em subagentes e quando sugerir /compact ou /clear com resumo de '
               'passagem.')
SECTIONS = ["## O que gasta cota", "## O que fazer em cada nível", "## Modelo dos subagentes",
            "## /compact ou /clear", "## Como sugerir ao usuário", "## Limites"]


def _skill(cug):
    path = cug.asset_path("skills/economia-de-cota/SKILL.md")
    assert path is not None
    return path.read_text(encoding="utf-8")


def test_frontmatter(cug):
    text = _skill(cug)
    assert text.startswith("---\n")
    head = text.split("---\n")[1]
    assert "name: economia-de-cota\n" in head
    assert f"description: {DESCRIPTION}\n" in head


def test_sections_in_order(cug):
    text = _skill(cug)
    positions = [text.find(s) for s in SECTIONS]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)


def test_handoff_template_and_size(cug):
    text = _skill(cug)
    assert "HANDOFF.md" in text and "[usage-guard]" in text
    for item in ("Objetivo", "Feito", "Falta", "Arquivos", "Decisões", "Próximos passos"):
        assert f"## {item}" in text, item
    assert len(text.splitlines()) <= 160
