"""Tray menu posts commands to the Tk thread."""
from __future__ import annotations

import queue
import threading

from PIL import Image, ImageDraw
import pystray


def start_tray(commands: queue.Queue[str]) -> pystray.Icon:
    image = Image.new("RGB", (64, 64), "#f7d83a")
    draw = ImageDraw.Draw(image)
    draw.ellipse((9, 9, 55, 55), fill="#f7d83a", outline="#4b351c", width=3)
    draw.ellipse((23, 26, 28, 31), fill="#222222")
    draw.ellipse((40, 26, 45, 31), fill="#222222")
    draw.arc((27, 30, 42, 44), 0, 180, fill="#4b351c", width=2)
    choices = [
        ("Microphone on / off", "microphone"),
        ("Status / commands", "status"), ("Top tasks", "top tasks"),
        ("Cool down", "cool down"), ("Pause / resume auto actions", "pause"),
        ("Mute / unmute", "mute"), ("Do not disturb", "dnd"),
        ("Dry run toggle", "dry_run"), ("Show / hide character", "overlay"),
        ("Drag mode (Ctrl+Alt+P)", "drag"), ("Undo last close", "undo"),
        ("View log", "history"), ("Edit whitelist", "whitelist"), ("Quit", "quit")]
    def post(command: str):
        def callback(icon, item):
            commands.put(command)
        return callback

    menu = pystray.Menu(*(pystray.MenuItem(label, post(command)) for label, command in choices))
    icon = pystray.Icon("Pikabot", image, "Pikabot", menu)
    threading.Thread(target=icon.run, daemon=True, name="Pikabot tray").start()
    return icon
