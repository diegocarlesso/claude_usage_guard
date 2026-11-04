# Botões da janela que mandam pedidos às sessões do Desktop: design

Data: 04/11/2026. Projeto: Claude Usage Guard (`ClaudeCodeSessionLimits\claude_usage_guard.py`), versão base 1.3.0
e versão nova **1.4.0**. Continua o modo Desktop (spec `2026-11-03-desktop-economia-de-cota-design.md`, decisões 21
e 22 do `CONTEXTO.md`). Toca nos subprojetos B (configurador por projeto) e C (pesquisa contínua), mas não os
substitui: aqui tudo acontece sob demanda, por clique.

## 1. Objetivo

O usuário trabalha só na aba Code do Claude Desktop e quer um guard **proativo**. Na seção "Sessões do Desktop" da
janela do guard, cada sessão ganha quatro botões que mandam uma instrução ao Claude daquela sessão:

| Botão | O Claude faz |
|---|---|
| **Compactar** | grava `HANDOFF.md` e devolve uma linha pronta `/compact <o que manter>` para o usuário colar |
| **Economizar** (liga/desliga) | entra em modo econômico até o usuário desligar |
| **Skills/MCPs** | analisa o projeto, sugere skills, MCPs, plugins e hooks (incluindo o que tirar) e instala só o que o usuário aprovar |
| **Pesquisar** | pesquisa na web como usar o Claude Code neste projeto gastando menos e boas práticas do stack, grava `OTIMIZACOES.md` e aplica as mudanças que o usuário aprovar |

**Pronto quando:** os botões funcionam numa sessão real do Desktop, os testes passam e o `CONTEXTO.md` está atualizado.

### Limites (confirmados)

- Um programa externo só fala com a sessão por hooks. A instrução chega ao Claude pelo `additionalContext` do
  `UserPromptSubmit` (próxima mensagem do usuário) ou pelo `reason` de um `Stop` com `decision: "block"`
  (fim do turno atual).
- Nenhum hook roda `/compact` ou `/clear`, e automatizar a interface está fora por causa dos termos de uso. Quem
  digita `/compact` é o usuário.

### Spike de 04/11/2026 (sessão real do Desktop em `_e2e\proj`, `_e2e\stop_block_probe.py`)

| Peça | Resultado |
|---|---|
| `Stop` devolvendo `{"decision":"block","reason":"..."}` | **funciona**: o Claude seguiu trabalhando e fez o que o `reason` pedia, sem mensagem nova |
| Como o Claude vê o `reason` | `Stop hook blocking error from command: "...": <reason>` (o texto precisa dizer que não é erro) |
| Segundo `Stop` do mesmo turno | chega com `stop_hook_active: true` (proteção contra laço) |
| Campos do `UserPromptSubmit` no Desktop | `cwd, hook_event_name, permission_mode, prompt, prompt_id, session_id, session_title, transcript_path` |
| Campos do `Stop` no Desktop | `background_tasks, cwd, effort, hook_event_name, last_assistant_message, permission_mode, prompt_id, session_crons, session_id, stop_hook_active, transcript_path` |

### Não-objetivos

- Rodar `/compact`, `/clear` ou trocar o modelo; digitar na interface do Desktop.
- Entregar pedidos a sessões sem os hooks do guard (só aparecem na janela as que têm).
- Configurador por projeto completo (subprojeto B) e pesquisa periódica automática (subprojeto C).
- Linha de comando para enfileirar pedidos (o teste real grava a fila pela função Python).

## 2. Arquitetura e fluxo

```
Janela do guard ─ clique ─► desktop\pending\<sessão>.json        (sob a trava desktop\pending.lock)
                                  │  {"session_id": ..., "requests": [{"action": "compact", "at": 1730...}]}
                                  ▼
desktop-hook ─ Stop (stop_hook_active falso) ─► retira da fila ─► stdout {"decision":"block","reason": pedidos}
            └─ UserPromptSubmit ──────────────► retira da fila ─► stdout additionalContext (notas de cota + pedidos)
                                  │  se a escrita no stdout falhar: devolve os pedidos à fila
                                  ▼
            desktop\<sessão>.json: last_event, economy_mode, delivered_actions, delivered_at, delivered_via
```

- **Ações:** `compact`, `economy_on`, `economy_off`, `tools`, `research`. Ordem de entrega fixa
  (`economy_*`, `compact`, `tools`, `research`), não importa a ordem dos cliques.
- **Clique de novo cancela** um pedido pendente. `economy_on` e `economy_off` se anulam: pedir um tira o outro.
- **Quem entrega:** o primeiro hook que rodar depois do clique.
  - `Stop` com `stop_hook_active` falso e fila não vazia: bloqueia com os pedidos no `reason`.
  - `UserPromptSubmit`: pedidos no `additionalContext`, depois das notas de cota.
  - `SessionStart` **não** entrega pedidos (um `/clear` logo depois do clique não deve receber "compacte").
  - `Stop` com `stop_hook_active` verdadeiro: não bloqueia; o pedido vai na próxima mensagem.
- **Modo econômico fixo:** `economy_mode` (estado da sessão) vira verdadeiro ao entregar `economy_on` e falso ao
  entregar `economy_off`. Em `SessionStart` com `source` `clear` ou `compact` e `economy_mode` verdadeiro,
  `advise()` acrescenta a nota de lembrete (uma linha). Fora isso, não custa nada por mensagem.
- **Trava única** `desktop\pending.lock` (`file_lock`), usada pela janela e pelo hook.
- **Entrega sem perda nem duplicata:** o hook faz a parte lenta (cota, contexto, `advise`) antes; depois **retira**
  os pedidos da fila sob a trava e escreve o stdout logo em seguida. Se a escrita falhar, devolve os pedidos à fila.
  Se já tiverem passado `HOOK_REQUEST_CUTOFF_SECONDS` (2,5 s) desde o início do hook, não mexe na fila (o prazo de
  4 s poderia matar o processo entre retirar e escrever). Retirar, em vez de ler e apagar depois, impede que dois
  hooks do guard rodando em paralelo na mesma sessão (registrados no `~/.claude` e no `.claude` do projeto, por
  exemplo) entreguem o mesmo pedido duas vezes: o Claude Code roda em paralelo os hooks de um evento.

### Unidades novas (mesmo arquivo, mesmas convenções)

| Unidade | Papel | Depende de |
|---|---|---|
| `PENDING_ACTIONS`, `ACTION_LABELS` | nomes das ações e rótulos dos botões | nada |
| `desktop_pending_path(sid)` | `desktop\pending\<sid>.json`, com o `sid` validado como em `desktop_state_path` | `SESSION_ID_RE` |
| `read_pending(sid)` | lista de ações pendentes (sem trava, para a janela); arquivo ausente ou corrompido = vazio | `read_json` |
| `toggle_request(sid, action, now)` | sob a trava: acrescenta ou cancela; trata o par `economy_*`; devolve `True` se ficou pendente | `file_lock`, `atomic_write_json` |
| `take_requests(sid, lock_timeout)` | sob a trava: retira e devolve as ações pendentes, na ordem de entrega; apaga o arquivo | idem |
| `restore_requests(sid, actions, now)` | sob a trava: devolve à fila as ações que não foram escritas | idem |
| `request_notes(actions, event)` | texto dos pedidos (puro) | nada |
| `economy_reminder_note()` | lembrete do modo econômico após `clear`/`compact` (puro) | nada |

`DesktopSessionState` ganha `last_event: Optional[str]`, `economy_mode: bool = False`,
`delivered_actions: list[str]` (vazia por padrão), `delivered_at: float = 0.0`, `delivered_via: Optional[str]`.
Estados antigos continuam carregando (campos ausentes ficam no padrão).

## 3. Janela

Cada cartão de "Sessões do Desktop" ganha uma linha de botões e, quando houver pedido, uma linha de situação:

```
MeuProjeto  #41bfd889
contexto 84k tokens · cota em atenção · há 3m
Cota 5h em 64% (reinicia em 2h10m). Modo econômico: ...
[Compactar] [Economizar: ligado] [Skills/MCPs] [Pesquisar]
pendente: Compactar · vai no fim do turno atual (ou com a sua próxima mensagem)
```

- **Rótulos:** "Compactar", "Skills/MCPs", "Pesquisar"; pendente vira "✓ <rótulo>". O botão de economia mostra:
  - "Economizar" (desligado; o clique pede `economy_on`);
  - "Economizar: ligado" (`economy_mode` verdadeiro; o clique pede `economy_off`);
  - "✓ Economizar" (`economy_on` pendente) ou "✓ Desligar economia" (`economy_off` pendente).
  Clicar num botão com "✓" cancela o pedido.
- **Linha de situação**:
  - com pendências e `last_event == "UserPromptSubmit"` (Claude trabalhando): "pendente: A, B · vai no fim do turno
    atual (ou com a sua próxima mensagem)";
  - com pendências e o Claude parado: "pendente: A, B · vai junto com a sua próxima mensagem (até um 'ok' serve)";
  - sem pendências e entrega há menos de 10 min: "entregue há 2m: A, B (fim do turno | sua mensagem)".
- **Cota crítica** (nível da conta, o mesmo da faixa do topo): "Skills/MCPs" e "Pesquisar" desabilitados; a linha de
  situação acrescenta "pesquisa e skills pausadas: cota crítica". Pedidos já pendentes dessas ações continuam
  pendentes e podem ser cancelados (o botão fica habilitado só para cancelar).
- **Rodapé** confirma cada clique: "Compactar pedido para #41bfd889: vai no fim do turno atual" ou "pedido
  cancelado". Trava ocupada ou erro de disco: "não deu para registrar o pedido (tente de novo): <motivo>", em vermelho.
- `desktop.enabled: false`: os botões ficam desabilitados e a seção diz "modo Desktop desligado no config".
- **Espaço:** até **4** cartões (antes 6) e depois "+ N outras"; janela de **600x840** (antes 600x780).

## 4. Textos injetados

Uma linha por ação, com o prefixo `[usage-guard]`. O cabeçalho depende do canal:

- `Stop`: `[usage-guard] Pedido do usuário pelo botão "<rótulo>" do Claude Usage Guard (não é erro; faça agora):`
- `UserPromptSubmit`: `[usage-guard] Pedido do usuário pelo botão "<rótulo>" do Claude Usage Guard (faça antes do
  resto da mensagem dele):`

| Ação | Texto depois do cabeçalho |
|---|---|
| `compact` | `grave HANDOFF.md (modelo da skill economia-de-cota) e devolva uma linha pronta "/compact <o que manter>" para ele colar. Não comece tarefa nova antes. Se o próximo assunto for outro, recomende /clear e depois ler o HANDOFF.md.` |
| `economy_on` | `modo econômico nesta sessão até ele desligar (skill economia-de-cota, nível attention). Confirme em uma linha.` |
| `economy_off` | `modo econômico desligado; volte ao normal, a menos que outra nota [usage-guard] de cota peça economia. Confirme em uma linha.` |
| `tools` | `use a skill ferramentas-do-projeto: analise o projeto, sugira skills, MCPs, plugins e hooks (o que pôr e o que tirar) e instale só o que ele aprovar.` |
| `research` | `use a skill pesquisar-otimizacoes: pesquise primeiro como usar o Claude Code neste projeto gastando menos, depois boas práticas do stack; grave OTIMIZACOES.md e proponha as 3 a 5 mudanças de maior ganho; aplique só o que ele aprovar.` |

Lembrete após `clear`/`compact` com o modo ligado: `[usage-guard] Modo econômico ligado pelo usuário nesta sessão
(skill economia-de-cota, nível attention).`

O JSON de saída continua ASCII (`json.dumps` com `ensure_ascii`), e cada texto se basta sozinho mesmo sem a skill
instalada.

## 5. Skills

Empacotadas em `assets\skills\<nome>\SKILL.md` (o `build_exe.bat` já inclui `assets\skills` inteiro).
`install-desktop` e `uninstall-desktop` passam a tratar as três da mesma forma que tratam hoje a `economia-de-cota`:
copia se não existir ou for igual; mantém e avisa se o usuário editou (com `--force`, substitui com backup); remove
só se for idêntica à empacotada.

### `ferramentas-do-projeto` (cerca de 80 linhas, português)

Frontmatter `description`: use quando o usuário pedir para sugerir, instalar ou revisar skills, MCPs, plugins ou
hooks do projeto, ou ao ver um pedido `[usage-guard]` do botão "Skills/MCPs".

1. **Stack, de forma barata:** manifestos (`package.json`, `pyproject.toml`, `*.csproj`, `go.mod`...), começo do
   `README`, `CLAUDE.md`, `.claude/`. Varredura feita por um subagente `model: haiku` que só devolve a conclusão.
2. **Inventário do que está ativo:** skills e MCPs (o Claude os vê no próprio contexto), plugins, hooks em
   `.claude/settings.json` e `~/.claude/settings.json`.
3. **Proposta:** até 5 coisas para **pôr** e até 5 para **tirar ou desligar**, numa tabela (nome, para quê, custo em
   contexto, como instalar ou remover). Lembra que a descrição de cada skill instalada entra no contexto de toda
   sessão, e que muitas skills sem relação com o projeto custam tokens em todo turno.
4. **Onde procurar:** primeiro as ferramentas de busca de plugins, skills e MCPs do próprio app, quando existirem
   (por exemplo `SearchPlugins`, `SuggestSkills`, busca no registro de MCP); senão, fontes oficiais. Confira na
   documentação atual antes de afirmar como instalar.
5. **Instalação só com aprovação**, item por item, de preferência no projeto (`.claude/skills/`, `.mcp.json`).
   Para remover algo global, explique o efeito em outros projetos e peça confirmação. Nunca mexa nos hooks do
   Claude Usage Guard.

### `pesquisar-otimizacoes` (cerca de 80 linhas, português)

Frontmatter `description`: use quando o usuário pedir para pesquisar boas práticas ou otimizações para o projeto ou
para o uso do Claude Code nele, ou ao ver um pedido `[usage-guard]` do botão "Pesquisar".

1. Se `OTIMIZACOES.md` na raiz tiver menos de 30 dias, use-o: mostre as pendências e pergunte antes de pesquisar de novo.
2. Contexto curto: stack (como na outra skill) e como o usuário trabalha (`CLAUDE.md`, `.claude/`).
3. Delegue a pesquisa a **um** subagente `model: sonnet`, com no máximo 6 buscas e resposta de até 400 palavras
   com links. Ordem: (a) uso do Claude Code neste tipo de projeto gastando menos (CLAUDE.md, skills, hooks,
   modelos, fluxo); (b) boas práticas e otimizações do stack.
4. Grave `OTIMIZACOES.md` (data, fontes, achados por ganho estimado, coluna "aplicado?"). Se o arquivo já existir,
   acrescente uma seção datada.
5. No chat, só as 3 a 5 mudanças de maior ganho, com custo e risco; aplique só as aprovadas e marque-as no arquivo.

### `economia-de-cota` (seção nova "Pedidos pelos botões do guard")

- **Compactar:** grave o `HANDOFF.md` (modelo já existente na skill) e entregue numa linha de código
  `/compact <foco>`, dizendo o que manter (objetivo, decisões, arquivos em jogo, próximo passo). Se o próximo assunto
  for outro, recomende `/clear` e depois ler o `HANDOFF.md`.
- **Modo econômico fixo:** siga o nível attention até ver "modo econômico desligado"; vale também depois de
  `/compact`, e o guard repete o lembrete.

## 6. Hook (`cmd_desktop_hook`)

Mudanças em relação à 1.3.0:

1. `state.last_event = event` em todo evento.
2. Pedidos: em `UserPromptSubmit`, e em `Stop` com `stop_hook_active` diferente de `true`, **depois** da cota, do
   contexto e do `advise`, e só se o hook começou há menos de 2,5 s: `actions = take_requests(sid, lock_timeout=1)`.
   Trava ocupada ou erro: `actions = []` e aviso no `guard.log` (a nota de cota sai normalmente).
3. `advise()` recebe o lembrete do modo econômico (pura; ver seção 2).
4. Se `actions`: `economy_mode` atualizado, `delivered_actions/at/via` gravados no estado e
   `last_note = request_notes(...)`.
5. Saída:
   - `UserPromptSubmit`: `additionalContext` = notas de cota e depois os pedidos (linhas separadas).
   - `Stop` com pedidos: `{"decision": "block", "reason": <pedidos>}`. Sem pedidos: nada, como hoje.
   - `SessionStart`: como hoje, mais o lembrete do modo econômico quando couber.
6. Se a escrita no stdout levantar exceção: `restore_requests(sid, actions, now)`.
7. Orçamento: o caminho comum continua abaixo de 1 s; o prazo de 4 s (`os._exit(0)`) continua valendo.

## 7. Erros e casos-limite

| Situação | Comportamento |
|---|---|
| Trava ocupada no hook (1 s) | pedido fica para o próximo hook; nota de cota sai |
| Trava ocupada na janela (2 s) | rodapé em vermelho, "tente de novo" |
| `pending\<sid>.json` corrompido | tratado como vazio (aviso no `guard.log`); o próximo clique o reescreve |
| `stop_hook_active: true` | não bloqueia; vai na próxima mensagem |
| Esc no meio do turno (não dispara `Stop`) | vai na próxima mensagem; a janela já diz "ou com a sua próxima mensagem" |
| Sessão fechada com pedido pendente | continua listada e "pendente" na janela até ser cancelado ou expirar (4 h sem entrega, `PENDING_MAX_AGE_SECONDS`) |
| `desktop.enabled: false` | hook não entrega nada; janela desabilita os botões |
| Skill não instalada | o texto da nota basta sozinho |
| `session_id` inválido | `GuardError` (o hook sai com 0, sem saída); a janela nunca grava fila para id inválido |
| Dois hooks do guard na mesma sessão (global + projeto), em paralelo | o primeiro a pegar a trava retira os pedidos; o outro não acha nada |
| Hook já perto do prazo (≥ 2,5 s) | não mexe na fila; o pedido vai no próximo hook |

## 8. Testes

1. **Fila** (`tests\test_desktop_requests.py`): acrescentar; clique de novo cancela; `economy_on` tira `economy_off`
   e vice-versa; ordem de entrega fixa; `take_requests` esvazia e apaga o arquivo; `restore_requests` devolve sem
   duplicar; JSON corrompido = vazio; `sid` inválido recusado.
2. **Textos e `advise`:** cabeçalho por canal; uma linha por ação; ASCII no JSON; lembrete do modo econômico em
   `SessionStart` `clear`/`compact` só com o modo ligado; nenhum lembrete em `startup`/`resume`.
3. **Hook de ponta a ponta** (subprocesso, como `test_desktop_hook.py`):
   - `UserPromptSubmit` com pedido e cota alta: `additionalContext` traz a nota de cota e o pedido; a fila esvazia;
     o estado tem `delivered_*`;
   - `Stop` com pedido: saída `{"decision":"block","reason":...}`;
   - `Stop` com `stop_hook_active: true`: sem saída e a fila continua;
   - `Stop` sem pedido: sem saída (regressão);
   - `economy_on` entregue e depois `SessionStart source=compact`: lembrete no `additionalContext`;
   - fila corrompida: nota de cota sai, código 0.
4. **Instalação:** as três skills copiadas, mantidas quando editadas, substituídas com `--force` e removidas no
   `uninstall-desktop` só se idênticas.
5. **Janela** (`tests\test_gui_desktop.py`): quatro botões por cartão; clique cria o pedido e o rótulo vira "✓";
   segundo clique cancela; rótulos do botão de economia nos quatro estados; cota crítica desabilita "Skills/MCPs" e
   "Pesquisar"; linha "fim do turno" e "próxima mensagem"; "entregue há"; no máximo 4 cartões.
6. **Sessão real do Desktop:** `.exe` refeito; os hooks globais já instalados pela 1.3.0 apontam para ele (não
   registrar hooks no projeto, senão rodam dois em paralelo). Na sessão de teste em `_e2e\proj`: (a) pedido gravado
   com a sessão parada mais uma mensagem: o Claude recebe e age; (b) pedido gravado com ela trabalhando: entrega no
   fim do turno; (c) o usuário clica num botão da janela de verdade.
7. **Regressão:** `py -m pytest tests -q` todo verde, pyflakes limpo, `_e2e\gui_checks.py`, `.exe` refeito (com a
   janela do guard fechada).

## 9. Critérios de aceite

- Numa sessão real do Desktop, um clique em cada botão leva o Claude a fazer o pedido: no fim do turno, se ele
  estava trabalhando; com a próxima mensagem, se estava parado.
- Nenhum pedido é entregue duas vezes no caso comum, e nenhum se perde por trava ou prazo.
- O hook continua sempre com código 0, abaixo de 1 s no caso comum, e sem nada no stdout além do JSON.
- Todos os testes passam, e `install-desktop` + `uninstall-desktop` continuam deixando o `settings.json` como estava.

## 10. Riscos

- **Custo:** "Pesquisar" e "Skills/MCPs" gastam cota (buscas, leitura do projeto). Mitigado com subagentes
  mais baratos, limite de buscas, reaproveitamento do `OTIMIZACOES.md` e bloqueio com cota crítica.
- **Texto de "erro" no `Stop`:** o Desktop mostra o pedido como "blocking error". O cabeçalho diz "não é erro";
  no spike, o Claude seguiu o pedido sem estranhar.
- **Mudança futura do Desktop** no `decision: block` do `Stop`: o `UserPromptSubmit` continua entregando; repetir o
  teste 6 após atualizações grandes.
- **Sessões abertas antes da 1.4.0:** os hooks já estão instalados e apontam para o mesmo `.exe`, então passam a
  entregar pedidos sem reabrir. As skills novas só aparecem em sessões novas.
