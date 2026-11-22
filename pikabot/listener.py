"""Offline, opt-out microphone listener using installed Windows speech."""
import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

from .actions import logger

WAKE_PHRASES = {'hey pikabot', 'hey pika bot', 'hey peek a bot'}
COMMANDS = {'status', 'temperature', 'top tasks', 'cool down', 'go to sleep', 'thank you'}
BREAK_PHRASES = {'ok you may take a break', 'okay you may take a break', 'you may take a break', 'take a break', 'go to sleep'}


class WakeSession:
    def __init__(self):
        self.active = False

    def accept(self, text, confidence, now):
        text = ' '.join(re.sub(r'[^a-z ]', ' ', text.lower()).split())
        if confidence < (0.4 if self.active else 0.65):
            return None
        if text in WAKE_PHRASES:
            self.active = True
            return 'wake'
        wants_break = text in BREAK_PHRASES or (text.endswith('you may take a break') and not re.search(r'\b(not|don t|never)\b', text))
        if self.active and wants_break:
            self.active = False
            return 'break'
        if self.active and text == 'cool down' and confidence < 0.65:
            return 'unknown'
        if self.active and text in COMMANDS:
            return text
        if self.active:
            if re.search(r'\b(temperature|how hot)\b', text):
                return 'temperature'
            if text in {'what is the status of my laptop', 'how is my laptop doing', 'check my laptop status'}:
                return 'status'
            if text in {'show me the top tasks', 'which app is using the most cpu', 'what are the top tasks'}:
                return 'top tasks'
            if text in {'please cool down my laptop', 'cool down my laptop', 'help me cool down my laptop'}:
                return 'cool down' if confidence >= 0.65 else 'unknown'
            return 'unknown'
        return None


class Listener:
    def __init__(self, config, commands: queue.Queue, voice):
        self.config, self.commands, self.voice = config, commands, voice
        self.status = 'Starting microphone'
        self.stop_event = threading.Event()
        self.process = None
        self.session = WakeSession()
        self.last_heard = ''
        threading.Thread(target=self._run, daemon=True, name='Pikabot microphone').start()

    def enabled(self):
        return self.config.get('voice_activation', True) and not self.config['do_not_disturb']

    def _run(self):
        while not self.stop_event.is_set():
            if not self.enabled():
                self.status = 'Microphone off'
                self.stop_event.wait(0.5)
                continue
            try:
                self.process = subprocess.Popen(['powershell.exe', '-NoProfile', '-File',
                    str(Path(__file__).with_name('listen.ps1')), '-ParentPid', str(os.getpid())], stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                for line in self.process.stdout:
                    if self.stop_event.is_set() or not self.enabled():
                        break
                    event = json.loads(line)
                    if event['kind'] == 'ready':
                        self.status = 'Listening for Hey Pikabot'
                        logger.info('Offline microphone listener ready')
                    elif event['kind'] == 'error':
                        self.status = 'Microphone unavailable: ' + event['message']
                        logger.warning(self.status)
                    elif event['kind'] == 'speech':
                        if not self.voice.speaking.is_set() and time.monotonic() > self.voice.suppress_listener_until:
                            self.last_heard = event['text']
                            action = self.session.accept(event['text'], event['confidence'], time.monotonic())
                            if action:
                                self.status = 'Awake — listening for commands' if self.session.active else 'Listening for Hey Pikabot'
                                self.commands.put('voice:' + action)
                        self.process.stdin.write('awake\n' if self.session.active else 'sleep\n')
                        self.process.stdin.flush()
            except Exception as exc:
                self.status = 'Microphone unavailable: ' + str(exc)
                logger.warning(self.status)
            finally:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                if self.status in ('Listening for Hey Pikabot', 'Awake — listening for commands'):
                    self.status = 'Microphone off' if not self.enabled() else 'Microphone restarting'
                self.session.active = False
            self.stop_event.wait(3)

    def stop(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
