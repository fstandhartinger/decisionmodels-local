"""Variant fit assessment and preference ordering."""
import re

from .pins import LLAMA_CPP_ASSETS
from .runtime_selection import installer_runtime, requires_errors, runtime_readiness_errors


def _available_vram_gb(hw):
    nvidia = [g for g in hw.get("gpus", []) if g.get("vendor") == "nvidia"]
    if nvidia:
        values = [g.get("memory_total_mb") for g in nvidia]
        values = [v for v in values if v is not None]
        return max(values) / 1024.0 if values else 0.0
    apple = hw.get("apple_silicon")
    return apple.get("unified_memory_gb") if apple else 0.0


def _platform_supported(variant, hw):
    supported = variant.get("platforms", [])
    osname = hw.get("os")
    machine = hw.get("arch")
    if hw.get("wsl2") and "wsl2-nvidia" in supported:
        return True
    if osname == "linux":
        return ("linux-nvidia" in supported and bool(hw.get("gpus"))) or ("linux-cpu" in supported)
    if osname == "darwin":
        if machine in ("arm64", "aarch64") and ("macos-arm64" in supported or "macos-arm64-metal" in supported):
            return True
        return "macos-x64" in supported
    if osname == "windows":
        return "windows-x64" in supported or ("windows-nvidia" in supported and bool(hw.get("gpus")))
    return False


def _llama_platform_key(variant, hw):
    osname = hw.get("os")
    arch = hw.get("arch")
    accelerator = str(variant.get("accelerator", "cpu")).lower()
    if osname == "linux" and arch in ("x86_64", "amd64"):
        return f"linux-x86_64-{accelerator}"
    if osname == "darwin" and arch in ("arm64", "aarch64"):
        return "macos-arm64-metal"
    if osname == "windows" and arch in ("x86_64", "amd64"):
        return f"windows-x86_64-{accelerator}"
    return None


# Vendors market memory in GB while tools report GiB/MiB (a "24 GB" RTX 4090 reports 24,564 MiB = 23.99 GiB).
VRAM_TOLERANCE = 0.97
RAM_TOLERANCE = 0.92


def assess_variant(variant, model, hw):
    reasons = []
    if not _platform_supported(variant, hw):
        reasons.append("unsupported operating system, architecture, or accelerator")
    memory_gb = _available_vram_gb(hw) / VRAM_TOLERANCE
    min_vram = variant.get("min_vram_gb")
    recommended_vram = variant.get("recommended_vram_gb", min_vram)
    runtime = installer_runtime(variant)
    recipe_errors = runtime_readiness_errors(variant)
    if recipe_errors:
        return {"id": variant["id"], "verdict": "not_installable",
                "reasons": ["not installable: " + "; ".join(recipe_errors)], "variant": variant}
    reasons.extend(requires_errors(variant, hw))
    if runtime == "llamacpp":
        key = _llama_platform_key(variant, hw)
        if not key or not LLAMA_CPP_ASSETS.get(key): reasons.append("no verified llama.cpp release asset is pinned for this platform yet")
    if min_vram is not None and memory_gb < float(min_vram):
        reasons.append(f"needs {min_vram:g} GB accelerator memory; detected {memory_gb:.1f} GB")
    elif min_vram is not None and recommended_vram is not None and memory_gb < float(recommended_vram):
        reasons.append(f"minimum memory fits; recommended {recommended_vram:g} GB, detected {memory_gb:.1f} GB")
    arch_min = variant.get("gpu_arch_min")
    if arch_min and not (variant.get("install") or {}).get("requires", {}).get("gpu_arch_min"):
        match = re.fullmatch(r"sm_(\d{2,3})[a-z]?", str(arch_min).lower())
        if not match:
            reasons.append("catalog has an invalid minimum GPU architecture")
        else:
            required = int(match.group(1)) / 10.0
            caps = []
            for gpu in hw.get("gpus", []):
                try: caps.append(float(gpu.get("compute_cap")))
                except (TypeError, ValueError): pass
            if not caps or max(caps) < required:
                reasons.append(f"requires NVIDIA compute capability {required:g} or newer")
    ram = hw.get("ram_gb") or {}
    min_ram = variant.get("min_ram_gb")
    if min_ram is not None and (ram.get("total") or 0) / RAM_TOLERANCE < float(min_ram):
        reasons.append(f"needs {min_ram:g} GB system RAM; detected {(ram.get('total') or 0):.1f} GB")
    disk = variant.get("disk_gb")
    if disk is not None and (hw.get("disk_free_gb") or 0) < float(disk) * 1.1:
        reasons.append(f"needs {disk:g} GB model storage plus 10% free-space margin")
    modalities = model.get("modalities", ["text"])
    if "image" in modalities and not variant.get("supports_images", False):
        reasons.append("variant does not declare image support")
    if reasons:
        verdict = "tight" if len(reasons) == 1 and reasons[0].startswith("minimum memory fits") else "does_not_fit"
    elif min_vram is not None and recommended_vram is not None and memory_gb < float(recommended_vram):
        verdict = "tight"
    else:
        verdict = "fits"
    return {"id": variant["id"], "verdict": verdict, "reasons": reasons, "variant": variant}


def plan_model(model, hw):
    results = [assess_variant(v, model, hw) for v in model.get("variants", [])]
    quantized_usable = any(
        r["verdict"] in ("fits", "tight") and not r["variant"].get("benchmarked", False)
        and str(r["variant"].get("precision", "")).lower() not in ("bf16", "fp16", "fp32", "float16", "float32")
        for r in results
    )
    for result in results:
        if result["variant"].get("benchmarked") and result["verdict"] == "does_not_fit" and quantized_usable:
            result["verdict"] = "needs_quantization"
            result["reasons"].append("a non-benchmarked quantized variant fits this machine")
    preferred = [r for r in results if r["verdict"] in ("fits", "tight")]
    apple = bool(hw.get("apple_silicon"))
    cpu_only = not hw.get("gpus") and not apple
    def score(result):
        variant = result["variant"]
        runtime = installer_runtime(variant) or ""
        return (
            0 if variant.get("benchmarked") else 1,
            0 if apple and runtime in ("mlx", "llamacpp") else (1 if apple else 0),
            0 if cpu_only and runtime == "llamacpp" else (1 if cpu_only else 0),
            0 if result["verdict"] == "fits" else 1,
        )
    chosen = min(preferred, key=score) if preferred else None
    if chosen:
        needed = f"Recommended variant: {chosen['id']} ({chosen['verdict']})."
    else:
        mins = [v.get("min_vram_gb") for v in model.get("variants", []) if v.get("min_vram_gb") is not None]
        positive_mins = [value for value in mins if float(value) > 0]
        if positive_mins:
            smallest = min(positive_mins)
            needed = f"No listed variant fits. At least {smallest:g} GB accelerator memory is listed; try a supported remote GPU with `dm-local remote user@host install {model['slug']}`."
        else:
            needed = f"No listed variant is installable on this machine. Try a supported remote machine with `dm-local remote user@host install {model['slug']}`."
    return {"slug": model["slug"], "variants": [{k: v for k, v in r.items() if k != "variant"} for r in results],
            "selected": chosen["id"] if chosen else None, "guidance": needed}


def choose_variant(model, hw, variant_id=None, runtime=None):
    candidates = [v for v in model.get("variants", []) if (not variant_id or v["id"] == variant_id)
                  and (not runtime or installer_runtime(v) == runtime)]
    if not candidates:
        raise ValueError("no catalog variant matches the requested variant/runtime")
    assessed = [assess_variant(v, model, hw) for v in candidates]
    chosen = next((r for r in assessed if r["verdict"] in ("fits", "tight")), None)
    if chosen is None:
        lines = "; ".join(f"{r['id']}: {', '.join(r['reasons']) or r['verdict']}" for r in assessed)
        raise ValueError("no requested variant fits this machine: " + lines)
    return chosen["variant"], chosen["verdict"]
