"""Cross-platform hardware detection using the Python standard library and OS tools."""
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def _run(args, timeout=4):
    if not args or args[0] is None:
        return ""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _ram_gb():
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        data = MEMORYSTATUSEX()
        data.dwLength = ctypes.sizeof(data)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(data)):
            return parse_windows_memory(data.ullTotalPhys, data.ullAvailPhys)
    if platform.system() == "Darwin":
        total = _run(["sysctl", "-n", "hw.memsize"])
        free = _run(["vm_stat"])
        try:
            return parse_sysctl_memory(total, free)
        except (ValueError, AttributeError):
            return None
    try:
        return parse_meminfo(Path("/proc/meminfo").read_text())
    except (OSError, KeyError, ValueError):
        return None


def _gpus():
    query = "name,memory.total,memory.free,compute_cap,driver_version"
    out = _run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    if out:
        rows = parse_nvidia_smi(out)
        if rows:
            return rows
    rocm = _run(["rocm-smi", "--json"])
    if rocm:
        try:
            data = json.loads(rocm)
            rows = []
            for idx, details in data.items():
                vals = details if isinstance(details, dict) else {}
                rows.append({"vendor": "amd", "name": vals.get("Card series", vals.get("Product Name", f"AMD GPU {idx}")),
                             "memory_total_mb": None, "memory_free_mb": None, "driver_version": vals.get("Driver version")})
            return rows
        except (ValueError, AttributeError):
            pass
    return []


def _cuda_version():
    text = _run(["nvidia-smi"])
    match = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)+)", text)
    return match.group(1) if match else None


def parse_nvidia_smi(text):
    rows = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 5: continue
        def number(value):
            try: return float(value)
            except ValueError: return None
        rows.append({"vendor": "nvidia", "name": cols[0], "memory_total_mb": number(cols[1]),
                     "memory_free_mb": number(cols[2]), "compute_cap": cols[3], "driver_version": cols[4]})
    return rows


def parse_meminfo(text):
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            values[key] = int(rest.strip().split()[0]) * 1024
    return {"total": round(values["MemTotal"] / 1e9, 2), "free": round(values["MemAvailable"] / 1e9, 2)}


def parse_sysctl_memory(total_bytes, vm_stat_text):
    page_match = re.search(r"page size of (\d+) bytes", vm_stat_text)
    if not page_match: raise ValueError("macOS vm_stat output is missing page size")
    page_size = int(page_match.group(1))
    pages = sum(int(x.replace(".", "")) for x in re.findall(r"(?:Pages free|Pages inactive|Pages speculative):\s+([0-9.]+)", vm_stat_text))
    return {"total": round(int(total_bytes) / 1e9, 2), "free": round(pages * page_size / 1e9, 2)}


def parse_windows_memory(total_bytes, available_bytes):
    return {"total": round(int(total_bytes) / 1e9, 2), "free": round(int(available_bytes) / 1e9, 2)}


def detect(state_path=None):
    system = platform.system().lower()
    machine = platform.machine().lower()
    gpu = _gpus()
    disk_path = Path(state_path or Path.home())
    try:
        disk_free = round(shutil.disk_usage(disk_path).free / 1e9, 2)
    except OSError:
        disk_free = None
    dmi = {}
    for key in ("sys_vendor", "product_name"):
        try: dmi[key] = Path("/sys/class/dmi/id", key).read_text().strip()
        except OSError: pass
    apple = None
    if system == "darwin" and machine in ("arm64", "aarch64"):
        apple = {"chip": _run(["sysctl", "-n", "machdep.cpu.brand_string"]), "unified_memory_gb": (_ram_gb() or {}).get("total")}
    docker = shutil.which("docker")
    docker_info = _run([docker, "info", "--format", "{{json .Runtimes}}"], timeout=6) if docker else ""
    try: docker_runtimes = json.loads(docker_info) if docker_info else {}
    except ValueError: docker_runtimes = {}
    if not isinstance(docker_runtimes, dict): docker_runtimes = {}
    python_version = platform.python_version()
    try: major, minor = map(int, python_version.split(".")[:2])
    except ValueError: major = minor = 0
    return {
        "os": system, "arch": machine, "platform": f"{system}-{machine}",
        "os_version": platform.mac_ver()[0] if system == "darwin" else platform.release(),
        "libc": {"name": platform.libc_ver()[0], "version": platform.libc_ver()[1]} if system == "linux" else None,
        "wsl2": bool(system == "linux" and "microsoft" in Path("/proc/version").read_text(errors="ignore").lower()) if Path("/proc/version").exists() else False,
        "cpu": platform.processor() or platform.machine(), "cpu_count": os.cpu_count(), "ram_gb": _ram_gb(),
        "disk_free_gb": disk_free, "gpus": gpu, "cuda_driver": next((g.get("driver_version") for g in gpu if g["vendor"] == "nvidia"), None),
        "cuda_version": _cuda_version() if any(g.get("vendor") == "nvidia" for g in gpu) else None,
        "docker": {"available": bool(docker and _run([docker, "--version"])), "nvidia_runtime": bool(docker) and ("nvidia" in docker_runtimes or "nvidia" in _run([docker, "info"], timeout=6).lower())},
        "python": {"version": python_version, "supported": (major, minor) >= (3, 9)},
        "uv": {"available": bool(shutil.which("uv")), "version": (_run(["uv", "--version"]) if shutil.which("uv") else None)},
        "cloud_vendor_dmi": dmi or None, "apple_silicon": apple,
    }
