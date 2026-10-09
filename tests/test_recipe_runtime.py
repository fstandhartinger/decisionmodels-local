import base64
import contextlib
import io
import json
import socket
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import threading
from types import SimpleNamespace

from dmlocal.gateway import Gateway, UnsupportedModalityError, make_handler
from dmlocal.recommend import plan_model
from dmlocal.runtimes.recipe import RecipeRuntime, _safe_extract_tar, allocate_ports, expand_placeholders
from dmlocal.runtime_selection import recipe_errors, requires_errors
from dmlocal.process import read_process
from dmlocal.remote import remote as remote_install
from dmlocal.runtimes.llamacpp import _safe_extract_tar as _safe_extract_llamacpp_tar
from tests.helpers import model_with_variants, variant


def _http_server_script(check_dependency=False):
    dep = "urllib.request.urlopen(f'http://127.0.0.1:{sys.argv[2]}/health', timeout=3).read()\n" if check_dependency else ""
    return "import sys\nimport urllib.request\n" + dep + """from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')
    def log_message(self, *args):
        pass
HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""


class RecipeValidationTests(unittest.TestCase):
    def test_valid_recipe_and_unpinned_packages(self):
        candidate = variant()
        self.assertEqual(recipe_errors(candidate), [])
        candidate["install"].pop("packages")
        self.assertEqual(recipe_errors(candidate), [])
        candidate["install"]["packages"] = ["vllm>=0.3"]
        self.assertIn("install.packages must use exact == versions or HTTPS URLs with #sha256 pins", recipe_errors(candidate))

    def test_recipe_validation_rejects_remote_readiness_urls_without_crashing_on_bad_shape(self):
        candidate = variant()
        candidate["install"]["processes"][0]["ready"]["url"] = "http://127.0.0.1:8080@attacker.example/health"
        self.assertTrue(any("ready.url must be an HTTP loopback URL" in error for error in recipe_errors(candidate)))
        candidate["install"]["processes"][0]["ready"] = "malformed"
        self.assertTrue(recipe_errors(candidate))

    def test_plan_explains_invalid_install_recipe(self):
        candidate = variant()
        candidate["install"]["packages"] = ["torch"]
        plan = plan_model(model_with_variants([candidate]), {
            "os": "linux", "arch": "x86_64", "gpus": [{"vendor": "nvidia", "memory_total_mb": 24000}],
            "docker": {"available": True, "nvidia_runtime": True}, "ram_gb": {"total": 64}, "disk_free_gb": 100,
        })
        row = plan["variants"][0]
        self.assertEqual(row["verdict"], "not_installable")
        self.assertIn("not installable:", row["reasons"][0])
        self.assertIn("exact", row["reasons"][0])

    def test_requires_checks_cuda_driver_compute_and_platform(self):
        candidate = variant()
        candidate["install"]["requires"] = {
            "cuda_min": "12.8", "driver_min": "570", "gpu_arch_min": "sm_80", "platforms": ["linux-nvidia"]
        }
        old = {"os": "linux", "arch": "x86_64", "gpus": [{"vendor": "nvidia", "compute_cap": "7.5", "driver_version": "550.10"}],
               "cuda_version": "12.4", "cuda_driver": "550.10", "docker": {"available": True, "nvidia_runtime": True}}
        errors = requires_errors(candidate, old)
        self.assertTrue(any("CUDA 12.8" in error for error in errors))
        self.assertTrue(any("driver 570" in error for error in errors))
        self.assertTrue(any("compute capability 8" in error for error in errors))
        self.assertEqual(requires_errors(candidate, {**old, "cuda_version": "12.8", "cuda_driver": "570.124",
                                                     "gpus": [{"vendor": "nvidia", "compute_cap": "8.6", "driver_version": "570.124"}]}), [])

    def test_macos_wheel_minimum_blocks_old_or_unknown_os_before_install(self):
        candidate = variant()
        candidate["install"]["requires"] = {"macos_min": "14.0"}
        hardware = {"os": "darwin", "arch": "arm64"}
        for version in (None, "13.6"):
            self.assertTrue(any("macOS 14.0" in error for error in requires_errors(candidate, {**hardware, "os_version": version})))
        self.assertEqual(requires_errors(candidate, {**hardware, "os_version": "14.0.1"}), [])

    def test_glibc_wheel_minimum_rejects_musl_old_and_unknown_libc(self):
        candidate = variant()
        candidate["install"]["requires"] = {"glibc_min": "2.39"}
        for libc in ({}, {"name": "musl", "version": "2.40"}, {"name": "glibc", "version": "2.35"}):
            self.assertTrue(requires_errors(candidate, {"os": "linux", "libc": libc}))
        self.assertEqual(requires_errors(candidate, {"os": "linux", "libc": {"name": "glibc", "version": "2.39"}}), [])


class RecipeRuntimeTests(unittest.TestCase):
    def test_placeholder_expansion_and_stable_port_allocation(self):
        self.assertEqual(expand_placeholders("http://127.0.0.1:{port:api}/{weights}",
                                             {"port:api": 54321, "weights": "/tmp/model"}),
                         "http://127.0.0.1:54321//tmp/model")
        recipe = {"api": {"port": "api"}, "processes": [{"command": ["--port", "{port:api}"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            first = allocate_ports(tmp, "fixture", recipe)
            second = allocate_ports(tmp, "fixture", recipe)
            self.assertEqual(first, second)
            self.assertEqual(json.loads((Path(tmp) / "run/fixture.json").read_text())["ports"], first)
            busy = socket.socket()
            busy.bind(("127.0.0.1", first["api"]))
            third = allocate_ports(tmp, "fixture", recipe)
            busy.close()
            self.assertNotEqual(third["api"], first["api"])

    def test_dry_run_commands_do_not_persist_port_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = model_with_variants([variant()])
            runtime = RecipeRuntime(model, model["variants"][0], tmp)
            commands = runtime.runtime_commands()
            self.assertTrue(commands)
            self.assertFalse(runtime.state_file.exists())

    def test_tar_extraction_rejects_traversal_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.tar.gz"
            with tarfile.open(bad, "w:gz") as archive:
                info = tarfile.TarInfo("../escape.txt")
                data = b"escape"
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            with self.assertRaisesRegex(RuntimeError, "unsafe"):
                _safe_extract_tar(bad, Path(tmp) / "out")
            link = Path(tmp) / "link.tar.gz"
            with tarfile.open(link, "w:gz") as archive:
                info = tarfile.TarInfo("root/link")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../escape"
                archive.addfile(info)
            with self.assertRaisesRegex(RuntimeError, "link"):
                _safe_extract_tar(link, Path(tmp) / "out2")

    def test_pinned_llamacpp_tar_accepts_internal_symlinks_but_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            internal = Path(tmp) / "internal.tar.gz"
            with tarfile.open(internal, "w:gz") as archive:
                data = b"shared library"
                info = tarfile.TarInfo("llama/libcore.so.1")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
                link = tarfile.TarInfo("llama/libcore.so")
                link.type = tarfile.SYMTYPE
                link.linkname = "libcore.so.1"
                archive.addfile(link)
            extracted = Path(tmp) / "safe"
            _safe_extract_llamacpp_tar(internal, extracted)
            self.assertTrue((extracted / "llama/libcore.so").is_symlink())
            self.assertEqual((extracted / "llama/libcore.so").read_bytes(), b"shared library")

            escape = Path(tmp) / "escape.tar.gz"
            with tarfile.open(escape, "w:gz") as archive:
                link = tarfile.TarInfo("llama/libcore.so")
                link.type = tarfile.SYMTYPE
                link.linkname = "../../outside"
                archive.addfile(link)
            with self.assertRaisesRegex(RuntimeError, "escapes"):
                _safe_extract_llamacpp_tar(escape, Path(tmp) / "unsafe")

    def test_ordered_process_startup_readiness_and_reverse_teardown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weights = root / "models/fixture-model"
            weights.mkdir(parents=True)
            recipe = {
                "runtime": "venv",
                "processes": [
                    {"name": "engine", "command": [sys.executable, "-c", _http_server_script(), "{port:engine}"],
                     "ready": {"url": "http://127.0.0.1:{port:engine}/health", "timeout_s": 8}},
                    {"name": "api", "command": [sys.executable, "-c", _http_server_script(check_dependency=True), "{port:api}", "{port:engine}"],
                     "ready": {"url": "http://127.0.0.1:{port:api}/health", "timeout_s": 8}},
                ],
                "api": {"mode": "proxy_jev", "port": "api", "text_path": "/v1/systemone", "image_path": None,
                        "model": None, "auth_header": None},
            }
            model = model_with_variants([variant()])
            model["slug"] = "fixture-model"
            candidate = model["variants"][0]
            candidate["install"] = recipe
            runtime = RecipeRuntime(model, candidate, root)
            runtime.ports = allocate_ports(root, model["slug"], recipe)
            try:
                result = runtime.start()
                self.assertEqual(result["started"], ["dm-local-fixture-model-engine", "dm-local-fixture-model-api"])
                self.assertTrue(runtime.all_ready())
                stopped = []
                from dmlocal.runtimes import recipe as recipe_module
                original_stop = recipe_module.stop_process
                def record_stop(state_root, name, timeout=20):
                    stopped.append(name)
                    return original_stop(state_root, name, timeout)
                with patch.object(recipe_module, "stop_process", side_effect=record_stop):
                    runtime.stop()
                self.assertEqual(stopped, ["dm-local-fixture-model-api", "dm-local-fixture-model-engine"])
                self.assertFalse(read_process(root, "dm-local-fixture-model-api")["running"])
                self.assertFalse(read_process(root, "dm-local-fixture-model-engine")["running"])
            finally:
                runtime.stop()

    def test_compose_env_is_expanded_and_secrets_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = model_with_variants([variant()])
            model["slug"] = "fixture-model"
            candidate = model["variants"][0]
            candidate["install"] = {
                "runtime": "docker-compose", "image": "fixture/image@sha256:" + "a" * 64,
                "processes": [], "api": {"mode": "proxy_jev", "port": "api", "text_path": "/v1/systemone", "image_path": None},
                "compose": {"bundle": "serving/app.tar.gz", "bundle_sha256": "b" * 64, "workdir": "app",
                            "env": {"MODEL_DIR": "{weights}", "API_PORT": "{port:api}", "HF_TOKEN": "do-not-copy",
                                    "OPENAI_API_KEY": "also-secret"}},
            }
            runtime = RecipeRuntime(model, candidate, tmp)
            runtime.ports = {"api": 45678}
            runtime.compose_dir = Path(tmp) / "compose"
            runtime.compose_dir.mkdir()
            path = runtime._write_compose_env()
            env = dict(line.split("=", 1) for line in path.read_text().splitlines())
            self.assertEqual(env["API_PORT"], "45678")
            self.assertEqual(Path(env["MODEL_DIR"]).resolve(), (Path(tmp) / "models/fixture-model").resolve())
            self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")
            self.assertNotIn("HF_TOKEN", env)
            self.assertNotIn("OPENAI_API_KEY", env)


class RecipeGatewayTests(unittest.TestCase):
    def test_proxy_routes_paths_and_auth_header_and_rejects_missing_image_path(self):
        seen = []
        def opener(request, timeout=10):
            headers = {key.lower(): value for key, value in request.header_items()}
            seen.append((request.full_url, headers.get("x-backend-token")))
            return type("Resp", (), {"status": 200, "read": lambda self: json.dumps({
                "answers": {"color": {"choice": "red", "probabilities": {"red": 1.0, "blue": 0.0}, "confidence": 1.0}},
                "usage": {"input_tokens": 2, "output_tokens": 0}}).encode(),
                "__enter__": lambda self: self, "__exit__": lambda self, *args: False})()
        gateway = Gateway("http://127.0.0.1:1234", "proxy_jev", "author-model", model_card={"slug": "fixture"},
                          opener=opener, backend_paths={"text": "/author/text", "image": None},
                          backend_auth_header="X-Backend-Token: local")
        request = {"model": "fixture", "state": "Mia owns a red bicycle.", "questions": {"color": {
            "type": "choice", "instructions": "What color?", "criteria": {"red": None, "blue": None}}}}
        gateway.infer(request)
        image = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (1).to_bytes(4, "big") * 2
        request["images"] = ["data:image/png;base64," + base64.b64encode(image).decode()]
        with self.assertRaises(UnsupportedModalityError):
            gateway.infer(request, multimodal=True)
        self.assertEqual(seen, [("http://127.0.0.1:1234/author/text", "local")])
        gateway.backend_paths["image"] = "/author/image"
        gateway.infer(request, multimodal=True)
        self.assertEqual(seen[-1][0], "http://127.0.0.1:1234/author/image")

    def test_missing_image_path_maps_to_422_unsupported_modality(self):
        gateway = Gateway("http://127.0.0.1:1234", "proxy_jev", model_card={"slug": "fixture"},
                          backend_paths={"text": "/text", "image": None})
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(gateway))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            image = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (1).to_bytes(4, "big") * 2
            request = {"model": "fixture", "state": "A picture.", "images": ["data:image/png;base64," + base64.b64encode(image).decode()],
                       "questions": {"color": {"type": "choice", "instructions": "What color?", "criteria": {"red": None, "blue": None}}}}
            http_request = Request(f"http://127.0.0.1:{server.server_port}/v1/multimodal",
                                  data=json.dumps(request).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as error:
                urlopen(http_request, timeout=3)
            self.assertEqual(error.exception.code, 422)
            self.assertEqual(json.loads(error.exception.read())["error"]["code"], "unsupported_modality")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class RemoteInstallTests(unittest.TestCase):
    def test_missing_remote_python_bootstraps_uv_and_forwards_requested_local_port(self):
        calls = []
        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        output = io.StringIO()
        with patch("dmlocal.remote.shutil.which", return_value="/usr/bin/ssh"), \
             patch("dmlocal.remote._local_pyz", return_value=Path("/tmp/dm-local.pyz")), \
             patch("dmlocal.remote._check_remote_python", return_value=False), \
             patch("dmlocal.remote._remote_uv_bootstrap") as bootstrap, \
             patch("dmlocal.remote.subprocess.run", side_effect=fake_run), \
             patch("dmlocal.remote.start_tunnel") as tunnel, contextlib.redirect_stdout(output):
            result = remote_install("user@gpu-host", ["install", "fixture-model", "--port", "18484"],
                                    local_port=8484, forward_port=18485)
        bootstrap.assert_called_once()
        remote_command = calls[-1][0][-1]
        self.assertIn("uv run --no-project --python 3.12 python", remote_command)
        self.assertIn("install fixture-model --port 18484", remote_command)
        tunnel.assert_called_once_with("user@gpu-host", 18485, 18484, None, None)
        self.assertIn("ssh -N -L 127.0.0.1:18485:127.0.0.1:18484 user@gpu-host", output.getvalue())
        self.assertIn("curl http://127.0.0.1:18485/v1/systemone", output.getvalue())
        self.assertEqual(result["local_endpoint"], "http://127.0.0.1:18485")


if __name__ == "__main__":
    unittest.main()
