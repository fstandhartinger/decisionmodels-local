import json
import unittest
from pathlib import Path

from dmlocal.hardware import parse_meminfo, parse_nvidia_smi, parse_sysctl_memory, parse_windows_memory

FIXTURES = Path(__file__).parent / "fixtures"


class HardwareParsingTests(unittest.TestCase):
    def test_nvidia_smi_csv(self):
        rows = parse_nvidia_smi((FIXTURES / "nvidia-smi.csv").read_text())
        self.assertEqual([x["name"] for x in rows], ["NVIDIA RTX 4090", "NVIDIA A10"])
        self.assertEqual(rows[0]["memory_total_mb"], 24564.0)
        self.assertEqual(rows[1]["compute_cap"], "8.6")

    def test_linux_meminfo(self):
        memory = parse_meminfo((FIXTURES / "meminfo.txt").read_text())
        self.assertAlmostEqual(memory["total"], 33.55, places=2)
        self.assertAlmostEqual(memory["free"], 16.78, places=2)

    def test_macos_sysctl_and_vm_stat(self):
        memory = parse_sysctl_memory("34359738368", (FIXTURES / "vm-stat.txt").read_text())
        self.assertAlmostEqual(memory["total"], 34.36, places=2)
        self.assertAlmostEqual(memory["free"], 0.50, places=2)

    def test_windows_global_memory_status(self):
        values = json.loads((FIXTURES / "windows-memory.json").read_text())
        memory = parse_windows_memory(values["total_bytes"], values["available_bytes"])
        self.assertAlmostEqual(memory["total"], 34.36, places=2)
        self.assertAlmostEqual(memory["free"], 17.18, places=2)


if __name__ == "__main__": unittest.main()


class MissingToolTests(unittest.TestCase):
    def test_docker_unavailable_daemon_null_runtimes(self):
        from unittest.mock import patch
        from dmlocal.hardware import detect
        def output(args, **kwargs):
            return "null" if "--format" in args else ""
        with patch("dmlocal.hardware.shutil.which", return_value="docker"), patch("dmlocal.hardware._run", side_effect=output):
            self.assertFalse(detect()["docker"]["nvidia_runtime"])

    def test_run_with_missing_executable_returns_empty(self):
        from dmlocal.hardware import _run
        self.assertEqual(_run([None, "--version"]), "")
        self.assertEqual(_run([]), "")
