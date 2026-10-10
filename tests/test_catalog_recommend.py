import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dmlocal.catalog import load_catalog, validate_model
from dmlocal.recommend import choose_variant, plan_model
from tests.helpers import model_with_variants, variant


def hardware(vram=16, disk=50, ram=32, osname="linux", apple=None, gpus=True):
    return {"os": osname, "arch": "x86_64", "wsl2": False,
            "ram_gb": {"total": ram, "free": ram / 2}, "disk_free_gb": disk,
            "gpus": ([{"vendor": "nvidia", "memory_total_mb": vram * 1024, "memory_free_mb": vram * 1024}] if gpus else []),
            "docker": {"available": True, "nvidia_runtime": True}, "apple_silicon": apple}


class CatalogAndRecommendationTests(unittest.TestCase):
    def test_catalog_load_and_duplicate_json_key_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture-model.json"
            path.write_text(json.dumps(model_with_variants([variant()])))
            self.assertIn("fixture-model", load_catalog(tmp))
            path.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_catalog(tmp)

    def test_bundled_catalog_entries_load(self):
        models = load_catalog()
        self.assertIn("h2o-lightning-4b", models)
        self.assertIn("test-tiny", models)

    def test_backend_description_without_install_recipe_fails_closed(self):
        candidate = variant()
        candidate["runtime"] = "vLLM (author recipe)"
        candidate.pop("packages")
        candidate["serve"] = {"steps": ["Run the author server"]}
        candidate.pop("install")
        model = model_with_variants([candidate])
        validate_model(model)
        result = plan_model(model, hardware())
        self.assertEqual(result["variants"][0]["verdict"], "not_installable")
        self.assertIn("not installable: install recipe is missing", result["variants"][0]["reasons"][0])

    def test_catalog_requires_pinned_revision_and_weight_hash(self):
        model = model_with_variants([variant()])
        model["weights"]["revision"] = "main"
        with self.assertRaisesRegex(ValueError, "40-character commit"):
            validate_model(model)
        model = model_with_variants([variant()])
        model["variants"][0]["files"][0]["sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_model(model)

    def test_recommended_fit_tight_and_does_not_fit(self):
        model = model_with_variants([variant()])
        self.assertEqual(plan_model(model, hardware(vram=16))["variants"][0]["verdict"], "fits")
        self.assertEqual(plan_model(model, hardware(vram=10))["variants"][0]["verdict"], "tight")
        self.assertEqual(plan_model(model, hardware(vram=4))["variants"][0]["verdict"], "does_not_fit")

    def test_quantized_variant_is_recommended_when_benchmarked_one_does_not_fit(self):
        variants = [variant("bf16", min_vram=12, recommended=16),
                    variant("q4", min_vram=4, recommended=6, benchmarked=False, precision="q4")]
        model = model_with_variants(variants)
        result = plan_model(model, hardware(vram=8))
        self.assertEqual(result["variants"][0]["verdict"], "needs_quantization")
        self.assertEqual(result["selected"], "q4")

    def test_image_only_model_requires_image_capable_variant(self):
        model = model_with_variants([variant(supports_images=False)], modalities=["image"])
        self.assertEqual(plan_model(model, hardware())["variants"][0]["verdict"], "does_not_fit")

    def test_text_and_image_model_accepts_text_only_variant(self):
        model = model_with_variants([variant(supports_images=False)], modalities=["text", "image"])
        self.assertNotEqual(plan_model(model, hardware())["variants"][0]["verdict"], "does_not_fit")

    def test_cpu_and_apple_preference(self):
        cpu_variants = [variant("venv", runtime="venv", min_vram=0, recommended=0, benchmarked=False,
                                precision="bf16", platforms=["linux-cpu"]),
                        variant("llama", runtime="llamacpp", min_vram=0, recommended=0, benchmarked=False,
                                precision="q4", platforms=["linux-cpu"])]
        cpu_variants[0]["install"]["requires"]["platforms"] = ["linux-cpu"]
        cpu_variants[1]["install"]["requires"]["platforms"] = ["linux-cpu"]
        cpu_variants[1]["files"][0]["path"] = "fixture.gguf"
        cpu_model = model_with_variants(cpu_variants)
        with patch("dmlocal.recommend.LLAMA_CPP_ASSETS", {"linux-x86_64-cpu": {"sha256": "a"}}):
            self.assertEqual(plan_model(cpu_model, hardware(gpus=False))["selected"], "llama")
        apple_variants = [variant("venv", runtime="venv", min_vram=0, recommended=0, benchmarked=False,
                                  platforms=["macos-arm64"]),
                          variant("mlx", runtime="mlx", min_vram=0, recommended=0, benchmarked=False,
                                  platforms=["macos-arm64"])]
        apple_variants[0]["install"]["requires"]["platforms"] = ["macos-arm64"]
        apple_variants[1]["install"]["requires"]["platforms"] = ["macos-arm64"]
        apple_model = model_with_variants(apple_variants)
        apple_hw = hardware(osname="darwin", gpus=False, apple={"chip": "Apple M", "unified_memory_gb": 24})
        apple_hw["arch"] = "arm64"
        self.assertEqual(plan_model(apple_model, apple_hw)["selected"], "mlx")

    def test_windows_cpu_variant_supports_x64_and_rejects_arm64(self):
        cpu = variant("windows-cpu-x64", runtime="venv", min_vram=0, recommended=0,
                      benchmarked=False, platforms=["windows-cpu"])
        cpu["install"]["requires"]["platforms"] = ["windows-x64"]
        model = model_with_variants([cpu])

        x64 = hardware(osname="windows", gpus=False)
        self.assertEqual(plan_model(model, x64)["selected"], "windows-cpu-x64")
        self.assertEqual(plan_model(model, x64)["variants"][0]["verdict"], "fits")

        arm64 = {**x64, "arch": "arm64"}
        result = plan_model(model, arm64)
        self.assertIsNone(result["selected"])
        self.assertEqual(result["variants"][0]["verdict"], "does_not_fit")
        self.assertIn("unsupported operating system, architecture, or accelerator",
                      result["variants"][0]["reasons"])


if __name__ == "__main__": unittest.main()
