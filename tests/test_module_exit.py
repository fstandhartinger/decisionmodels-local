import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ModuleExitTests(unittest.TestCase):
    def test_failed_module_command_returns_nonzero_to_automation(self):
        with tempfile.TemporaryDirectory() as root:
            env = {**os.environ, "HOME": root, "USERPROFILE": root, "LOCALAPPDATA": root}
            result = subprocess.run([sys.executable, "-m", "dmlocal", "licence", "activate"],
                                    cwd=Path(__file__).resolve().parents[1], env=env,
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("licence activate requires a key", result.stderr)
