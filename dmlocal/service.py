"""Systemd user and launchd service unit management."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .paths import current_executable


def _command(slug):
    exe = str(current_executable())
    if exe.endswith(".pyz"):
        return [sys.executable, exe, "start", slug]
    return [sys.executable, "-m", "dmlocal", "start", slug]


def manage(slug, enable):
    if sys.platform.startswith("linux"):
        unit_dir = Path.home() / ".config/systemd/user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        unit = unit_dir / f"dm-local-{slug}.service"
        if enable:
            cmd = " ".join('"' + item.replace('"', '\\"') + '"' for item in _command(slug))
            unit.write_text("[Unit]\nDescription=Decision Models local gateway for " + slug +
                            "\nAfter=network.target\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=" + cmd +
                            "\nExecStop=" + " ".join('"' + x.replace('"', '\\"') + '"' for x in _command(slug)[:-2] + ["stop", slug]) +
                            "\n\n[Install]\nWantedBy=default.target\n", encoding="utf-8")
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", unit.name], check=True)
            return {"enabled": True, "unit": str(unit)}
        subprocess.run(["systemctl", "--user", "disable", "--now", unit.name], check=False)
        unit.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        return {"enabled": False, "unit": str(unit)}
    if sys.platform == "darwin":
        directory = Path.home() / "Library/LaunchAgents"
        directory.mkdir(parents=True, exist_ok=True)
        label = "io.decisionmodels.dm-local." + slug
        plist = directory / (label + ".plist")
        if enable:
            log_path = Path.home() / ".decisionmodels" / "run" / ("service-" + slug + ".log")
            payload = {"Label": label, "ProgramArguments": _command(slug), "RunAtLoad": True,
                       "KeepAlive": False, "StandardOutPath": str(log_path), "StandardErrorPath": str(log_path)}
            plist.write_bytes(plistlib.dumps(payload))
            subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], check=True)
            return {"enabled": True, "unit": str(plist)}
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)], check=False)
        plist.unlink(missing_ok=True)
        return {"enabled": False, "unit": str(plist)}
    raise RuntimeError("service management is supported only on Linux systemd or macOS launchd")
