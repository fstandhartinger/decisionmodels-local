import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from dmlocal import cli, licence
from tests.helpers import model_with_variants, variant
from dmlocal.runtimes.docker import DockerRuntime


class FakeResponse:
    status = 200
    def read(self): return b'{"valid":true,"plan":"commercial","expires_at":"2099-01-01T00:00:00Z"}'
    def __enter__(self): return self
    def __exit__(self, *args): return False


class LicenceAndUninstallTests(unittest.TestCase):
    def test_free_use_declaration_saved_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = model_with_variants([variant()])
            self.assertEqual(licence.require_install(model, tmp, "individual", accept=True), "individual")
            self.assertEqual(json.loads((Path(tmp) / "config.json").read_text())["usage"], "individual")
            def unexpected(_): raise AssertionError("existing declaration should not prompt")
            self.assertEqual(licence.require_install(model, tmp, input_fn=unexpected), "individual")

    def test_company_needs_verified_commercial_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = model_with_variants([variant()])
            with self.assertRaisesRegex(RuntimeError, "licence activate"):
                licence.require_install(model, tmp, "company", accept=True)
            result = licence.activate("dm-test-key", tmp, opener=lambda *a, **k: FakeResponse())
            self.assertTrue(result["valid"])
            self.assertEqual(licence.require_install(model, tmp, "company", accept=True), "company")
            self.assertNotIn("dm-test-key", json.dumps(licence.status(tmp)))

    def test_noncommercial_model_refuses_company(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = model_with_variants([variant()], policy="supported_noncommercial_only")
            for usage in ("small_company", "company"):
                with self.subTest(usage=usage), self.assertRaisesRegex(RuntimeError, "not installable for company"):
                    licence.require_install(model, tmp, usage, accept=True)

    def test_company_offline_grace_is_bounded_to_fourteen_days_after_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = 1_800_000_000
            config = {"usage": "company", "licence": {"key": "stored", "valid": True, "verified_at": now - 31 * 86400,
                      "expires_at": "2099-01-01T00:00:00Z"}}
            (Path(tmp) / "config.json").write_text(json.dumps(config))
            model = model_with_variants([variant()])
            with patch.object(licence.time, "time", return_value=now):
                result = licence.require_install(model, tmp, accept=True,
                    opener=lambda *a, **k: (_ for _ in ()).throw(URLError("offline")))
            self.assertEqual(result, "company")

    def test_uninstall_removes_only_exact_recorded_container_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "run").mkdir(); (root / "models/fixture-model").mkdir(parents=True)
            runtime_path = root / "runtimes/fixture-model-bf16"; runtime_path.mkdir(parents=True)
            legacy_variant = variant(); legacy_variant.pop("install")
            install = {"model": model_with_variants([legacy_variant]), "variant": legacy_variant, "runtime": "docker",
                       "container_name": "dm-local-fixture-model", "runtime_path": str(runtime_path)}
            (root / "run/installed-fixture-model.json").write_text(json.dumps(install))
            with patch.object(cli, "ensure_state", return_value=root), patch.object(cli, "_stop", return_value=None), \
                 patch.object(cli.subprocess, "run") as run, patch("dmlocal.service.manage"):
                self.assertEqual(cli.exact_owned_container_names(root), ["dm-local-fixture-model"])
                cli._uninstall("fixture-model")
                run.assert_not_called()
            self.assertFalse((root / "models/fixture-model").exists())

    def test_docker_runtime_removes_only_its_exact_container_name(self):
        model = model_with_variants([variant()])
        docker_variant = variant(runtime="docker")
        docker_variant["image"] = "vllm/vllm-openai@sha256:" + "c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3"
        runtime = DockerRuntime(model, docker_variant, "/tmp/dm-local-test-state")
        with patch("dmlocal.runtimes.docker.subprocess.run") as run:
            runtime.stop()
        run.assert_called_once_with(["docker", "rm", "-f", "dm-local-fixture-model"], check=False, capture_output=True)

    def test_uninstall_refuses_noncanonical_container_name_without_docker_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "run").mkdir(); (root / "models/fixture-model").mkdir(parents=True)
            legacy_variant = variant(); legacy_variant.pop("install")
            install = {"model": model_with_variants([legacy_variant]), "variant": legacy_variant, "runtime": "docker",
                       "container_name": "other-container"}
            (root / "run/installed-fixture-model.json").write_text(json.dumps(install))
            with patch.object(cli, "ensure_state", return_value=root), patch.object(cli, "_stop") as stop, \
                 patch.object(cli.subprocess, "run") as run, patch("dmlocal.service.manage"):
                with self.assertRaisesRegex(RuntimeError, "unrecognized Docker"):
                    cli._uninstall("fixture-model")
                stop.assert_not_called(); run.assert_not_called()

    def test_uninstall_all_removes_bootstrap_but_preserves_shared_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / "DecisionModels"
            (root / "run").mkdir(parents=True)
            (root / "bin").mkdir()
            (root / "lib").mkdir()
            (root / "bin/dm-local.cmd").write_text("launcher")
            (root / "lib/dm-local.pyz").write_text("zipapp")
            shared = home / "uv/python/shared-runtime"
            shared.mkdir(parents=True)
            sentinel = shared / "python.exe"
            sentinel.write_bytes(b"shared Python")
            with patch.object(cli, "ensure_state", return_value=root), patch.object(Path, "home", return_value=home):
                result = cli._uninstall_all(True)
            self.assertEqual(result, {"removed": [], "state_dir": str(root)})
            self.assertFalse(root.exists())
            self.assertEqual(sentinel.read_bytes(), b"shared Python")

    def test_uninstall_all_failure_preserves_bootstrap_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / "DecisionModels"
            (root / "run").mkdir(parents=True)
            (root / "bin").mkdir()
            launcher = root / "bin/dm-local.cmd"
            launcher.write_text("launcher")
            manifest = root / "run/installed-fixture-model.json"
            manifest.write_text(json.dumps({"runtime": "llamacpp"}))
            with patch.object(cli, "ensure_state", return_value=root), patch.object(Path, "home", return_value=home), \
                 patch.object(cli, "_uninstall", side_effect=RuntimeError("owned process still running")):
                with self.assertRaisesRegex(RuntimeError, "state was preserved"):
                    cli._uninstall_all(True)
            self.assertEqual(launcher.read_text(), "launcher")
            self.assertTrue(manifest.exists())

    @unittest.skipUnless(os.name == "nt", "native Windows registry path handling")
    def test_uninstall_all_removes_only_owned_user_path_entry(self):
        import winreg
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / "DecisionModels"
            (root / "run").mkdir(parents=True)
            owned = str(root / "bin")
            keep = r"C:\Shared Python;C:\Other App\bin"
            key = MagicMock()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(home)}), \
                 patch.object(cli, "ensure_state", return_value=root), patch.object(Path, "home", return_value=home), \
                 patch.object(winreg, "OpenKey", return_value=key), \
                 patch.object(winreg, "QueryValueEx", return_value=(keep + ";" + owned.upper() + "\\", winreg.REG_EXPAND_SZ)), \
                 patch.object(winreg, "SetValueEx") as update:
                cli._uninstall_all(True)
            update.assert_called_once_with(key.__enter__.return_value, "Path", 0, winreg.REG_EXPAND_SZ, keep)
            self.assertFalse(root.exists())


if __name__ == "__main__": unittest.main()
