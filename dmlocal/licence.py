"""Local licence declaration and commercial licence verification."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FREE_TEXT = ("Free for individuals and companies with up to 10 employees and under USD 1M annual revenue. "
             "Larger companies need the Decision Models commercial licence (USD 1,000 once + USD 100/month): "
             "https://decisionmodels.io/local/licence")


def _read_config(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


def _write_config(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try: os.chmod(tmp, 0o600)
    except OSError: pass
    os.replace(tmp, target)


def activate(key, state_root, opener=urllib.request.urlopen):
    if not key or not key.strip():
        raise ValueError("licence key cannot be empty")
    base = os.environ.get("DM_LOCAL_API", "https://decisionmodels.io").rstrip("/")
    url = base + "/local/api/licence/verify"
    body = json.dumps({"key": key.strip()}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"licence verification failed: {exc}") from exc
    if not result.get("valid") or result.get("plan") != "commercial":
        raise RuntimeError("licence key is invalid or is not a commercial plan")
    if result.get("expires_at"):
        try:
            expiry = datetime.fromisoformat(str(result["expires_at"]).replace("Z", "+00:00"))
            if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry.timestamp() <= time.time(): raise RuntimeError("commercial licence has expired")
        except ValueError as exc:
            raise RuntimeError("licence service returned an invalid expires_at value") from exc
    config_path = Path(state_root) / "config.json"
    config = _read_config(config_path)
    config["licence"] = {"key": key.strip(), "verified_at": int(time.time()),
                         "expires_at": result.get("expires_at"), "valid": True}
    _write_config(config_path, config)
    return {"valid": True, "expires_at": result.get("expires_at")}


def status(state_root):
    config = _read_config(Path(state_root) / "config.json")
    usage = config.get("usage")
    licence = config.get("licence", {})
    return {"usage": usage, "commercial_licence": bool(licence.get("valid")),
            "expires_at": licence.get("expires_at"), "verified_at": licence.get("verified_at")}


def _check_commercial(config, state_root, opener):
    licence = config.get("licence", {})
    key = licence.get("key")
    now = int(time.time())
    verified_at = int(licence.get("verified_at", 0))
    if not key:
        raise RuntimeError("company usage requires `dm-local licence activate <key>`")
    expires_at = licence.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry.timestamp() <= now: raise RuntimeError("commercial licence has expired")
        except ValueError as exc:
            raise RuntimeError("cached commercial licence has an invalid expiry value") from exc
    if verified_at and now - verified_at < 30 * 86400 and licence.get("valid"):
        return
    try:
        activate(key, state_root, opener=opener)
    except Exception as exc:
        if verified_at and now - verified_at < 44 * 86400 and licence.get("valid"):
            return  # documented 14-day offline grace after a 30-day cache
        raise RuntimeError(f"commercial licence could not be verified and offline grace expired: {exc}") from exc


def require_install(model, state_root, usage=None, accept=False, input_fn=input, opener=urllib.request.urlopen):
    policy = model.get("installer_policy", {})
    status = policy.get("status", "excluded")
    if status == "excluded":
        raise RuntimeError(f"this model is excluded from the installer: {policy.get('reason', 'policy')}")
    if status not in ("supported", "supported_noncommercial_only"):
        raise RuntimeError(f"unknown installer policy status {status!r}; refusing install")
    config_path = Path(state_root) / "config.json"
    config = _read_config(config_path)
    previous_usage = config.get("usage")
    chosen = usage or previous_usage
    is_first_declaration = chosen is None
    is_new_declaration = is_first_declaration or (usage is not None and usage != previous_usage)
    if is_new_declaration:
        print(FREE_TEXT)
    if chosen not in ("individual", "small_company", "company"):
        if not sys.stdin.isatty():
            raise RuntimeError("first install requires `--usage individual|small_company|company --accept` in non-interactive mode")
        chosen = input_fn("Select individual, small_company, or company: ").strip().lower()
    if chosen not in ("individual", "small_company", "company"):
        raise ValueError("usage must be individual, small_company, or company")
    if not accept and is_new_declaration:
        if not sys.stdin.isatty():
            raise RuntimeError("non-interactive install requires --accept")
        answer = input_fn("Do you accept this usage declaration? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            raise RuntimeError("licence declaration was not accepted")
    if status == "supported_noncommercial_only":
        print("Model licence summary: " + str(model.get("licence", {}).get("notes", "non-commercial use only")))
        if chosen == "company":
            raise RuntimeError("this model is not installable for company usage under its non-commercial licence")
        if not accept:
            answer = input_fn("Confirm that your use complies with this model's licence? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                raise RuntimeError("model licence was not accepted")
    elif model.get("licence", {}).get("notes"):
        print("Model licence summary: " + model["licence"]["notes"])
    if chosen == "company":
        _check_commercial(config, state_root, opener)
        config = _read_config(config_path)
    config["usage"] = chosen
    _write_config(config_path, config)
    return chosen
