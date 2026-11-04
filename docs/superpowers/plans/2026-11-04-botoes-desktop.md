# Botões da janela que mandam pedidos às sessões do Desktop: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** quatro botões por sessão na seção "Sessões do Desktop" da janela do guard (Compactar, Economizar
liga/desliga, Skills/MCPs, Pesquisar) que põem um pedido numa fila; o `desktop-hook` o entrega ao Claude no fim do
turno (`Stop` com `decision: block`) ou junto da próxima mensagem (`UserPromptSubmit`).

**Architecture:** tudo em `ClaudeCodeSessionLimits\claude_usage_guard.py` (arquivo único, só biblioteca padrão),
mais duas skills novas em `assets\skills\`. A fila fica em `desktop\pending\<sessão>.json` sob a trava
`desktop\pending.lock`; funções puras montam os textos e o estado entregue; o hook faz a E/S.

**Tech Stack:** Python 3.14 (Windows), pytest (só testes), tkinter, PyInstaller (`build_exe.bat`).

**Spec:** `docs/superpowers/specs/2026-11-04-botoes-desktop-design.md`

## Global Constraints

- Código de produto só com biblioteca padrão; pytest só em `tests\`.
- `desktop-hook`: sai **sempre com código 0**, nada no stdout além do JSON, abaixo de 1 s no caso comum; o JSON é
  ASCII (`json.dumps(...).encode("ascii")`, como hoje).
- Textos injetados: exatamente os da seção 4 da spec (cabeçalho por canal + texto por ação, prefixo `[usage-guard]`).
- Ações e ordem de entrega: `("economy_on", "economy_off", "compact", "tools", "research")`.
- Prazos: trava da fila 1 s no hook e 2 s na janela; o hook só mexe na fila se começou há menos de 2,5 s
  (`HOOK_REQUEST_CUTOFF_SECONDS = 2.5`); prazo total do hook continua 4 s.
- Janela: 600x840, no máximo 4 cartões de sessão do Desktop, "entregue há" visível por 10 min.
- Versão nova: `1.4.0`.
- Comentários e mensagens em português, no estilo do arquivo; `py -m pyflakes claude_usage_guard.py` limpo ao fim de
  cada tarefa.
- **Git:** a pasta não é repositório. Pule os passos de commit, a menos que o usuário aprove `git init`.
- Testes: `py -m pytest tests -q` a partir de `F:\Projetos\ClaudeCodeSessionLimits` (hoje 73 passam).

## Review Focus

1. **Clique de cancelar que cruza com a entrega:** a janela mostra "✓ Compactar", o hook entrega e o usuário clica
   para cancelar; o clique não pode criar um pedido novo. `toggle_request(..., expect_pending=True)` não faz nada se
   o pedido já saiu → teste na Task 1.
2. **Primeira vez, sem as pastas `desktop\` e `desktop\pending\`:** o primeiro clique cria tudo e funciona → teste na
   Task 1.
3. **Estado gravado pela 1.3.0** (sem `economy_mode`, `last_event`, `delivered_*`): carrega com os padrões, e a
   janela e o hook seguem normais → teste na Task 2.
4. **`Stop` sem a chave `stop_hook_active`** (versão mais antiga do Claude Code): trata como falso e entrega →
   teste na Task 3.
5. **Trava da fila presa pela janela durante o hook:** a nota de cota sai, o pedido fica para o próximo hook e o hook
   termina em menos de 3 s → teste na Task 3.

---

### Task 1: fila de pedidos por sessão

**Files:**
- Modify: `ClaudeCodeSessionLimits\claude_usage_guard.py` (perto de `desktop_state_path`, ~linha 2943)
- Test: `tests\test_desktop_requests.py` (novo)

**Interfaces:**
- Consumes: `desktop_dir()`, `SESSION_ID_RE`, `file_lock(path, timeout)`, `atomic_write_json`, `read_json`, `GuardError`.
- Produces:
  - `PENDING_ACTIONS: tuple[str, ...] = ("economy_on", "economy_off", "compact", "tools", "research")`
  - `ACTION_LABELS: dict[str, str] = {"economy_on": "Economizar", "economy_off": "Desligar economia", "compact": "Compactar", "tools": "Skills/MCPs", "research": "Pesquisar"}`
  - `pending_dir() -> Path` (= `desktop_dir() / "pending"`), `pending_lock_path() -> Path` (= `desktop_dir() / "pending.lock"`)
  - `desktop_pending_path(session_id: str) -> Path` (`GuardError` se o id não casar com `SESSION_ID_RE`)
  - `read_pending(session_id: str) -> list[str]` (sem trava; na ordem de `PENDING_ACTIONS`; ausente ou corrompido → `[]`, corrompido com `log.warning`)
  - `toggle_request(session_id: str, action: str, now: float, expect_pending: Optional[bool] = None, lock_timeout: float = 2.0) -> bool` (devolve se a ação ficou pendente; `ValueError` para ação desconhecida; `GuardError` se a trava não vier)
  - `take_requests(session_id: str, lock_timeout: float = 1.0) -> list[str]` (retira tudo, apaga o arquivo)
  - `restore_requests(session_id: str, actions: list[str], now: float, lock_timeout: float = 1.0) -> None`
  - Formato do arquivo: `{"session_id": sid, "requests": [{"action": "compact", "at": 1730000000.0}]}`

- [ ] **Step 1: Escrever os testes que falham** (usam as fixtures `cug` e `state_dir`; `SID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"`)

```python
def test_toggle_adds_then_cancels(cug, state_dir):
    assert cug.toggle_request(SID, "compact", 1.0) is True
    assert cug.read_pending(SID) == ["compact"]
    assert cug.toggle_request(SID, "compact", 2.0) is False
    assert cug.read_pending(SID) == [] and not cug.desktop_pending_path(SID).exists()

def test_first_click_creates_dirs(cug, state_dir):            # Review Focus 2
    assert not (state_dir / "desktop").exists()
    assert cug.toggle_request(SID, "research", 1.0) is True
    data = json.loads(cug.desktop_pending_path(SID).read_text(encoding="utf-8"))
    assert data == {"session_id": SID, "requests": [{"action": "research", "at": 1.0}]}

def test_economy_pair_cancels_each_other(cug, state_dir):
    cug.toggle_request(SID, "economy_on", 1.0)
    cug.toggle_request(SID, "economy_off", 2.0)
    assert cug.read_pending(SID) == ["economy_off"]

def test_delivery_order_is_fixed(cug, state_dir):
    for a in ("research", "compact", "tools", "economy_on"):
        cug.toggle_request(SID, a, 1.0)
    assert cug.read_pending(SID) == ["economy_on", "compact", "tools", "research"]

def test_cancel_click_after_delivery_is_noop(cug, state_dir):   # Review Focus 1
    cug.toggle_request(SID, "compact", 1.0)
    assert cug.take_requests(SID) == ["compact"]
    assert cug.toggle_request(SID, "compact", 2.0, expect_pending=True) is False
    assert cug.read_pending(SID) == []

def test_take_empties_and_restore_does_not_duplicate(cug, state_dir):
    cug.toggle_request(SID, "compact", 1.0)
    cug.toggle_request(SID, "tools", 1.0)
    got = cug.take_requests(SID)
    assert got == ["compact", "tools"] and not cug.desktop_pending_path(SID).exists()
    cug.toggle_request(SID, "tools", 2.0)          # clicado de novo no meio
    cug.restore_requests(SID, got, 3.0)
    assert cug.read_pending(SID) == ["compact", "tools"]

def test_corrupted_file_reads_empty_and_is_rewritten(cug, state_dir):
    p = cug.desktop_pending_path(SID); p.parent.mkdir(parents=True); p.write_text("{oops", encoding="utf-8")
    assert cug.read_pending(SID) == [] and cug.take_requests(SID) == []
    assert cug.toggle_request(SID, "compact", 1.0) is True and cug.read_pending(SID) == ["compact"]

@pytest.mark.parametrize("bad", ["../x", r"..\..\aaaaaaaa", "", "a" * 81])
def test_invalid_session_id_rejected(cug, state_dir, bad):
    with pytest.raises(cug.GuardError):
        cug.toggle_request(bad, "compact", 1.0)

def test_unknown_action_rejected(cug, state_dir):
    with pytest.raises(ValueError):
        cug.toggle_request(SID, "rm -rf", 1.0)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_desktop_requests.py -q`
Expected: FAIL com `AttributeError: module 'cug' has no attribute 'toggle_request'`

- [ ] **Step 3: Implementar as funções da seção Interfaces**

Toda leitura e escrita com trava passa por `with file_lock(pending_lock_path(), timeout=lock_timeout)`. A fila vazia
apaga o arquivo (`unlink`, sem erro se não existir). `expect_pending` é comparado com o estado em disco dentro da
trava: se diferir, não muda nada e devolve o estado atual. `restore_requests` junta sem repetir ações e mantém a
ordem de `PENDING_ACTIONS`.

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests -q`
Expected: todos passam (73 antigos + os novos)

- [ ] **Step 5: pyflakes**

Run: `py -m pyflakes ClaudeCodeSessionLimits\claude_usage_guard.py` → sem saída.

---

### Task 2: textos dos pedidos, estado entregue e lembrete do modo econômico

**Files:**
- Modify: `ClaudeCodeSessionLimits\claude_usage_guard.py` (`DesktopSessionState` ~1296, `advise` ~1332, textos perto de `context_note` ~1279)
- Test: `tests\test_desktop_requests.py`, `tests\test_desktop_advise.py`

**Interfaces:**
- Consumes: `PENDING_ACTIONS`, `ACTION_LABELS` (Task 1), `NOTE_PREFIX`.
- Produces:
  - `DesktopSessionState` ganha `last_event: Optional[str] = None`, `economy_mode: bool = False`,
    `delivered_actions: list[str] = dataclasses.field(default_factory=list)`, `delivered_at: float = 0.0`,
    `delivered_via: Optional[str] = None`
  - `request_notes(actions: list[str], event: str) -> str` (uma linha por ação, `"\n"` entre elas; `event` é `"Stop"` ou `"UserPromptSubmit"`)
  - `ECONOMY_REMINDER: str = "[usage-guard] Modo econômico ligado pelo usuário nesta sessão (skill economia-de-cota, nível attention)."`
  - `apply_delivery(state: DesktopSessionState, actions: list[str], event: str, now: float) -> DesktopSessionState` (pura: `economy_mode`, `delivered_*`, `last_note`, `last_note_at`)
  - `advise(...)`: mesma assinatura; em `SessionStart` com `source` `clear` ou `compact` e `economy_mode` verdadeiro, acrescenta `ECONOMY_REMINDER` depois da nota de cota

Cabeçalhos e textos (copiar da seção 4 da spec, sem mudar uma vírgula):
- `Stop`: `[usage-guard] Pedido do usuário pelo botão "<rótulo>" do Claude Usage Guard (não é erro; faça agora): `
- `UserPromptSubmit`: `[usage-guard] Pedido do usuário pelo botão "<rótulo>" do Claude Usage Guard (faça antes do resto da mensagem dele): `
- O rótulo vem de `ACTION_LABELS`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# test_desktop_requests.py
def test_request_notes_by_channel(cug):
    stop = cug.request_notes(["compact", "research"], "Stop").split("\n")
    assert len(stop) == 2
    assert stop[0].startswith('[usage-guard] Pedido do usuário pelo botão "Compactar" do Claude Usage Guard '
                              '(não é erro; faça agora): grave HANDOFF.md')
    assert stop[1].startswith('[usage-guard] Pedido do usuário pelo botão "Pesquisar"')
    ups = cug.request_notes(["tools"], "UserPromptSubmit")
    assert "(faça antes do resto da mensagem dele): use a skill ferramentas-do-projeto" in ups
    assert json.dumps({"x": ups}).isascii()

def test_apply_delivery(cug):
    st = cug.apply_delivery(cug.DesktopSessionState(SID), ["economy_on", "compact"], "Stop", 50.0)
    assert (st.economy_mode, st.delivered_actions, st.delivered_at, st.delivered_via) == \
           (True, ["economy_on", "compact"], 50.0, "Stop")
    assert st.last_note.startswith("[usage-guard] Pedido") and st.last_note_at == 50.0
    assert cug.apply_delivery(st, ["economy_off"], "UserPromptSubmit", 60.0).economy_mode is False

def test_old_state_loads_with_defaults(cug):                    # Review Focus 3
    old = {"session_id": SID, "cwd": "F:/x", "updated_at": 1.0, "last_level": "high", "context_toast_done": True}
    st = cug.DesktopSessionState.from_json(old)
    assert (st.economy_mode, st.last_event, st.delivered_actions, st.delivered_via) == (False, None, [], None)

# test_desktop_advise.py
@pytest.mark.parametrize("source,economy,expected", [("compact", True, True), ("clear", True, True),
                                                     ("startup", True, False), ("resume", True, False),
                                                     ("compact", False, False)])
def test_economy_reminder_after_clear_or_compact(cug, make_snap, source, economy, expected):
    st = cug.DesktopSessionState("s1", economy_mode=economy)
    notes, _, _ = cug.advise(cfg_(cug), make_snap(10, 10), st, "SessionStart", source, NOW)
    assert (cug.ECONOMY_REMINDER in notes) is expected
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_desktop_requests.py tests/test_desktop_advise.py -q`
Expected: FAIL (`request_notes` inexistente; `economy_mode` argumento inesperado)

- [ ] **Step 3: Implementar** os campos, `request_notes`, `ECONOMY_REMINDER`, `apply_delivery` e o acréscimo em `advise`
  (o lembrete sai mesmo sem dados de cota; `last_note` segue a regra atual de "última nota").

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests -q` → todos passam.

- [ ] **Step 5: pyflakes** limpo.

---

### Task 3: entrega pelo `desktop-hook`

**Files:**
- Modify: `ClaudeCodeSessionLimits\claude_usage_guard.py` (`cmd_desktop_hook` ~3089, constantes ~2931)
- Test: `tests\test_desktop_hook.py`

**Interfaces:**
- Consumes: `take_requests`, `restore_requests`, `pending_lock_path` (Task 1); `request_notes`, `apply_delivery`, campos novos (Task 2).
- Produces: `HOOK_REQUEST_CUTOFF_SECONDS = 2.5`. Saída do `Stop` com pedidos: `{"decision": "block", "reason": "<request_notes(..., "Stop")>"}`.

Ordem dentro de `cmd_desktop_hook` (spec, seção 6): `started = time.monotonic()` no início; `state.last_event = event`;
contexto do `Stop`; cota; `advise`; **depois** pedidos (só em `UserPromptSubmit` e em `Stop` com
`data.get("stop_hook_active") is not True`, e só se `time.monotonic() - started < HOOK_REQUEST_CUTOFF_SECONDS`;
`GuardError`/`OSError` → `[]` com `log.warning`); `apply_delivery`; grava o estado; escreve o stdout. Se a escrita
levantar, chama `restore_requests` e relança para o tratamento atual do `run_desktop_hook`. No `UserPromptSubmit` o
`additionalContext` é `"\n".join(notas de cota + [request_notes(..., "UserPromptSubmit")])`.

- [ ] **Step 1: Escrever os testes que falham** (helpers existentes `hook_env`, `write_cache`, `run_hook`, `payload`; novo helper `queue(tmp_path, *actions)` que grava `tmp_path/"desktop"/"pending"/f"{SID}.json"` no formato da Task 1)

```python
def test_prompt_delivers_request_after_quota_note(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 83)
    queue(tmp_path, "compact")
    r, _ = run_hook(hook_env, payload("hook_user_prompt.json"))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].split("\n")
    assert ctx[0].startswith("[usage-guard] Cota 5h em 83%")
    assert ctx[1].startswith('[usage-guard] Pedido do usuário pelo botão "Compactar"')
    assert not (tmp_path / "desktop" / "pending" / f"{SID}.json").exists()
    st = json.loads((tmp_path / "desktop" / f"{SID}.json").read_text(encoding="utf-8"))
    assert (st["delivered_actions"], st["delivered_via"], st["last_event"]) == \
           (["compact"], "UserPromptSubmit", "UserPromptSubmit")

def test_stop_blocks_with_request(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    queue(tmp_path, "research")
    r, _ = run_hook(hook_env, payload("hook_stop.json"))
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and "pesquisar-otimizacoes" in out["reason"]
    assert "(não é erro; faça agora)" in out["reason"] and r.stdout.isascii()

def test_stop_hook_active_does_not_block(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    queue(tmp_path, "compact")
    r, _ = run_hook(hook_env, payload("hook_stop.json", stop_hook_active=True))
    assert (r.returncode, r.stdout) == (0, b"")
    assert (tmp_path / "desktop" / "pending" / f"{SID}.json").exists()

def test_stop_without_stop_hook_active_key_delivers(tmp_path, hook_env, make_snap):   # Review Focus 4
    write_cache(tmp_path, make_snap, 10)
    queue(tmp_path, "tools")
    data = payload("hook_stop.json"); del data["stop_hook_active"]
    assert json.loads(run_hook(hook_env, data)[0].stdout)["decision"] == "block"

def test_economy_reminder_after_compact(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    queue(tmp_path, "economy_on")
    run_hook(hook_env, payload("hook_user_prompt.json"))
    r, _ = run_hook(hook_env, payload("hook_session_start.json", source="compact"))
    assert "Modo econômico ligado pelo usuário" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

def test_corrupted_queue_keeps_quota_note(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 83)
    p = tmp_path / "desktop" / "pending" / f"{SID}.json"; p.parent.mkdir(parents=True); p.write_text("{oops")
    r, _ = run_hook(hook_env, payload("hook_user_prompt.json", session_id=SID))
    assert r.returncode == 0 and "Cota 5h em 83%" in r.stdout.decode()

def test_session_start_does_not_deliver(tmp_path, hook_env, make_snap):
    write_cache(tmp_path, make_snap, 10)
    queue(tmp_path, "compact")
    r, _ = run_hook(hook_env, payload("hook_session_start.json", source="clear"))
    assert r.stdout == b"" and (tmp_path / "desktop" / "pending" / f"{SID}.json").exists()

def test_locked_queue_keeps_note_and_request(cug, tmp_path, hook_env, make_snap):   # Review Focus 5
    write_cache(tmp_path, make_snap, 83)
    queue(tmp_path, "compact")
    with cug.file_lock(tmp_path / "desktop" / "pending.lock", timeout=2):
        r, took = run_hook(hook_env, payload("hook_user_prompt.json"))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Cota 5h em 83%" in ctx and "Pedido" not in ctx and took < 3
    assert (tmp_path / "desktop" / "pending" / f"{SID}.json").exists()
```

O teste antigo `test_stop_measures_context_then_prompt_gets_note` continua valendo como regressão do `Stop` sem pedido.

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_desktop_hook.py -q` → os novos falham (sem entrega).

- [ ] **Step 3: Implementar** a ordem descrita acima em `cmd_desktop_hook`.

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests -q` → todos passam; `test_fast_with_fresh_cache` continua abaixo de 1 s.

- [ ] **Step 5: pyflakes** limpo.

---

### Task 4: skills novas e instalação das três

**Files:**
- Create: `ClaudeCodeSessionLimits\assets\skills\ferramentas-do-projeto\SKILL.md`
- Create: `ClaudeCodeSessionLimits\assets\skills\pesquisar-otimizacoes\SKILL.md`
- Modify: `ClaudeCodeSessionLimits\assets\skills\economia-de-cota\SKILL.md` (seção nova `## Pedidos pelos botões do guard`, entre `## Como sugerir ao usuário` e `## Limites`)
- Modify: `ClaudeCodeSessionLimits\claude_usage_guard.py` (`SKILL_ASSET` ~3167, `cmd_install_desktop` ~3351-3364, `cmd_uninstall_desktop` ~3392-3401)
- Test: `tests\test_skill.py`, `tests\test_desktop_install.py`

**Interfaces:**
- Produces: `SKILL_NAMES: tuple[str, ...] = ("economia-de-cota", "ferramentas-do-projeto", "pesquisar-otimizacoes")`,
  `skill_asset(name: str) -> str` (= `f"skills/{name}/SKILL.md"`), `install_skill(name: str, force: bool) -> None` e
  `uninstall_skill(name: str) -> None` (as mesmas mensagens de hoje, com o nome da skill). `SKILL_ASSET` sai.

Conteúdo das skills: seção 5 da spec, em português, no máximo 120 linhas cada, frontmatter com `name:` e
`description:` em uma linha (a description começa com "Use quando o usuário pedir" e cita "[usage-guard]" e o
rótulo do botão).

- [ ] **Step 1: Escrever os testes que falham**

```python
# test_skill.py
NEW = {"ferramentas-do-projeto": ["haiku", "SearchPlugins", "tirar", ".claude/skills", "Claude Usage Guard"],
       "pesquisar-otimizacoes": ["sonnet", "OTIMIZACOES.md", "30 dias", "6 buscas", "400 palavras"]}

@pytest.mark.parametrize("name", list(NEW))
def test_new_skills(cug, name):
    text = cug.asset_path(f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
    head = text.split("---\n")[1]
    assert f"name: {name}\n" in head and "description: Use quando o usuário pedir" in head
    assert "[usage-guard]" in head
    assert all(k in text for k in NEW[name]) and len(text.splitlines()) <= 120

def test_economia_has_buttons_section(cug):
    text = _skill(cug)
    i = text.find("## Pedidos pelos botões do guard")
    assert text.find("## Como sugerir ao usuário") < i < text.find("## Limites")
    assert "/compact <" in text[i:] and "modo econômico desligado" in text[i:]

# test_desktop_install.py
def test_install_uninstall_all_skills(cug, claude_dir):
    cfg, _ = cug.load_config(None)
    assert cug.cmd_install_desktop(cfg, ns()) == 0
    for name in cug.SKILL_NAMES:
        dst = claude_dir / "skills" / name / "SKILL.md"
        assert dst.read_bytes() == cug.asset_path(cug.skill_asset(name)).read_bytes()
    edited = claude_dir / "skills" / "pesquisar-otimizacoes" / "SKILL.md"
    edited.write_text("minha", encoding="utf-8")
    assert cug.cmd_uninstall_desktop(cfg, ns()) == 0
    assert edited.read_text(encoding="utf-8") == "minha"
    assert not (claude_dir / "skills" / "ferramentas-do-projeto").exists()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_skill.py tests/test_desktop_install.py -q` → falham (arquivos e `SKILL_NAMES` inexistentes).

- [ ] **Step 3: Escrever as duas skills e a seção nova; trocar o código de skill do install/uninstall por um laço em `SKILL_NAMES`.**

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests -q` → todos passam (os testes antigos da `economia-de-cota` também, incluindo o limite de 160 linhas).

- [ ] **Step 5: pyflakes** limpo.

---

### Task 5: botões na janela

**Files:**
- Modify: `ClaudeCodeSessionLimits\claude_usage_guard.py` (`list_desktop_sessions` ~2417, `GuardWindow.__init__` geometria ~2499, `draw` ~2568, `_draw_desktop_sessions` ~2598)
- Test: `tests\test_gui_desktop.py`

**Interfaces:**
- Consumes: `read_pending`, `toggle_request`, `ACTION_LABELS`, `pending_dir` (Task 1); campos novos de `DesktopSessionState` (Task 2); `quota_level`.
- Produces:
  - `economy_button(pending: list[str], economy_mode: bool) -> tuple[str, str]` (rótulo, ação do clique):
    `economy_on` pendente → `("✓ Economizar", "economy_on")`; `economy_off` pendente → `("✓ Desligar economia", "economy_off")`;
    modo ligado → `("Economizar: ligado", "economy_off")`; senão `("Economizar", "economy_on")`
  - `desktop_status_line(pending: list[str], st: DesktopSessionState, now: float, critical: bool) -> Optional[str]`, com os textos da spec:
    - pendente e `st.last_event == "UserPromptSubmit"`: `"pendente: A, B · vai no fim do turno atual (ou com a sua próxima mensagem)"`
    - pendente e parado: `"pendente: A, B · vai junto com a sua próxima mensagem (até um 'ok' serve)"`
    - sem pendência e `now - st.delivered_at < 600`: `"entregue há 2m: A, B (fim do turno)"` (`delivered_via == "Stop"`) ou `"(sua mensagem)"`
    - `critical`: acrescenta `" · pesquisa e skills pausadas: cota crítica"` (ou só esse trecho, sem o separador inicial, se não houver outra parte)
    - nada a dizer → `None`. Os nomes A, B vêm de `ACTION_LABELS`, na ordem de `PENDING_ACTIONS`.
  - `GuardWindow._toggle_request(sid: str, action: str, expect_pending: bool) -> None`
  - `GuardWindow._draw_desktop_sessions(sessions, now, level)` (o `draw` passa o `level` de `quota_level`)

Regras da janela (spec, seção 3): ordem dos botões `Compactar`, economia, `Skills/MCPs`, `Pesquisar`; pendente vira
`"✓ <rótulo>"`; com `level == "critical"`, "Skills/MCPs" e "Pesquisar" ficam desabilitados, exceto se já pendentes
(habilitados só para cancelar); `desktop.enabled` falso → todos desabilitados e o rótulo da seção
`"modo Desktop desligado no config"`; até 4 cartões e depois `"+ N outras"`; geometria `600x840`. Rodapé:
`"<rótulo> pedido para #<sid[:8]>: <vai no fim do turno atual | vai com a sua próxima mensagem>"`,
`"<rótulo> cancelado para #<sid[:8]>"` ou, em vermelho, `"não deu para registrar o pedido (tente de novo): <motivo>"`.
`list_desktop_sessions` também apaga `pending\*.json` com mais de 7 dias.

- [ ] **Step 1: Escrever os testes que falham** (helper novo `_buttons(widget) -> list[tk.Button]`, recursivo como `_texts`)

```python
def test_status_line_texts(cug):
    st = cug.DesktopSessionState(SID, last_event="UserPromptSubmit")
    assert cug.desktop_status_line(["compact", "research"], st, 100.0, False) == \
        "pendente: Compactar, Pesquisar · vai no fim do turno atual (ou com a sua próxima mensagem)"
    st.last_event = "Stop"
    assert cug.desktop_status_line(["tools"], st, 100.0, False) == \
        "pendente: Skills/MCPs · vai junto com a sua próxima mensagem (até um 'ok' serve)"
    st2 = cug.DesktopSessionState(SID, delivered_actions=["compact"], delivered_at=1000.0, delivered_via="Stop")
    assert cug.desktop_status_line([], st2, 1120.0, False) == "entregue há 2m: Compactar (fim do turno)"
    assert cug.desktop_status_line([], st2, 1700.0, False) is None
    assert cug.desktop_status_line([], st2, 1700.0, True) == "pesquisa e skills pausadas: cota crítica"
    assert cug.desktop_status_line([], cug.DesktopSessionState(SID), 1120.0, False) is None

@pytest.mark.parametrize("pending,mode,expected", [
    (["economy_on"], False, ("✓ Economizar", "economy_on")),
    (["economy_off"], True, ("✓ Desligar economia", "economy_off")),
    ([], True, ("Economizar: ligado", "economy_off")),
    ([], False, ("Economizar", "economy_on"))])
def test_economy_button(cug, pending, mode, expected):
    assert cug.economy_button(pending, mode) == expected

def test_buttons_toggle_request(cug, state_dir, window):
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    window.draw(None, None, [], [], cug.list_desktop_sessions(2))
    btn = {b.cget("text"): b for b in _buttons(window.body)}
    assert {"Compactar", "Economizar", "Skills/MCPs", "Pesquisar"} <= set(btn)
    btn["Compactar"].invoke()
    assert cug.read_pending(SID) == ["compact"]
    btn = {b.cget("text"): b for b in _buttons(window.body)}
    assert "✓ Compactar" in btn and any(t.startswith("pendente: Compactar") for t in _texts(window.body))
    btn["✓ Compactar"].invoke()
    assert cug.read_pending(SID) == []

def test_critical_disables_research_and_tools(cug, state_dir, make_snap, window):
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    window.draw(make_snap(96, 10), None, [], [], cug.list_desktop_sessions(2))
    state = {b.cget("text"): str(b.cget("state")) for b in _buttons(window.body)}
    assert state["Pesquisar"] == state["Skills/MCPs"] == "disabled"
    assert state["Compactar"] == state["Economizar"] == "normal"

def test_desktop_disabled_turns_buttons_off(cug, state_dir, window):
    _write_state(cug, SID, 60, cwd="F:/Projetos/App")
    window.cfg["desktop"]["enabled"] = False
    try:
        window.draw(None, None, [], [], cug.list_desktop_sessions(2))
    finally:
        window.cfg["desktop"]["enabled"] = True
    assert all(str(b.cget("state")) == "disabled" for b in _buttons(window.body) if b.cget("text") != "Abrir log")
    assert any("modo Desktop desligado no config" in t for t in _texts(window.body))

def test_old_pending_files_deleted(cug, state_dir):
    cug.toggle_request(SID, "compact", 1.0)
    p = cug.desktop_pending_path(SID)
    t = time.time() - 8 * 86400
    os.utime(p, (t, t))
    cug.list_desktop_sessions(2)
    assert not p.exists()

def test_at_most_four_cards(cug, state_dir, window):
    for i in range(6):
        _write_state(cug, f"{i:08d}-aaaa", 60 + i, cwd=f"F:/P/p{i}")
    window.draw(None, None, [], [], cug.list_desktop_sessions(2))
    assert "+ 2 outras" in _texts(window.body)
    assert sum(1 for b in _buttons(window.body) if b.cget("text") == "Compactar") == 4
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_gui_desktop.py -q` → falham (sem botões nem funções).

- [ ] **Step 3: Implementar** `economy_button`, `desktop_status_line`, os botões, o rodapé, o limite de 4 cartões, a geometria e a limpeza de `pending\`.

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests -q` → todos passam.

- [ ] **Step 5: pyflakes** limpo.

---

### Task 6: versão, documentação, `.exe` e teste real no Desktop

**Files:**
- Modify: `ClaudeCodeSessionLimits\claude_usage_guard.py` (`__version__` linha 179 → `"1.4.0"`; documentação de uso no topo: os botões)
- Modify: `ClaudeCodeSessionLimits\LEIA-ME.txt` (seção curta sobre os botões e quando o pedido é entregue)
- Modify: `CONTEXTO.md` (versão 1.4.0, decisão 23, arquivos novos, testes, o que foi testado no Desktop)
- Modify: `_e2e\gui_checks.py` (checagem: clique em "Compactar" cria a fila e vira "✓ Compactar")

- [ ] **Step 1:** subir a versão e atualizar a documentação de uso no topo do arquivo e o `LEIA-ME.txt`.
- [ ] **Step 2:** `py -m pytest tests -q` → todos passam; `py -m pyflakes ClaudeCodeSessionLimits\claude_usage_guard.py` limpo.
- [ ] **Step 3:** pedir ao usuário que **feche a janela do guard**; rodar `ClaudeCodeSessionLimits\build_exe.bat` →
  `dist\claude_usage_guard\claude_usage_guard.exe --version` mostra `1.4.0` e as três skills estão em
  `dist\claude_usage_guard\_internal\assets\skills\`.
- [ ] **Step 4:** acrescentar a checagem ao `_e2e\gui_checks.py` e rodar com o `.py` e com o `.exe` → "TUDO OK".
- [ ] **Step 5:** instalar as skills novas com `dist\...\claude_usage_guard.exe install-desktop` (backup automático
  do `settings.json`; os hooks continuam os mesmos).
- [ ] **Step 6: Teste real, sessão parada.** Na sessão de teste do Desktop em `_e2e\proj`, gravar `economy_on` com
  `toggle_request(<id da sessão>, "economy_on", time.time())` e mandar uma mensagem curta à sessão → o Claude
  confirma o modo econômico; `desktop\<id>.json` tem `delivered_via == "UserPromptSubmit"`.
- [ ] **Step 7: Teste real, sessão trabalhando.** Mandar à sessão um pedido que demore (ex.: rodar
  `ping -n 20 127.0.0.1`), gravar `compact` enquanto ela trabalha → no fim do turno o Claude grava `HANDOFF.md` e
  devolve a linha `/compact ...`; `delivered_via == "Stop"`.
- [ ] **Step 8: Teste real pela janela.** O usuário abre a janela, clica em "Skills/MCPs" ou "Pesquisar" numa sessão
  e manda uma mensagem → o Claude usa a skill. Registrar o resultado.
- [ ] **Step 9:** atualizar o `CONTEXTO.md` (decisão 23: botões, entrega por `Stop`/`UserPromptSubmit`, retirada
  sob trava, skills novas; testes; o que foi verificado nos Steps 6 a 8) e apagar `HANDOFF.md`/`OTIMIZACOES.md`
  que os testes deixarem em `_e2e\proj`.
