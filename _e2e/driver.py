"""Teste ponta a ponta do `claude_usage_guard run` com o Claude Code REAL no
Windows. Abre o guard num ConPTY (como um terminal), digita como um usuário e
confere hooks.jsonl / status.json / actions.jsonl / transcript.

Uso: py driver.py <caminho do claude_usage_guard.exe>
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from winpty import PtyProcess

EXE = sys.argv[1]
# comando do guard: o .exe, ou "py claude_usage_guard.py -v" (argv[1:])
GUARD = sys.argv[1:]
HERE = Path(__file__).resolve().parent
PROJ = HERE / "proj"
PROJ.mkdir(exist_ok=True)
STATE = Path(os.environ["USERPROFILE"]) / ".claude-usage-guard"
INST = STATE / "instances"
ACTIONS = STATE / "actions.jsonl"
LOG = HERE / "pty_output.log"

ANSI = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[@-_]")
buf = []
lock = threading.Lock()
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'OK' if ok else 'FALHA'}] {name} {detail}", flush=True)


def screen_text():
    with lock:
        return ANSI.sub("", "".join(buf))


def reader(p):
    with open(LOG, "w", encoding="utf-8") as fh:
        while True:
            try:
                data = p.read(65536)
            except EOFError:
                break
            if not data:
                if not p.isalive():
                    break
                time.sleep(0.02)
                continue
            fh.write(data)
            fh.flush()
            with lock:
                buf.append(data)


def wait_for(pred, timeout, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def new_instance(before):
    now = {d.name for d in INST.iterdir()} if INST.is_dir() else set()
    new = now - before
    return INST / sorted(new)[0] if new else None


def hooks(idir):
    f = idir / "hooks.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def status(idir):
    try:
        return json.loads((idir / "status.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def actions_since(iid, t0):
    if not ACTIONS.exists():
        return []
    out = []
    for line in ACTIONS.read_text(encoding="utf-8").splitlines():
        try:
            a = json.loads(line)
        except ValueError:
            continue
        if a.get("instance") == iid and a.get("ts", 0) >= t0:
            out.append(a)
    return out


def type_slow(p, text, delay=0.03):
    for ch in text:
        p.write(ch)
        time.sleep(delay)


def user_prompts(transcript):
    out = []
    if not wait_for(lambda: Path(transcript).is_file(), 10):
        return ["<transcript não existe>"]
    for line in Path(transcript).read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "user":
            c = (o.get("message") or {}).get("content")
            if isinstance(c, str):
                out.append(c)
    return out


def count_events(idir, name, source=None):
    return sum(1 for h in hooks(idir) if h["event"] == name and (source is None or h.get("source") == source))


def main():
    before = {d.name for d in INST.iterdir()} if INST.is_dir() else set()
    # Sem as variáveis da sessão do app desktop que roda este teste: o claude
    # aninhado viraria "sessão filha" (sem transcript, outro ANTHROPIC_BASE_URL).
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("CLAUDE", "ANTHROPIC")) and k.upper() not in ("CLAUDECODE",)}
    env["CUG_COMPACT_CONTEXT_TOKENS_THRESHOLD"] = "1000"
    t0 = time.time()
    p = PtyProcess.spawn([*GUARD, "run", "--", "--model", "haiku", "--no-chrome"], cwd=str(PROJ), env=env, dimensions=(40, 140))
    threading.Thread(target=reader, args=(p,), daemon=True).start()

    idir = wait_for(lambda: new_instance(before), 30)
    check("instância criada", bool(idir), str(idir))
    if not idir:
        return
    iid = idir.name
    gui_pid = wait_for(gui_pid_alive, 20)
    check("o run abriu a janela gráfica (gui.pid vivo)", bool(gui_pid), str(gui_pid))

    # Diálogo "confia nesta pasta?" numa pasta nova
    if wait_for(lambda: "trust" in screen_text().lower(), 15):
        time.sleep(1)
        p.write("\r")
        print("  (aceitei o diálogo de confiança da pasta de teste)")

    ss = wait_for(lambda: count_events(idir, "SessionStart"), 40)
    check("hook SessionStart chegou (hooks funcionam)", bool(ss), json.dumps(hooks(idir)[:1], ensure_ascii=False))
    if not ss:
        print(screen_text()[-3000:])
        return
    time.sleep(3)

    # --- entrada: acentos, setas, colar -----------------------------------
    type_slow(p, "Responda apenas OK. Texto: açúcar ção abc")
    p.write("\x1b[D")  # ←
    time.sleep(0.1)
    p.write("\x1b[D")  # ←
    time.sleep(0.1)
    p.write("X")
    time.sleep(0.2)
    p.write("\x1b[F")  # End
    time.sleep(0.1)
    p.write(" \x1b[200~colado\x1b[201~")
    time.sleep(1.0)
    st = status(idir)
    p.write("\r")
    stop = wait_for(lambda: count_events(idir, "Stop"), 90)
    check("hook Stop após o turno", bool(stop))
    tr = next((h.get("transcript_path") for h in hooks(idir) if h.get("transcript_path")), None)
    if tr:
        prompts = user_prompts(tr)
        last = prompts[-1] if prompts else ""
        check("acentos/setas/colar chegaram ao Claude", "açúcar ção aXbc colado" in last, repr(last))

    # --- status ocioso + contexto ------------------------------------------
    ok = wait_for(lambda: status(idir).get("state") == "ocioso" and status(idir).get("context_tokens"), 30)
    st = status(idir)
    check("dashboard: estado ocioso + contexto", bool(ok), f"state={st.get('state')} ctx={st.get('context_tokens')}")

    # --- compact automático (limiar 1000 tokens) ----------------------------
    comp = wait_for(lambda: any(a["action"] == "compact" for a in actions_since(iid, t0)), 60)
    check("/compact injetado sozinho após o turno", bool(comp))
    if comp:
        done = wait_for(lambda: count_events(idir, "SessionStart", "compact"), 120)
        check("/compact executado pelo Claude Code (SessionStart source=compact)", bool(done))
        wait_for(lambda: status(idir).get("state") == "ocioso", 60)

    # --- signal clear -------------------------------------------------------
    t_sig = time.time()
    subprocess.run([*GUARD, "signal", "clear", "--instance", iid], capture_output=True)
    clr = wait_for(lambda: any(a["action"] == "clear" for a in actions_since(iid, t_sig)), 60)
    check("signal clear → /clear injetado", bool(clr))
    if clr:
        check("/clear executado (SessionStart source=clear)",
              bool(wait_for(lambda: count_events(idir, "SessionStart", "clear"), 30)))
    time.sleep(2)

    # --- prompt de permissão: o guard não pode digitar nada -----------------
    type_slow(p, "Use a ferramenta Write para criar o arquivo nota.txt contendo oi. Nao faca mais nada.")
    time.sleep(0.5)
    p.write("\r")
    perm = wait_for(lambda: any(h["event"] == "PreToolUse" for h in hooks(idir)[-5:]), 90)
    check("PreToolUse chegou (pedido de permissão)", bool(perm))
    time.sleep(3)
    t_perm = time.time()
    subprocess.run([*GUARD, "signal", "clear", "--instance", iid], capture_output=True)
    time.sleep(40)  # bem mais que input_quiet (15 s) + output_quiet (6 s)
    acts = actions_since(iid, t_perm)
    st = status(idir)
    check("nenhuma injeção durante o prompt de permissão", not acts, f"ações={acts} state={st.get('state')}")
    check("arquivo ainda não criado (prompt intacto)", not (PROJ / "nota.txt").exists())
    p.write("\x1b")  # Esc: recusa a permissão
    # recusar com Esc NÃO dispara o hook Stop: o guard detecta pelo transcript
    clr2 = wait_for(lambda: any(a["action"] == "clear" for a in actions_since(iid, t_perm)), 90)
    check("/clear pendente executado depois que o turno acabou", bool(clr2))
    time.sleep(12)

    # --- Ctrl-C duas vezes sai ---------------------------------------------
    p.write("\x03")
    time.sleep(0.6)
    p.write("\x03")
    gone = wait_for(lambda: not p.isalive(), 20)
    check("Ctrl-C Ctrl-C encerra o Claude Code e o guard", bool(gone), f"exit={p.exitstatus}")
    check("pasta da instância removida", bool(wait_for(lambda: not idir.exists(), 10)))
    check("a janela continua aberta depois que a sessão sai", bool(gui_pid_alive()))
    close_gui()


def gui_pid_alive():
    try:
        pid = int((STATE / "gui.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, errors="replace").stdout
    return pid if str(pid) in out else None


def close_gui():
    pid = gui_pid_alive()
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def settings_model():
    try:
        return json.loads((Path(os.environ["USERPROFILE"]) / ".claude" / "settings.json").read_text(encoding="utf-8")).get("model", "<ausente>")
    except Exception as exc:
        return f"<erro {exc}>"


def last_assistant_model(transcript):
    model = None
    for line in Path(transcript).read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "assistant" and not o.get("isSidechain"):
            model = (o.get("message") or {}).get("model") or model
    return model


def main_model():
    """Troca de modelo no meio da sessão (limiar de 1%) para sonnet; o guard
    deve devolver o "model" do settings.json ao valor de antes."""
    before = {d.name for d in INST.iterdir()} if INST.is_dir() else set()
    original = settings_model()
    print("  settings.json model antes:", original)
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("CLAUDE", "ANTHROPIC")) and k.upper() not in ("CLAUDECODE",)}
    env.update(CUG_MODEL_SWITCH_SESSION_THRESHOLD="1", CUG_MODEL_SWITCH_RESTORE="false",
               CUG_MODEL_SWITCH_MODEL="sonnet", CUG_COMPACT_ENABLED="false")
    t0 = time.time()
    # --model explícito: o guard não põe --model na abertura e precisa injetar /model
    p = PtyProcess.spawn([*GUARD, "run", "--", "--model", "haiku", "--no-chrome"], cwd=str(PROJ), env=env,
                         dimensions=(40, 140))
    threading.Thread(target=reader, args=(p,), daemon=True).start()
    idir = wait_for(lambda: new_instance(before), 30)
    check("instância criada", bool(idir))
    if not idir:
        return
    iid = idir.name
    sw = wait_for(lambda: any(a["action"] == "switch_model" for a in actions_since(iid, t0)), 60)
    check("/model sonnet injetado com a sessão ociosa", bool(sw))
    shown = wait_for(lambda: re.search(r"(?i)set\s*model\s*to.{0,40}sonnet", screen_text()), 20)
    check("Claude Code confirmou a troca na tela", bool(shown), shown.group(0) if shown else "")
    restored = wait_for(lambda: settings_model() == original, 20)
    check("settings.json voltou ao valor original", bool(restored), f"agora={settings_model()} antes={original}")
    time.sleep(17)  # input_quiet + folga
    type_slow(p, "Responda apenas OK.")
    time.sleep(0.5)
    p.write("\r")
    n = wait_for(lambda: count_events(idir, "Stop"), 90)
    tr = next((h.get("transcript_path") for h in reversed(hooks(idir)) if h.get("transcript_path")), None)
    model = last_assistant_model(tr) if n and tr and Path(tr).is_file() else None
    check("o turno seguinte rodou em sonnet (troca valeu na sessão)", bool(model and "sonnet" in model), str(model))
    check("settings.json continua com o valor original", settings_model() == original, settings_model())
    time.sleep(3)
    p.write("\x03")
    time.sleep(0.6)
    p.write("\x03")
    check("Ctrl-C Ctrl-C encerra", bool(wait_for(lambda: not p.isalive(), 20)))
    check("settings.json com o valor original após sair", settings_model() == original, settings_model())
    close_gui()


try:
    main_model() if os.environ.get("E2E_MODE") == "model" else main()
finally:
    print("\nRESUMO:", sum(ok for _, ok, _ in results), "/", len(results), "ok")
    for n, ok, d in results:
        if not ok:
            print("  FALHA:", n, d)
