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
    platforms = platforms or ["linux-nvidia"]
    install_runtime = runtime.replace("llama.cpp", "llamacpp")
    packages = ["fixture==1.0"] if install_runtime in ("venv", "mlx") else []
    process = {"name": "api", "command": ["python", "-m", "http.server", "{port:api}", "--bind", "127.0.0.1"],
               "ready": {"url": "http://127.0.0.1:{port:api}/health", "timeout_s": 5}}
    recipe = {
        "runtime": install_runtime,
        "processes": [process],
        "api": {"mode": "proxy_jev", "port": "api", "text_path": "/v1/systemone",
                "image_path": "/v1/multimodal" if supports_images else None, "model": None, "auth_header": None},
        "requires": {"platforms": platforms},
    }
    if install_runtime in ("venv", "mlx"):
        recipe["python"] = "3.12"
        recipe["packages"] = packages
    if install_runtime == "docker":
        recipe["image"] = "fixture/runtime@sha256:" + "a" * 64
    if install_runtime == "llamacpp":
        process["command"] = ["llama-server", "-m", "{weights}/model.gguf", "--host", "127.0.0.1", "--port", "{port:api}"]
    return {
        "id": variant_id, "runtime": runtime, "runtime_version": "1.0", "precision": precision,
        "benchmarked": benchmarked, "platforms": platforms or ["linux-nvidia"],
        "min_vram_gb": min_vram, "recommended_vram_gb": recommended, "min_ram_gb": 8, "disk_gb": 5,
        "supports_images": supports_images,
        "files": [{"path": "model.bin", "size": 4, "sha256": "1" * 64}],
        "serve": {"port": 8741, "command": ["python", "serve.py", "--host", "127.0.0.1", "--port", "{port}"]},
        "packages": ["fixture==1.0"],
        "install": recipe,
    }
