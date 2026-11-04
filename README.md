# Claude Usage Guard

Guarda de consumo das cotas de 5 horas e semanal da assinatura Claude (Pro/Max) para o Claude Code no Windows.

- **Claude Desktop (aba Code):** `claude_usage_guard.exe install-desktop` registra hooks que mandam notas
  `[usage-guard]` ao Claude quando a cota sobe ou o contexto cresce (economizar, subagentes mais baratos,
  `/compact` ou `/clear` com resumo de passagem), mostram toasts do Windows e listam as sessões na janela do guard.
  Instala também a skill `economia-de-cota`. `uninstall-desktop` desfaz.
  Cada sessão ganha na janela do guard quatro botões: **Compactar** (resumo de passagem e linha `/compact`),
  **Economizar** (liga/desliga o modo econômico), **Skills/MCPs** (skill `ferramentas-do-projeto`) e **Pesquisar**
  (skill `pesquisar-otimizacoes`). O clique grava um pedido na fila da sessão e o hook o entrega ao Claude no fim
  do turno (`Stop`) ou junto da próxima mensagem (`UserPromptSubmit`).
- **Terminal:** `claude_usage_guard.exe run` abre o Claude Code num pseudo-terminal e aplica `/compact`, `/clear`,
  troca de modelo e failover opcional quando é seguro.

Download: veja os [Releases](https://github.com/diegocarlesso/claude_usage_guard/releases) (extraia a pasta inteira).
Passo a passo em [ClaudeCodeSessionLimits/LEIA-ME.txt](ClaudeCodeSessionLimits/LEIA-ME.txt); detalhes técnicos e
decisões em [CONTEXTO.md](CONTEXTO.md).

Desenvolvimento:

```bat
py -m pip install -r ClaudeCodeSessionLimits\requirements-windows.txt pytest
py -m pytest tests -q
ClaudeCodeSessionLimits\build_exe.bat
```

Não faz rodízio de contas nem contorna limites: só ajuda a gastar menos da cota que você já tem.
