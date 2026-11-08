"""Rilevamento best-effort dell'hardware per il broker LLM."""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import sys

from pathlib import Path
from typing import Any


def detect_hardware() -> dict[str, Any]:
    """Restituisce CPU, RAM, GPU e informazioni di sistema.

    I campi non rilevabili restano ``None``: il chiamante deve trattarli
    come sconosciuti, non come zero.
    """

    info: dict[str, Any] = {
        "platform": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hostname": platform.node(),
        "cpu": {
            "model": None,
            "physical_cores": None,
            "logical_cores": os.cpu_count(),
            "mhz_current": None,
            "mhz_max": None,
            "ghz_current": None,
            "ghz_max": None,
        },
        "memory": {
            "total_bytes": None,
            "available_bytes": None,
            "total_gib": None,
            "available_gib": None,
        },
        "gpus": [],
    }

    if sys.platform == "win32":
        _windows(info)
    elif sys.platform == "darwin":
        _macos(info)
    else:
        _linux(info)

    memory = info["memory"]
    if memory["total_bytes"] is not None:
        memory["total_gib"] = round(
            memory["total_bytes"] / (1024 ** 3),
            2,
        )
    if memory["available_bytes"] is not None:
        memory["available_gib"] = round(
            memory["available_bytes"] / (1024 ** 3),
            2,
        )

    cpu = info["cpu"]
    if cpu["mhz_current"]:
        cpu["ghz_current"] = round(cpu["mhz_current"] / 1000, 3)
    if cpu["mhz_max"]:
        cpu["ghz_max"] = round(cpu["mhz_max"] / 1000, 3)

    return info


def _run(
    command: list[str],
    timeout: float = 2.0,
) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return ""

    return completed.stdout.strip()


# ======================================================
# Windows
# ======================================================


def _windows(info: dict[str, Any]) -> None:

    cpu = info["cpu"]
    memory = info["memory"]

    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        cpu["model"] = str(
            winreg.QueryValueEx(key, "ProcessorNameString")[0]
        ).strip()
        cpu["mhz_max"] = int(
            winreg.QueryValueEx(key, "~MHz")[0]
        )
        winreg.CloseKey(key)
    except Exception:
        pass

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status)
        )
        memory["total_bytes"] = int(status.ullTotalPhys)
        memory["available_bytes"] = int(status.ullAvailPhys)
    except Exception:
        pass

    output = _run(
        ["wmic", "cpu", "get", "NumberOfCores", "/value"]
    )
    match = re.search(r"NumberOfCores=(\d+)", output)
    if match:
        cpu["physical_cores"] = int(match.group(1))

    gpus = _nvidia_gpus()
    if not gpus:
        output = _run(
            [
                "wmic",
                "path",
                "win32_VideoController",
                "get",
                "Name,AdapterRAM",
                "/format:csv",
            ]
        )
        for line in output.splitlines()[1:]:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 4 and parts[-2]:
                gpus.append({
                    "name": parts[-2],
                    "vendor": None,
                    "vram_bytes": _int(parts[-1]),
                    "driver": None,
                    "api": None,
                })
    info["gpus"] = gpus


# ======================================================
# Linux
# ======================================================


def _linux(info: dict[str, Any]) -> None:

    cpu = info["cpu"]
    memory = info["memory"]

    try:
        text = Path("/proc/cpuinfo").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        model = re.search(r"^model name\s*:\s*(.+)$", text, re.M)
        if model:
            cpu["model"] = model.group(1).strip()

        mhz = re.search(r"^cpu MHz\s*:\s*([0-9.]+)", text, re.M)
        if mhz:
            cpu["mhz_current"] = float(mhz.group(1))

        physical = set()
        current_physical = None
        current_core = None

        for line in text.splitlines():
            if line.startswith("physical id"):
                current_physical = line.split(":", 1)[1].strip()
            elif line.startswith("core id"):
                current_core = line.split(":", 1)[1].strip()
            elif not line.strip() and current_physical is not None:
                physical.add((current_physical, current_core))
                current_physical = None
                current_core = None

        if physical:
            cpu["physical_cores"] = len(physical)
    except Exception:
        pass

    try:
        text = Path("/proc/meminfo").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        total = re.search(r"^MemTotal:\s*(\d+)\s*kB", text, re.M)
        available = re.search(
            r"^MemAvailable:\s*(\d+)\s*kB",
            text,
            re.M,
        )
        if total:
            memory["total_bytes"] = int(total.group(1)) * 1024
        if available:
            memory["available_bytes"] = int(available.group(1)) * 1024
    except Exception:
        pass

    gpus = _nvidia_gpus()

    try:
        drm = Path("/sys/class/drm")
        if drm.is_dir():
            for card in sorted(drm.glob("card[0-9]*")):
                vendor_path = card / "device" / "vendor"
                if not vendor_path.is_file():
                    continue
                vendor = vendor_path.read_text().strip()
                if vendor == "0x10de" and gpus:
                    continue
                gpus.append({
                    "name": card.name,
                    "vendor": vendor,
                    "vram_bytes": None,
                    "driver": None,
                    "api": None,
                })
    except Exception:
        pass

    info["gpus"] = _dedupe_gpus(gpus)


# ======================================================
# macOS
# ======================================================


def _macos(info: dict[str, Any]) -> None:

    cpu = info["cpu"]
    memory = info["memory"]

    cpu["model"] = _run(
        ["sysctl", "-n", "machdep.cpu.brand_string"]
    ) or None
    physical = _int(
        _run(["sysctl", "-n", "hw.physicalcpu"])
    )
    logical = _int(
        _run(["sysctl", "-n", "hw.logicalcpu"])
    )
    cpu["physical_cores"] = physical
    cpu["logical_cores"] = logical or cpu["logical_cores"]
    memory["total_bytes"] = _int(
        _run(["sysctl", "-n", "hw.memsize"])
    )

    output = _run(
        ["system_profiler", "SPDisplaysDataType"],
        timeout=4.0,
    )
    gpus = []
    for block in re.split(r"\n\s*\n", output):
        name = re.search(r"Chipset Model:\s*(.+)", block)
        vram = re.search(r"VRAM.*?:\s*(\d+)\s*MB", block)
        if name:
            gpus.append({
                "name": name.group(1).strip(),
                "vendor": None,
                "vram_bytes": (
                    int(vram.group(1)) * 1024 * 1024
                    if vram
                    else None
                ),
                "driver": None,
                "api": "Metal",
            })
    info["gpus"] = gpus


# ======================================================
# GPU helper
# ======================================================


def _nvidia_gpus() -> list[dict[str, Any]]:

    if shutil.which("nvidia-smi") is None:
        return []

    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=3.0,
    )
    gpus = []

    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        vram_mb = _int(parts[1])
        gpus.append({
            "name": parts[0],
            "vendor": "NVIDIA",
            "vram_bytes": (
                vram_mb * 1024 * 1024
                if vram_mb is not None
                else None
            ),
            "driver": parts[2] if len(parts) > 2 else None,
            "api": "CUDA",
        })

    return gpus


def _dedupe_gpus(
    gpus: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    seen = set()
    result = []

    for gpu in gpus:
        key = (gpu.get("name"), gpu.get("vendor"))
        if key in seen:
            continue
        seen.add(key)
        result.append(gpu)

    return result


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
