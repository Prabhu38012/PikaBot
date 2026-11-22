"""Closes only a disposable window created by this test; never a user app."""
import subprocess
import sys
import time
import psutil
from pikabot.actions import ActionManager, Candidate
from pikabot.config import load
from pikabot.monitor import ProcessInfo

if '--child' in sys.argv:
    import tkinter as tk
    root = tk.Tk()
    root.title('Pikabot disposable close test')
    root.after(15000, root.destroy)
    root.mainloop()
else:
    child = subprocess.Popen([sys.executable, __file__, '--child'])
    try:
        time.sleep(2)
        live = psutil.Process(child.pid)
        cfg = load()
        cfg.update(dry_run=False, whitelist=[], browsers=[live.name()])
        info = ProcessInfo(child.pid, live.name(), 30, 1200, live.exe(), tuple(live.cmdline()))
        result = ActionManager(cfg).close(Candidate(info, 'disposable integration test'), 85, True)
        assert result.startswith('close requested'), result
        assert child.wait(timeout=5) == 0
        print('PASS: real WM_CLOSE delivered; disposable app exited normally.')
    finally:
        if child.poll() is None:
            child.terminate()
