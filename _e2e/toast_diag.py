"""Diagnóstico do toast: lança o script do guard de várias formas e confere
no registro se o Windows recebeu a notificação (LastNotificationAddedTime)."""
import importlib.util
import os
import subprocess
import sys
import time
import winreg

spec = importlib.util.spec_from_file_location("cug", sys.argv[1])
cug = importlib.util.module_from_spec(spec)
sys.modules["cug"] = cug
spec.loader.exec_module(cug)

KEY = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings" \
      r"\{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def last_added():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        return winreg.QueryValueEx(k, "LastNotificationAddedTime")[0]


def child(mode):
    """Roda num processo filho que sai logo depois de lançar o PowerShell."""
    code = (f"import importlib.util,sys,subprocess,os;"
            f"s=importlib.util.spec_from_file_location('cug',{sys.argv[1]!r});"
            f"c=importlib.util.module_from_spec(s);sys.modules['cug']=c;s.loader.exec_module(c);")
    if mode == "notify_toast":
        code += "print(c.notify_toast('Diagnóstico', 'variante notify_toast (flags do guard)'))"
    else:
        flags = {"no_window": 0x08000000, "new_group": 0x08000000 | 0x00000200,
                 "breakaway_only": 0x08000000 | 0x01000000}[mode]
        code += ("cmd=['powershell','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',c._TOAST_SCRIPT];"
                 f"env=dict(os.environ,CUG_NOTIFY_TITLE='Diagnóstico',CUG_NOTIFY_MSG='variante {mode}',CUG_NOTIFY_ICON='');"
                 f"subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
                 f"stderr=subprocess.DEVNULL,creationflags={flags});print('lançado')")
    subprocess.run([sys.executable, "-c", code], check=False)


for mode in sys.argv[2:]:
    before = last_added()
    t0 = time.time()
    child(mode)
    got = False
    while time.time() - t0 < 12:
        time.sleep(0.5)
        if last_added() != before:
            got = True
            break
    print(f"{mode:15} → {'NOTIFICAÇÃO CHEGOU' if got else 'nada'} ({time.time() - t0:.1f}s)")
    time.sleep(1)
