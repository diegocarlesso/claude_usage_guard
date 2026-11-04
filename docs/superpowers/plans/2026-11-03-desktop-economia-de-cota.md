# Economia de cota na aba Code do Claude Desktop — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hooks do Claude Code que, nas sessões da aba Code do Desktop, medem cota e contexto, orientam o Claude com notas curtas `[usage-guard]`, avisam o usuário por toast e na janela do guard, mais skill e instalador reversível.

**Architecture:** tudo em `ClaudeCodeSessionLimits\claude_usage_guard.py` (padrão do projeto: arquivo único, só biblioteca padrão). Uma função pura `advise()` decide nota/toast; `cmd_desktop_hook` faz a E/S (stdin do Claude Code → stdout JSON, estado em `desktop\<sessão>.json`). Instalação edita só as entradas do guard no `~/.claude/settings.json`.

**Tech Stack:** Python 3.14 (Windows), pytest 9 (só testes), tkinter (janela), PowerShell 5.1 (toast WinRT), PyInstaller (`build_exe.bat`).

**Spec:** `docs/superpowers/specs/2026-11-03-desktop-economia-de-cota-design.md`

## Global Constraints

- Código de produto só com biblioteca padrão (+ `pywinpty`/`pyyaml` já existentes); pytest só em `tests\`.
- O hook `desktop-hook` sai **sempre com código 0**, nunca escreve nada no stdout além do JSON da nota, e responde em < 1 s com cache fresco.
- Nunca alterar o `"model"` do `settings.json` do usuário.
- Textos das notas: exatamente os da seção 4 da spec, prefixo `[usage-guard]`, tempo de reinício formatado por `_fmt_duration`.
- Limiares padrão: attention 60/70, high 80/85, critical 92/95 (5h/7d), `context_tokens_threshold` 120000, `context_repeat_tokens` 30000, `session_list_hours` 2, `usage_fetch_timeout_seconds` 2.
- Toast: `powershell.exe` 5.1, AUMID `{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe`, texto por variável de ambiente.
- Comentários e mensagens em português, no estilo do arquivo; `py -m pyflakes claude_usage_guard.py` limpo ao fim de cada tarefa.
- **Git:** a pasta não é repositório. Se o usuário aprovar `git init` antes da execução, faça o commit indicado ao fim de cada tarefa; senão, pule os passos de commit.
- Testes: `py -m pytest tests -q` a partir de `F:\Projetos\ClaudeCodeSessionLimits`.

## Review Focus

1. **Caminho do `.exe` com espaços ou acentos** (ex.: `C:\Users\José\Meus Apps\...`): o comando registrado no `settings.json` precisa rodar no shell dos hooks → teste na Task 5.
2. **`settings.json` com BOM UTF-8 ou CRLF** (editado no Bloco de Notas): instalar deve funcionar e não corromper o arquivo → teste na Task 7.
3. **Endpoint de uso pendurado** (rede lenta): o hook tem de devolver em ~`usage_fetch_timeout_seconds` sem nota, bem antes do corte de 5 s do Claude Code → teste na Task 5.
4. **Resposta do endpoint sem `seven_day` ou sem `five_hour`**: o nível sai da janela que existir, sem exceção → teste na Task 2.
5. **Pasta do projeto com acentos** (`F:\Projetos\Açúcar`): estado gravado e janela exibem o nome certo → teste na Task 8.

---

### Task 1: Configuração `desktop:`

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (dict de padrões perto da linha 270; `validate_config` ~474)
- Modify: `ClaudeCodeSessionLimits/config.yaml` (seção nova no fim)
- Create: `tests/conftest.py`, `tests/test_desktop_config.py`

**Interfaces:**
- Produces: `cfg["desktop"]` com as chaves `enabled, attention_session, attention_weekly, high_session, high_weekly, critical_session, critical_weekly, context_tokens_threshold, context_repeat_tokens, toast, session_list_hours, usage_fetch_timeout_seconds`.
- Produces (testes): fixture `cug` (módulo carregado via `importlib` de `ClaudeCodeSessionLimits/claude_usage_guard.py`, registrado em `sys.modules["cug"]`) e fixture `state_dir(tmp_path, monkeypatch, cug)` que aponta `cug.STATE_DIR`, `cug.INSTANCES_DIR`, `cug.ACTIONS_LOG` e `cug.GUI_PID_FILE` para `tmp_path` e devolve o caminho.

- [ ] **Step 1: Escrever os testes**

```python
def test_desktop_defaults(cug):
    cfg, _ = cug.load_config(None)
    d = cfg["desktop"]
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
    assert any("desktop" in e for e in cug.validate_config(cfg))

def test_desktop_threshold_out_of_range_rejected(cug):
    cfg, _ = cug.load_config(None)
    cfg["desktop"]["critical_weekly"] = 120
    assert any("desktop" in e for e in cug.validate_config(cfg))
```

- [ ] **Step 2: Rodar e ver falhar** — `py -m pytest tests/test_desktop_config.py -q` → FAIL (`KeyError: 'desktop'`).
- [ ] **Step 3: Implementar** — acrescentar `"desktop": {...}` ao dict de padrões com os valores da Global Constraints; em `validate_config`, para `session` e `weekly`, exigir 0–100 e `attention ≤ high ≤ critical`, com mensagens começando por `desktop.`; copiar a seção da spec (§3, com os comentários) para o `config.yaml`.
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → 4 passed; `py ClaudeCodeSessionLimits/claude_usage_guard.py check-config` mostra a seção `desktop`.
- [ ] **Step 5: Commit** — `feat(desktop): configuração e validação da seção desktop`

---

### Task 2: Nível de cota e textos das notas

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (seção nova "Sessões do Desktop", depois de `decide()`)
- Create: `tests/test_desktop_levels.py`

**Interfaces:**
- Produces: `DESKTOP_LEVELS = ("normal", "attention", "high", "critical")`
- Produces: `quota_level(cfg, snap: Optional[UsageSnapshot]) -> tuple[str, Optional[str]]` — `(nível, janela)` com janela `"five_hour"`/`"seven_day"` que definiu o nível (empate: `five_hour`); `("normal", None)` sem dados.
- Produces: `level_note(level: str, window: Optional[str], pct: Optional[float], resets_in: Optional[float]) -> str` e `context_note(tokens: int) -> str` — texto exato da spec §4; `"Cota 5h"` para `five_hour`, `"Cota semanal"` para `seven_day`; `%` sem casas (`f"{pct:.0f}%"`); reinício via `_fmt_duration`; tokens como `f"{tokens // 1000}k"`.

- [ ] **Step 1: Escrever os testes**

```python
import datetime as dt, time

def snap(cug, s5=None, s7=None, resets_in=3600):
    r = dt.datetime.fromtimestamp(time.time() + resets_in, dt.timezone.utc).isoformat()
    data = {}
    if s5 is not None: data["five_hour"] = {"utilization": s5, "resets_at": r}
    if s7 is not None: data["seven_day"] = {"utilization": s7, "resets_at": r}
    return cug.UsageSnapshot.from_api(data, time.time())

def test_levels(cug):
    cfg, _ = cug.load_config(None)
    assert cug.quota_level(cfg, snap(cug, 10, 10)) == ("normal", None)
    assert cug.quota_level(cfg, snap(cug, 60, 10)) == ("attention", "five_hour")
    assert cug.quota_level(cfg, snap(cug, 50, 86)) == ("high", "seven_day")
    assert cug.quota_level(cfg, snap(cug, 92, 96)) == ("critical", "five_hour")
    assert cug.quota_level(cfg, None) == ("normal", None)

def test_missing_window(cug):                      # Review Focus 4
    cfg, _ = cug.load_config(None)
    assert cug.quota_level(cfg, snap(cug, s7=90)) == ("high", "seven_day")
    assert cug.quota_level(cfg, snap(cug, s5=93)) == ("critical", "five_hour")

def test_note_texts(cug):
    assert cug.level_note("attention", "five_hour", 64, 2 * 3600 + 600) == (
        "[usage-guard] Cota 5h em 64% (reinicia em 2h10m). Modo econômico: respostas diretas, delegue buscas "
        "e leituras longas a subagentes com model haiku, evite reler arquivos grandes. Detalhes: skill economia-de-cota.")
    assert cug.level_note("critical", "seven_day", 93, 1500).startswith("[usage-guard] Cota semanal em 93% (reinicia em 25m).")
    assert cug.level_note("normal", "five_hour", 8, 0) == "[usage-guard] Cota normalizada (5h em 8%). Pode trabalhar normalmente."
    assert cug.context_note(132_400) == ("[usage-guard] Contexto com 132k tokens. Ao terminar a tarefa atual, sugira ao "
                                         "usuário /compact (mesmo assunto) ou /clear com resumo de passagem (assunto novo).")
```

- [ ] **Step 2: Rodar e ver falhar** — `py -m pytest tests/test_desktop_levels.py -q` → FAIL (`AttributeError: quota_level`).
- [ ] **Step 3: Implementar** as três funções e a constante. Textos `high`/`critical` exatamente como na spec §4 (com o prefixo e o trecho `(reinicia em …)` montados como no `attention`). Nota de normalização: usa a janela de 5h quando existir, senão a de 7d ("semanal em X%").
- [ ] **Step 4: Rodar e ver passar** — 3 passed.
- [ ] **Step 5: Commit** — `feat(desktop): níveis de cota e textos das notas`

---

### Task 3: `advise()` e estado da sessão

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (mesma seção da Task 2)
- Create: `tests/test_desktop_advise.py`

**Interfaces:**
- Consumes: `quota_level`, `level_note`, `context_note` (Task 2); `cfg["desktop"]` (Task 1).
- Produces:
  - `@dataclasses.dataclass class DesktopSessionState` com os campos da spec §5 (`session_id: str`, `cwd: str = ""`, `transcript_path: str = ""`, `updated_at: float = 0.0`, `context_tokens: Optional[int] = None`, `context_measured_at: float = 0.0`, `context_noted_at: Optional[int] = None`, `last_level: Optional[str] = None`, `last_note: Optional[str] = None`, `last_note_at: float = 0.0`, `context_toast_done: bool = False`), mais `to_json() -> dict` e `@classmethod from_json(d: dict) -> DesktopSessionState` (ignora chaves desconhecidas).
  - `@dataclasses.dataclass class ToastRequest: key: str; title: str; message: str` — `key` = `f"{janela}:{reset_key}:{nível}"` para cota (`reset_key` = `resets_at` arredondado à hora, em epoch-hora) e `f"context:{session_id}"` para contexto.
  - `advise(cfg, snap: Optional[UsageSnapshot], state: DesktopSessionState, event: str, source: Optional[str], now: float) -> tuple[list[str], list[ToastRequest], DesktopSessionState]` — **pura**: devolve notas (cada uma uma linha), pedidos de toast e um estado novo (não altera o recebido). `snap` mais velho que `cfg["max_stale_seconds"]` conta como sem dados.

- [ ] **Step 1: Escrever os testes** (reusar o helper `snap` da Task 2 copiando-o para `tests/conftest.py` como fixture `make_snap`)

```python
def test_session_start_high_gives_note_and_sets_level(cug, make_snap):
    cfg, _ = cug.load_config(None)
    st = cug.DesktopSessionState("s1")
    notes, toasts, st2 = cug.advise(cfg, make_snap(83, 10), st, "SessionStart", "startup", 1000.0)
    assert len(notes) == 1 and notes[0].startswith("[usage-guard] Cota 5h em 83% (reinicia em ")
    assert st2.last_level == "high" and st.last_level is None
    assert [t.key.split(":")[-1] for t in toasts] == ["high"]

def test_same_level_no_repeat(cug, make_snap):
    # UserPromptSubmit com last_level == "high" e cota em 85% → notes == [] e toasts == []

def test_level_down_to_normal_gives_normalization(cug, make_snap):
    # last_level "high", cota 5h 8% → notes == ["[usage-guard] Cota normalizada (5h em 8%). Pode trabalhar normalmente."]

def test_no_data_silence(cug):
    # snap None e snap velho (fetched_at = now - max_stale - 1) → ([], [], estado com last_level inalterado)

def test_context_threshold_and_repeat(cug, make_snap):
    # cota normal; context_tokens 125_000 → 1 nota de contexto, context_noted_at == 125_000, 1 toast key "context:s1"
    # depois context_tokens 150_000 → nada (< +30k); 155_000 → nova nota e nenhum toast (context_toast_done)

def test_level_and_context_together(cug, make_snap):
    # last_level "normal", cota 64%, contexto 130k → notes == [nota attention, nota contexto] nessa ordem

def test_clear_resets_context(cug, make_snap):
    # SessionStart source "clear" com context_tokens 130_000 e context_noted_at 130_000 → st2.context_tokens is None and st2.context_noted_at is None

def test_missing_state_treated_as_session_start(cug, make_snap):
    # UserPromptSubmit com last_level None e cota 64% → nota attention (comporta-se como SessionStart)

def test_weekly_drives_note(cug, make_snap):
    # cota 5h 10%, 7d 90% → nota começa com "[usage-guard] Cota semanal em 90%"; toast key começa com "seven_day:"

def test_state_roundtrip(cug):
    st = cug.DesktopSessionState("s1", cwd="F:/Projetos/Açúcar", context_tokens=5)
    assert cug.DesktopSessionState.from_json({**st.to_json(), "extra": 1}) == st
```

(Onde o comentário descreve o teste, escreva o assert exato que ele indica.)

- [ ] **Step 2: Rodar e ver falhar** — `py -m pytest tests/test_desktop_advise.py -q` → FAIL.
- [ ] **Step 3: Implementar** `DesktopSessionState`, `ToastRequest`, `advise` seguindo a tabela da spec §4. Usar `dataclasses.replace` para o estado novo. `Stop` não gera nota nem toast (só a Task 5 atualiza o contexto antes de chamar `advise`).
- [ ] **Step 4: Rodar e ver passar** — todos passam; `py -m pytest tests -q` também.
- [ ] **Step 5: Commit** — `feat(desktop): advise() e estado da sessão`

---

### Task 4: Toast do Windows

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (`desktop_notify` ~710 e função nova ao lado)
- Create: `tests/test_toast.py`

**Interfaces:**
- Produces: `notify_toast(title: str, message: str) -> bool` — lança o PowerShell e devolve `True` se o processo foi criado; nunca levanta exceção. Fora do Windows, delega ao ramo atual de macOS/Linux do `desktop_notify`.
- `desktop_notify(cfg, title, message)` continua com a mesma assinatura e passa a chamar `notify_toast` no Windows.

- [ ] **Step 1: Escrever os testes** (com `monkeypatch.setattr(cug.subprocess, "Popen", fake)` gravando args/kwargs)

```python
def test_toast_command_and_env(cug, monkeypatch):
    calls = []
    monkeypatch.setattr(cug, "IS_WINDOWS", True)
    monkeypatch.setattr(cug.subprocess, "Popen", lambda *a, **k: calls.append((a, k)) or object())
    assert cug.notify_toast("Claude Usage Guard", 'Cota 5h em 83% "aspas" $x') is True
    (args,), kw = calls[0]
    assert args[0] == "powershell" and "-NoProfile" in args
    script = args[-1]
    assert "ToastNotificationManager" in script and "1AC14E77-02E7-4E5D-B744-2EB1AE5198B7" in script
    assert "83%" not in script                     # texto só pela env
    assert kw["env"]["CUG_NOTIFY_MSG"] == 'Cota 5h em 83% "aspas" $x'
    assert kw["creationflags"] & 0x01000000        # CREATE_BREAKAWAY_FROM_JOB

def test_toast_retries_without_breakaway(cug, monkeypatch):
    # 1ª chamada levanta OSError → 2ª sem 0x01000000; retorna True

def test_toast_never_raises(cug, monkeypatch):
    # Popen sempre levanta OSError → notify_toast(...) is False
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Script PowerShell fixo: carrega `Windows.UI.Notifications.ToastNotificationManager` e `Windows.Data.Xml.Dom.XmlDocument` (`ContentType = WindowsRuntime`), monta `ToastGeneric` com dois `<text>` preenchidos por `CreateTextNode($env:CUG_NOTIFY_TITLE)`/`($env:CUG_NOTIFY_MSG)` (nunca concatenando o texto no XML), mostra com o AUMID da Global Constraints; no `catch`, o balão `NotifyIcon` atual (ícone `$env:CUG_NOTIFY_ICON`) + `Start-Sleep 7`. Flags: `DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB` (`0x00000008 | 0x08000000 | 0x01000000`), repetindo sem o último em `OSError`.
- [ ] **Step 4: Rodar e ver passar; verificação manual:** `py -c "...; cug.notify_toast('Claude Usage Guard', 'teste da Task 4')"` → o usuário confirma que o toast apareceu.
- [ ] **Step 5: Commit** — `feat: notificações por toast do Windows 11`

---

### Task 5: Comando `desktop-hook`

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (`hook_command` ~1619, `build_parser`, `main`, seção Desktop)
- Create: `tests/test_desktop_hook.py`, `tests/fixtures/hook_session_start.json`, `hook_user_prompt.json`, `hook_stop.json` (formatos do spike: chaves `cwd, hook_event_name, session_id, source, transcript_path` / `prompt, prompt_id, permission_mode` / `last_assistant_message, stop_hook_active, effort`)

**Interfaces:**
- Consumes: `advise`, `DesktopSessionState`, `ToastRequest` (Task 3); `notify_toast` (Task 4); `read_context_tokens`, `UsageClient`, `atomic_write_json`, `read_json`, `file_lock` (existentes).
- Produces:
  - `hook_command(parts=None, windows=IS_WINDOWS, sub: str = "hook") -> str` (novo parâmetro `sub`; chamadas atuais inalteradas).
  - `desktop_dir() -> Path` (= `STATE_DIR / "desktop"`), `desktop_state_path(session_id: str) -> Path` (valida `[0-9A-Za-z-]{8,80}`, senão `GuardError`).
  - `load_snapshot_for_hook(cfg) -> Optional[UsageSnapshot]` — cache se idade < `poll_interval_seconds`; senão `UsageClient(timeout=cfg["desktop"]["usage_fetch_timeout_seconds"], retries=1).get(...)`; em erro, `UsageClient().cached()` se idade ≤ `max_stale_seconds`; senão `None`.
  - `cmd_desktop_hook(args) -> int` e subcomando `desktop-hook` (oculto no `--help`). Em `main`, caminho rápido antes de `repair_windows_state_acl()`: carrega config (`args.config`), logging só para arquivo, chama `cmd_desktop_hook`; qualquer exceção → `log.exception` e `return 0`.
  - Toasts filtrados por `desktop_dir() / "alerts.json"` (`{key: ts}`) sob `file_lock(desktop_dir() / "alerts.lock", timeout=2)`; chaves com mais de 8 dias são descartadas.

- [ ] **Step 1: Escrever os testes** (via `subprocess.run([sys.executable, GUARD_PY, "desktop-hook"], input=json, env={..., "CUG_STATE_DIR": tmp, "CUG_USAGE_URL": "http://127.0.0.1:9/"} )`, com cache falso gravado em `tmp/usage_cache.json` no formato `{"snapshot": snap.to_json(), "cooldown_until": 0}`)

```python
def test_session_start_high_outputs_note(...):
    # cache 5h=83% → returncode 0; json.loads(stdout) == {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <começa com "[usage-guard] Cota 5h em 83%">}}
    # tmp/desktop/<session_id>.json existe com last_level "high"; tmp/desktop/alerts.json tem 1 chave terminando em ":high"

def test_normal_outputs_nothing(...):            # cache 5h=10% → stdout == "" e returncode 0

def test_stop_measures_context_no_output(...):
    # transcript falso com uma linha assistant usage input 100_000 + cache_read 30_000 → stdout == ""; estado.context_tokens == 130_000

def test_prompt_after_stop_gives_context_note(...):   # depois do teste acima, UserPromptSubmit → additionalContext contém "Contexto com 130k tokens"

def test_toast_not_repeated_across_sessions(...):     # duas sessões diferentes em high na mesma janela → alerts.json com 1 chave de cota

def test_garbage_input_is_silent(...):           # stdin "não é json" e session_id "../x" → returncode 0, stdout ""

def test_hung_endpoint_returns_fast(...):        # Review Focus 3: sem cache; CUG_USAGE_URL → servidor local (thread) que dorme 10 s → returncode 0, stdout "", tempo < 4 s

def test_fast_with_fresh_cache(...):             # cache fresco: 5 execuções, mediana < 1.0 s

def test_desktop_hook_command_with_spaces_and_accents(cug):   # Review Focus 1
    cmd = cug.hook_command([r"C:\Users\José\Meus Apps\claude_usage_guard.exe"], windows=True, sub="desktop-hook")
    assert cmd == '"C:/Users/José/Meus Apps/claude_usage_guard.exe" desktop-hook'
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Fluxo do `cmd_desktop_hook`: ler stdin (até 2 MB, UTF-8 com `replace`) → JSON → validar `session_id` → carregar estado (ou `DesktopSessionState(session_id)`) → atualizar `cwd`/`transcript_path`/`updated_at` → em `Stop`, `read_context_tokens` e grava em `context_tokens`/`context_measured_at` → `snap = load_snapshot_for_hook(cfg)` (no `Stop`, pular a rede: só cache) → `advise(...)` → gravar estado → filtrar toasts por `alerts.json` e chamar `notify_toast` se `cfg["desktop"]["toast"]` e `cfg["notifications"]["desktop"]` → se houver notas e o evento for `SessionStart`/`UserPromptSubmit`, imprimir o JSON com `"\n".join(notes)`.
- [ ] **Step 4: Rodar e ver passar** — `py -m pytest tests -q` todo verde; pyflakes limpo.
- [ ] **Step 5: Commit** — `feat(desktop): comando desktop-hook`

---

### Task 6: Skill `economia-de-cota`

**Files:**
- Create: `ClaudeCodeSessionLimits/assets/skills/economia-de-cota/SKILL.md`
- Modify: `ClaudeCodeSessionLimits/build_exe.bat` (`--add-data "assets\skills;assets\skills"`)
- Create: `tests/test_skill.py`

**Interfaces:**
- Produces: `asset_path("skills/economia-de-cota/SKILL.md")` encontra o arquivo (no `.py` e no `.exe`).

- [ ] **Step 1: Escrever o teste** — o arquivo existe via `cug.asset_path(...)`; o frontmatter tem `name: economia-de-cota` e a `description` exata da spec §7; o corpo tem os 6 títulos de seção da spec §7 (`## O que gasta cota`, `## O que fazer em cada nível`, `## Modelo dos subagentes`, `## /compact ou /clear`, `## Como sugerir ao usuário`, `## Limites`); contém o modelo de `HANDOFF.md` com os itens objetivo, feito, falta, arquivos, decisões, próximos passos; tem ≤ 160 linhas.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Escrever o `SKILL.md`** com o conteúdo da spec §7 (≈120 linhas, português, frases de ação; as notas `[usage-guard]` como gatilho no início).
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `feat(desktop): skill economia-de-cota`

---

### Task 7: `install-desktop` / `uninstall-desktop` e `check-config`

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (seção Desktop, `restore_default_model` ~1700, `cmd_check_config`, `build_parser`, handlers do `main`)
- Create: `tests/test_desktop_install.py`, `tests/fixtures/settings_real_like.json` (cópia anonimizada do `settings.json` do usuário: `permissions`, `model`, hooks `SessionStart` com `gsd-check-update.js` etc.)

**Interfaces:**
- Consumes: `hook_command(sub="desktop-hook")` (Task 5), `asset_path` (Task 6), `claude_config_dir()`.
- Produces:
  - `read_settings_json(path) -> tuple[dict, str]` (lê com `utf-8-sig`, devolve dados + texto original) e `write_settings_json(path, data, original_text) -> None` (indentação 2, `ensure_ascii=False`, preserva quebra final e o estilo `\r\n` se o original usava; grava atômico) — `restore_default_model` passa a usar `write_settings_json`.
  - `is_guard_desktop_hook(hook: dict) -> bool` (comando contém `desktop-hook` e `claude_usage_guard`).
  - `merge_desktop_hooks(settings: dict, command: str) -> dict` e `strip_desktop_hooks(settings: dict) -> dict` — puras, eventos `SessionStart`, `UserPromptSubmit`, `Stop`, entrada `{"hooks": [{"type": "command", "command": command, "timeout": 5}]}`; `strip` remove listas de evento que ficarem vazias e o dict `hooks` se ficar vazio.
  - `cmd_install_desktop(cfg, args)` (`--force`) e `cmd_uninstall_desktop(cfg, args)`; `desktop_hooks_status() -> tuple[bool, bool]` (`instalado`, `exe_existe`) usado pelo `check-config`.
  - Atalho: `start_menu_shortcut_path() -> Path` (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Claude Usage Guard.lnk`), criado/removido via `powershell` + `WScript.Shell` (alvo = `self_command()[0]`, argumentos = resto + `gui`).

- [ ] **Step 1: Escrever os testes** (com `monkeypatch.setenv("CLAUDE_CONFIG_DIR", tmp)` e `monkeypatch.setattr(cug, "start_menu_shortcut_path", lambda: tmp / "x.lnk")` + Popen/run falsos para o atalho)

```python
def test_merge_is_idempotent_and_keeps_user_hooks(cug, fixture_settings):
    once = cug.merge_desktop_hooks(fixture_settings, "G desktop-hook")
    twice = cug.merge_desktop_hooks(once, "G desktop-hook")
    assert once == twice
    assert [h for h in once["hooks"]["SessionStart"] if not any(cug.is_guard_desktop_hook(x) for x in h["hooks"])] \
           == fixture_settings["hooks"]["SessionStart"]          # hooks do usuário intactos e na ordem

def test_strip_restores_original(cug, fixture_settings):
    assert cug.strip_desktop_hooks(cug.merge_desktop_hooks(fixture_settings, "G desktop-hook")) == fixture_settings

def test_install_uninstall_roundtrip(cug, tmp_path, ...):
    # install-desktop → settings tem os 3 eventos do guard, existe settings.json.bak-*, skill copiada
    # uninstall-desktop → json.loads(settings) == original; skill removida

def test_install_aborts_on_invalid_json(...):    # settings "{ inválido" → código 1, arquivo byte a byte igual, nenhum backup

def test_install_handles_bom_and_crlf(...):       # Review Focus 2: original com BOM + CRLF → instala; o novo arquivo é JSON válido (utf-8-sig), usa CRLF, mantém os hooks do usuário

def test_user_modified_skill_kept_without_force(...):  # skill diferente já instalada → mantida + aviso; com --force → substituída e backup .bak-* criado

def test_check_config_reports_moved_exe(...):     # settings com hook desktop-hook apontando para exe inexistente → desktop_hooks_status() == (True, False)
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** seguindo a spec §8 (passos 1–7 do install; uninstall). O `install` imprime: caminho do `settings.json`, backup, skill, atalho e "abra uma sessão nova no Desktop para ativar".
- [ ] **Step 4: Rodar e ver passar** — `py -m pytest tests -q` verde; pyflakes limpo.
- [ ] **Step 5: Commit** — `feat(desktop): instalador reversível dos hooks e da skill`

---

### Task 8: Janela — sessões do Desktop, faixa de alerta e console

**Files:**
- Modify: `ClaudeCodeSessionLimits/claude_usage_guard.py` (`DashboardData` ~2160, `GuardWindow.draw` ~2283, `cmd_gui` ~2507)
- Modify: `_e2e/gui_snapshot.py`, `_e2e/gui_checks.py` (nova forma de `DashboardData`)
- Create: `tests/test_gui_desktop.py`

**Interfaces:**
- Consumes: `DesktopSessionState.from_json`, `desktop_dir()` (Tasks 3 e 5), `quota_level` (Task 2).
- Produces:
  - `list_desktop_sessions(hours: float, now: Optional[float] = None) -> list[DesktopSessionState]` — estados atualizados nas últimas `hours` horas, mais recentes primeiro; apaga arquivos com mais de 7 dias.
  - `DashboardData` passa a ter 5 itens: `(snap, err, instances, actions, desktop_sessions)`; `GuardWindow.draw(snap, err, instances, actions, desktop=None, now=None)`.
  - `_draw_desktop_sessions(sessions, now)` (título "Sessões do Desktop"; linha: nome da pasta, `contexto Nk tokens`, último nível, `há X`) e `_draw_banner(level, window, snap, now)` (só `high` amarelo / `critical` vermelho; texto `"Cota 5h alta: 83% · reinicia em 1h05m"` / `"Cota semanal crítica: …"`).
  - Em `cmd_gui`: se `getattr(sys, "frozen", False)` e `kernel32.GetConsoleProcessList` indicar 1 processo, `kernel32.FreeConsole()`.

- [ ] **Step 1: Escrever os testes** (criam `GuardWindow` com dados falsos, chamam `draw`, percorrem os widgets e coletam os textos de `Label`)

```python
def test_desktop_section_lists_recent_sessions(cug, state_dir):   # inclui Review Focus 5
    # grava 2 estados: cwd "F:/Projetos/Açúcar" atualizado há 10 min (context 84_300, last_level "attention") e outro há 3 h
    # textos contêm "Sessões do Desktop", "Açúcar", "contexto 84k tokens"; não contêm a sessão de 3 h

def test_old_state_files_deleted(cug, state_dir):  # arquivo com mtime de 8 dias some depois de list_desktop_sessions(2)

def test_banner_only_when_high_or_critical(cug, make_snap):
    # 5h 83% → algum texto começa com "Cota 5h alta: 83%"; 5h 64% → nenhum texto começa com "Cota "
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar**; ajustar `cmd_gui` (`lambda: (*monitor.latest(), list_instances(), recent_actions(), list_desktop_sessions(cfg["desktop"]["session_list_hours"]))`) e os dois scripts de `_e2e`.
- [ ] **Step 4: Rodar e ver passar** — `py -m pytest tests -q`; `py -X utf8 _e2e/gui_checks.py ClaudeCodeSessionLimits/claude_usage_guard.py` → TUDO OK; `py -X utf8 _e2e/gui_snapshot.py ClaudeCodeSessionLimits/claude_usage_guard.py` (com uma sessão do Desktop e faixa `high` nos dados falsos) → conferir `gui_snapshot.png`.
- [ ] **Step 5: Commit** — `feat(gui): sessões do Desktop e faixa de alerta`

---

### Task 9: Build, sessão real do Desktop e documentação

**Files:**
- Modify: `CONTEXTO.md`, `ClaudeCodeSessionLimits/LEIA-ME.txt`, `ClaudeCodeSessionLimits/claude_usage_guard.py` (`__version__ = "1.3.0"` e docstring do topo: modo Desktop)
- Create (temporário, apagado no fim): `_e2e/proj/.claude/settings.json`, `_e2e/desktop_test_config.yaml`

- [ ] **Step 1: Build** — `cmd /c ClaudeCodeSessionLimits\build_exe.bat` → `dist\claude_usage_guard\claude_usage_guard.exe --version` imprime `1.3.0`; `asset_path` da skill resolve dentro do `.exe` (`<exe> install-desktop --help` roda).
- [ ] **Step 2: Regressão** — `py -m pytest tests -q` verde; `py -X utf8 _e2e/driver.py <exe>` → `RESUMO: 17 / 17 ok`; `_e2e/gui_checks.py ... <exe>` → TUDO OK.
- [ ] **Step 3: Sessão real do Desktop** — `desktop_test_config.yaml` com `desktop.attention_session: 1` e `context_tokens_threshold: 1000`; `_e2e/proj/.claude/settings.json` com os 3 hooks `"<exe>" --config <yaml> desktop-hook`; abrir uma sessão nova do Desktop em `_e2e\proj` pedindo que ela cite qualquer texto `[usage-guard]` do contexto. Esperado: a sessão cita a nota attention; `desktop\<sessão>.json` existe; o usuário confirma o toast (cota ≥ 80% não é necessária: toast de contexto aparece no 2º prompt) e vê a sessão na janela (`<exe> gui`). Apagar os dois arquivos temporários.
- [ ] **Step 4: Documentar** — CONTEXTO.md: decisão 21 (modo Desktop: hooks + `advise` + skill + toast; resultados do spike; o que não dá), testes novos e como rodá-los, comandos `install-desktop`/`uninstall-desktop`; LEIA-ME.txt: seção "Usar com o Claude Desktop (aba Code)" com instalar, o que muda, desinstalar.
- [ ] **Step 5: Instalação de verdade (só com o OK do usuário)** — perguntar antes de rodar `<exe> install-desktop` no `~/.claude` real; depois mostrar o diff do `settings.json` (backup × novo).
- [ ] **Step 6: Commit** — `release: 1.3.0 com modo Desktop`
