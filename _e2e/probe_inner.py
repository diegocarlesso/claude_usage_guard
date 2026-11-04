"""Roda dentro de um ConPTY: lê o teclado como o guard e registra cada pedaço."""
import importlib.util
import sys
import time

spec = importlib.util.spec_from_file_location("cug", sys.argv[1])
cug = importlib.util.module_from_spec(spec)
sys.modules["cug"] = cug
spec.loader.exec_module(cug)

out = open(sys.argv[2], "w", encoding="utf-8")
con = cug.WinConsole()
con.enter_raw()
# as consultas que o Claude Code manda ao abrir (o terminal responde pela entrada)
sys.stdout.write("\x1b[>0q\x1b[c\x1b[?1004h")
sys.stdout.flush()
sess = cug.TerminalSession([], {}, lambda s: None)
t0 = time.time()
while time.time() - t0 < 25:
    text = con.read_input()
    sess._track_input(text.encode("utf-8", "replace"))
    out.write(f"{time.time() - t0:6.2f} {text!r} dirty={sess.input_dirty}\n")
    out.flush()
