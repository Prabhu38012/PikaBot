"""Collect a live snapshot without blocking the interface."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
import time
from urllib.request import urlopen

import psutil


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    cpu: float
    ram_mb: float
    executable: str | None
    command: tuple[str, ...]


@dataclass(frozen=True)
class Snapshot:
    temperature_c: float | None
    temperature_source: str
    fan_rpm: float | None
    cpu_percent: float
    ram_percent: float
    disk_percent: float
    battery_percent: float | None
    charging: bool | None
    processes: tuple[ProcessInfo, ...]


def _number(value: object) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _lhm_sensors(node: object, parent: str = ""):
    if isinstance(node, dict):
        text = " ".join(str(node.get(k, "")) for k in ("Text", "Name", "SensorType", "Type", "HardwareType"))
        label = (parent + " " + text).lower()
        value = _number(node.get("Value", node.get("value", "")))
        if value is not None:
            yield label, value
        for child in node.values():
            if isinstance(child, (dict, list)):
                yield from _lhm_sensors(child, label)
    elif isinstance(node, list):
        for child in node:
            yield from _lhm_sensors(child, parent)


class Monitor:
    def __init__(self, config: dict, simulate_c: float | None = None):
        self.config = config
        self.simulate_c = simulate_c
        self._previous_cpu: dict[int, float] = {}
        self._previous_sample_time = time.monotonic()

    def sensors(self) -> tuple[float | None, str, float | None]:
        if self.simulate_c is not None:
            return self.simulate_c, "SIMULATED (no real actions)", None
        try:
            with urlopen(self.config["lhm_url"], timeout=0.8) as response:
                sensors = list(_lhm_sensors(json.load(response)))
            cpu_temps = [v for label, v in sensors if "temperature" in label and "distance" not in label and "tjmax" not in label and ("cpu" in label or "package" in label) and 0 < v < 120]
            fans = [v for label, v in sensors if "fan" in label and 0 <= v < 20000]
            if cpu_temps:
                return max(cpu_temps), "LibreHardwareMonitor", max(fans) if fans else None
        except (OSError, ValueError, TimeoutError, KeyError):
            pass
        try:
            for values in psutil.sensors_temperatures().values():
                for sensor in values:
                    if 0 < sensor.current < 120 and ("cpu" in sensor.label.lower() or "package" in sensor.label.lower()):
                        return sensor.current, "system sensor", None
        except (AttributeError, OSError):
            pass
        return None, "unavailable; CPU load is not a temperature reading", None

    def snapshot(self) -> Snapshot:
        temperature, source, fan = self.sensors()
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage(str(__import__("pathlib").Path.home().anchor)).percent
        battery = psutil.sensors_battery()
        found: list[ProcessInfo] = []
        now = time.monotonic()
        elapsed = max(0.001, now - self._previous_sample_time)
        current_cpu: dict[int, float] = {}
        candidate_names = {x.lower() for x in self.config["browsers"] + self.config["background_apps"]}
        for process in psutil.process_iter(["pid", "name", "memory_info", "cpu_times"]):
            try:
                pid = process.pid
                info = process.info
                cpu_times = info.get("cpu_times")
                total_cpu = cpu_times.user + cpu_times.system if cpu_times else 0.0
                current_cpu[pid] = total_cpu
                usage = max(0.0, (total_cpu - self._previous_cpu.get(pid, total_cpu)) / elapsed * 100)
                name = info.get("name") or "?"
                ram_mb = (info["memory_info"].rss / 1048576) if info.get("memory_info") else 0
                executable = None
                command: tuple[str, ...] = ()
                if name.lower() in candidate_names and (usage >= self.config["browser_cpu_percent"] or ram_mb >= self.config["browser_ram_mb"]):
                    try:
                        executable = process.exe()
                        command = tuple(process.cmdline())
                    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                        pass
                found.append(ProcessInfo(pid, info.get("name") or "?", usage,
                    ram_mb, executable, command))
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                continue
        self._previous_cpu = current_cpu
        self._previous_sample_time = now
        found.sort(key=lambda p: (p.cpu, p.ram_mb), reverse=True)
        return Snapshot(temperature, source, fan, cpu, ram, disk,
            battery.percent if battery else None, battery.power_plugged if battery else None,
            tuple(found))
