import json
import tempfile
import unittest
from pathlib import Path

from dmlocal import licence
from dmlocal.runtime_selection import recipe_errors, requires_errors
from tests.helpers import model_with_variants, variant

CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "models"

# Union of the open JevBench board's top 10 by Capability Score and top 10 by Composite Score (board v1.7.43, 2026-10-10).
UNION = {"quyet-1-0-large", "jeff-1-0-large", "decisio-gemma-4-31b-v080", "deck31b", "rene-1-31b-fp8", "h2o-lightning-4b",
         "bobcat-flash-1.2", "surogate-rune-26b-a4b-v3", "decider-12b", "xor-26b-a4b", "torchcast-decision-12b",
         "winnow-12b", "cygnet"}


class Top10PolicyTests(unittest.TestCase):
    def test_catalog_supports_exactly_the_union(self):
        supported, other = set(), {}
        for path in CATALOG.glob("*.json"):
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry["slug"] == "test-tiny":
                continue
            status = entry["installer_policy"]["status"]
            (supported.add(entry["slug"]) if status in ("supported", "supported_noncommercial_only") else other.__setitem__(entry["slug"], status))
        self.assertEqual(supported, UNION)
        self.assertTrue(other)
        self.assertEqual(set(other.values()), {"on_request"})

    def test_on_request_model_is_refused_with_a_friendly_message(self):
        model = model_with_variants([variant()], policy="on_request")
        with tempfile.TemporaryDirectory() as root, self.assertRaises(RuntimeError) as ctx:
            licence.require_install(model, root, usage="individual", accept=True)
        self.assertIn("on request", str(ctx.exception))
        self.assertIn("info@decisionmodels.io", str(ctx.exception))

    def test_cpu_flags_requirement(self):
        item = variant()
        item["install"]["requires"]["cpu_flags"] = ["avx512f"]
        hw = {"os": "linux", "gpus": [{"vendor": "nvidia"}], "cpu_flags": ["avx2"]}
        self.assertTrue(any("AVX512F" in e for e in requires_errors(item, hw)))
        hw["cpu_flags"] = ["avx2", "avx512f"]
        self.assertFalse(any("AVX512F" in e for e in requires_errors(item, hw)))

    def test_github_release_code_source_is_validated(self):
        item = variant()
        item["install"]["code"] = [{"source": "github-release", "repo": "owner/project", "revision": "a" * 40, "tag": "v1.0",
                                    "asset": "tool-linux.tar.gz", "sha256": "b" * 64, "dest": "code/tool"}]
        self.assertFalse([e for e in recipe_errors(item) if "code" in e])
        item["install"]["code"][0]["asset"] = "../evil.tar.gz"
        self.assertTrue([e for e in recipe_errors(item) if "asset" in e])


if __name__ == "__main__":
    unittest.main()
