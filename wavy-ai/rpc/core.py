"""Core RPC handlers."""
from __future__ import annotations

import os
from pathlib import Path
from loguru import logger
from models.registry import ModelRegistry
import config
from rpc.helpers import _clean_str

# ── Health ────────────────────────────────────────────────────────────────────

def _health(params: dict, registry: ModelRegistry) -> dict:
    return {
        "status":                       "ok",
        "version":                      "1.0.0",
        "loaded_models":                registry.loaded_model_names(),
        "cloud_provider":               config.CLOUD_PROVIDER,
        "elevenlabs_api_key_configured": bool(config.ELEVENLABS_API_KEY),
        "anthropic_api_key_configured":  bool(config.ANTHROPIC_API_KEY),
    }


# ── Model Manager ─────────────────────────────────────────────────────────────

def _list_models(params: dict, registry: ModelRegistry) -> dict:
    from model_check import get_model_disk_size
    status = registry.model_status()
    for m in status:
        m["disk_size_gb"] = get_model_disk_size(m["name"])
    return {"models": status}


def _delete_model(params: dict, registry: ModelRegistry) -> dict:
    """Remove a local model's files from disk.

    params:
        name : str — model name (must match MODEL_DIR subdirectory)
    returns:
        {"deleted": name, "success": bool}
    """
    from model_check import uninstall_model

    name = params.get("name", "")
    if not name:
        raise ValueError("'name' param required")

    registry.unload(name)  # unload if currently loaded
    ok = uninstall_model(name)
    return {"deleted": name, "success": ok}


def _load_model(params: dict, registry: ModelRegistry) -> dict:
    name = params["name"]
    registry.load(name)
    return {"loaded": name}


def _unload_model(params: dict, registry: ModelRegistry) -> dict:
    name = params["name"]
    registry.unload(name)
    return {"unloaded": name}

# ── Voice Personas ────────────────────────────────────────────────────────────

_PERSONAS_FILE = config.GENERATION_DIR / "personas.json"


def _save_persona(params: dict, registry: ModelRegistry) -> dict:
    """params: name, voice_id, stability, similarity, description"""
    import json as _json
    config.GENERATION_DIR.mkdir(parents=True, exist_ok=True)
    personas = []
    if _PERSONAS_FILE.exists():
        try:
            personas = _json.loads(_PERSONAS_FILE.read_text())
        except Exception:
            pass
    name = params.get("name", "").strip()
    if not name:
        return {"error": "name is required"}
    personas = [p for p in personas if p.get("name") != name]
    personas.append({
        "name":        name,
        "voice_id":    params.get("voice_id", ""),
        "stability":   float(params.get("stability", 0.5)),
        "similarity":  float(params.get("similarity", 0.75)),
        "description": params.get("description", ""),
    })
    _PERSONAS_FILE.write_text(_json.dumps(personas, indent=2))
    return {"ok": True, "persona_count": len(personas)}


def _load_personas(params: dict, registry: ModelRegistry) -> dict:
    """returns: {"personas": [...]}"""
    import json as _json
    if not _PERSONAS_FILE.exists():
        return {"personas": []}
    try:
        return {"personas": _json.loads(_PERSONAS_FILE.read_text())}
    except Exception:
        return {"personas": []}


# ── Startup Diagnostics ───────────────────────────────────────────────────────

def _startup_check(params: dict, registry: ModelRegistry) -> dict:
    """Run startup diagnostics; returns structured check results."""

    checks: list[dict] = []

    def ok(name: str, msg: str):   checks.append({"name": name, "status": "ok",    "message": msg})
    def warn(name: str, msg: str): checks.append({"name": name, "status": "warn",  "message": msg})
    def err(name: str, msg: str):  checks.append({"name": name, "status": "error", "message": msg})

    # ── ElevenLabs ─────────────────────────────────────────────────────────
    # Tiers that include the Music compose() API (Creator plan and above)
    _EL_MUSIC_TIERS = {"creator", "pro", "scale", "business", "enterprise", "growing", "professional"}

    if config.ELEVENLABS_API_KEY:
        ok("ElevenLabs Key", "API key configured")

        # Connectivity — list voices (cheap, validates auth token)
        _el_client = None
        try:
            from cloud.elevenlabs_voices import list_voices
            from elevenlabs import ElevenLabs
            voices = list_voices()
            _el_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            ok("ElevenLabs API", f"Connected — {len(voices)} voices available")
        except Exception as exc:
            err("ElevenLabs API", f"Connection failed: {_clean_str(exc)}")

        # Credit quota + plan tier — client.user.get()
        _el_tier = "unknown"
        try:
            if _el_client is None:
                from elevenlabs import ElevenLabs
                _el_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            user_info = _el_client.user.get()
            sub = getattr(user_info, "subscription", None)
            if sub is not None:
                remaining  = getattr(sub, "character_count",
                              getattr(sub, "credit_count", None))
                limit      = getattr(sub, "character_limit",
                              getattr(sub, "credit_limit", None))
                _el_tier   = getattr(sub, "tier", "unknown")
                if remaining is not None and limit and limit > 0:
                    pct = remaining / limit * 100
                    msg = f"{remaining:,}/{limit:,} credits remaining ({pct:.0f}%) — tier: {_el_tier}"
                    (ok if pct > 20 else warn)("EL Quota", msg)
                else:
                    ok("EL Quota", f"Subscription active — tier: {_el_tier}")
            else:
                ok("EL Quota", "Subscription info not available")
        except Exception as exc:
            # Extract the real error body from ElevenLabs ApiError if available
            import json as _json
            body = getattr(exc, "body", None)
            status = getattr(exc, "status_code", None)
            if body:
                try:
                    detail = _json.loads(body).get("detail", str(body)) if isinstance(body, str) else str(body)
                    warn("EL Quota", f"HTTP {status}: {str(detail)[:100]}")
                except Exception:
                    warn("EL Quota", f"HTTP {status}: {_clean_str(exc)}")
            else:
                warn("EL Quota", f"Could not fetch quota: {_clean_str(exc)}")

        # Music API availability — based on plan tier (Creator plan or higher required)
        if any(t in _el_tier.lower() for t in _EL_MUSIC_TIERS):
            ok("EL Music API", f"Available (tier: {_el_tier})")
        elif _el_tier == "unknown":
            warn("EL Music API", "Plan tier unknown — will fall back to DiffRhythm if generation fails")
        else:
            warn("EL Music API", f"Requires Creator plan (current: {_el_tier}) — will fall back to DiffRhythm local model")
    else:
        err("ElevenLabs Key",
            "ELEVENLABS_API_KEY not set — music/voice/SFX generation disabled")

    # ── LLM Provider (prompt commands / chat) ──────────────────────────────
    if config.ANTHROPIC_API_KEY:
        ok("LLM Provider", "Anthropic API key configured (Claude)")
    elif config.GROQ_API_KEY:
        ok("LLM Provider", "Groq API key configured (llama-3.3-70b, free tier)")
    else:
        warn("LLM Provider",
             "No ANTHROPIC_API_KEY or GROQ_API_KEY — will fall back to local Mistral 7B")

    # ── Demucs (stem splitting) ────────────────────────────────────────────
    try:
        import importlib
        importlib.import_module("demucs")
        ok("Demucs", "Available — stem splitting enabled")
    except ImportError:
        err("Demucs", "Not installed — stem splitting disabled (pip install demucs)")

    # ── Output directory writable ──────────────────────────────────────────
    try:
        import appdirs, tempfile, os
        out_dir = config.GENERATION_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        test_file = out_dir / ".write_test"
        test_file.write_bytes(b"ok")
        test_file.unlink()
        ok("Output Dir", f"Writable: {out_dir}")
    except Exception as exc:
        err("Output Dir", f"Not writable: {_clean_str(exc)} — audio saves will fail")

    return {"checks": checks}


# ── Runtime API Key Update ────────────────────────────────────────────────────

def _update_api_keys(params: dict, registry: ModelRegistry) -> dict:
    """Inject new API keys into the running process without restart.

    params: anthropic, groq, elevenlabs, freesound  (any subset)
    returns: {"updated": [list of keys that were set]}
    """
    key_map = [
        ("anthropic",  "ANTHROPIC_API_KEY"),
        ("groq",       "GROQ_API_KEY"),
        ("elevenlabs", "ELEVENLABS_API_KEY"),
        ("freesound",  "FREESOUND_API_KEY"),
    ]
    updated = []
    for param_key, env_name in key_map:
        val = params.get(param_key, "")
        if val:
            os.environ[env_name] = val
            setattr(config, env_name, val)
            updated.append(param_key)
            logger.info(f"[update_api_keys] {env_name} updated")

    # Force ElevenLabs SDK client recreation so new key takes effect immediately
    try:
        import cloud.elevenlabs_provider as ep
        ep._cached_client = None
        ep._cached_key = None
    except Exception:
        pass

    return {"updated": updated}


# ── Session Context Lock (A5) ─────────────────────────────────────────────────

_global_context: dict = {}


def _set_session_context(params: dict, registry: ModelRegistry) -> dict:
    """
    Lock key / scale / bpm / style for the session so all subsequent
    generation requests inherit them without repeating.
    params: key, scale, bpm, style  (any may be None to clear)
    returns: {"context": dict}
    """
    global _global_context
    _global_context.update({k: v for k, v in params.items() if v is not None})
    # Allow explicit None to clear individual keys
    for k, v in params.items():
        if v is None and k in _global_context:
            del _global_context[k]
    return {"context": _global_context}

