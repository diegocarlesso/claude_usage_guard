import sys
import threading
import time
from pathlib import Path

from winpty import PtyProcess

HERE = Path(__file__).resolve().parent
GUARD = sys.argv[1]
p = PtyProcess.spawn([sys.executable, str(HERE / "probe_inner.py"), GUARD, str(HERE / "probe.log")], dimensions=(30, 100))


def drain():
    while p.isalive():
        try:
            p.read(65536)
        except EOFError:
            break


threading.Thread(target=drain, daemon=True).start()
time.sleep(2)
for ch in "abc ção":
    p.write(ch)
    time.sleep(0.03)
p.write("\x1b[D")
time.sleep(0.1)
p.write("X")
time.sleep(0.1)
p.write(" \x1b[200~colado\x1b[201~")
time.sleep(1)
p.write("\r")
time.sleep(3)
p.write("\x03")
time.sleep(0.5)
p.write("\x1b")
time.sleep(1)
p.terminate(force=True)
print(Path(HERE / "probe.log").read_text(encoding="utf-8"))
