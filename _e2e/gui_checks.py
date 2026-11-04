"""Checagens da janela: botão "Pedir /clear", nível das barras e janela única.

Uso: py gui_checks.py <claude_usage_guard.py> [<claude_usage_guard.exe>]
(o .exe, se dado, é o usado no teste de janela única)."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

# Pasta de estado temporária (antes de importar o guard, que a lê na carga); os
# subprocessos da janela única a herdam. Nada vai para o ~/.claude-usage-guard real.
STATE_TMP = tempfile.mkdtemp(prefix="cug-guichecks-")
os.environ["CUG_STATE_DIR"] = STATE_TMP

spec = importlib.util.spec_from_file_location("cug", sys.argv[1])
cug = importlib.util.module_from_spec(spec)
sys.modules["cug"] = cug
spec.loader.exec_module(cug)
GUARD = [sys.argv[2]] if len(sys.argv) > 2 else [sys.executable, sys.argv[1]]
ok_all = True


def check(name, ok, detail=""):
    global ok_all
    ok_all &= bool(ok)
    print(f"[{'OK' if ok else 'FALHA'}] {name} {detail}", flush=True)


cfg, _ = cug.load_config(None)
lv = cug._window_level
check("níveis das barras", [lv(cfg, "five_hour", 20), lv(cfg, "five_hour", 75), lv(cfg, "five_hour", 95),
                            lv(cfg, "seven_day", 86), lv(cfg, "iguana_necktie", 100), lv(cfg, "five_hour", None)]
      == ["normal", "warn", "crit", "warn", "dim", "dim"])

# botão "Pedir /clear" com uma instância de verdade (pasta criada aqui)
iid = "abcdef123456"
d = cug.ensure_private_dir(cug.instance_dir(iid))
try:
    inst = [{"instance": iid, "state": "ocioso", "hooks_ok": True, "cwd": os.getcwd(), "pid": os.getpid()}]
    win = cug.GuardWindow(cfg, lambda: (None, "erro de teste", inst, [], []))
    win.refresh(reschedule=False)
    win._ask_clear(iid)
    win.root.update()
    check("botão cria clear.request", (d / "clear.request").exists())
    texts = []

    def walk(w):
        for c in w.winfo_children():
            if c.winfo_class() == "Button":
                texts.append((c.cget("text"), c.cget("state")))
            walk(c)
    walk(win.root)
    check("botão vira '/clear pendente' desabilitado", ("/clear pendente", "disabled") in texts, str(texts))
    check("rodapé confirma o pedido", "/clear pedido" in win.footer_note.cget("text"), win.footer_note.cget("text"))
    win._ask_clear("0123456789ab")  # instância que não existe
    check("instância inexistente avisa no rodapé", "não deu" in win.footer_note.cget("text"), win.footer_note.cget("text"))
    win.root.destroy()
finally:
    shutil.rmtree(d, ignore_errors=True)

# botões das sessões do Desktop (1.4.0): "Compactar" grava a fila e vira "✓ Compactar"
sid = "e2e0e2e0-0000-4000-8000-guichecks000"
desk = [cug.DesktopSessionState(sid, cwd=os.getcwd(), updated_at=time.time(), last_event="Stop")]
pend = cug.desktop_pending_path(sid)
try:
    win = cug.GuardWindow(cfg, lambda: (None, None, [], [], desk))
    win.refresh(reschedule=False)
    btns = {}

    def walk_btn(w):
        for c in w.winfo_children():
            if c.winfo_class() == "Button":
                btns[c.cget("text")] = c
            walk_btn(c)
    walk_btn(win.root)
    check("4 botões no cartão do Desktop", {"Compactar", "Economizar", "Skills/MCPs", "Pesquisar"} <= set(btns),
          str(sorted(btns)))
    btns["Compactar"].invoke()
    win.root.update()
    check("Compactar grava a fila", cug.read_pending(sid) == ["compact"], str(cug.read_pending(sid)))
    btns.clear()
    walk_btn(win.root)
    check("botão vira '✓ Compactar'", "✓ Compactar" in btns, str(sorted(btns)))
    check("rodapé diz quando vai", "próxima mensagem" in win.footer_note.cget("text"), win.footer_note.cget("text"))
    btns["✓ Compactar"].invoke()
    check("segundo clique cancela", cug.read_pending(sid) == [] and not pend.exists())
    win.root.destroy()
finally:
    pend.unlink(missing_ok=True)

# janela única: a 1ª fica aberta; a 2ª sai na hora dizendo que já está aberta
first = subprocess.Popen([*GUARD, "gui"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
end = time.time() + 20
while time.time() < end and not cug.gui_running():
    time.sleep(0.2)
check("1ª janela registrou gui.pid", cug.gui_running())
second = subprocess.run([*GUARD, "gui"], capture_output=True, text=True, encoding="utf-8", timeout=30)
check("2ª janela não abre", "já está aberta" in second.stdout and second.returncode == 0, repr(second.stdout))
check("1ª janela continua aberta", first.poll() is None)
first.terminate()
first.wait(10)
shutil.rmtree(STATE_TMP, ignore_errors=True)
print("TUDO OK" if ok_all else "HÁ FALHAS")
