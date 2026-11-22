"""Windows entry point: monitoring worker, Tk UI, tray, and commands."""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

from . import config
from .actions import ActionManager, LOG_DIR, candidates, logger
from .monitor import Monitor, Snapshot
from .overlay import Overlay
from .thermal import Level, ThermalState
from .tray import start_tray
from .voice import Voice
from .listener import Listener


def single_instance() -> object:
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = ctypes.wintypes.HANDLE
    kernel.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, "Local\\PikabotGuardian")
    if not handle or kernel.GetLastError() == 183:
        raise RuntimeError("Pikabot is already running")
    return handle


class App:
    def __init__(self, simulate_c: float | None):
        self.mutex = single_instance()
        self.config = config.load()
        if simulate_c is not None:
            self.config["dry_run"] = True
        self.monitor = Monitor(self.config, simulate_c)
        self.thermal = ThermalState(self.config)
        self.actions = ActionManager(self.config, simulate_c is not None)
        self.voice = Voice(self.config)
        self.events: queue.Queue[Snapshot | Exception] = queue.Queue()
        self.commands: queue.Queue[str] = queue.Queue()
        self.listener = Listener(self.config, self.commands, self.voice)
        self.stop = threading.Event()
        self.root = tk.Tk()
        self.root.withdraw()
        self.overlay = Overlay(self.root)
        self.tray = start_tray(self.commands)
        self.snapshot: Snapshot | None = None
        self.last_level = Level.SAFE
        self.last_prompt_pid: int | None = None
        self.last_prompt_time = 0.0
        self.hot_since: float | None = None
        self.hot_start_temp: float | None = None
        self.power_saver_set = False
        self.last_visibility_check = 0.0
        self.overlay_visible = True
        self.user32 = ctypes.windll.user32
        self.user32.RegisterHotKey(None, 1, 0x0002 | 0x0001, ord("P"))
        threading.Thread(target=self._monitor_loop, daemon=True, name="Pikabot monitor").start()
        self.root.after(100, self._pump)
        self.voice.say("Pika-pika! I'm awake and guarding your laptop!")

    def _monitor_loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.events.put(self.monitor.snapshot())
            except Exception as exc:
                logger.exception("Monitor failed")
                self.events.put(exc)
            self.stop.wait(self.config["monitor_interval_seconds"])

    def _pump(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if isinstance(event, Exception):
                    logger.error("Monitoring error: %s", event)
                else:
                    self._handle_snapshot(event)
        except queue.Empty:
            pass
        try:
            while True:
                self.command(self.commands.get_nowait())
        except queue.Empty:
            pass
        msg = ctypes.wintypes.MSG()
        while self.user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
            if msg.message == 0x0312 and msg.wParam == 1:
                self.overlay.toggle_drag()
        if time.monotonic() - self.last_visibility_check >= 1:
            self._update_visibility()
            self.last_visibility_check = time.monotonic()
        if not self.stop.is_set():
            self.root.after(100, self._pump)

    def _handle_snapshot(self, snap: Snapshot) -> None:
        self.snapshot = snap
        level = self.thermal.update(snap.temperature_c)
        self.overlay.set_level(level)
        if level != self.last_level:
            logger.info("LEVEL %s temp=%s source=%s", level.name, snap.temperature_c, snap.temperature_source)
            if level == Level.WARM:
                self.voice.say("Things are getting warm. Let's cool down together!")
            elif level == Level.HOT:
                self.voice.say("Pika! It's hot. Let's check the heavy apps!")
            elif level == Level.CRITICAL:
                self.voice.say("Pika! Too hot! Please save your work and cool the laptop!", urgent=True)
            self.last_level = level
        if (level >= Level.HOT and snap.temperature_source in ("LibreHardwareMonitor", "system sensor")
                and self.monitor.simulate_c is None):
            self._critical_response(snap, level)
        else:
            self.hot_since = None
        if level < Level.HOT or self.config["auto_actions_paused"] or not self.actions.can_act():
            return
        choices = candidates(snap.processes, self.config)
        if not choices:
            return
        choice = choices[0]
        if self.last_prompt_pid == choice.process.pid and time.monotonic() - self.last_prompt_time < 60:
            return
        self.last_prompt_pid = choice.process.pid
        self.last_prompt_time = time.monotonic()
        self._ask_action(choice, snap)

    def _ask_action(self, choice, snap: Snapshot) -> None:
        temperature = "simulation" if self.monitor.simulate_c is not None else (f"{snap.temperature_c:.1f}°C" if snap.temperature_c is not None else "unavailable")
        dry = self.config["dry_run"] or self.monitor.simulate_c is not None
        verb = "record a dry run for" if dry else "request that this process close"
        approved = messagebox.askyesno("Pikabot", f"Temperature: {temperature}\n{choice.process.name} (PID {choice.process.pid})\n{choice.reason}\n\nWould you like to {verb}? Save work first.")
        result = self.actions.close(choice, snap.temperature_c, approved)
        if result.startswith("close requested"):
            self.voice.say("I requested an app close to reduce heat. Save any work first.")
            self.root.after(1000, lambda: self._remember_closed(choice.process, 0))
        elif result == "dry run":
            self.voice.say("Dry run recorded. No app was closed.")
        logger.info("ACTION RESULT pid=%s result=%s", choice.process.pid, result)

    def _remember_closed(self, process, attempts: int) -> None:
        import psutil
        if not psutil.pid_exists(process.pid):
            self.actions.closed.append((process.executable or "", process.command))
            logger.info("EXIT CONFIRMED pid=%s", process.pid)
        elif attempts < 60:
            self.root.after(1000, lambda: self._remember_closed(process, attempts + 1))

    def _critical_response(self, snap: Snapshot, level: Level) -> None:
        if self.config["auto_actions_paused"]:
            self.hot_since = None
            return
        if level != Level.CRITICAL:
            self.hot_since = None
            return
        if self.hot_since is None:
            self.hot_since = time.monotonic()
            self.hot_start_temp = snap.temperature_c
            if not self.power_saver_set and not self.config["dry_run"]:
                try:
                    subprocess.run(["powercfg", "/setactive", "a1841308-3541-4fab-bc81-f71556f20b4a"],
                        check=True, capture_output=True, timeout=5)
                    logger.info("POWER SAVER temp=%s", snap.temperature_c)
                    self.power_saver_set = True
                except (OSError, subprocess.SubprocessError) as exc:
                    logger.warning("Power saver unavailable: %s", exc)
        if (self.config["allow_critical_hibernate"] and not self.config["dry_run"]
                and self.hot_since and time.monotonic() - self.hot_since >= 60
                and snap.temperature_c is not None and self.hot_start_temp is not None
                and snap.temperature_c > self.hot_start_temp):
            self.config["allow_critical_hibernate"] = False
            logger.warning("HIBERNATE requested after sustained rising CPU temperature %s", snap.temperature_c)
            try:
                subprocess.run(["shutdown", "/h"], check=True, timeout=5)
            except (OSError, subprocess.SubprocessError) as exc:
                logger.error("Hibernate failed: %s", exc)

    def _update_visibility(self) -> None:
        visible = self.config["show_overlay"]
        if self.config.get('pet_always_visible', True):
            if visible != self.overlay_visible:
                self.overlay.set_visible(visible)
                self.overlay_visible = visible
            return
        try:
            hwnd = self.user32.GetForegroundWindow()
            rect = ctypes.wintypes.RECT()
            self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()
            full = rect.left <= 0 and rect.top <= 0 and rect.right >= width and rect.bottom >= height
            title = ctypes.create_unicode_buffer(512)
            self.user32.GetWindowTextW(hwnd, title, 512)
            meeting = any(word in title.value.lower() for word in self.config.get("meeting_title_keywords", ["zoom meeting", "microsoft teams", "google meet"]))
            visible = visible and not full and not meeting
        except Exception:
            pass
        if visible != self.overlay_visible:
            self.overlay.set_visible(visible)
            self.overlay_visible = visible

    def command(self, raw: str) -> None:
        if raw.startswith('voice:'):
            action = raw[6:]
            if action == 'wake':
                self.voice.say("I'm here! I'll keep listening until you tell me to take a break.", urgent=True)
            elif action == 'break':
                self.voice.say("Okay, taking a break. Say my wake phrase when you need me.", urgent=True)
            elif action == 'unknown':
                self.voice.say("I didn't understand. Ask about temperature, status, top tasks, or cooling.", urgent=True)
            elif action in ('status', 'temperature'):
                snap = self.snapshot
                if snap and snap.temperature_c is not None:
                    self.voice.say(f"Temperature is {snap.temperature_c:.0f} degrees. CPU load is {snap.cpu_percent:.0f} percent.", urgent=True)
                else:
                    self.voice.say('The temperature sensor is unavailable right now.', urgent=True)
            elif action == 'top tasks':
                if self.snapshot and self.snapshot.processes:
                    self.voice.say('The busiest app is ' + self.snapshot.processes[0].name, urgent=True)
            elif action == 'cool down':
                self.voice.say('I will show you an app to review before closing.', urgent=True)
                self.command('cool down')
            else:
                self.voice.say("You're welcome. I'm still listening.", urgent=True)
            return
        if raw == 'microphone':
            self.config['voice_activation'] = not self.config.get('voice_activation', True)
            config.save(self.config)
            return
        parts = raw.strip().split()
        if not parts:
            return
        command = parts[0].lower()
        snap = self.snapshot
        if raw == "status":
            text = "Waiting for first sample" if not snap else (
                f"{self.thermal.level.name if snap.temperature_c is not None else 'UNKNOWN'} | CPU temp: {snap.temperature_c if snap.temperature_c is not None else 'unavailable'} °C ({snap.temperature_source})\n"
                f"CPU {snap.cpu_percent:.0f}% | RAM {snap.ram_percent:.0f}% | Disk {snap.disk_percent:.0f}%\n"
                f"Battery {snap.battery_percent if snap.battery_percent is not None else 'unavailable'}% | charging {snap.charging if snap.charging is not None else 'unknown'} | fan {snap.fan_rpm if snap.fan_rpm is not None else 'unavailable'} RPM\n"
                f"Dry run: {self.config['dry_run']} | Actions paused: {self.config['auto_actions_paused']}")
            response = simpledialog.askstring("Pikabot status", text + '\n' + self.listener.status + '\nLast heard: ' + self.listener.last_heard + "\n\nCommand (optional):", parent=self.root)
            if response:
                self.command(response)
        elif raw == "top tasks":
            text = "Waiting for a sample" if not snap else (
                "Top CPU:\n" + "\n".join(f"{p.name} ({p.pid}) {p.cpu:.0f}%" for p in snap.processes[:10])
                + "\n\nTop RAM:\n" + "\n".join(f"{p.name} ({p.pid}) {p.ram_mb:.0f} MB"
                    for p in sorted(snap.processes, key=lambda item: item.ram_mb, reverse=True)[:10]))
            messagebox.showinfo("Top tasks", text)
        elif raw == "cool down":
            if snap:
                choices = candidates(snap.processes, self.config)
                if choices:
                    self._ask_action(choices[0], snap)
                else:
                    messagebox.showinfo("Pikabot", "No eligible heavy app found. Close unused apps and improve airflow.")
        elif command == "whitelist":
            if len(parts) >= 3 and parts[1] in ("add", "remove"):
                name = " ".join(parts[2:])
                existing = {x.lower(): x for x in self.config["whitelist"]}
                if parts[1] == "add" and name.lower() not in existing:
                    self.config["whitelist"].append(name)
                elif parts[1] == "remove" and name.lower() in existing:
                    self.config["whitelist"].remove(existing[name.lower()])
                config.save(self.config)
                messagebox.showinfo("Whitelist", ", ".join(self.config["whitelist"]))
            else:
                response = simpledialog.askstring("Whitelist", "Enter: whitelist add/remove app.exe\nCurrent: " + ", ".join(self.config["whitelist"]))
                if response:
                    self.command(response)
        elif raw == "history":
            os.startfile(LOG_DIR / "actions.log")
        elif raw == "sleep":
            self.config["auto_actions_paused"] = True
            config.save(self.config)
        elif raw in ("pause", "mute", "dnd", "dry_run", "overlay"):
            key = {"pause": "auto_actions_paused", "mute": "mute", "dnd": "do_not_disturb", "dry_run": "dry_run", "overlay": "show_overlay"}[raw]
            self.config[key] = not self.config[key]
            if self.monitor.simulate_c is not None:
                self.config["dry_run"] = True
            else:
                config.save(self.config)
        elif raw == "drag":
            self.overlay.toggle_drag()
        elif raw == "undo":
            messagebox.showinfo("Undo", self.actions.undo())
        elif raw == "quit":
            self.stop.set()
            self.voice.stop()
            self.listener.stop()
            self.tray.stop()
            self.user32.UnregisterHotKey(None, 1)
            ctypes.windll.kernel32.CloseHandle(self.mutex)
            self.root.destroy()
        else:
            messagebox.showinfo("Pikabot", "Commands: status, top tasks, cool down, whitelist add/remove <app>, history, sleep")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate-temp", type=float, help="Fake Celsius temperature; all actions stay dry run")
    args = parser.parse_args()
    App(args.simulate_temp).run()


if __name__ == "__main__":
    main()
