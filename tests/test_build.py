import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_pyz import build


class ZipappBuildTests(unittest.TestCase):
    def test_build_is_deterministic_and_runnable(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, _ = build(Path(tmp) / "first.pyz")
            first_bytes = first.read_bytes()
            second, _ = build(Path(tmp) / "second.pyz")
            self.assertEqual(hashlib.sha256(first_bytes).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                info = archive.infolist()
                self.assertEqual([x.filename for x in info], sorted(x.filename for x in info))
                self.assertTrue(all(x.date_time == (1980, 1, 1, 0, 0, 0) for x in info))
            result = subprocess.run([sys.executable, str(first), "version"], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "0.1.0")


if __name__ == "__main__": unittest.main()
