# Economia de cota nas sessões da aba Code do Claude Desktop — design

Data: 03/11/2026 · Projeto: Claude Usage Guard (`ClaudeCodeSessionLimits\claude_usage_guard.py`, versão base 1.2.0)
Subprojeto **A** de três (B: configurador por projeto; C: pesquisa contínua de otimizações — fora deste documento).

## 1. Objetivo e contexto

O usuário trabalha só no **Claude Desktop, aba Code** (sessões do Claude Code dentro do app). Os problemas a
atacar são: bater o limite de 5h, bater o limite semanal e sessões com contexto grande e caro. O modo `run` do
guard (que digita `/compact` etc. num terminal) não serve para ele, porque o Desktop não roda num terminal.

**Resultado esperado:** o próprio Claude, dentro de cada sessão do Desktop, passa a economizar cota na hora certa
(respostas diretas, subagentes mais baratos, resumo de passagem + sugestão de `/clear`/`/compact`), e o usuário é
avisado por notificação do Windows e pela janela do guard quando a cota fica alta ou o contexto cresce.

### O que o spike de 03/11/2026 confirmou (sessão real do Desktop em `_e2e\proj`)

| Peça | Resultado |
|---|---|
| Hooks `SessionStart`, `UserPromptSubmit`, `Stop` do `settings.json` | disparam; `CLAUDE_CODE_ENTRYPOINT=claude-desktop`; JSON traz `session_id`, `transcript_path`, `cwd` (e `source` no SessionStart) |
| `hookSpecificOutput.additionalContext` | **chega ao contexto do Claude** (SessionStart e UserPromptSubmit) |
| `"model"` no `settings.json` | **ignorado**: o Desktop define o modelo da sessão |
| `systemMessage` | gravado no transcript (`hook_system_message`), mas **não aparece** para o usuário |
| Toast WinRT via `powershell.exe` 5.1 | **aparece** (e fica na central de notificações) |
| Balão `NotifyIcon` lançado sem esperar | não apareceu: o processo morre antes de o balão ser mostrado |

### Não-objetivos

- Aba de chat comum do Desktop (sem hooks; automatizar a interface com bot é frágil e esbarra nos termos de uso).
- Executar `/compact`, `/clear` ou trocar o modelo da sessão aberta (nenhum hook consegue). O guard **leva o
  Claude e o usuário a agir**.
- Alterar o `"model"` do `settings.json` (o Desktop ignora; e a decisão 18 do CONTEXTO.md promete não mexer nisso).
- Subprojetos B e C; identidade própria nas notificações (AppUserModelID registrado).

## 2. Arquitetura

```
Claude Desktop (aba Code) ── hooks do ~/.claude/settings.json ──► claude_usage_guard.exe desktop-hook
                                                                     │  lê JSON do stdin (evento, sessão, transcript)
                                                                     │  cota: usage_cache.json (rede só se velho, 2 s)
                                                                     │  contexto: read_context_tokens(transcript)
                                                                     ▼
                                                     advise(cfg, snap, estado, evento, agora)  ── função pura
                                                        │ nota (additionalContext) ─► stdout JSON ─► contexto do Claude
                                                        │ toast  ─────────────────► notify_toast() (processo à parte)
                                                        ▼
                                  .claude-usage-guard\desktop\<session_id>.json  ◄── janela do guard (seção nova)
                                  .claude-usage-guard\desktop\alerts.json (sob trava): toasts já mostrados
Skill ~/.claude/skills/economia-de-cota/SKILL.md ◄── o Claude carrega quando vê "[usage-guard]"
```

Componentes novos em `claude_usage_guard.py` (mesmo arquivo, mesma convenção do resto):

| Unidade | Papel | Depende de |
|---|---|---|
| `cmd_desktop_hook` | entrada do hook; nunca falha; sai em < 1 s | `advise`, leitores existentes |
| `advise()` | decide nota e toast a partir de cota, contexto e estado | nada (pura) |
| `DesktopSessionState` | estado por sessão (dataclass ↔ JSON) | — |
| `notify_toast()` | toast WinRT, com balão como reserva | PowerShell 5.1 |
| `cmd_install_desktop` / `cmd_uninstall_desktop` | instala/remove hooks, skill e atalho | `settings.json` do usuário |
| `GuardWindow._draw_desktop_sessions` + faixa de alerta | mostra as sessões do Desktop | `desktop\*.json` |

O modo `run` continua igual; só o `desktop_notify()` passa a usar `notify_toast()`.

## 3. Configuração (`config.yaml`, seção nova)

Chaves planas, para os overrides `CUG_DESKTOP_*` funcionarem sem mudança no carregador:

```yaml
desktop:
  enabled: true
  attention_session: 60      # % da janela de 5h
  attention_weekly: 70       # % da janela de 7d
  high_session: 80
  high_weekly: 85
  critical_session: 92
  critical_weekly: 95
  context_tokens_threshold: 120000
  context_repeat_tokens: 30000   # nova nota de contexto a cada +30k
  toast: true
  session_list_hours: 2      # janela do guard: some com sessões paradas há mais tempo
  usage_fetch_timeout_seconds: 2
```

Validação: cada limiar entre 0 e 100 e `attention ≤ high ≤ critical` por janela; caso contrário, erro de config.

## 4. Regras de decisão (`advise`)

**Nível de cota** = o pior entre a janela de 5h (limiares `*_session`) e a de 7d (`*_weekly`):
`normal` < `attention` < `high` < `critical`. A nota cita a janela que definiu o nível, com % e "reinicia em".
Sem dados (snapshot ausente ou mais velho que `max_stale_seconds`): nenhuma nota, nenhum toast, estado mantido.

| Evento | Regra |
|---|---|
| `SessionStart` (qualquer `source`) | se nível ≥ attention: nota do nível atual (contexto novo não tem a nota). Sempre grava `last_level` = nível atual (o primeiro prompt não repete a nota). `source` `clear`/`compact`: zera `context_tokens` e `context_noted_at`. |
| `UserPromptSubmit` | se o nível mudou desde `last_level`: nota do novo nível (`normal` → nota de normalização) e grava o novo `last_level`. Sessão sem estado (arquivo apagado ou SessionStart perdido por erro): trata como SessionStart. Se `context_tokens ≥ context_tokens_threshold` e (`context_noted_at` vazio ou `context_tokens ≥ context_noted_at + context_repeat_tokens`): nota de contexto. As duas podem sair juntas (uma linha cada). |
| `Stop` | mede o contexto pelo transcript e grava; **sem saída** (o Claude Code não aceita `additionalContext` no Stop). |

**Toasts:** ao entrar em `high` ou `critical`, uma vez por nível por janela (chave = janela de 5h ou de 7d +
`resets_at` arredondado, como `_window_key`), registrado em `alerts.json` sob trava. Contexto: um toast na
primeira nota de contexto de cada sessão.

**Textos** (uma linha, prefixo `[usage-guard]`, 40–60 tokens):

- attention: `[usage-guard] Cota 5h em 64% (reinicia em 2h10). Modo econômico: respostas diretas, delegue buscas e leituras longas a subagentes com model haiku, evite reler arquivos grandes. Detalhes: skill economia-de-cota.`
- high: `[usage-guard] Cota 5h em 83% (reinicia em 1h05). Economia forte: só o essencial; subagentes haiku/sonnet para o que não exige raciocínio difícil; antes de tarefas longas, confirme com o usuário e sugira /model sonnet para trabalho rotineiro.`
- critical: `[usage-guard] Cota 5h em 93% (reinicia em 25min). Conclua o passo atual, grave um resumo de passagem em HANDOFF.md e diga ao usuário quando a cota reinicia. Não comece tarefas novas.`
- contexto: `[usage-guard] Contexto com 132k tokens. Ao terminar a tarefa atual, sugira ao usuário /compact (mesmo assunto) ou /clear com resumo de passagem (assunto novo).`
- normalização: `[usage-guard] Cota normalizada (5h em 8%). Pode trabalhar normalmente.`

("Cota 5h" vira "Cota semanal" quando é a de 7d que define o nível.)

## 5. O hook (`claude_usage_guard.exe desktop-hook`)

- Registrado para `SessionStart`, `UserPromptSubmit` e `Stop`, `timeout: 5`, comando no formato de
  `hook_command()` (barras normais; aspas só com espaço) com `desktop-hook` no lugar de `hook`.
- Caminho rápido como o `hook` atual: sem logging para stderr; nada no stdout além do JSON da nota.
- Saída quando há nota: `{"hookSpecificOutput": {"hookEventName": "<evento>", "additionalContext": "<linhas>"}}`.
  Sem nota: saída vazia. Código de saída **sempre 0**.
- `session_id` validado (`[0-9A-Za-z-]{8,80}`) antes de virar nome de arquivo.
- Cota: lê `usage_cache.json`; se mais velho que `poll_interval_seconds`, tenta `UsageClient.get` com
  `usage_fetch_timeout_seconds` (respeitando a trava e o cooldown de 429 existentes); se falhar, usa o cache velho
  dentro do limite de `max_stale_seconds`, senão segue sem dados.
- Qualquer exceção: registra no `guard.log` e sai com 0 sem saída. Orçamento: < 1 s no caso comum (cache fresco).
- Estado gravado com `atomic_write_json` em `desktop\<session_id>.json`:
  `{session_id, cwd, transcript_path, updated_at, context_tokens, context_measured_at, context_noted_at, last_level, last_note, last_note_at, context_toast_done}`.

## 6. Notificações (`notify_toast`)

- PowerShell 5.1 (`powershell.exe`; o `pwsh` 7 não carrega WinRT), script fixo, título e texto por variável de
  ambiente (nada interpolado no script, como hoje).
- `ToastNotificationManager.CreateToastNotifier("{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe")`
  com `ToastGeneric` (título "Claude Usage Guard" + texto). Em erro, o mesmo script cai para o balão `NotifyIcon`
  e espera 7 s.
- Lançado com `DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB`; se o breakaway for negado,
  tenta sem ele. O hook não espera o PowerShell.
- `desktop_notify()` (modo `run`) passa a chamar `notify_toast()`. Respeita `notifications.desktop` e
  `desktop.toast`.

## 7. Skill `economia-de-cota`

Arquivo empacotado em `assets\skills\economia-de-cota\SKILL.md` (entra no `.exe` com `--add-data`) e copiado
pelo `install-desktop`. Frontmatter:

```yaml
name: economia-de-cota
description: Use ao ver uma nota "[usage-guard]" no contexto, quando a cota de uso (5h/semanal) estiver alta ou o contexto da sessão estiver grande, ou quando o usuário pedir para economizar tokens. Diz como reduzir consumo, que modelo usar em subagentes e quando sugerir /compact ou /clear com resumo de passagem.
```

Seções (≈120 linhas, português):
1. O que gasta cota no Claude Code (contexto reenviado a cada turno, saídas grandes, arquivos inteiros, raciocínio longo, retrabalho).
2. Comportamento por nível: attention / high / critical (como na seção 4, em forma de lista de ações).
3. Modelos em subagentes: `haiku` (buscar, ler, listar, resumir, tarefas mecânicas); `sonnet` (implementação rotineira, revisões simples); modelo atual (design, depuração difícil, arquitetura).
4. `/compact` × `/clear`: quando usar cada um; modelo do `HANDOFF.md` (objetivo, feito, falta, arquivos, decisões, próximos passos); depois do `/clear`, começar lendo o `HANDOFF.md`.
5. Como sugerir ao usuário: frases curtas e acionáveis; informar quando a cota reinicia.
6. Limites: não pular trabalho pedido sem avisar; qualidade antes de economia em decisões críticas; nunca editar `settings.json` para trocar modelo.

## 8. Instalação (`install-desktop` / `uninstall-desktop`)

`install-desktop`:
1. Lê `claude_config_dir()\settings.json`. JSON inválido → aborta sem mudar nada. Inexistente → cria `{}`.
2. Backup `settings.json.bak-AAAAMMDD-HHMMSS` ao lado.
3. Para cada evento, remove entradas anteriores do guard (comando contém `desktop-hook` e o nome
   `claude_usage_guard`) e acrescenta a atual. Os demais hooks do usuário ficam intactos e na mesma ordem.
4. Grava de forma atômica, preservando a indentação de 2 espaços e a quebra de linha final.
5. Copia a skill. Se já existir e for diferente da empacotada: mantém a do usuário e avisa (`--force` sobrescreve, com backup).
6. Cria `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Claude Usage Guard.lnk` → `<exe> gui` (via `WScript.Shell`).
7. Imprime o resumo e lembra que só **sessões novas** do Desktop pegam os hooks.

`uninstall-desktop`: remove só as entradas do guard (e listas de evento que ficarem vazias), remove a skill se
for idêntica à empacotada, remove o atalho. Backups ficam.

`check-config`: informa se os hooks do Desktop estão instalados e se o caminho do `.exe` registrado ainda existe
(se não, manda rodar `install-desktop` de novo).

## 9. Janela do guard

- Seção **"Sessões do Desktop"** abaixo de "Sessões protegidas": uma linha por `desktop\*.json` atualizado nas
  últimas `session_list_hours` horas — pasta (`cwd`), contexto em tokens, último nível/nota e "há X min". Sem botões.
  Arquivos com mais de 7 dias são apagados.
- **Faixa** no topo quando o nível da conta é `high` (amarelo) ou `critical` (vermelho), com a janela que definiu e o reinício.
- Aberta por atalho/duplo clique (`.exe` congelado e único processo no console, via `GetConsoleProcessList`):
  `FreeConsole()` fecha o console preto.

## 10. Erros e casos-limite

| Situação | Comportamento |
|---|---|
| Endpoint 401/429/fora do ar | sem dados → sem nota; o cache e o cooldown existentes evitam martelar o endpoint |
| Transcript ausente/ilegível | contexto desconhecido → só regras de cota |
| Duas sessões ao mesmo tempo | estado por sessão; `alerts.json` sob `file_lock` |
| `.exe` movido de pasta | hooks falham em silêncio (o Claude Code segue); `check-config` avisa |
| `settings.json` editado pelo usuário entre instalações | reinstalar só troca as entradas do guard |
| Claude ignora a nota | aceitável: o usuário ainda recebe o toast; a skill reforça quando carregada |
| Desktop muda o formato dos hooks | campos lidos com `.get`; ausência = sem nota |

## 11. Testes

1. **Unitários de `advise()`** (tabela): cada nível e virada; sem repetição; contexto a cada +30k; normalização;
   SessionStart com nível alto; `clear`/`compact` zerando contexto; sem dados → silêncio; janela semanal definindo o nível.
2. **Hook ponta a ponta:** `exe desktop-hook` com o JSON dos três eventos (formato capturado no spike), state dir
   temporário (`CUG_STATE_DIR`) e cache de uso falso; confere o JSON de saída, o estado gravado e o tempo (< 1 s, cache fresco).
3. **Instalação** com `CLAUDE_CONFIG_DIR` temporário contendo uma cópia do `settings.json` real (com os hooks
   `gsd-*` do usuário): instalar 2× não duplica; os outros hooks ficam idênticos; backup criado; desinstalar
   devolve o JSON equivalente ao original; JSON inválido aborta sem mudar o arquivo.
4. **Sessão real do Desktop** (como o spike): o `~/.claude` real não é tocado; o `.claude\settings.json` da pasta
   de teste `_e2e\proj` registra `<exe> --config <config de teste> desktop-hook` com limiares baixos (ex.:
   attention 1%); uma sessão nova do Desktop nessa pasta relata a nota recebida; o usuário confirma o toast; no fim
   o `settings.json` de teste é apagado.
5. **Janela:** captura com sessões do Desktop e faixa `high`/`critical` (dados falsos), como o `gui_snapshot.py`.
6. **Regressão:** `_e2e\driver.py` (17/17), `gui_checks.py` (8/8), pyflakes limpo, rebuild do `.exe`.

## 12. Critérios de aceite

- Numa sessão nova do Desktop com limiares de teste, o Claude recebe a nota `[usage-guard]` e age conforme ela
  (por exemplo, diz que vai economizar ou sugere `/compact`), e o toast aparece.
- Hook: p95 < 1 s com cache fresco; nunca sai com código ≠ 0; nunca imprime nada além do JSON da nota.
- `install-desktop` + `uninstall-desktop` deixam o `settings.json` equivalente ao original.
- Nenhuma regressão nos testes atuais.

## 13. Riscos e pontos em aberto

- **Custo das notas:** baixo (só nas viradas), mas a skill carregada custa ~1–2k tokens por sessão em que for usada.
- **Atribuição do toast** aparece como "Windows PowerShell"; trocar por identidade própria exige registrar um
  AppUserModelID (fora do escopo).
- **Sessões abertas antes da instalação** não recebem os hooks até serem reabertas.
- O Desktop pode mudar o comportamento de hooks em versões futuras; o teste 4 da seção 11 deve ser repetido após atualizações grandes.
