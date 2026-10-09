"""Catalog loading and small, strict validation helpers."""
import json
import re
from importlib import resources
from pathlib import Path

SCHEMA = "decisionmodels-local-catalog/1"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def validate_model(model):
    if not isinstance(model, dict) or model.get("schema") != SCHEMA:
        raise ValueError("catalog entry must use decisionmodels-local-catalog/1")
    slug = model.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError("catalog slug must be lowercase kebab-case")
    if not isinstance(model.get("name"), str) or not model["name"].strip():
        raise ValueError(f"{slug}: name is required")
    weights = model.get("weights")
    if not isinstance(weights, dict) or not isinstance(weights.get("repo"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", weights.get("repo", "")):
        raise ValueError(f"{slug}: weights.repo is required")
    if not re.fullmatch(r"[0-9a-f]{40}", str(weights.get("revision", ""))):
        raise ValueError(f"{slug}: weights.revision must be a pinned 40-character commit")
    variants = model.get("variants")
    if not isinstance(variants, list):
        raise ValueError(f"{slug}: variants must be an array")
    if not variants:
        raise ValueError(f"{slug}: at least one verified variant is required")
    seen = set()
    for variant in variants:
        if not isinstance(variant, dict) or not variant.get("id"):
            raise ValueError(f"{slug}: each variant needs an id")
        if variant["id"] in seen:
            raise ValueError(f"{slug}: duplicate variant id {variant['id']!r}")
        seen.add(variant["id"])
        if not isinstance(variant.get("runtime"), str) or not variant["runtime"].strip():
            raise ValueError(f"{slug}/{variant['id']}: runtime description is required")
        if variant.get("max_options") is not None and (not isinstance(variant["max_options"], int) or not 2 <= variant["max_options"] <= 64):
            raise ValueError(f"{slug}/{variant['id']}: max_options must be between 2 and 64")
        for package in variant.get("packages", []):
            if not isinstance(package, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", package):
                raise ValueError(f"{slug}/{variant['id']}: runtime packages must use exact == versions")
        for url in variant.get("extra_index_urls", []):
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError(f"{slug}/{variant['id']}: package indexes must use HTTPS")
        if not isinstance(variant.get("files"), list) or not variant["files"]:
            raise ValueError(f"{slug}/{variant['id']}: at least one verified weight file is required")
        for file in variant.get("files", []):
            if not isinstance(file, dict) or not isinstance(file.get("path"), str) or not file["path"].strip():
                raise ValueError(f"{slug}/{variant['id']}: each file needs a relative path")
            if not isinstance(file.get("size"), int) or file["size"] < 0:
                raise ValueError(f"{slug}/{variant['id']}: invalid file size")
            if not re.fullmatch(r"[0-9a-f]{64}", str(file.get("sha256", ""))):
                raise ValueError(f"{slug}/{variant['id']}: each file needs a SHA-256")
            path = Path(file.get("path", ""))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"{slug}/{variant['id']}: unsafe weight path")
    return model


def load_catalog(directory=None):
    if directory:
        base = Path(directory)
        paths = sorted(base.glob("*.json")) if base.exists() else []
    else:
        bundled = resources.files("dmlocal").joinpath("_catalog", "models")
        if bundled.is_dir():
            paths = sorted((p for p in bundled.iterdir() if p.name.endswith(".json")), key=lambda p: p.name)
        else:
            base = Path(__file__).resolve().parent.parent / "catalog" / "models"
            paths = sorted(base.glob("*.json")) if base.exists() else []
    models = {}
    for path in paths:
        try:
            model = validate_model(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid catalog file {path.name}: {exc}") from exc
        if Path(path.name).stem != model["slug"]:
            raise ValueError(f"catalog filename {path.name} must match slug {model['slug']!r}")
        if model["slug"] in models:
            raise ValueError(f"duplicate catalog slug {model['slug']!r}")
        models[model["slug"]] = model
    return models


def get_model(slug, catalog=None):
    models = catalog if catalog is not None else load_catalog()
    try:
        model = models[slug]
    except KeyError as exc:
        raise KeyError(f"unknown model {slug!r}; run 'dm-local list' to see available models") from exc
    return model
