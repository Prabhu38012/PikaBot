"""Offline speech queue with rate limiting."""
from __future__ import annotations

import queue
import os
import subprocess
import threading
import time

from .actions import logger


class Voice:
    def __init__(self, config: dict):
        self.config = config
        self.messages: queue.Queue[tuple[str, bool] | None] = queue.Queue()
        self.last_spoken = 0.0
        self.speaking = threading.Event()
        self.suppress_listener_until = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True, name="Pikabot voice")
        self.thread.start()

    def say(self, message: str, urgent: bool = False) -> None:
        if not self.config["mute"] and not self.config["do_not_disturb"]:
            self.messages.put((message, urgent))

    def _run(self) -> None:
        engine = None
        if self.config.get("voice_backend") == "pyttsx3":
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", 180)
            except Exception as exc:
                logger.warning("pyttsx3 unavailable; using Windows speech: %s", exc)
        while True:
            item = self.messages.get()
            if item is None:
                break
            message, urgent = item
            if self.config["mute"] or self.config["do_not_disturb"]:
                continue
            if not urgent and time.monotonic() - self.last_spoken < 60:
                continue
            try:
                self.speaking.set()
                if engine is None:
                    environment = os.environ.copy()
                    environment["PIKABOT_SPEECH"] = message
                    script = ("Add-Type -AssemblyName System.Speech; "
                              "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                              "$s.Speak($env:PIKABOT_SPEECH)")
                    subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                        env=environment, timeout=20, check=True, capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                else:
                    engine.say(message)
                    engine.runAndWait()
                self.last_spoken = time.monotonic()
            except Exception as exc:
                logger.warning("Voice playback failed: %s", exc)
            finally:
                self.suppress_listener_until = time.monotonic() + 1
                self.speaking.clear()

    def stop(self) -> None:
        self.messages.put(None)
