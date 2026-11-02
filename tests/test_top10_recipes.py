import json
import re
import unittest
from pathlib import Path

from dmlocal.runtime_selection import recipe_errors

CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "models"

# JevBench v1.8.4 top-10 recipes added 2026-11-02. A recipe may only be supported with a passing selftest receipt.
SLUGS = ["vllm-sr-d3", "vllm-sr-d3-turbo", "pplx-decider-v1-1-27b", "fastino-glide-1.2-open", "basal-omni-1.0-ultra",
         "knowline-31b-gen1", "mammoth-1"]


class Top10RecipeTests(unittest.TestCase):
    def entries(self):
        for slug in SLUGS:
            yield slug, json.loads((CATALOG / f"{slug}.json").read_text(encoding="utf-8"))

    def test_recipes_are_valid_and_pinned(self):
        for slug, model in self.entries():
            self.assertRegex(model["weights"]["revision"], r"^[0-9a-f]{40}$", slug)
            for variant in model["variants"]:
                self.assertEqual(recipe_errors(variant), [], slug)
                for file in variant["files"]:
                    self.assertRegex(file["sha256"], r"^[0-9a-f]{64}$", f"{slug}/{file['path']}")
                for package in variant["install"].get("packages", []):
                    self.assertRegex(package, r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+$", slug)
                for code in variant["install"].get("code", []):
                    self.assertRegex(code["revision"], r"^[0-9a-f]{40}$", slug)
                    self.assertRegex(code["sha256"], r"^[0-9a-f]{64}$", slug)

    def test_servers_bind_loopback_only(self):
        for slug, model in self.entries():
            for variant in model["variants"]:
                for process in variant["install"]["processes"]:
                    command = process["command"]
                    if "--host" in command:
                        self.assertEqual(command[command.index("--host") + 1], "127.0.0.1", slug)
                    else:
                        self.assertEqual(process.get("env", {}).get("AUTOJEV_HOST"), "127.0.0.1", slug)

    def test_supported_only_with_passing_selftest(self):
        for slug, model in self.entries():
            supported = model["installer_policy"]["status"] in ("supported", "supported_noncommercial_only")
            for variant in model["variants"]:
                verified = variant["install"]["verified"]
                if supported:
                    self.assertEqual((verified.get("status"), verified.get("selftest")), ("verified", "pass"), slug)
                    self.assertTrue(re.search(r"2026-\d\d-\d\d", verified.get("where", "")), slug)
                else:
                    self.assertEqual(model["installer_policy"]["status"], "on_request", slug)
                    self.assertNotEqual(verified.get("status"), "verified", slug)


if __name__ == "__main__":
    unittest.main()
