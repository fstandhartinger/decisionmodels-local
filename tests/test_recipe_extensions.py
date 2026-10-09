"""Offline tests: no author imports, downloads, uv execution, weights, or GPUs."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dmlocal.runtimes.recipe import RecipeRuntime
from tests.helpers import model_with_variants, variant


def support(path="server.py", content="print('fixture')\n"):
    return {"path": path, "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}


class RecipeExtensionTests(unittest.TestCase):
    def runtime(self, root):
        candidate = variant()
        candidate["install"]["packages"] = []
        return RecipeRuntime(model_with_variants([candidate]), candidate, root)

    def locked_runtime(self, root, verified=True):
        runtime = self.runtime(root)
        spec = {"id": "author", "source": "github", "repo": "owner/project", "revision": "a" * 40,
                "sha256": "b" * 64, "dest": "code/project"}
        runtime.recipe["code"] = [spec]
        runtime.recipe["venv"] = {"lockfile": {"manager": "uv", "code_id": "author", "path": "app/uv.lock"}}
        checkout = runtime.weights / spec["dest"]
        runtime.code_dirs[spec["dest"]] = str(checkout)
        project = checkout / "app"
        project.mkdir(parents=True)
        (project / "uv.lock").write_text("version = 1\n")
        (project / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
        if verified:
            (checkout / ".dm-local-source.json").write_text(json.dumps({k: spec[k] for k in ("repo", "revision", "sha256")}))
        return runtime, checkout, project

    def test_support_bytes_hash_placeholder_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            spec = support("nested/server.py", "# café\r\nprint('ok')\n")
            runtime.recipe["support_files"] = [spec]
            runtime._write_support_files()
            target = runtime.support_dir / spec["path"]
            self.assertEqual(target.read_bytes(), spec["content"].encode("utf-8"))
            self.assertEqual(runtime._mapping()["support_dir"], runtime.support_dir)
            target.write_text("old")
            runtime._write_support_files()
            self.assertEqual(target.read_bytes(), spec["content"].encode("utf-8"))
            self.assertFalse(list(target.parent.glob(".dm-support-*")))

    def test_entire_batch_hash_checked_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            bad = support("bad.py")
            bad["sha256"] = "0" * 64
            runtime.recipe["support_files"] = [support(), bad]
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                runtime._write_support_files()
            self.assertFalse(runtime.support_dir.exists())

    def test_unsafe_paths_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            for path in ("../escape.py", "/escape.py", "a/../../escape.py", "a\\escape.py", "C:/escape.py",
                         "./server.py", "a//server.py", "a/./server.py", "", "a/", "nul.py", "server.py.", "x\x00.py"):
                with self.subTest(path=path):
                    runtime.recipe["support_files"] = [support(path)]
                    with self.assertRaises(ValueError):
                        runtime._write_support_files()
            self.assertFalse(runtime.support_dir.exists())

    def test_symlink_escape_in_root_parent_and_leaf_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            for relative in ("nested/server.py", "server.py"):
                runtime.support_dir.mkdir(parents=True, exist_ok=True)
                link = runtime.support_dir / ("nested" if relative.startswith("nested") else "server.py")
                link.symlink_to(outside if relative.startswith("nested") else outside / "victim.py")
                runtime.recipe["support_files"] = [support(relative)]
                with self.assertRaisesRegex(RuntimeError, "symlink"):
                    runtime._write_support_files()
                link.unlink()
            runtime.support_dir.rmdir()
            runtime.support_dir.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                runtime._write_support_files()
            self.assertEqual(list(outside.iterdir()), [])

    def test_duplicate_casefolded_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            runtime.recipe["support_files"] = [support("server.py"), support("SERVER.py")]
            with self.assertRaisesRegex(ValueError, "duplicate"):
                runtime._write_support_files()
            self.assertFalse(runtime.support_dir.exists())

    def test_frozen_sync_uses_pinned_uv_project_python_and_clean_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, checkout, project = self.locked_runtime(tmp)
            expected_python = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            def sync(command, **kwargs):
                self.assertEqual(command, [str(Path("/pinned/uv")), "sync", "--frozen", "--project", str(project), "--python", "3.12"])
                env = kwargs["env"]
                for key in ("HF_TOKEN", "OPENAI_API_KEY", "VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONHOME", "PYTHONPATH"):
                    self.assertNotIn(key, env)
                self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(project / ".venv"))
                self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")
                expected_python.parent.mkdir(parents=True)
                expected_python.touch()
            with patch("dmlocal.uv.ensure_uv", return_value=Path("/pinned/uv")) as pinned, \
                    patch("dmlocal.runtimes.recipe.subprocess.run", side_effect=sync) as run, \
                    patch.dict(os.environ, {"HF_TOKEN": "fixture", "OPENAI_API_KEY": "fixture", "VIRTUAL_ENV": "/foreign",
                                            "UV_PROJECT_ENVIRONMENT": "/foreign", "PYTHONPATH": "/foreign"}):
                runtime._prepare_python()
                pinned.assert_called_once_with(runtime.root)
                self.assertEqual(run.call_count, 1)
                command, env, cwd = runtime._expanded_process({"command": ["python", "{support_dir}/server.py"],
                                                             "cwd": "{code_author}/app", "env": {"HF_TOKEN": "fixture"}})
            self.assertEqual(command[0], str(expected_python))
            self.assertEqual(env["VIRTUAL_ENV"], str(project / ".venv"))
            self.assertEqual(env["PATH"].split(os.pathsep)[0], str(expected_python.parent))
            self.assertNotIn("HF_TOKEN", env)
            self.assertEqual(cwd, project)
            self.assertEqual(runtime._mapping()["code_author"], str(checkout))

    def test_missing_or_wrong_checkout_marker_prevents_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, checkout, project = self.locked_runtime(tmp, verified=False)
            with patch("dmlocal.uv.ensure_uv") as uv, patch("dmlocal.runtimes.recipe.subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError, "verified"):
                    runtime._prepare_python()
                (checkout / ".dm-local-source.json").write_text('{}')
                with self.assertRaisesRegex(RuntimeError, "marker"):
                    runtime._prepare_python()
                uv.assert_not_called()
                run.assert_not_called()

    def test_lock_validation_rejects_escapes_missing_files_unlocked_overlays_and_wrong_manager(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, checkout, project = self.locked_runtime(tmp)
            lock = runtime.recipe["venv"]["lockfile"]
            for key, value, pattern in (("path", "../uv.lock", "relative"), ("path", "app/other.lock", "uv.lock"),
                                        ("code_id", "unknown", "code_id"), ("manager", "pip", "manager")):
                original = lock[key]
                lock[key] = value
                with self.assertRaisesRegex(ValueError, pattern):
                    runtime._lock_project()
                lock[key] = original
            runtime.recipe["packages"] = ["fixture==1.0"]
            with self.assertRaisesRegex(ValueError, "combined"):
                runtime._lock_project()
            runtime.recipe["packages"] = []
            runtime.recipe["code"][0]["pip_install"] = True
            with self.assertRaisesRegex(ValueError, "combined"):
                runtime._lock_project()
            runtime.recipe["code"][0]["pip_install"] = False
            (project / "uv.lock").unlink()
            with self.assertRaisesRegex(RuntimeError, "contain"):
                runtime._lock_project()

    def test_dry_run_renders_frozen_sync_without_downloads_or_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            runtime.recipe["code"] = [{"id": "author", "dest": "code/author"}]
            runtime.recipe["venv"] = {"lockfile": {"code_id": "author", "path": "uv.lock", "manager": "uv"}}
            with patch("dmlocal.uv.ensure_uv") as uv, patch("dmlocal.runtimes.recipe.subprocess.run") as run:
                commands = runtime.runtime_commands()
                uv.assert_not_called()
                run.assert_not_called()
            project = runtime.weights / "code/author"
            self.assertEqual(commands[0][:5], ["uv", "sync", "--frozen", "--project", str(project)])
            self.assertEqual(commands[1][0], str(project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_frozen_project_extras_and_console_script_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, checkout, project = self.locked_runtime(tmp)
            lock = runtime.recipe["venv"]["lockfile"]
            lock["extras"] = ["serve"]
            commands = runtime.runtime_commands()
            self.assertEqual(commands[0][-2:], ["--extra", "serve"])
            entry = runtime.venv_dir / ("Scripts" if os.name == "nt" else "bin") / "author-server"
            entry.parent.mkdir(parents=True)
            entry.touch()
            command, env, cwd = runtime._expanded_process({"command": ["author-server"], "cwd": "{code_author}/app"})
            self.assertEqual(command, [str(entry)])
            lock["extras"] = ["--unlocked"]
            with self.assertRaisesRegex(ValueError, "extras"):
                runtime.runtime_commands()

    def test_lock_path_and_project_venv_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, checkout, project = self.locked_runtime(tmp)
            lock = project / "uv.lock"
            lock.unlink()
            outside = Path(tmp) / "foreign.lock"
            outside.write_text("untrusted")
            lock.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                runtime._lock_project()
            lock.unlink()
            lock.write_text("locked")
            (project / ".venv").symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                runtime._lock_project()

    def test_atomic_failure_preserves_existing_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            runtime.recipe["support_files"] = [support()]
            runtime.support_dir.mkdir(parents=True)
            target = runtime.support_dir / "server.py"
            target.write_bytes(b"previous")
            with patch("dmlocal.runtimes.recipe.os.replace", side_effect=OSError("fixture failure")):
                with self.assertRaisesRegex(OSError, "fixture failure"):
                    runtime._write_support_files()
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertFalse(list(runtime.support_dir.glob(".dm-support-*")))

    @unittest.skipUnless(os.name == "posix", "directory-handle writes are Unix-specific")
    def test_concurrent_support_directory_link_swap_cannot_write_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            runtime.recipe["support_files"] = [support("nested/server.py")]
            outside = Path(tmp) / "outside"
            outside.mkdir()
            original_replace = os.replace
            def swap_then_replace(source, target, **kwargs):
                parent = runtime.support_dir / "nested"
                parent.rename(runtime.support_dir / "original")
                parent.symlink_to(outside, target_is_directory=True)
                return original_replace(source, target, **kwargs)
            with patch("dmlocal.runtimes.recipe.os.replace", side_effect=swap_then_replace):
                runtime._write_support_files()
            self.assertFalse((outside / "server.py").exists())
            self.assertEqual((runtime.support_dir / "original/server.py").read_bytes(), support()["content"].encode())

    def test_docker_dry_run_mounts_support_directory_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.runtime(tmp)
            runtime.runtime_name = runtime.recipe["runtime"] = "docker"
            runtime.recipe["image"] = "fixture/image@sha256:" + "a" * 64
            runtime.recipe["support_files"] = [support()]
            runtime.recipe["processes"][0]["command"] = ["{python}", "{support_dir}/server.py"]
            command = runtime.runtime_commands()[-1]
            self.assertIn(str(runtime.support_dir) + ":" + str(runtime.support_dir) + ":ro", command)
            self.assertEqual(command[-2:], ["python3", str(runtime.support_dir) + "/server.py"])
            self.assertFalse(runtime.support_dir.exists())

    def test_prepare_downloads_code_before_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, checkout, project = self.locked_runtime(tmp)
            events = []
            with patch.object(runtime, "_download_code", side_effect=lambda spec: events.append("download") or checkout), \
                    patch.object(runtime, "_prepare_python", side_effect=lambda: events.append("sync")):
                runtime.prepare()
            self.assertEqual(events, ["download", "sync"])


if __name__ == "__main__":
    unittest.main()
