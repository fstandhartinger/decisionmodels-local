def model_with_variants(variants, modalities=None, policy="supported"):
    return {
        "schema": "decisionmodels-local-catalog/1", "slug": "fixture-model", "name": "Fixture decision model",
        "modalities": modalities or ["text"], "question_types": {"choice": "native", "noul": "native", "score": "native"},
        "weights": {"repo": "owner/model", "revision": "a" * 40},
        "licence": {"spdx": "apache-2.0", "commercial_use": "yes", "notes": "Apache-2.0."},
        "installer_policy": {"status": policy, "reason": "fixture"},
        "readout": {"type": "letter_logprobs", "endpoint": "openai", "prompt_template": "{state}\n{instructions}\n{options}"},
        "variants": variants,
    }


def variant(variant_id="bf16", runtime="venv", min_vram=8, recommended=12, benchmarked=True,
            precision="bf16", platforms=None, supports_images=False):
    return {
        "id": variant_id, "runtime": runtime, "runtime_version": "1.0", "precision": precision,
        "benchmarked": benchmarked, "platforms": platforms or ["linux-nvidia"],
        "min_vram_gb": min_vram, "recommended_vram_gb": recommended, "min_ram_gb": 8, "disk_gb": 5,
        "supports_images": supports_images,
        "files": [{"path": "model.bin", "size": 4, "sha256": "1" * 64}],
        "serve": {"port": 8741, "command": ["python", "serve.py", "--host", "127.0.0.1", "--port", "{port}"]},
        "packages": ["fixture==1.0"],
    }
