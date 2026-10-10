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
from .runtimes import runtime_class
from .runtimes.recipe import RecipeRuntime
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
        if install.get("runtime") == "docker" and (install.get("variant") or {}).get("install"):
            try:
                state = json.loads((Path(root) / "run" / (str(slug) + ".json")).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}
            for name in state.get("processes", []):
                if isinstance(name, str) and name.startswith(expected + "-") and re.fullmatch(r"dm-local-[a-z0-9.-]+-[A-Za-z0-9_.-]+", name):
                    names.append(name)
        elif install.get("runtime") == "docker" and install.get("container_name") == expected:
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
    backend_url = install["backend_url"]
    api_port_name = (((install.get("variant") or {}).get("install") or {}).get("api") or {}).get("port")
    if api_port_name:
        state_file = root / "run" / (slug + ".json")
        fallback = backend_url

        def backend_url():
            try:
                port = json.loads(state_file.read_text(encoding="utf-8"))["ports"][api_port_name]
                return f"http://127.0.0.1:{int(port)}"
            except (OSError, ValueError, KeyError, TypeError):
                return fallback
    gateway = Gateway(backend_url, install["backend_mode"], install.get("backend_model"),
                      install.get("prompt_config"), {"slug": slug, "name": model.get("name"),
                      "modalities": model.get("modalities", ["text"]), "question_types": model.get("question_types", {})},
                      api_key=config.get("api_key"), max_options=install.get("max_options", 64),
                      backend_paths=install.get("backend_paths"),
                      backend_auth_header=install.get("backend_auth_header"))
    serve(install.get("listen", "127.0.0.1"), int(install["gateway_port"]), gateway)


def _start(slug, root=None, runtime=None, prepared=False):
    root = Path(root or ensure_state())
    install = _load_install(root, slug)
    gateway_state = read_process(root, "dm-local-" + slug + "-gateway")
    runtime = runtime or _make_runtime(install, root)
    backend_ready = runtime.health() and (not isinstance(runtime, RecipeRuntime) or runtime.all_ready())
    if gateway_state["running"] and backend_ready:
        return install
    if gateway_state["running"]: stop_process(root, "dm-local-" + slug + "-gateway")
    if not backend_ready:
        try:
            runtime.stop()
        except RuntimeError:
            pass
    if not prepared and not backend_ready:
        runtime.prepare()
    if not backend_ready:
        runtime.start()
    if not _wait_runtime_health(runtime, 60):
        try: runtime.stop()
        except RuntimeError: pass
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
    runtime = _make_runtime(install, root)
    runtime.stop()
    return install


def _make_runtime(install, root):
    if (install.get("variant") or {}).get("install"):
        return RecipeRuntime(install["model"], install["variant"], root, install.get("gateway_port", 8484))
    return runtime_class(install["runtime"])(install["model"], install["variant"], root, install.get("backend_port", 8741))


def _wait_runtime_health(runtime, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if runtime.health():
            return True
        time.sleep(0.5)
    return False


def _install(args):
    root = ensure_state()
    models = load_catalog()
    model = get_model(args.slug, models)
    hw = detect(root)
    variant, verdict = choose_variant(model, hw, args.variant, args.runtime)
    recipe = variant["install"]
    runtime_name = recipe["runtime"]
    config = _read_config(root)
    api_key = args.api_key or config.get("api_key")
    if args.api_key is not None and not args.api_key:
        raise RuntimeError("--api-key cannot be empty")
    if args.listen not in ("127.0.0.1", "0.0.0.0"):
        raise RuntimeError("--listen must be 127.0.0.1 or 0.0.0.0")
    if not 1 <= int(args.port) <= 65535:
        raise RuntimeError("gateway port must be between 1 and 65535")
    if args.listen == "0.0.0.0" and not api_key:
        raise RuntimeError("--listen 0.0.0.0 requires --api-key")
    print("✓ Check hardware — " + variant["id"] + " (" + verdict + ")")
    if args.dry_run:
        print("✓ Licence — would verify the declared usage before downloading")
        extra = recipe.get("extra_weights", [])
        file_count = len(variant.get("files", [])) + sum(len(item.get("files", [])) for item in extra)
        byte_count = sum(int(f.get("size", 0)) for f in variant.get("files", [])) + sum(
            int(f.get("size", 0)) for item in extra for f in item.get("files", []))
        print(f"✓ Download {file_count} files ({byte_count / 1_000_000_000:.2f} GB) — dry run")
        runtime = RecipeRuntime(model, variant, root, args.port)
        for spec in variant.get("files", []):
            url = __import__("dmlocal.storage", fromlist=["hf_url"]).hf_url(model["weights"]["repo"], model["weights"]["revision"], spec["path"])
            print("Would download and verify: " + url + " sha256=" + spec["sha256"])
        for item in recipe.get("extra_weights", []):
            for spec in item.get("files", []):
                url = __import__("dmlocal.storage", fromlist=["hf_url"]).hf_url(item["repo"], item["revision"], spec["path"])
                print("Would download and verify: " + url + " sha256=" + spec["sha256"])
        for item in recipe.get("code", []):
            url = (f"https://github.com/{item['repo']}/releases/download/{item['tag']}/{item['asset']}" if item.get("source") == "github-release"
                   else f"https://codeload.github.com/{item['repo']}/tar.gz/{item['revision']}")
            print("Would download, verify, and safely extract: " + url + " sha256=" + item["sha256"])
        if runtime_name == "docker-compose":
            compose = recipe["compose"]
            url = __import__("dmlocal.storage", fromlist=["hf_url"]).hf_url(model["weights"]["repo"], model["weights"]["revision"], compose["bundle"])
            print("Would download, verify, and safely extract: " + url + " sha256=" + compose["bundle_sha256"])
            print("Would write the verified Compose environment to .env, then remove it with docker compose down on stop")
        if runtime_name == "llamacpp":
            from .runtimes.llamacpp import platform_key
            from .pins import require_llama_asset
            asset = require_llama_asset(platform_key(variant))
            print("Would download and verify: " + asset["url"] + " sha256=" + asset["sha256"])
        print(f"✓ Set up runtime — {runtime_name}")
        import shlex
        for command in runtime.runtime_commands():
            print("Would run: " + shlex.join(command))
        if not args.no_start:
            print("✓ Start — dry run")
            print("✓ Self-test — dry run")
        else:
            print("✓ Start — skipped by --no-start")
            print("✓ Self-test — skipped by --no-start")
        print(f"Endpoint: http://{args.listen}:{args.port}")
        print(f"Try: curl -s http://127.0.0.1:{args.port}/v1/models")
        print(f"Manage with: dm-local stop {args.slug} | dm-local uninstall {args.slug}")
        return {"slug": args.slug, "dry_run": True}

    usage = require_install(model, root, usage=args.usage, accept=(args.accept or args.yes))
    print(f"✓ Licence — declared use: {usage}")
    extra = recipe.get("extra_weights", [])
    file_count = len(variant.get("files", [])) + sum(len(item.get("files", [])) for item in extra)
    byte_count = sum(int(f["size"]) for f in variant.get("files", [])) + sum(
        int(f["size"]) for item in extra for f in item.get("files", []))
    print(f"Download {file_count} files ({byte_count / 1_000_000_000:.2f} GB)")
    weights = download_variant(model, variant, root)
    print(f"✓ Download {file_count} files ({byte_count / 1_000_000_000:.2f} GB)")
    api = recipe["api"]
    backend_mode = api["mode"]
    runtime = RecipeRuntime(model, variant, root, args.port)
    runtime.prepare()
    backend_port = runtime.ports[api["port"]]
    backend_url = f"http://127.0.0.1:{backend_port}"
    prompt_config = {"prompt_template": model.get("readout", {}).get("prompt_template"), "model": api.get("model") or args.slug}
    backend_paths = {"text": api.get("text_path"), "image": api.get("image_path")}
    max_options = min(20, int(variant.get("max_options", 20))) if backend_mode == "letter_logprobs" else int(variant.get("max_options", 64))
    listen = args.listen
    if listen == "0.0.0.0": print(_color("Warning: the gateway will listen on every network interface.", "33"), file=sys.stderr)
    if args.api_key:
        config["api_key"] = args.api_key
        _write_config(root, config)
    install = {"model": model, "variant": variant, "runtime": runtime_name, "backend_mode": backend_mode,
               "backend_url": backend_url, "backend_model": api.get("model") or prompt_config.get("model"), "prompt_config": prompt_config,
               "backend_paths": backend_paths, "backend_auth_header": api.get("auth_header"),
               "gateway_port": int(args.port), "backend_port": backend_port, "listen": listen, "max_options": max_options,
               "weight_files": [str(x) for x in weights], "runtime_path": str(runtime.runtime_dir),
               "container_name": "dm-local-" + args.slug if runtime_name == "docker" and not variant.get("install") else None}
    _save_install(root, args.slug, install)
    print(f"✓ Set up runtime — {runtime_name}")
    if not args.no_start:
        _start(args.slug, root, runtime=runtime, prepared=True)
        print("✓ Start — model processes and gateway are ready")
        try:
            report = selftest_run(f"http://127.0.0.1:{args.port}", api_key=api_key, model=args.slug,
                                  image=bool(backend_paths.get("image")))
            print("Self-test passed; p50 latency over five choice runs: " + str(report["latency_p50_ms_5_runs"]) + " ms")
            print("✓ Self-test")
        except Exception:
            _stop(args.slug, root)
            raise
    else:
        print("✓ Start — skipped by --no-start")
        print("✓ Self-test — skipped by --no-start")
    print(f"Endpoint: http://{listen}:{args.port}")
    print("Try: curl -s http://127.0.0.1:" + str(args.port) + "/v1/models")
    print(f"Stop or remove it with: dm-local stop {args.slug} | dm-local uninstall {args.slug}")
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
            if row["installer_policy"] == "on_request": selected = "; local install on request (not in the one-command installer)"
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
    runtime = _make_runtime(install, root)
    backend_healthy = runtime.health() and (not isinstance(runtime, RecipeRuntime) or runtime.all_ready())
    result = {"slug": slug, "gateway": gateway_state, "backend_healthy": backend_healthy,
              "endpoint": f"http://127.0.0.1:{install['gateway_port']}", "runtime": install["runtime"]}
    if args.as_json: _json(result)
    else: print(f"{slug}: gateway={'running' if gateway_state['running'] else 'stopped'}, backend={'healthy' if result['backend_healthy'] else 'not healthy'}; {result['endpoint']}")


def _logs(slug, lines):
    root = ensure_state()
    paths = [root / "run" / ("dm-local-" + slug + "-backend.log"), root / "run" / ("dm-local-" + slug + "-gateway.log")]
    install = _load_install(root, slug)
    if install["runtime"] == "docker":
        if (install.get("variant") or {}).get("install"):
            try:
                state = json.loads((root / "run" / (slug + ".json")).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}
            for name in state.get("processes", []):
                if not isinstance(name, str) or not name.startswith("dm-local-" + slug + "-"):
                    continue
                result = subprocess.run(["docker", "logs", "--tail", str(lines), name], check=False, text=True, capture_output=True)
                print(f"--- {name} ---\n" + result.stdout + result.stderr, end="")
        else:
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
    elif (install.get("variant") or {}).get("install"):
        if install.get("runtime") == "docker-compose":
            runtime = _make_runtime(install, root)
            runtime._download_compose_bundle()
            result = subprocess.run(["docker", "compose", "-p", "dm-local-" + slug, "logs", "--tail", str(lines)],
                                    cwd=runtime.compose_dir, check=False, text=True, capture_output=True)
            print(result.stdout + result.stderr, end="")
        for proc in install["variant"]["install"].get("processes", []):
            path = root / "run" / ("dm-local-" + slug + "-" + proc["name"] + ".log")
            if path.exists():
                print(f"--- {path.name} ---")
                print("\n".join(path.read_text(errors="replace").splitlines()[-lines:]))
    for path in paths:
        if path.exists():
            print(f"--- {path.name} ---")
            print("\n".join(path.read_text(errors="replace").splitlines()[-lines:]))


def _uninstall(slug, keep_weights=False):
    root = ensure_state()
    install = _load_install(root, slug)
    container = install.get("container_name")
    if install["runtime"] == "docker" and not (install.get("variant") or {}).get("install"):
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
    support_path = root / "support" / slug
    if support_path.is_symlink():
        raise RuntimeError("refusing to remove a linked support directory")
    if support_path.exists():
        support_path.resolve().relative_to((root / "support").resolve())
        shutil.rmtree(support_path)
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
            recipe_backed = bool((install.get("variant") or {}).get("install"))
            if install.get("runtime") == "docker" and not recipe_backed and install.get("container_name") not in owned_names:
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
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        default_root = Path(os.environ["LOCALAPPDATA"]) / "DecisionModels"
        if root.resolve() == default_root.resolve():
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as env_key:
                    user_path, kind = winreg.QueryValueEx(env_key, "Path")
                    owned_bin = os.path.normcase(str(default_root / "bin").rstrip("\\/"))
                    remaining = [entry for entry in user_path.split(";") if os.path.normcase(entry.rstrip("\\/")) != owned_bin]
                    if len(remaining) != len(user_path.split(";")):
                        winreg.SetValueEx(env_key, "Path", 0, kind, ";".join(remaining))
            except FileNotFoundError:
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
    return remote_command(args.host, args.subcommand, args.port, args.identity, args.local_port, args.remote_port,
                          forward_port=args.forward_port)


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
    p = commands.add_parser("install"); p.add_argument("slug"); p.add_argument("--variant"); p.add_argument("--runtime", choices=["docker", "docker-compose", "venv", "llamacpp", "mlx"])
    p.add_argument("--port", type=int, default=8484); p.add_argument("--listen", default="127.0.0.1"); p.add_argument("--api-key")
    p.add_argument("--usage", choices=["individual", "small_company", "company"]); p.add_argument("--accept", action="store_true")
    p.add_argument("--yes", action="store_true"); p.add_argument("--no-start", action="store_true"); p.add_argument("--dry-run", action="store_true")
    for name in ("start", "stop", "test"):
        p = commands.add_parser(name); p.add_argument("slug")
    p = commands.add_parser("status"); p.add_argument("slug"); p.add_argument("--json", dest="as_json", action="store_true")
    p = commands.add_parser("logs"); p.add_argument("slug"); p.add_argument("--lines", type=int, default=100)
    p = commands.add_parser("uninstall"); p.add_argument("slug", nargs="?"); p.add_argument("--all", action="store_true"); p.add_argument("--keep-weights", action="store_true"); p.add_argument("--yes", action="store_true")
    p = commands.add_parser("service"); p.add_argument("slug"); group = p.add_mutually_exclusive_group(required=True); group.add_argument("--enable", action="store_true"); group.add_argument("--disable", action="store_true")
    p = commands.add_parser("remote"); p.add_argument("host"); p.add_argument("-p", "--port", type=int); p.add_argument("-i", "--identity"); p.add_argument("--local-port", type=int, default=8484); p.add_argument("--remote-port", type=int, default=8484); p.add_argument("--forward-port", type=int); p.add_argument("subcommand", nargs=argparse.REMAINDER)
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
            result = selftest_run(f"http://127.0.0.1:{install['gateway_port']}", _read_config(ensure_state()).get("api_key"), model=args.slug,
                                  image=bool((install.get("backend_paths") or {}).get("image")))
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
