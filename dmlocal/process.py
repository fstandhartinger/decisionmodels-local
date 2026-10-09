"""Named process and log bookkeeping under the per-user state directory."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def safe_slug(value):
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in value)[:96]


def pidfile(root, name):
    return Path(root) / "run" / (safe_slug(name) + ".json")


def process_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _record_matches_process(data):
    pid = data.get("pid")
    if not process_alive(pid): return False
    expected = [str(x) for x in data.get("command", [])]
    if not expected: return False
    if sys.platform.startswith("linux"):
        try:
            actual = [part.decode(errors="replace") for part in (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0") if part]
            return actual[:len(expected)] == expected
        except OSError:
            return False
    if sys.platform == "darwin":
        try:
            output = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False).stdout.strip()
            return bool(output and Path(expected[0]).name in output and all(arg in output for arg in expected[1:]))
        except OSError:
            return False
    return True


def start_process(root, name, command, cwd=None, env=None):
    run = Path(root) / "run"
    run.mkdir(parents=True, exist_ok=True)
    record = pidfile(root, name)
    if record.exists():
        try:
            old = json.loads(record.read_text())
            if _record_matches_process(old):
                raise RuntimeError(f"{name} is already running (pid {old['pid']})")
        except (ValueError, OSError):
            pass
    log_path = run / (safe_slug(name) + ".log")
    handle = log_path.open("ab", buffering=0)
    kwargs = {"stdout": handle, "stderr": subprocess.STDOUT, "cwd": str(cwd) if cwd else None, "env": env,
              "close_fds": True}
    if os.name == "nt": kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else: kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(command, **kwargs)
    finally:
        handle.close()
    payload = {"name": name, "pid": proc.pid, "command": list(command), "started_at": int(time.time()), "log": str(log_path)}
    tmp = record.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, record)
    return payload


def stop_process(root, name, timeout=10):
    record = pidfile(root, name)
    if not record.exists(): return {"stopped": False, "reason": "no pidfile"}
    try: data = json.loads(record.read_text())
    except (OSError, ValueError):
        record.unlink(missing_ok=True)
        return {"stopped": False, "reason": "invalid pidfile removed"}
    pid = data.get("pid")
    if not _record_matches_process(data):
        record.unlink(missing_ok=True)
        return {"stopped": False, "reason": "process already stopped or its PID now belongs to another command"}
    try:
        if os.name == "nt": os.kill(int(pid), signal.SIGTERM)
        else:
            if os.getpgid(int(pid)) != int(pid):
                raise RuntimeError("managed process is no longer the leader of its own process group")
            os.killpg(int(pid), signal.SIGTERM)
    except OSError as exc:
        raise RuntimeError(f"could not stop {name}: {exc}") from exc
    deadline = time.monotonic() + timeout
    while process_alive(pid) and time.monotonic() < deadline: time.sleep(0.1)
    if process_alive(pid):
        try:
            if os.name == "nt": os.kill(int(pid), signal.SIGKILL)
            else: os.killpg(int(pid), signal.SIGKILL)
        except OSError: pass
    record.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def read_process(root, name):
    record = pidfile(root, name)
    try: data = json.loads(record.read_text())
    except (OSError, ValueError): return {"running": False, "pid": None}
    alive = _record_matches_process(data)
    return {"running": alive, "pid": data.get("pid") if alive else None, "log": data.get("log")}
