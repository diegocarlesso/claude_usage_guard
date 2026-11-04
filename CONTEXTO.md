# CONTEXTO — Claude Usage Guard

Passagem de bastão da sessão na nuvem (onde o projeto foi escrito) para uma
sessão local do Claude Code em `F:\Projetos\ClaudeCodeSessionLimits`.
Leia isto antes de mexer no código. Data: 03/11/2026. Versão: 1.3.0
(1.1.0 veio da nuvem; a 1.2.0 tem as correções do teste em Windows real; a
1.3.0 traz o modo Claude Desktop, decisão 21).

O código fica na subpasta `ClaudeCodeSessionLimits\` (os caminhos abaixo são
relativos a ela). O teste ponta a ponta automatizado fica em `_e2e\`, fora do
que é distribuído.

## Objetivo

CLI em Python que reduz o consumo das cotas de sessão (5h) e semanal (7d) do
Claude Code sem violar os termos de uso:

- monitora o uso pelo endpoint `GET https://api.anthropic.com/api/oauth/usage`;
- aplica mitigações dentro da sessão: `/compact`, `/clear`, troca para Haiku
  e failover para um proxy local;
- mostra um dashboard no terminal e uma janela gráfica (tkinter) que abre
  sozinha com o `run`;
- é configurado por `config.yaml` e por variáveis de ambiente `CUG_*`;
- **modo Claude Desktop (aba Code):** o usuário só usa o Desktop, onde o `run`
  não serve. `install-desktop` registra hooks no `~/.claude/settings.json` que
  mandam notas `[usage-guard]` ao Claude (economizar, `/compact`, `/clear` com
  `HANDOFF.md`), toasts do Windows e a seção "Sessões do Desktop" na janela,
  mais a skill `economia-de-cota`. Spec e plano em `docs\superpowers\`.

Ambiente do usuário: **Windows nativo** (sem WSL), Claude Code rodando direto
no Windows.

## Arquivos

| Arquivo | Papel |
|---|---|
| `claude_usage_guard.py` | Programa inteiro (só biblioteca padrão; `pywinpty` no Windows). A documentação de uso está no topo. |
| `config.yaml` | Limiares e ações. `compact.context_tokens_threshold: 120000` (pedido do usuário). |
| `build_exe.bat` | Gera `dist\claude_usage_guard\claude_usage_guard.exe` com PyInstaller (`--onedir`, ícone `assets\app.ico`). |
| `requirements-windows.txt` | `pywinpty`, `pyyaml`. |
| `LEIA-ME.txt` | Passo a passo para o usuário. |
| `assets\` | Ícones do usuário (`app.ico` com 16 a 256 px) e paleta (`colors.png`: `#2DAAF4`, preto, branco). |
| `installer.nsi` | Script NSIS do `ClaudeUsageGuard-Setup.exe` (só extrai arquivos; precisa do `makensis`). **Não veio para a pasta local**, e o `makensis` não está instalado. |
| `..\_e2e\driver.py` | Teste ponta a ponta com o Claude Code real (ver "Testado em Windows real"). `probe.py`/`probe_inner.py`: registram o que o `ReadConsoleW` entrega num ConPTY. |
| `..\_e2e\lowpriv.cmd` | Roda um comando sem elevação (`runas /trustlevel:0x20000 "cmd /c ...\lowpriv.cmd <comando>"`) e grava a saída em `lowpriv.txt`. |
| `assets\skills\economia-de-cota\SKILL.md` | Skill copiada pelo `install-desktop` para `~/.claude/skills/` (entra no `.exe` com `--add-data`). |
| `..\tests\` | Testes pytest (68): config `desktop:`, níveis/notas, `advise()`, toast, `desktop-hook` ponta a ponta (subprocesso), instalador, janela, achados da revisão final (`test_review_fixes.py`). `py -m pytest tests -q` na pasta de fora. O `conftest.py` isola o estado num diretório temporário. |
| `..\docs\superpowers\` | Spec (`specs\2026-11-03-desktop-economia-de-cota-design.md`) e plano do modo Desktop. |
| `..\_e2e\gui_snapshot.py` / `gui_checks.py` | Captura da janela com dados falsos (`gui_snapshot.png`, precisa do Pillow) e checagens do botão "Pedir /clear" e da janela única. |

## Arquitetura

```
UsageMonitor (thread) ──► cache compartilhado ~/.claude-usage-guard/usage_cache.json
        │                          (lock entre processos; respeita 429 / Retry-After)
        ▼
decide(cfg, snapshot, GuardState) ── função pura: lista de ações por prioridade
        │                            failover > clear > compact > switch/restore model
        ▼
GuardController.on_tick ── só age se safe_to_inject() ─► TerminalSession.inject("/compact")
        ▲
        └── hooks do Claude Code (SessionStart, UserPromptSubmit, PreToolUse,
            Notification, Stop) chamam `claude_usage_guard hook` e gravam
            eventos em instances/<id>/hooks.jsonl
```

- `TerminalSession` tem duas implementações:
  - `PosixPtySession` (Linux/macOS): `pty.fork` + `select`.
  - `WindowsConPtySession`: `winpty.PtyProcess` (ConPTY). Uma thread única lê
    o teclado com `ReadConsoleW` (console em modo raw + entrada VT) e alimenta
    uma fila; outra thread copia a saída para `sys.stdout.buffer`, em bytes,
    sem converter `\n` em `\r\n`. O tamanho da janela é verificado por polling,
    porque o Windows não tem SIGWINCH.
- `safe_to_inject` exige todas estas condições:
  - o último hook foi `Stop` ou `SessionStart`, ou uma Notification de "idle";
  - a tela está parada há N segundos;
  - o usuário não digita há N segundos;
  - não há texto pela metade no campo de entrada (`input_dirty`).

  `PreToolUse` deixa o estado "ocupado" até o próximo `Stop`. Por isso o guard
  **nunca aperta Enter num prompt de permissão**. Com `-v`, o `guard.log`
  registra cada mudança do motivo de bloqueio ("tela mudando", "texto pela
  metade no campo", "aguardando permissão"...), o que facilita diagnosticar.
- `input_dirty` é calculado por `INPUT_TOKEN_RE`, que entende teclas comuns,
  sequências ESC, colagem (bracketed paste) e o **win32-input-mode**
  (`ESC[Vk;Sc;Uc;Kd;Cs;Rc_`, ver decisão 14).
- **Esc não dispara `Stop`** (nem `idle_prompt`): recusar uma permissão ou
  interromper um turno deixaria o guard "ocupado" para sempre. Por isso, com a
  tela parada e o estado ocupado, `_check_interrupted` lê o fim do transcript a
  cada 3 s; se a última mensagem for `[Request interrupted by user...]` e for
  posterior ao último hook ocupado, trata como fim de turno.
- **Janela (`gui`)**: `GuardWindow` desenha a cada `dashboard.refresh_seconds`
  os mesmos dados do `dashboard` (`UsageMonitor` + `list_instances()` +
  `recent_actions()`), recebidos por uma função, o que permite testá-la com
  dados falsos. O `run` chama `launch_gui_detached()` (processo destacado, sem
  console e fora do grupo do Ctrl-C) se `gui.open_on_run` e se não houver
  janela viva em `gui.pid`; `cmd_gui` confere isso de novo sob `gui.lock`.
  Botões: "Pedir /clear" (`request_clear()`, o mesmo do `signal clear`) e
  "Abrir log". A cor das barras vem de `_window_level()`, compartilhada com o
  dashboard.
- Estado em `%USERPROFILE%\.claude-usage-guard\`:
  - `guard.log` (rotativo) e `actions.jsonl`;
  - `gui.pid` e `gui.lock` (janela única);
  - `usage_cache.json`;
  - `instances\<id>\` com `status.json`, `hooks.jsonl`, `settings.json` e
    `clear.request`.

## Decisões tomadas (e por quê)

1. **O CLI não tem `--clear` nem `--compact`** (conferido no `claude --help`).
   Comandos de barra só existem na sessão interativa, por isso o guard roda o
   `claude` num pseudo-terminal e "digita" os comandos.
2. **Os hooks entram via `claude --settings <arquivo>`** e não alteram o
   `settings.json` do usuário. É um arquivo, e não JSON na linha de comando,
   porque as aspas quebram no Windows.
3. **Comando do hook no Windows:** barras normais, aspas só se houver espaço.
   Assim funciona em Git Bash, cmd e PowerShell. No `.exe` congelado o
   comando é `<exe> hook`. Se o `python.exe` estiver num caminho com espaços,
   usa `py -3`.
4. **`claude.cmd` do npm:** o ConPTY não executa `.cmd` e o `cmd.exe`
   embaralharia as aspas. Por isso `npm_shim_target()` lê o `.cmd` e chama
   `node cli.js` (ou o `.exe` apontado) diretamente. O `claude.exe` do
   instalador nativo roda direto.
5. **Credenciais:** `%USERPROFILE%\.claude\.credentials.json`, campo
   `claudeAiOauth.accessToken`; no macOS, Keychain. **O guard nunca renova o
   token**, porque renovar troca o refresh token e deslogaria o Claude Code.
   Em 401, ele espera o Claude Code renovar e relê o arquivo.
6. **O token só vai para `*.anthropic.com`** (ou localhost em testes). O
   failover só aceita `http` em localhost.
7. **Sem rodízio de contas Anthropic** (estilo `shunt`): viola os termos de
   uso. O failover é para backends próprios ou pagos (Ollama, LiteLLM, chave
   de API).
8. **`ANTHROPIC_BASE_URL` só vale ao iniciar o processo.** O failover no meio
   da sessão (`relaunch_session: true`) faz `/exit` e reabre com
   `claude --resume <session_id>` apontando para o proxy.
9. **Compact só quando há conversa** (`turns_since_clear > 0`); compactar uma
   sessão vazia desperdiça uma chamada. Por janela de 5h ele roda uma vez; por
   tamanho de contexto (lido do transcript JSONL) roda de novo após novos
   turnos, respeitando o cooldown.
10. **Um `/clear` manual cancela um `signal clear` pendente.**
11. **PyInstaller com `--onedir`:** os hooks chamam o `.exe` a cada uso de
    ferramenta, e `--onefile` descompacta tudo a cada chamada (cerca de 1 s
    mais lento).
12. **`pid_alive` no Windows usa a API Win32.** `os.kill(pid, 0)` no Windows
    mandaria Ctrl-C (0 == `CTRL_C_EVENT`).
13. **Dashboard:** a cor da marca é `#2DAAF4` (ANSI truecolor). Amarelo e
    vermelho ficam reservados para limiares cruzados.
14. **win32-input-mode:** quando o Claude Code abre, o ConPTY pede ao terminal
    `ESC[?9001h` e, a partir daí, cada tecla chega como
    `ESC[13;28;13;1;0;1_` (Enter) em vez de `\r`. A 1.1.0 tratava tudo que
    começa com ESC como "seta", então o Enter nunca limpava `input_dirty` e
    **nenhum `/compact`, `/clear` ou `/model` era injetado no Windows**. A 1.2.0
    decodifica essas sequências (só tecla pressionada, `Kd=1`, com caractere
    `Uc`). As teclas continuam sendo repassadas sem alteração ao ConPTY interno,
    que entende o protocolo.
15. **Janelas extras do endpoint:** a resposta real traz `five_hour`,
    `seven_day`, `iguana_necktie` (100% sem bloquear nada; codinome interno) e
    `extra_usage` (`null`). Só `five_hour`/`seven_day` entram na política. No
    dashboard e no `status`, janelas sem rótulo aparecem esmaecidas, sem cor de
    alerta, e as que vêm com `utilization: null` são omitidas.
16. **Encoding no Windows:** com a saída redirecionada (pipe/arquivo), stdout e
    stderr passam a usar UTF-8 (antes era cp1252 e `→`/`█`/acentos viravam `?`).
    O `guard.log` também é gravado em UTF-8.
17. **Variáveis do app desktop:** rodar o guard de dentro de uma sessão do
    Claude Code (app desktop/terminal integrado) faz o `claude` filho herdar
    `CLAUDE_CODE_*`/`ANTHROPIC_BASE_URL` e virar "sessão filha", sem gravar
    transcript. Num terminal normal isso não acontece; o driver de teste remove
    essas variáveis.
18. **`/model` grava o padrão do usuário:** no Claude Code atual, `/model X`
    responde "saved as your default for new sessions" e escreve `"model": X`
    em `~/.claude/settings.json`. Para manter a promessa da decisão 2, o
    `GuardController` lê o valor de `"model"` ao abrir e, por até 15 s depois de
    cada `/model` que ele mesmo digita, devolve o valor original (ou remove a
    chave, se ela não existia); faz isso de novo ao sair. Testado: a sessão
    continua no modelo trocado (o Claude Code não recarrega o `model` do
    arquivo) e o arquivo volta ao que era em ~0,5 s. Um `/model` digitado por
    você não é desfeito.
19. **Janela em tkinter, sem dependência nova:** vem com o Python e o
    PyInstaller empacota sozinho. Uma janela para todas as sessões; fechá-la
    não afeta nada, e o próximo `run` a reabre. Os botões nunca digitam
    direto no Claude ("Pedir /clear" só agenda). Ficaram fora: ícone na
    bandeja e "sempre por cima". O `build_exe.bat` exclui numpy/PIL, que o
    PyInstaller puxava por estarem instalados no Python (83 MB → 42 MB).
20. **Permissões da pasta de estado no Windows:** a 1.1.0 criava as pastas com
    `mkdir(mode=0o700)`, e no Python 3.13+ isso grava uma ACL que só libera o
    **dono** de cada arquivo (mais SISTEMA/Administradores). Arquivos criados
    num terminal elevado ficam com dono "Administradores", e o terminal normal
    recebia `PermissionError` no `guard.log`, no `usage_cache.lock` e em
    `instances\`, e nem conseguia listar a pasta. Agora:
    - no Windows, as pastas são criadas sem `mode` e herdam a ACL do perfil
      (que já é privada para o usuário);
    - na primeira execução, `repair_windows_state_acl()` roda
      `icacls <pasta> /reset /T /C /Q` e confere o resultado testando o acesso
      a cada item (o `icacls` devolve 0 mesmo com "Acesso negado"). Deu certo:
      grava `.acl-ok`. Não deu, num terminal normal: avisa o comando a rodar
      uma vez como administrador;
    - se o `guard.log` não abrir, o programa segue sem log em arquivo, e um
      `PermissionError` vira uma mensagem com a correção, sem traceback.
    Testado com `runas /trustlevel:0x20000` (processo não elevado): pasta
    antiga → aviso claro; depois de um reparo elevado → `status`/`gui` ok;
    pasta nova criada elevada → acessível sem elevação.
21. **Modo Claude Desktop = hooks + `advise()` + skill + toast.** O spike de
    03/11 numa sessão real da aba Code mostrou: `SessionStart`,
    `UserPromptSubmit` e `Stop` do `settings.json` disparam
    (`CLAUDE_CODE_ENTRYPOINT=claude-desktop`); `additionalContext` chega ao
    contexto do Claude; `systemMessage` não aparece para o usuário; o `"model"`
    do `settings.json` é ignorado; o toast WinRT via `powershell.exe` 5.1
    aparece (o `pwsh` 7 não carrega WinRT; o balão `NotifyIcon` morre junto com
    o processo). Daí:
    - `desktop-hook` (caminho rápido, sem reparo de ACL, sempre código 0, só o
      JSON da nota no stdout, ASCII): cota do cache (rede só com cache velho,
      timeout e espera da trava de `usage_fetch_timeout_seconds`), contexto do
      transcript no `Stop`, estado em `desktop\<sessão>.json`;
    - `advise()` é pura: nota só nas viradas de nível (normal/attention/high/
      critical, o pior entre 5h e 7d) e a cada +30k de contexto; toasts em
      high/critical uma vez por janela (registro em `desktop\alerts.json` sob
      trava, mesmo com toast desligado) e um de contexto por sessão;
    - `install-desktop` mexe só nas entradas do guard (comando com
      `desktop-hook` e `claude_usage_guard`), com backup, preservando BOM, CRLF
      e a quebra final; `uninstall-desktop` desfaz. A skill só é trocada com
      `--force` se o usuário a editou. Cria o atalho "Claude Usage Guard" no
      Menu Iniciar (`gui`); aberta assim, a janela solta o console
      (`FreeConsole`).
    O que não dá: nenhum hook roda `/compact`, `/clear` ou troca o modelo da
    sessão; o guard leva o Claude e o usuário a agir. A aba de chat comum não
    tem hooks.
22. **Correções do primeiro dia de uso real (04/11):**
    - **Token vencido:** o Desktop autentica as sessões pelo próprio app
      (`CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH`) e não renova o
      `~/.claude/.credentials.json`; o token do CLI vence em ~8 h e o guard
      ficava sem dados de uso (janela "token OAuth expirado", nenhuma nota).
      `claude auth status` não renova; uma chamada mínima renova:
      `claude -p ok --model haiku --tools "" --system-prompt ... --setting-sources ""
      --strict-mcp-config --disable-slash-commands --no-session-persistence`
      (390 tokens de entrada + 138 de saída, 3,6 s; `CLAUDE_CODE_SIMPLE=1`
      desliga o OAuth, por isso não é usado). O hook e a janela, ao verem o
      token vencido, lançam `refresh-auth` em segundo plano (no máximo a cada
      20 min), que faz essa chamada com o ambiente limpo e já atualiza o
      cache. Desligável: `desktop.refresh_auth_with_cli: false`.
    - **Toast que nunca aparecia:** dentro da sessão do Claude Code o
      `CREATE_BREAKAWAY_FROM_JOB` é negado (WinError 5) e a 2ª tentativa usava
      `DETACHED_PROCESS`, com o qual o PowerShell é criado mas o toast não chega
      ao Windows. Medido pelo `LastNotificationAddedTime` no registro
      (`_e2e\toast_diag.py`, `_e2e\toast_via_hook.py`): sem `DETACHED_PROCESS`
      (`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`) chega em 0,9 s.
    - **Build com a janela aberta:** os hooks apontam para `dist\`; com a
      janela do guard aberta (ou um terminal parado dentro de `dist\`), o
      `build_exe.bat` falha com "Acesso negado". Feche a janela antes de
      refazer o `.exe`.

## O que foi testado (na nuvem, Linux)

- **Política:** rampa de uso de 20% a 95% → compact (60%), haiku (70%),
  failover (90%) e volta ao modelo original quando a janela reinicia (`demo`).
- **Config:** PyYAML e o parser YAML interno leem o `config.yaml` igual; os
  overrides `CUG_*` funcionam; a validação rejeita limiares fora de 0–100.
- **Endpoint (servidor falso local):**
  - 200 ok;
  - 401 → mensagem de token expirado;
  - 429 → cooldown gravado no cache e respeitado por outros processos;
  - 500 / servidor fora do ar → 3 tentativas com backoff e depois erro claro;
  - URL remota não-Anthropic recusada.
- **Ponta a ponta com um `claude` falso** que dispara os hooks reais:
  - `--model haiku` na abertura com uso alto;
  - nada de compact numa sessão vazia;
  - **nenhuma injeção durante prompt de permissão** nem com texto pela metade;
  - `/compact` após o turno, contexto medido no transcript (152k);
  - `signal clear` → `/clear` no fim do turno seguinte;
  - saída limpa e pasta da instância removida;
  - failover na abertura e no meio da sessão (proxy sobe, `--resume`,
    `${VAR}` expandido em `failover.env`, proxy derrubado ao sair).
- **Caminho Windows simulado:** o código carregado com `IS_WINDOWS = True`,
  `pywinpty` e `msvcrt` substituídos por dublês com a mesma API, mesmo roteiro
  ponta a ponta → passou. A API real do `pywinpty` 3.1.2 foi conferida no
  wheel (`spawn`, `read`, `write`, `isalive`, `exitstatus`, `setwinsize`).
- **Unitários:** formato do comando do hook no Windows; leitura do
  `claude.cmd` do npm (variantes `cli.js`, `.exe` e arquivo inválido).
- **Instalador:** extraído com 7-Zip e comparado arquivo a arquivo com os
  originais.

O harness de teste (claude falso, servidor falso, dublês do Windows) ficou na
nuvem e não veio junto. Se precisar, recrie a ideia: um `claude` falso que lê
o `--settings`, executa o comando do hook com JSON no stdin e registra os
comandos de barra que recebe.

## Testado em Windows real (03/11/2026, Windows 11, Claude Code nativo `claude.exe`, Python 3.14, pywinpty instalado)

- **Build:** `build_exe.bat` gera `dist\claude_usage_guard\claude_usage_guard.exe`
  (PyInstaller 6, `--collect-all winpty`) sem erros.
- **`check-config`:** acha `C:\Users\<você>\.local\bin\claude.EXE` (roda direto,
  sem shim npm), pywinpty e as credenciais OAuth.
- **`status` / endpoint real:** respondeu `five_hour`, `seven_day`,
  `iguana_necktie` e `extra_usage` (ver decisão 15).
- **Ponta a ponta automatizado** (`_e2e\driver.py`): abre o guard (o `.exe` ou
  o `.py`) num ConPTY próprio, digita como um usuário e confere
  hooks/status/ações/transcript. Usa `--model haiku --no-chrome` e uma pasta de
  teste em `_e2e\proj`. **17/17** com o `.exe` (15/15 antes da janela, com o `.exe` e o `.py`):
  - hooks rodam no Windows (o comando `F:/.../claude_usage_guard.exe hook`
    funciona no shell que o Claude Code usa): risco nº 1 da nuvem resolvido;
  - acentos, setas, End e colagem chegam intactos ao Claude
    (`açúcar ção aXbc colado`);
  - estado "ocioso" e contexto medido (42k tokens) depois de um turno;
  - `/compact` automático por tamanho de contexto (limiar 1000) e
    `SessionStart source=compact`;
  - `signal clear` → `/clear` digitado sozinho → `SessionStart source=clear`;
  - prompt de permissão: nada digitado por 40 s, arquivo não criado; depois do
    Esc, o `/clear` pendente roda;
  - Ctrl-C duas vezes encerra tudo (código 0) e apaga a pasta da instância.
- **Troca de modelo** (`E2E_MODE=model`): `/model sonnet` injetado com a sessão
  ociosa, o Claude Code confirma, o turno seguinte roda em
  `claude-sonnet-5` e o `settings.json` volta ao valor de antes. **8/8** com o
  `.exe` e com o `.py`.
- **Janela (`gui`):** o driver confere que o `run` abre a janela sozinho
  (`gui.pid` vivo) e que ela continua aberta depois que a sessão sai.
  `gui_checks.py` (8/8 com o `.py` e com o `.exe`): níveis das barras, botão
  "Pedir /clear" criando `clear.request` e virando "/clear pendente"
  desabilitado, aviso para sessão inexistente, segunda janela recusada com "já
  está aberta". `gui_snapshot.py` gera uma captura com dados falsos para
  conferir o visual.
- **Unitários rápidos:** `_track_input` com teclas comuns, win32-input-mode
  (pressionar/soltar, Shift, setas, Esc, Ctrl-C), colagem e foco;
  `transcript_interrupted` com transcripts reais.

- **Modo Desktop (1.3.0):** `py -m pytest tests -q` → 68 passed (hook pelo
  subprocesso: mediana 0,44 s com o `.py` e **0,48 s com o `.exe`**; endpoint
  pendurado → sai em ~3 s sem nota; endpoint que manda bytes devagar → o prazo
  total de 4 s (`os._exit(0)`) corta, e os próximos prompts pulam a rede por
  60 s (`desktop\fetch_backoff.json`); comando do hook roda no Git Bash com
  pastas `a b`, `O'Neil(x)&y` e `José Açúcar`; `settings.json` com BOM+CRLF ida e volta
  byte a byte; caminho com espaços/acentos; pasta `Açúcar`). Sessão real do
  Desktop em `_e2e\proj` (hooks só no `.claude\settings.json` da pasta,
  `--config` de teste com attention 1% e contexto 1000): o Claude citou a nota
  `[usage-guard] Cota 5h em 31% (reinicia em 1h02m). Modo econômico...` vinda
  do `SessionStart`, e o estado `desktop\<sessão>.json` foi gravado (contexto
  76k medido no `Stop`). Regressão com o `.exe` 1.3.0: driver 17/17,
  `gui_checks` TUDO OK.

Como rodar o driver (de um terminal comum; leva ~3 min e gasta poucos tokens do Haiku):

```bat
cd F:\Projetos\ClaudeCodeSessionLimits\_e2e
py -X utf8 driver.py F:\Projetos\ClaudeCodeSessionLimits\ClaudeCodeSessionLimits\dist\claude_usage_guard\claude_usage_guard.exe
set E2E_MODE=model
py -X utf8 driver.py F:\Projetos\ClaudeCodeSessionLimits\ClaudeCodeSessionLimits\dist\claude_usage_guard\claude_usage_guard.exe
```

Para usar o `.py` com log detalhado, troque o caminho do `.exe` por
`C:\Python314\python.exe ...\claude_usage_guard.py -v` (o `py` sem caminho
pode escolher um Python sem pywinpty).

## Ainda NÃO testado (precisa de uma pessoa olhando)

1. **Aparência no terminal real:** cores do `demo`/`dashboard` e do TUI do
   Claude Code, cursor e **redimensionar a janela** no Windows Terminal e no
   conhost. O driver só confere o texto, não o visual.
2. **Teclado físico:** o driver injeta teclas no ConPTY; IME, Alt+teclas,
   colar com o botão direito e teclados com AltGr não foram exercitados.
3. **Notificação:** agora é toast WinRT (`notify_toast`), com o balão
   `NotifyIcon` como reserva. O script WinRT rodou sem erro em 0,6 s; falta a
   pessoa confirmar o toast visualmente a cada mudança, e o toast aparece como
   "Windows PowerShell" (sem AppUserModelID próprio).
4. **Failover** (proxy local, `claude-spillway`): flags não verificadas; por isso
   `failover.command` é configurável e o failover vem desligado.
5. **`/model default`** (o `restore_model`): a restauração do `settings.json`
   vale igual, mas o texto "default" não foi testado no `/model` atual.
6. **Instalador NSIS:** o `installer.nsi` não está na pasta local.
7. **Janela em outras telas:** escala de DPI diferente de 100%/125% e
   monitores múltiplos. Aberta por duplo clique ou pelo atalho do Menu
   Iniciar, a janela chama `FreeConsole()` (1.3.0); o console preto ainda pisca
   ao abrir, e isso não foi conferido por uma pessoa.
9. **Modo Desktop por muito tempo:** notas nas viradas reais de nível (o teste
   real usou limiares artificiais), o Claude seguindo a skill numa sessão
   longa e o atalho do Menu Iniciar criado pelo `install-desktop` de verdade.
8. **`/compact` que falha no Claude Code** (visto uma vez: "summarization
   produced empty response"): o guard registra a ação como feita e só tenta de
   novo depois do `compact.cooldown_seconds`.

## Próximos passos (checklist para a sessão local)

- [x] `build_exe.bat` → `dist\claude_usage_guard\claude_usage_guard.exe` existe.
- [x] `claude_usage_guard.exe check-config` → binário do claude, comando de execução, comando dos hooks, pywinpty e credenciais.
- [x] `claude_usage_guard.exe status` → uso real das janelas (valida o endpoint).
- [ ] `claude_usage_guard.exe demo` → **cores** do dashboard no terminal real (o texto foi conferido; falta olhar as cores).
- [x] Em um projeto de teste: `claude_usage_guard.exe run` (pelo driver automatizado).
  - [x] Digitar, usar setas, colar, acentos e Ctrl-C funcionam normalmente.
  - [x] Depois de um turno, o estado fica "ocioso" com o contexto em tokens (prova de que os hooks funcionam).
  - [x] `signal clear` → `/clear` aparece sozinho quando o Claude termina.
  - [x] Durante um prompt de permissão, nada é digitado pelo guard.
  - [x] Teste rápido de compact: `CUG_COMPACT_CONTEXT_TOKENS_THRESHOLD=1000`.
  - [ ] Olhar o `dashboard` numa segunda aba durante uma sessão de verdade.
- [x] Ajustar o que falhou (win32-input-mode, Esc sem `Stop`, `/model` gravando o padrão, encoding, janelas extras) e rodar `py -m pyflakes claude_usage_guard.py` (limpo).
- [x] Atualizar este CONTEXTO.md e o `LEIA-ME.txt`.

## Comandos úteis

```bat
py claude_usage_guard.py check-config
py claude_usage_guard.py demo
py claude_usage_guard.py status --json
py claude_usage_guard.py run -- --permission-mode plan
py claude_usage_guard.py dashboard
py claude_usage_guard.py gui
py claude_usage_guard.py signal clear
py claude_usage_guard.py install-desktop   & rem modo Claude Desktop (uninstall-desktop desfaz)
py -m pytest tests -q                      & rem na pasta de fora (F:\Projetos\ClaudeCodeSessionLimits)
py claude_usage_guard.py -v run        & rem guard.log com o motivo de cada bloqueio de injeção
type %USERPROFILE%\.claude-usage-guard\guard.log
```
