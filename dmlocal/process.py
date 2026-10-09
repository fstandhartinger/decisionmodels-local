"""Named process and log bookkeeping under the per-user state directory."""
import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

_managed_processes = {}


# Standalone because the installer may be running from a zipapp. The gate makes
# assignment atomic with respect to spawning the requested executable. Keep the
# supervisor alive while any descendants remain, so later CLI invocations can
# still verify its creation time and stop an orphaned subtree safely.
_WINDOWS_SUPERVISOR = """
import ctypes, json, subprocess, sys, time
from ctypes import wintypes as w
if sys.stdin.buffer.read(1) != b'1':
    sys.exit(1)
api = ctypes.WinDLL('kernel32', use_last_error=True)
api.OpenJobObjectW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
api.OpenJobObjectW.restype = w.HANDLE
api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
api.QueryInformationJobObject.restype = w.BOOL
api.CloseHandle.argtypes = [w.HANDLE]
api.CloseHandle.restype = w.BOOL
class Accounting(ctypes.Structure):
    _fields_ = [('times', ctypes.c_longlong * 4), ('faults', w.DWORD),
                ('total', w.DWORD), ('active', w.DWORD), ('terminated', w.DWORD)]
job = api.OpenJobObjectW(4, False, sys.argv[2])
if not job:
    raise ctypes.WinError(ctypes.get_last_error())
try:
    result = subprocess.call(json.loads(sys.argv[1]), stdin=subprocess.DEVNULL)
    while True:
        info = Accounting()
        if not api.QueryInformationJobObject(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.active <= 1:
            break
        time.sleep(.1)
finally:
    api.CloseHandle(job)
sys.exit(result)
"""


def _windows_api():
    """Declare pointer-sized handles explicitly (including on 64-bit Python)."""
    from ctypes import wintypes as w
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "GetExitCodeProcess": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "GetProcessTimes": ([w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4, w.BOOL),
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "OpenJobObjectW": ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "IsProcessInJob": ([w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD,
                                       ctypes.POINTER(w.DWORD)], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _windows_birth(api, handle):
    from ctypes import wintypes as w
    times = [w.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def _windows_job_active(api, job):
    from ctypes import wintypes as w

    class Accounting(ctypes.Structure):
        _fields_ = [("times", ctypes.c_longlong * 4), ("page_faults", w.DWORD),
                    ("total", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]

    info = Accounting()
    if not api.QueryInformationJobObject(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
        raise ctypes.WinError(ctypes.get_last_error())
    return info.active


def _command_digest(command):
    return hashlib.sha256(json.dumps(command, ensure_ascii=True).encode("ascii")).hexdigest()


def _windows_record_handle(data):
    """Return a verified handle, never a PID that can be recycled before termination.

    Creation time binds the exact command recorded at launch to this process;
    membership in its unique job binds all child processes to the same owner.
    Old Windows records without this identity fail closed.
    """
    from ctypes import wintypes as w
    api = _windows_api()
    command = data.get("command")
    job_name = data.get("windows_job")
    if (not isinstance(command, list) or not command or not isinstance(job_name, str)
            or not job_name.startswith("dm-local-")
            or data.get("command_sha256") != _command_digest(command)):
        return api, None, None
    handle = api.OpenProcess(0x1000 | 0x00100000, False, int(data["pid"]))
    job = api.OpenJobObjectW(0x0004 | 0x0008, False, job_name)
    try:
        member = w.BOOL()
        if (handle and job and _windows_birth(api, handle) == data.get("windows_birth")
                and api.WaitForSingleObject(handle, 0) == 258
                and api.IsProcessInJob(handle, job, ctypes.byref(member)) and member.value):
            return api, handle, job
    except OSError:
        pass
    if handle: api.CloseHandle(handle)
    if job: api.CloseHandle(job)
    return api, None, None


def _darwin_argv(pid):
    """Read NUL-delimited argv, rather than ps's lossy multiline rendering."""
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    mib = (ctypes.c_int * 3)(1, 49, int(pid))  # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(1024 * 1024)
    buffer = ctypes.create_string_buffer(size.value)
    libc.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                           ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                           ctypes.c_void_p, ctypes.c_size_t]
    libc.sysctl.restype = ctypes.c_int
    if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        raise OSError(ctypes.get_errno(), "cannot read process argv")
    raw = buffer.raw[:size.value]
    argc = int.from_bytes(raw[:4], sys.byteorder, signed=True)
    start = raw.index(b"\0", 4) + 1  # Skip executable path and padding.
    while start < len(raw) and raw[start] == 0:
        start += 1
    return [os.fsdecode(part) for part in raw[start:].split(b"\0")[:argc]]


def safe_slug(value):
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in value)[:96]


def pidfile(root, name):
    return Path(root) / "run" / (safe_slug(name) + ".json")


def process_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        if os.name == "nt":
            from ctypes import wintypes as w
            api = _windows_api()
            handle = api.OpenProcess(0x1000 | 0x00100000, False, pid)
            if not handle:
                return False
            try:
                code = w.DWORD()
                return bool(api.GetExitCodeProcess(handle, ctypes.byref(code))
                            and code.value == 259 and api.WaitForSingleObject(handle, 0) == 258)
            finally:
                api.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _session_has_member(sid):
    """Whether a process remains in the detached session created for a managed command."""
    if os.name == "nt":
        return process_alive(sid)
    if sys.platform.startswith("linux"):
        try:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    text = (entry / "stat").read_text()
                    _, rest = text.rsplit(")", 1)
                    fields = rest.split()
                    if len(fields) > 3 and fields[0] not in ("Z", "X") and int(fields[3]) == int(sid):
                        return True
                except (OSError, ValueError, IndexError):
                    continue
            return False
        except OSError:
            return process_alive(sid)
    try:
        output = subprocess.run(["ps", "-axo", "pgid=,stat="], capture_output=True, text=True, check=False).stdout
        return any(len(parts) >= 2 and parts[0] == str(sid) and not parts[1].startswith(("Z", "X"))
                   for parts in (line.split() for line in output.splitlines()))
    except OSError:
        return process_alive(sid)


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
            actual = _darwin_argv(pid)
            return (len(actual) == len(expected) and actual[1:] == expected[1:]
                    and Path(actual[0]).resolve() == Path(expected[0]).resolve())
        except (OSError, ValueError, IndexError):
            return False
    if os.name == "nt":
        try:
            api, handle, job = _windows_record_handle(data)
        except (OSError, ValueError, TypeError, KeyError):
            return False
        if not handle:
            return False
        api.CloseHandle(handle)
        api.CloseHandle(job)
        return True
    return False


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
    windows_identity = {}
    try:
        if os.name == "nt":
            # The supervisor cannot spawn the requested command until it is in
            # the job. Descendants inherit membership, closing the spawn race.
            api = _windows_api()
            job_name = "dm-local-" + uuid.uuid4().hex
            job = api.CreateJobObjectW(None, job_name)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            proc = None
            try:
                supervisor = [sys.executable, "-c", _WINDOWS_SUPERVISOR,
                              json.dumps([os.fspath(arg) for arg in command]), job_name]
                proc = subprocess.Popen(supervisor, stdin=subprocess.PIPE, **kwargs)
                if not api.AssignProcessToJobObject(job, int(proc._handle)):
                    raise ctypes.WinError(ctypes.get_last_error())
                windows_identity = {"windows_job": job_name,
                                    "windows_birth": _windows_birth(api, int(proc._handle)),
                                    "command_sha256": _command_digest(list(command))}
                proc.stdin.write(b"1")
                proc.stdin.close()
            except BaseException:
                if proc is not None:
                    api.TerminateJobObject(job, 1)
                    proc.kill()
                    proc.wait(timeout=5)
                raise
            finally:
                api.CloseHandle(job)
        else:
            proc = subprocess.Popen(command, **kwargs)
    finally:
        handle.close()
    # This process is deliberately detached and supervised through its pidfile.
    # Keep the handle while the current CLI process is alive so stop can reap it.
    proc._child_created = False
    _managed_processes[proc.pid] = proc
    payload = {"name": name, "pid": proc.pid, "pgid": proc.pid if os.name != "nt" else None,
               "command": list(command), "started_at": int(time.time()), "log": str(log_path), **windows_identity}
    tmp = record.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, record)
    return payload


def stop_process(root, name, timeout=20):
    record = pidfile(root, name)
    if not record.exists(): return {"stopped": False, "reason": "no pidfile"}
    try: data = json.loads(record.read_text())
    except (OSError, ValueError):
        record.unlink(missing_ok=True)
        return {"stopped": False, "reason": "invalid pidfile removed"}
    pid = data.get("pid")
    if os.name == "nt":
        try:
            api, handle, job = _windows_record_handle(data)
        except (OSError, ValueError, TypeError, KeyError):
            handle = None
        if not handle:
            record.unlink(missing_ok=True)
            return {"stopped": False, "reason": "process already stopped or ownership cannot be verified"}
        try:
            if not api.TerminateJobObject(job, 1):
                raise ctypes.WinError(ctypes.get_last_error())
            deadline = time.monotonic() + max(0, timeout)
            while _windows_job_active(api, job):
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"could not confirm {name}'s process tree stopped")
                time.sleep(0.05)
        finally:
            api.CloseHandle(handle)
            api.CloseHandle(job)
        managed = _managed_processes.pop(int(pid), None)
        if managed is not None:
            managed.wait(timeout=5)
        record.unlink(missing_ok=True)
        return {"stopped": True, "pid": pid}
    leader_matches = _record_matches_process(data)
    pgid = data.get("pgid", pid)
    if pgid != pid:
        raise RuntimeError("managed process record has an unexpected process-group id")
    if sys.platform == "darwin" and not leader_matches and process_alive(pid):
        raise RuntimeError("refusing to stop a process whose command does not match its record")
    if not leader_matches and not _session_has_member(pgid):
        record.unlink(missing_ok=True)
        return {"stopped": False, "reason": "process and its managed group are already stopped"}
    try:
        os.killpg(int(data.get("pgid", pid)), signal.SIGTERM)
    except OSError as exc:
        if getattr(exc, "errno", None) == 3:
            record.unlink(missing_ok=True)
            return {"stopped": False, "reason": "process group already stopped"}
        raise RuntimeError(f"could not stop {name}: {exc}") from exc
    deadline = time.monotonic() + timeout
    while _session_has_member(pid) and time.monotonic() < deadline: time.sleep(0.1)
    still_running = _session_has_member(pid)
    if still_running:
        try:
            os.killpg(int(pid), signal.SIGKILL)
        except OSError: pass
        deadline = time.monotonic() + 2
        while _session_has_member(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
    managed = _managed_processes.pop(int(pid), None)
    if managed is not None:
        try: managed.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired): pass
    record.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def read_process(root, name):
    record = pidfile(root, name)
    try: data = json.loads(record.read_text())
    except (OSError, ValueError): return {"running": False, "pid": None}
    alive = _record_matches_process(data)
    return {"running": alive, "pid": data.get("pid") if alive else None, "log": data.get("log")}
