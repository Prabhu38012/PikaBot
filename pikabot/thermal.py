"""Temperature states with downward hysteresis."""
from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    SAFE = 0
    WARM = 1
    HOT = 2
    CRITICAL = 3


class ThermalState:
    def __init__(self, config: dict):
        self.config = config
        self.level = Level.SAFE

    def update(self, temperature_c: float | None) -> Level:
        if temperature_c is None:
            self.level = Level.SAFE
            return self.level
        boundaries = [self.config["safe_below_c"], self.config["hot_at_c"], self.config["critical_at_c"]]
        while self.level < Level.CRITICAL and temperature_c >= boundaries[self.level]:
            self.level = Level(self.level + 1)
        while self.level > Level.SAFE and temperature_c < boundaries[self.level - 1] - self.config["hysteresis_c"]:
            self.level = Level(self.level - 1)
        return self.level
