"""Instrument catalog RPC handlers (v0.14.0)."""
from __future__ import annotations

from loguru import logger
from models.registry import ModelRegistry


def _clean_str(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:500]


def _list_instruments(params: dict, registry: ModelRegistry) -> dict:
    """Search/list instruments from the catalog.

    params: {query?, category?, source?, tags?, offset?, limit?}
    returns: {items: [...], total: int, has_more: bool}
    """
    from utils.instrument_catalog import search_instruments
    try:
        return search_instruments(
            query=str(params.get("query", "")),
            category=str(params.get("category", "")),
            source=str(params.get("source", "")),
            tags=params.get("tags"),
            offset=int(params.get("offset", 0)),
            limit=int(params.get("limit", 50)),
        )
    except Exception as exc:
        logger.error(f"[list_instruments] {exc}")
        return {"error": _clean_str(exc)}


def _get_instrument_details(params: dict, registry: ModelRegistry) -> dict:
    """Get details for a specific instrument.

    params: {id: str}
    returns: full instrument entry or {error}
    """
    from utils.instrument_catalog import get_instrument_details
    instrument_id = params.get("id", "")
    if not instrument_id:
        return {"error": "'id' param required"}
    try:
        entry = get_instrument_details(instrument_id)
        if entry is None:
            return {"error": f"Instrument not found: {instrument_id}"}
        return entry
    except Exception as exc:
        logger.error(f"[get_instrument_details] {exc}")
        return {"error": _clean_str(exc)}


def _download_instrument_pack(params: dict, registry: ModelRegistry) -> dict:
    """Download an instrument pack.

    params: {name: str}
    returns: {path: str, name: str}
    """
    from utils.instrument_catalog import download_instrument_pack
    name = params.get("name", "")
    if not name:
        return {"error": "'name' param required"}
    try:
        path = download_instrument_pack(name)
        return {"path": path, "name": name}
    except Exception as exc:
        logger.error(f"[download_instrument_pack] {name}: {exc}")
        return {"error": _clean_str(exc)}


def _list_instrument_packs(params: dict, registry: ModelRegistry) -> dict:
    """List available instrument packs with install status.

    returns: {packs: [...]}
    """
    from utils.instrument_catalog import list_packs
    try:
        return {"packs": list_packs()}
    except Exception as exc:
        logger.error(f"[list_instrument_packs] {exc}")
        return {"error": _clean_str(exc)}
