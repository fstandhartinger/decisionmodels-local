"""Command-line interface for dm-local."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import re
from pathlib import Path

from . import __version__
from .catalog import get_model, load_catalog
from .gateway import Gateway, serve
from .hardware import detect
from .licence import activate, require_install, status as licence_status
from .paths import current_executable, ensure_state, state_dir
from .process import read_process, start_process, stop_process
from .recommend import choose_variant, plan_model
from .remote import remote as remote_command, start_tunnel, stop_tunnel, tunnel_status
from .runtime_selection import installer_runtime
from .runtimes import runtime_class
from .selftest import run as selftest_run
from .storage import download_variant


def _installed_path(root, slug):
    return Path(root) / "run" / ("installed-" + slug + ".json")


def exact_owned_container_names(root):
    """Return only canonical container names recorded by this installer's manifests."""
    names = []
    for path in (Path(root) / "run").glob("installed-*.json"):
        try: install = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError): continue
        slug = install.get("model", {}).get("slug")
        expected = "dm-local-" + str(slug) if slug else None
        if install.get("runtime") == "docker" and install.get("container_name") == expected:
            names.append(expected)
    return sorted(set(names))


def _load_install(root, slug):
    path = _installed_path(root, slug)
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc: raise RuntimeError(f"{slug} is not installed") from exc


def _save_install(root, slug, data):
    path = _installed_path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_config(root):
    try: return json.loads((Path(root) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


def _write_config(root, data):
    path = Path(root) / "config.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try: os.chmod(tmp, 0o600)
    except OSError: pass
    os.replace(tmp, path)


def _json(value): print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _color(text, code):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _text(value):
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(value)


def _backend_spec(model, variant):
    readout = model.get("readout", {})
    serve_spec = variant.get("serve", {})
    endpoint = readout.get("endpoint")
    backend_mode = serve_spec.get("backend_mode") or readout.get("backend_mode")
    if not backend_mode:
        backend_mode = "letter_logprobs" if readout.get("type") == "letter_logprobs" or endpoint == "openai" else "proxy_jev"
    if backend_mode not in ("letter_logprobs", "proxy_jev"):
        raise RuntimeError(f"catalog backend mode {backend_mode!r} is unsupported")
    backend_port = int(serve_spec.get("port", 8741))
    url = serve_spec.get("base_url") or f"http://127.0.0.1:{backend_port}"
    prompt_config = {"prompt_template": readout.get("prompt_template") or serve_spec.get("prompt_template"),
                     "model": serve_spec.get("model_id", model["slug"]), "extra_body": serve_spec.get("extra_body", {})}
    return backend_mode, url, prompt_config


def _gateway_worker(slug):
    root = ensure_state()
    install = _load_install(root, slug)
    config = _read_config(root)
    model = install["model"]
    gateway = Gateway(install["backend_url"], install["backend_mode"], install.get("backend_model"),
                      install.get("prompt_config"), {"slug": slug, "name": model.get("name"),
                      "modalities": model.get("modalities", ["text"]), "question_types": model.get("question_types", {})},
                      api_key=config.get("api_key"), max_options=install.get("max_options", 64))
    serve(install.get("listen", "127.0.0.1"), int(install["gateway_port"]), gateway)


def _start(slug, root=None):
    root = Path(root or ensure_state())
    install = _load_install(root, slug)
    gateway_state = read_process(root, "dm-local-" + slug + "-gateway")
    runtime = runtime_class(install["runtime"])(install["model"], install["variant"], root, install["backend_port"])
    if gateway_state["running"] and runtime.health():
        return install
    if gateway_state["running"]: stop_process(root, "dm-local-" + slug + "-gateway")
    runtime.prepare()
    runtime.start()
    if not runtime._wait_ready(60):
        raise RuntimeError(f"model backend did not become healthy; inspect `dm-local logs {slug}`")
    process_name = "dm-local-" + slug + "-gateway"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([*sys.path, env.get("PYTHONPATH", "")]))
    cmd = [sys.executable, "-m", "dmlocal", "_gateway", slug]
    start_process(root, process_name, cmd, env=env)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{install['gateway_port']}/health", timeout=1) as response:
                if response.status == 200: return install
        except OSError: time.sleep(0.2)
    stop_process(root, process_name)
    runtime.stop()
    raise RuntimeError("local gateway did not become healthy")


def _stop(slug, root=None):
    root = Path(root or ensure_state())
    install = _load_install(root, slug)
    stop_process(root, "dm-local-" + slug + "-gateway")
    runtime = runtime_class(install["runtime"])(install["model"], install["variant"], root, install["backend_port"])
    runtime.stop()
    return install


def _install(args):
    root = ensure_state()
    models = load_catalog()
    model = get_model(args.slug, models)
    hw = detect(root)
    variant, verdict = choose_variant(model, hw, args.variant, args.runtime)
    backend_port = int(variant.get("serve", {}).get("port", 8741))
    config = _read_config(root)
    api_key = args.api_key or config.get("api_key")
    if args.api_key is not None and not args.api_key:
        raise RuntimeError("--api-key cannot be empty")
    if args.listen not in ("127.0.0.1", "0.0.0.0"):
        raise RuntimeError("--listen must be 127.0.0.1 or 0.0.0.0")
    if not 1 <= int(args.port) <= 65535 or not 1 <= backend_port <= 65535:
        raise RuntimeError("gateway/backend ports must be between 1 and 65535")
    if args.listen == "0.0.0.0" and not api_key:
        raise RuntimeError("--listen 0.0.0.0 requires --api-key")
    usage = require_install(model, root, usage=args.usage, accept=(args.accept or args.yes))
    print(f"Using {variant['id']} ({verdict}); declared use: {usage}.")
    weights = download_variant(model, variant, root)
    runtime_name = installer_runtime(variant)
    if runtime_name is None:
        raise RuntimeError("catalog variant has no supported installation runtime")
    cls = runtime_class(runtime_name)
    runtime = cls(model, variant, root, backend_port)
    runtime.prepare()
    backend_mode, backend_url, prompt_config = _backend_spec(model, variant)
    max_options = min(20, int(variant.get("max_options", 20))) if backend_mode == "letter_logprobs" else int(variant.get("max_options", 64))
    listen = args.listen
    if listen == "0.0.0.0": print(_color("Warning: the gateway will listen on every network interface.", "33"), file=sys.stderr)
    if args.api_key:
        config["api_key"] = args.api_key
        _write_config(root, config)
    install = {"model": model, "variant": variant, "runtime": runtime_name, "backend_mode": backend_mode,
               "backend_url": backend_url, "backend_model": prompt_config.get("model"), "prompt_config": prompt_config,
               "gateway_port": int(args.port), "backend_port": backend_port, "listen": listen, "max_options": max_options,
               "weight_files": [str(x) for x in weights], "runtime_path": str(runtime.runtime_dir),
               "container_name": "dm-local-" + args.slug if runtime_name == "docker" else None}
    _save_install(root, args.slug, install)
    if not args.no_start:
        _start(args.slug, root)
        try:
            report = selftest_run(f"http://127.0.0.1:{args.port}", api_key=api_key, model=args.slug)
            print("Self-test passed; p50 latency over five choice runs: " + str(report["latency_p50_ms_5_runs"]) + " ms")
        except Exception:
            _stop(args.slug, root)
            raise
    print(f"Endpoint: http://{listen}:{args.port}")
    print("Try: curl -s http://127.0.0.1:" + str(args.port) + "/v1/models")
    if api_key: print("Inference calls require Authorization: Bearer <your-api-key>.")
    return install


def _list(args):
    models = load_catalog()
    hw = detect(ensure_state())
    output = []
    for model in models.values():
        if model.get("hidden"):
            continue
        plan = plan_model(model, hw)
        output.append({"slug": model["slug"], "name": model["name"], "fit": plan["variants"],
                       "selected": plan["selected"], "installer_policy": model.get("installer_policy", {}).get("status")})
    if args.as_json: _json(output)
    elif not output: print("No verified model entries are bundled yet. Catalog entries will appear here once reviewed.")
    else:
        for row in output:
            selected = f"; recommended {row['selected']}" if row["selected"] else "; no listed variant fits"
            print(f"{row['slug']}: {row['name']}{selected}")


def _plan(args):
    model = get_model(args.slug)
    plan = plan_model(model, detect(ensure_state()))
    plan["variant_details"] = [{"id": v["id"], "min_vram_gb": v.get("min_vram_gb"),
                                 "recommended_vram_gb": v.get("recommended_vram_gb"),
                                 "example_gpus": v.get("example_gpus") or ([v["measured"]["gpu"]] if (v.get("measured") or {}).get("gpu") else []),
                                 "example_cloud_instances": v.get("example_cloud_instances", []),
                                 "runtime": v.get("runtime"), "notes": v.get("notes", "")} for v in model.get("variants", [])]
    if args.as_json: _json(plan)
    else:
        details = {item["id"]: item for item in plan["variant_details"]}
        for row in plan["variants"]:
            reasons = "; ".join(row["reasons"]) or "meets the listed memory requirements"
            detail = details[row["id"]]
            minimum = f"min VRAM {detail['min_vram_gb']:g} GB" if detail["min_vram_gb"] is not None else "min VRAM not listed"
            recommended = f", recommended {detail['recommended_vram_gb']:g} GB" if detail["recommended_vram_gb"] is not None else ""
            print(f"{row['id']}: {row['verdict']} — {minimum}{recommended}; {reasons}")
        print(plan["guidance"])
        for item in plan["variant_details"]:
            if item["example_gpus"] or item["example_cloud_instances"]:
                print(f"{item['id']} examples: GPUs={item['example_gpus']}; cloud={item['example_cloud_instances']}")


def _status(slug, args):
    root = ensure_state()
    install = _load_install(root, slug)
    gateway_state = read_process(root, "dm-local-" + slug + "-gateway")
    runtime = runtime_class(install["runtime"])(install["model"], install["variant"], root, install["backend_port"])
    result = {"slug": slug, "gateway": gateway_state, "backend_healthy": runtime.health(),
              "endpoint": f"http://127.0.0.1:{install['gateway_port']}", "runtime": install["runtime"]}
    if args.as_json: _json(result)
    else: print(f"{slug}: gateway={'running' if gateway_state['running'] else 'stopped'}, backend={'healthy' if result['backend_healthy'] else 'not healthy'}; {result['endpoint']}")


def _logs(slug, lines):
    root = ensure_state()
    paths = [root / "run" / ("dm-local-" + slug + "-backend.log"), root / "run" / ("dm-local-" + slug + "-gateway.log")]
    install = _load_install(root, slug)
    if install["runtime"] == "docker":
        serve = install["variant"].get("serve", {})
        if serve.get("compose_files"):
            command = ["docker", "compose", "-p", "dm-local-" + slug]
            weights = root / "models" / slug
            for value in serve["compose_files"]:
                path = (weights / value).resolve()
                try: path.relative_to(weights.resolve())
                except ValueError as exc: raise RuntimeError("compose file escapes the model directory") from exc
                command.extend(["-f", str(path)])
            command.extend(["logs", "--tail", str(lines)])
        else:
            if install.get("container_name") != "dm-local-" + slug:
                raise RuntimeError("refusing to inspect an unrecognized Docker container name")
            command = ["docker", "logs", "--tail", str(lines), install["container_name"]]
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        print(result.stdout + result.stderr, end="")
    for path in paths:
        if path.exists():
            print(f"--- {path.name} ---")
            print("\n".join(path.read_text(errors="replace").splitlines()[-lines:]))


def _uninstall(slug, keep_weights=False):
    root = ensure_state()
    install = _load_install(root, slug)
    container = install.get("container_name")
    if install["runtime"] == "docker":
        expected = "dm-local-" + slug
        if container != expected:
            raise RuntimeError("refusing to remove an unrecognized Docker container name")
    runtime_value = install.get("runtime_path")
    runtime_path = None
    if runtime_value:
        runtime_path = Path(runtime_value).resolve()
        try: runtime_path.relative_to((root / "runtimes").resolve())
        except ValueError as exc: raise RuntimeError("refusing to remove a runtime path outside the state directory") from exc
    _stop(slug, root)
    try:
        from .service import manage
        manage(slug, False)
    except Exception:
        pass
    if runtime_path and runtime_path.exists(): shutil.rmtree(runtime_path)
    if not keep_weights:
        weight_path = root / "models" / slug
        if weight_path.exists(): shutil.rmtree(weight_path)
    _installed_path(root, slug).unlink(missing_ok=True)
    return {"slug": slug, "removed_weights": not keep_weights, "container_name": container}


def _uninstall_all(yes):
    root = ensure_state()
    if not yes:
        if not sys.stdin.isatty() or input(f"Remove all Decision Models data under {root}? [y/N] ").strip().lower() not in ("y", "yes"):
            raise RuntimeError("uninstall cancelled")
    manifests = sorted((root / "run").glob("installed-*.json"))
    owned_names = set(exact_owned_container_names(root))
    slugs = []
    failures = []
    for path in manifests:
        slug = path.name[len("installed-"):-len(".json")]
        try:
            install = _load_install(root, slug)
            if install.get("runtime") == "docker" and install.get("container_name") not in owned_names:
                raise RuntimeError("manifest does not name an exact dm-local container created by this installer")
            _uninstall(slug, keep_weights=False); slugs.append(slug)
        except Exception as exc:
            failures.append(slug)
            print(f"Could not fully uninstall {slug}: {exc}", file=sys.stderr)
    if failures:
        raise RuntimeError("some installs could not be safely removed; state was preserved: " + ", ".join(failures))
    for record in sorted((root / "run").glob("dm-local-tunnel-*.json")):
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
            name = data.get("name", "")
            if name == record.stem and re.fullmatch(r"dm-local-tunnel-[0-9a-f]{12}", name):
                stop_process(root, name)
        except (OSError, ValueError, RuntimeError):
            continue
    wrapper = Path.home() / ".local" / "bin" / "dm-local"
    try:
        if wrapper.is_file() and "# installed by dm-local bootstrap" in wrapper.read_text(encoding="utf-8"):
            wrapper.unlink()
    except OSError:
        pass
    shutil.rmtree(root)
    return {"removed": slugs, "state_dir": str(root)}


def _service(slug, enable):
    from .service import manage
    if enable: _load_install(ensure_state(), slug)
    result = manage(slug, enable)
    print(json.dumps(result, indent=2))


def _license(args):
    root = ensure_state()
    if args.action == "status":
        result = licence_status(root)
        if args.as_json: _json(result)
        else: print(json.dumps(result, indent=2))
    elif args.action == "declare":
        chosen = args.usage
        print("Usage declaration: " + "\n" + __import__("dmlocal.licence", fromlist=["FREE_TEXT"]).FREE_TEXT)
        if not chosen:
            if not sys.stdin.isatty(): raise RuntimeError("non-interactive declaration requires --usage and --accept")
            chosen = input("Select individual, small_company, or company: ").strip().lower()
        if chosen not in ("individual", "small_company", "company"): raise ValueError("invalid usage declaration")
        if not args.accept:
            if not sys.stdin.isatty(): raise RuntimeError("non-interactive declaration requires --accept")
            if input("Do you accept this usage declaration? [y/N] ").strip().lower() not in ("y", "yes"):
                raise RuntimeError("usage declaration was not accepted")
        config = _read_config(root); config["usage"] = chosen; _write_config(root, config)
        print("Usage declaration saved.")
    elif args.action == "activate":
        if not args.key: raise ValueError("licence activate requires a key")
        result = activate(args.key, root)
        print("Commercial licence verified; expires_at=" + str(result.get("expires_at")))


def _remote(args):
    return remote_command(args.host, args.subcommand, args.port, args.identity, args.local_port, args.remote_port)


def _tunnel(args):
    if args.action == "start": result = start_tunnel(args.host, args.local_port, args.remote_port, args.port, args.identity)
    elif args.action == "stop": result = stop_tunnel(args.host, args.local_port, args.remote_port)
    else: result = tunnel_status(args.host, args.local_port, args.remote_port)
    _json(result)


def parser():
    root = argparse.ArgumentParser(prog="dm-local", description="Install and serve local decision models.")
    commands = root.add_subparsers(dest="command", required=True)
    p = commands.add_parser("doctor"); p.add_argument("--json", dest="as_json", action="store_true")
    p = commands.add_parser("list"); p.add_argument("--json", dest="as_json", action="store_true")
    p = commands.add_parser("plan"); p.add_argument("slug"); p.add_argument("--json", dest="as_json", action="store_true")
    p = commands.add_parser("install"); p.add_argument("slug"); p.add_argument("--variant"); p.add_argument("--runtime", choices=["docker", "venv", "llamacpp", "mlx"])
    p.add_argument("--port", type=int, default=8484); p.add_argument("--listen", default="127.0.0.1"); p.add_argument("--api-key")
    p.add_argument("--usage", choices=["individual", "small_company", "company"]); p.add_argument("--accept", action="store_true")
    p.add_argument("--yes", action="store_true"); p.add_argument("--no-start", action="store_true")
    for name in ("start", "stop", "test"):
        p = commands.add_parser(name); p.add_argument("slug")
    p = commands.add_parser("status"); p.add_argument("slug"); p.add_argument("--json", dest="as_json", action="store_true")
    p = commands.add_parser("logs"); p.add_argument("slug"); p.add_argument("--lines", type=int, default=100)
    p = commands.add_parser("uninstall"); p.add_argument("slug", nargs="?"); p.add_argument("--all", action="store_true"); p.add_argument("--keep-weights", action="store_true"); p.add_argument("--yes", action="store_true")
    p = commands.add_parser("service"); p.add_argument("slug"); group = p.add_mutually_exclusive_group(required=True); group.add_argument("--enable", action="store_true"); group.add_argument("--disable", action="store_true")
    p = commands.add_parser("remote"); p.add_argument("host"); p.add_argument("-p", "--port", type=int); p.add_argument("-i", "--identity"); p.add_argument("--local-port", type=int, default=8484); p.add_argument("--remote-port", type=int, default=8484); p.add_argument("subcommand", nargs=argparse.REMAINDER)
    p = commands.add_parser("tunnel"); p.add_argument("host"); p.add_argument("action", choices=["start", "stop", "status"]); p.add_argument("--port", type=int); p.add_argument("-i", "--identity"); p.add_argument("--local-port", type=int, default=8484); p.add_argument("--remote-port", type=int, default=8484)
    p = commands.add_parser("licence"); p.add_argument("action", nargs="?", choices=["status", "declare", "activate"], default="status"); p.add_argument("key", nargs="?"); p.add_argument("--usage", choices=["individual", "small_company", "company"]); p.add_argument("--accept", action="store_true"); p.add_argument("--json", dest="as_json", action="store_true")
    commands.add_parser("version")
    hidden = commands.add_parser("_gateway", help=argparse.SUPPRESS); hidden.add_argument("slug")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            report = detect(ensure_state())
            if args.as_json: _json(report)
            else: print(json.dumps(report, indent=2))
        elif args.command == "list": _list(args)
        elif args.command == "plan": _plan(args)
        elif args.command == "install": _install(args)
        elif args.command == "start":
            _start(args.slug); print(f"Endpoint ready: http://127.0.0.1:{_load_install(ensure_state(), args.slug)['gateway_port']}")
        elif args.command == "stop": _stop(args.slug); print(f"Stopped {args.slug}.")
        elif args.command == "status": _status(args.slug, args)
        elif args.command == "logs": _logs(args.slug, max(1, args.lines))
        elif args.command == "test":
            install = _load_install(ensure_state(), args.slug)
            result = selftest_run(f"http://127.0.0.1:{install['gateway_port']}", _read_config(ensure_state()).get("api_key"), model=args.slug)
            _json(result)
        elif args.command == "uninstall":
            if args.all:
                if args.slug: raise ValueError("do not pass a slug with uninstall --all")
                _json(_uninstall_all(args.yes))
            else:
                if not args.slug: raise ValueError("uninstall requires a slug or --all")
                _json(_uninstall(args.slug, args.keep_weights))
        elif args.command == "service": _service(args.slug, args.enable)
        elif args.command == "remote": _remote(args)
        elif args.command == "tunnel": _tunnel(args)
        elif args.command == "licence": _license(args)
        elif args.command == "version": print(__version__)
        elif args.command == "_gateway": _gateway_worker(args.slug)
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"dm-local: {exc}", file=sys.stderr)
        return 2
    return 0
