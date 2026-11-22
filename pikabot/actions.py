"""Conservative process selection and reversible action history."""
from __future__ import annotations

import json
import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from .monitor import ProcessInfo


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(filename=LOG_DIR / "actions.log", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
logger = logging.getLogger("pikabot")


@dataclass(frozen=True)
class Candidate:
    process: ProcessInfo
    reason: str


def candidates(processes: tuple[ProcessInfo, ...], config: dict) -> list[Candidate]:
    protected = {x.lower() for x in config["protected"] + config["whitelist"]}
    browsers = {x.lower() for x in config["browsers"]}
    background = {x.lower() for x in config["background_apps"]}
    result = []
    for proc in processes:
        name = proc.name.lower()
        if proc.pid == os.getpid() or name in protected or proc.pid <= 4:
            continue
        if name in browsers and (proc.cpu >= config["browser_cpu_percent"] or proc.ram_mb >= config["browser_ram_mb"]):
            result.append(Candidate(proc, f"browser using {proc.cpu:.0f}% CPU and {proc.ram_mb:.0f} MB RAM"))
        elif name in background and proc.cpu >= config["browser_cpu_percent"]:
            result.append(Candidate(proc, f"background app using {proc.cpu:.0f}% CPU"))
    return sorted(result, key=lambda c: (c.process.cpu, c.process.ram_mb), reverse=True)


class ActionManager:
    def __init__(self, config: dict, simulation: bool = False):
        self.config = config
        self.simulation = simulation
        self.last_action = 0.0
        self.closed: list[tuple[str, tuple[str, ...]]] = []

    def can_act(self) -> bool:
        return time.monotonic() - self.last_action >= self.config["action_cooldown_seconds"]

    def close(self, candidate: Candidate, temperature: float | None, approved: bool) -> str:
        proc = candidate.process
        if not approved:
            return "cancelled"
        if not self.can_act():
            return "cooldown"
        current = candidates((proc,), self.config)
        if not current:
            return "protected"
        self.last_action = time.monotonic()
        if self.simulation or self.config["dry_run"]:
            logger.info("DRY RUN pid=%s name=%s temp=%s reason=%s", proc.pid, proc.name, temperature, candidate.reason)
            return "dry run"
        try:
            live = psutil.Process(proc.pid)
            if live.name().lower() != proc.name.lower() or live.exe() != proc.executable:
                return "process changed"
            # On Windows terminate() forcibly kills the process. WM_CLOSE instead
            # lets the application display its own save/cancel dialog.
            user32 = ctypes.windll.user32
            posted = []
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def visit(hwnd, unused):
                owner = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value == proc.pid and user32.IsWindowVisible(hwnd):
                    posted.append(bool(user32.PostMessageW(hwnd, 0x0010, 0, 0)))
                return True
            user32.EnumWindows(callback_type(visit), 0)
            if not any(posted):
                return "no closable window; left running"
            logger.info("CLOSE REQUEST pid=%s name=%s temp=%s reason=%s", proc.pid, proc.name, temperature, candidate.reason)
            return "close requested; app may ask to save"
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as exc:
            logger.warning("SKIP pid=%s temp=%s reason=%s error=%s", proc.pid, temperature, candidate.reason, exc)
            return f"skipped: {exc}"

    def lower_priority(self, candidate: Candidate, temperature: float | None) -> str:
        if not candidates((candidate.process,), self.config):
            return "protected"
        if self.simulation or self.config["dry_run"]:
            logger.info("DRY RUN PRIORITY pid=%s temp=%s reason=%s", candidate.process.pid, temperature, candidate.reason)
            return "dry run"
        try:
            live = psutil.Process(candidate.process.pid)
            if live.name().lower() != candidate.process.name.lower():
                return "process changed"
            live.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            logger.info("LOWER PRIORITY pid=%s temp=%s reason=%s", live.pid, temperature, candidate.reason)
            return "lowered priority"
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as exc:
            logger.warning("SKIP PRIORITY pid=%s temp=%s error=%s", candidate.process.pid, temperature, exc)
            return f"skipped: {exc}"

    def undo(self) -> str:
        if not self.closed:
            return "No closed app to reopen. Unsaved state cannot be restored."
        executable, command = self.closed.pop()
        if not executable or not Path(executable).is_file():
            return "The executable is unavailable. Unsaved state cannot be restored."
        try:
            subprocess.Popen(list(command) if command and command[0] == executable else [executable],
                close_fds=True)
            logger.info("REOPEN executable=%s", json.dumps(executable))
            return f"Reopened {Path(executable).name}. Unsaved state cannot be restored."
        except OSError as exc:
            logger.warning("REOPEN FAILED executable=%s error=%s", executable, exc)
            return f"Could not reopen: {exc}"
