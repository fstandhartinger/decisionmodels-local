"""SSH-based install control and local forwarding for remote GPU machines."""
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .paths import ensure_state
from .pins import UV_ASSETS, UV_RELEASE, UV_VERSION
from .process import pidfile, read_process, start_process, stop_process

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@:-]*$")


def _ssh_args(port=None, identity=None, scp=False):
    args = ["scp" if scp else "ssh"]
    if port: args.extend(["-P" if scp else "-p", str(port)])
    if identity: args.extend(["-i", identity])
    return args


def _validate_host(host):
    if not HOST_RE.fullmatch(host):
        raise ValueError("host must be a user@host or host name without shell punctuation")


def _local_pyz():
    candidate = Path(sys.argv[0]).resolve()
    if candidate.suffix == ".pyz" and candidate.is_file(): return candidate
    raise RuntimeError("remote requires the installed dm-local.pyz executable")


def _check_remote_python(ssh, host, port, identity):
    command = "python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)'"
    result = subprocess.run(_ssh_args(port, identity) + ["-t", host, command], check=False)
    return result.returncode == 0


def _remote_uv_bootstrap(ssh, host, port, identity):
    hashes = {key: value["sha256"] for key, value in UV_ASSETS.items()}
    assets = {key: value["file"] for key, value in UV_ASSETS.items()}
    lines = [
        "set -eu",
        "mkdir -p ~/.decisionmodels/bin ~/.decisionmodels/runtimes/uv-" + UV_VERSION,
        "os=$(uname -s); arch=$(uname -m)",
        "case \"$os/$arch\" in",
        f"Linux/x86_64|Linux/amd64) file={assets['x86_64-unknown-linux-gnu']}; hash={hashes['x86_64-unknown-linux-gnu']};;",
        f"Linux/aarch64|Linux/arm64) file={assets['aarch64-unknown-linux-gnu']}; hash={hashes['aarch64-unknown-linux-gnu']};;",
        f"Darwin/arm64|Darwin/aarch64) file={assets['aarch64-apple-darwin']}; hash={hashes['aarch64-apple-darwin']};;",
        f"Darwin/x86_64) file={assets['x86_64-apple-darwin']}; hash={hashes['x86_64-apple-darwin']};;",
        "*) echo 'No pinned uv build for this remote OS/architecture.' >&2; exit 1;;",
        "esac",
        "tmp=$(mktemp -d)",
        f"curl -fsSL {UV_RELEASE}/\"$file\" -o \"$tmp/uv.tgz\"",
        "echo \"$hash  $tmp/uv.tgz\" | (sha256sum -c - 2>/dev/null || shasum -a 256 -c -)",
        "tar -xzf \"$tmp/uv.tgz\" -C \"$tmp\"",
        "find \"$tmp\" -type f -name uv -exec cp {} ~/.decisionmodels/bin/uv \\;",
        "chmod 700 ~/.decisionmodels/bin/uv",
        "rm -rf \"$tmp\"",
        "~/.decisionmodels/bin/uv python install 3.12",
    ]
    script = "\n".join(lines)
    subprocess.run(_ssh_args(port, identity) + ["-t", host, "sh -c " + shlex.quote(script)], check=True)


def remote(host, subcommand, port=None, identity=None, local_port=8484, remote_port=8484, forward_port=None):
    _validate_host(host)
    if not shutil.which("ssh") or not shutil.which("scp"):
        raise RuntimeError("OpenSSH ssh and scp are required")
    subcommand = list(subcommand)
    if subcommand and subcommand[0] == "--": subcommand = subcommand[1:]
    if not subcommand:
        raise ValueError("remote requires a subcommand, for example install <slug>")
    if "--port" in subcommand:
        try: remote_port = int(subcommand[subcommand.index("--port") + 1])
        except (IndexError, ValueError): raise ValueError("remote subcommand --port needs an integer")
        if forward_port is None:
            local_port = remote_port
    if forward_port is not None:
        if not 1 <= int(forward_port) <= 65535:
            raise ValueError("--forward-port must be between 1 and 65535")
        local_port = int(forward_port)
    pyz = _local_pyz()
    subprocess.run(_ssh_args(port, identity) + [host, "mkdir -p ~/.decisionmodels/bin"], check=True)
    remote_path = "~/.decisionmodels/bin/dm-local.pyz"
    subprocess.run(_ssh_args(port, identity, scp=True) + [str(pyz), host + ":" + remote_path], check=True)
    if not _check_remote_python("ssh", host, port, identity):
        print("Remote Python 3.9+ is unavailable; installing the pinned uv runtime.", file=sys.stderr)
        _remote_uv_bootstrap("ssh", host, port, identity)
        runner = "~/.decisionmodels/bin/uv run --no-project --python 3.12 python " + remote_path
    else:
        runner = "python3 " + remote_path
    remote_cmd = runner + " " + " ".join(shlex.quote(arg) for arg in subcommand)
    subprocess.run(_ssh_args(port, identity) + ["-t", host, remote_cmd], check=True)
    if subcommand[0] in ("install", "start") and "--no-start" not in subcommand:
        tunnel = start_tunnel(host, local_port, remote_port, port, identity)
        tunnel_command = _ssh_args(port, identity) + ["-N", "-L", f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}", host]
        print(f"Local endpoint: http://127.0.0.1:{local_port}")
        print("Tunnel command: " + shlex.join(tunnel_command))
        print(f"Try: curl http://127.0.0.1:{local_port}/v1/systemone")
        return {"tunnel": tunnel, "tunnel_command": shlex.join(tunnel_command),
                "local_endpoint": f"http://127.0.0.1:{local_port}"}


def _tunnel_name(host, local_port, remote_port):
    digest = hashlib.sha256(f"{host}|{local_port}|{remote_port}".encode()).hexdigest()[:12]
    return "dm-local-tunnel-" + digest


def start_tunnel(host, local_port=8484, remote_port=8484, port=None, identity=None):
    _validate_host(host)
    name = _tunnel_name(host, local_port, remote_port)
    command = _ssh_args(port, identity) + ["-o", "ExitOnForwardFailure=yes", "-o", "BatchMode=yes",
        "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
        "-N", "-L", f"127.0.0.1:{int(local_port)}:127.0.0.1:{int(remote_port)}", host]
    state = ensure_state()
    current = read_process(state, name)
    if current["running"]: return {"running": True, "pid": current["pid"], "name": name}
    data = start_process(state, name, command)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not read_process(state, name)["running"]:
            raise RuntimeError("SSH tunnel exited; check your SSH key and forwarding permissions")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{int(local_port)}/health", timeout=1) as response:
                if response.status == 200:
                    return {"running": True, "pid": data["pid"], "name": name}
        except (OSError, ValueError):
            time.sleep(0.2)
    stop_process(state, name)
    raise RuntimeError("SSH tunnel did not reach the remote endpoint; check the remote service logs")


def stop_tunnel(host, local_port=8484, remote_port=8484):
    return stop_process(ensure_state(), _tunnel_name(host, local_port, remote_port))


def tunnel_status(host, local_port=8484, remote_port=8484):
    return read_process(ensure_state(), _tunnel_name(host, local_port, remote_port))
