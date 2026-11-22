"""Small transparent character; tray and hotkey enable dragging."""
from __future__ import annotations

import ctypes
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from .thermal import Level

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def make_pet_frames() -> None:
    """Render the desktop pet from simple vector shapes at double resolution."""
    ASSETS.mkdir(exist_ok=True)
    for level in Level:
        for frame in range(4):
            image = Image.new('RGBA', (112, 112))
            d = ImageDraw.Draw(image)
            yellow, edge = '#ffd839', '#573b25'
            bob = [0, -2, 0, 2][frame]
            # Lightning tail, long black-tipped ears, red cheeks and running feet.
            d.polygon([(72,69),(91,58),(84,48),(104,33),(109,49),(97,58),(103,70),(80,82)], fill=yellow, outline=edge)
            d.ellipse((28,48+bob,80,93+bob), fill=yellow, outline=edge, width=2)
            d.polygon([(34,43+bob),(24,9+bob),(35,13+bob),(47,39+bob)], fill=yellow, outline=edge)
            d.polygon([(24,9+bob),(35,13+bob),(39,23+bob),(29,24+bob)], fill='#272221')
            d.polygon([(60,40+bob),(73,7+bob),(80,13+bob),(73,48+bob)], fill=yellow, outline=edge)
            d.polygon([(73,7+bob),(80,13+bob),(77,25+bob),(68,21+bob)], fill='#272221')
            d.ellipse((24,29+bob,79,74+bob), fill=yellow, outline=edge, width=2)
            for x in (37,59):
                d.ellipse((x,43+bob,x+7,53+bob), fill='#262222')
                d.ellipse((x+1,44+bob,x+3,47+bob), fill='white')
            d.ellipse((28,54+bob,40,65+bob), fill='#f04742')
            d.ellipse((65,54+bob,77,65+bob), fill='#f04742')
            d.polygon([(50,53+bob),(55,53+bob),(52,56+bob)], fill=edge)
            d.arc((44,55+bob,59,66+bob), 0, 180, fill=edge, width=2)
            stride = [-7,0,7,0][frame]
            d.ellipse((28+stride,85,48+stride,97), fill=yellow, outline=edge, width=2)
            d.ellipse((60-stride,85,80-stride,97), fill=yellow, outline=edge, width=2)
            d.line((35,70+bob,23-stride,79+bob), fill=edge, width=5)
            d.line((35,70+bob,23-stride,79+bob), fill=yellow, width=3)
            if level >= Level.WARM:
                d.ellipse((77,43+bob,82,53+bob), fill='#5bbef4')
            if level == Level.CRITICAL and frame % 2:
                d.text((91,8), '!', fill='#ef3e33', stroke_width=1)
            image.save(ASSETS / f'pet_{level.name.lower()}_{frame}.png')


def make_placeholder_frames() -> None:
    ASSETS.mkdir(exist_ok=True)
    for level in Level:
        for frame in range(2):
            target = ASSETS / f"{level.name.lower()}_{frame}.png"
            if target.exists():
                continue
            image = Image.new("RGBA", (88, 88), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.polygon([(26, 35), (13, 5), (34, 20)], fill="#f3cc26", outline="#5a391d")
            draw.polygon([(59, 32), (72, 5), (53, 20)], fill="#f3cc26", outline="#5a391d")
            draw.ellipse((17, 20, 70, 72), fill="#f9d838", outline="#5a391d", width=2)
            draw.ellipse((30, 40, 35, 45), fill="#252525")
            draw.ellipse((52, 40, 57, 45), fill="#252525")
            draw.ellipse((23, 48, 32, 57), fill="#ed6570")
            draw.ellipse((55, 48, 64, 57), fill="#ed6570")
            draw.arc((37, 47, 49, 62), 0, 180, fill="#5a391d", width=2)
            draw.line((30, 72, 25 - frame * 4, 80), fill="#5a391d", width=4)
            draw.line((57, 72, 62 + frame * 4, 80), fill="#5a391d", width=4)
            if level >= Level.WARM:
                draw.ellipse((66, 39, 72, 50), fill="#56bde9")
            if level >= Level.HOT:
                draw.arc((37, 51, 50, 66), 0, 180, fill="#5a391d", width=3)
            if level == Level.CRITICAL:
                draw.polygon([(74, 18), (68, 32), (75, 32), (69, 46), (84, 26), (77, 26), (82, 18)], fill="#e95343")
            image.save(target)


class Overlay:
    def __init__(self, root: tk.Tk):
        make_pet_frames()
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.wm_attributes("-transparentcolor", "#010203")
        self.window.configure(bg="#010203")
        self.label = tk.Label(self.window, bg="#010203", borderwidth=0)
        self.label.pack()
        self.frames = {}
        for level in Level:
            for i in range(4):
                with Image.open(ASSETS / f'pet_{level.name.lower()}_{i}.png') as source:
                    self.frames[(level, i, 1)] = ImageTk.PhotoImage(source)
                    self.frames[(level, i, -1)] = ImageTk.PhotoImage(source.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
        self.level = Level.SAFE
        self.frame = 0
        self.drag_mode = False
        self.direction = -1
        self.x = root.winfo_screenwidth() - 120
        self.y = root.winfo_screenheight() - 140
        self.window.title('Pikabot desktop pet')
        self.window.geometry(f"112x112+{self.x}+{self.y}")
        self.label.bind("<ButtonPress-1>", self._start_drag)
        self.label.bind("<B1-Motion>", self._drag)
        self._set_clickthrough(True)
        self._animate()

    def _set_clickthrough(self, enabled: bool) -> None:
        self.window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, -20)
        style = (style | 0x80000 | 0x20) if enabled else (style & ~0x20)
        user32.SetWindowLongW(hwnd, -20, style)

    def toggle_drag(self) -> None:
        self.drag_mode = not self.drag_mode
        self._set_clickthrough(not self.drag_mode)

    def _start_drag(self, event) -> None:
        self._offset = (event.x_root - self.x, event.y_root - self.y)

    def _drag(self, event) -> None:
        if self.drag_mode:
            self.x = event.x_root - self._offset[0]
            self.y = event.y_root - self._offset[1]
            self.window.geometry(f"+{self.x}+{self.y}")

    def _animate(self) -> None:
        self.label.configure(image=self.frames[(self.level, self.frame, self.direction)])
        self.frame = (self.frame + 1) % 4
        if not self.drag_mode:
            self.x += self.direction * (5 if self.level == Level.SAFE else 3)
            if self.x <= 0 or self.x >= self.root.winfo_screenwidth() - 112:
                self.direction *= -1
                self.x = min(max(0, self.x), self.root.winfo_screenwidth() - 112)
            self.window.geometry(f"+{max(0, self.x)}+{max(0, self.y)}")
        self.root.after(140, self._animate)

    def set_level(self, level: Level) -> None:
        self.level = level

    def set_visible(self, visible: bool) -> None:
        if visible:
            self.window.deiconify()
        else:
            self.window.withdraw()
