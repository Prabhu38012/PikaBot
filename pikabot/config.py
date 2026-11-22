"""Persistent, user-editable settings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def load() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not (0 < data["safe_below_c"] < data["hot_at_c"] < data["critical_at_c"]):
        raise ValueError("Temperature thresholds must increase in config.json")
    return data


def save(data: dict[str, Any]) -> None:
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_PATH)
