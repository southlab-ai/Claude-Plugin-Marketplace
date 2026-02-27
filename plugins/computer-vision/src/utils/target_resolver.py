"""Target resolution: map a ref_id or natural-language query to a live COM element.

resolve_target(hwnd, target, cache) -> (metadata_dict, live_com_element)
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

from src.errors import FIND_NO_MATCH, CVPluginError
from src.utils.uia import get_ui_tree, UIA_RUNTIME_ID_PROPERTY_ID
from src.utils.element_cache import ElementCache, CacheHit

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 0.5
_SUBSTRING_SCORE = 0.7


class TargetNotFoundError(CVPluginError):
    """Raised when resolve_target cannot find the requested element."""

    def __init__(self, target: str) -> None:
        super().__init__(FIND_NO_MATCH, f"Could not resolve target '{target}'")


def _fuzzy_score(query: str, text: str) -> float:
    """Compute fuzzy match score between query and text (0.0 - 1.0)."""
    if not query or not text:
        return 0.0
    q = query.lower()
    t = text.lower()
    if q in t:
        return max(_SUBSTRING_SCORE, SequenceMatcher(None, q, t).ratio())
    return SequenceMatcher(None, q, t).ratio()


def _flatten_elements(elements: list) -> list:
    """Recursively flatten a UiaElement tree."""
    flat: list = []
    for el in elements:
        flat.append(el)
        if el.children:
            flat.extend(_flatten_elements(el.children))
    return flat


def _element_to_cache_meta(element: Any) -> dict:
    """Convert a UiaElement model to a metadata dict suitable for the cache."""
    rect = element.rect
    return {
        "name": element.name,
        "control_type": element.control_type,
        "rect": {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height},
        "is_enabled": element.is_enabled,
        "ref_id": element.ref_id,
        "supported_patterns": [],
        "runtime_id": None,  # Not available from UiaElement model; set by caller if known
    }


def _walk_and_populate_cache(hwnd: int, cache: ElementCache) -> list[dict]:
    """Re-walk the UIA subtree for hwnd, populate cache, return flat metadata list."""
    tree = get_ui_tree(hwnd, depth=8, filter="all")
    flat = _flatten_elements(tree)
    metas: list[dict] = []
    for el in flat:
        meta = _element_to_cache_meta(el)
        metas.append(meta)
    # Bulk insert (entries without runtime_id will be skipped by cache.put)
    cache.put(hwnd, metas)
    return metas


def _find_by_ref_id(
    hwnd: int, ref_id: str, cache: ElementCache
) -> tuple[dict, Any] | None:
    """Attempt cache lookup by ref_id. Returns (meta, element) or None."""
    hit = cache.get(hwnd, ref_id)
    if hit is not None:
        return (hit.metadata, hit.element)
    return None


def _fuzzy_match_in_metas(
    query: str, metas: list[dict]
) -> dict | None:
    """Find best fuzzy match among metadata dicts. Returns best meta or None."""
    best_score = 0.0
    best_meta: dict | None = None

    for meta in metas:
        name = meta.get("name", "")
        control_type = meta.get("control_type", "")

        # Score against name
        score = _fuzzy_score(query, name)

        # Also check control_type
        ct_score = _fuzzy_score(query, control_type)
        score = max(score, ct_score)

        # Combine name + control_type for richer matching
        combined = f"{name} {control_type}".strip()
        combined_score = _fuzzy_score(query, combined)
        score = max(score, combined_score)

        if score > best_score:
            best_score = score
            best_meta = meta

    if best_score >= _MATCH_THRESHOLD and best_meta is not None:
        return best_meta
    return None


def resolve_target(
    hwnd: int,
    target: str,
    cache: ElementCache,
) -> tuple[dict, Any]:
    """Resolve a target string to (element_metadata, live_com_element).

    Args:
        hwnd: Window handle.
        target: Either a "ref_<N>" identifier or a natural-language query.
        cache: ElementCache instance.

    Returns:
        (metadata_dict, live_com_element)

    Raises:
        TargetNotFoundError: if the element cannot be found.
    """
    # ------------------------------------------------------------------
    # 1. ref_id path
    # ------------------------------------------------------------------
    if target.startswith("ref_"):
        # First try cache
        result = _find_by_ref_id(hwnd, target, cache)
        if result is not None:
            return result

        # Cache miss — re-walk tree, populate cache, retry
        _walk_and_populate_cache(hwnd, cache)
        result = _find_by_ref_id(hwnd, target, cache)
        if result is not None:
            return result

        raise TargetNotFoundError(target)

    # ------------------------------------------------------------------
    # 2. Natural-language query path
    # ------------------------------------------------------------------
    # First try fuzzy match against current cache contents
    # (we need to access internal state for NL matching)
    metas = _collect_all_metas_for_window(hwnd, cache)

    if metas:
        best = _fuzzy_match_in_metas(target, metas)
        if best is not None:
            ref_id = best.get("ref_id", "")
            if ref_id:
                result = _find_by_ref_id(hwnd, ref_id, cache)
                if result is not None:
                    return result

    # Cache had no match — re-walk and try again
    fresh_metas = _walk_and_populate_cache(hwnd, cache)
    if fresh_metas:
        best = _fuzzy_match_in_metas(target, fresh_metas)
        if best is not None:
            ref_id = best.get("ref_id", "")
            if ref_id:
                result = _find_by_ref_id(hwnd, ref_id, cache)
                if result is not None:
                    return result

    raise TargetNotFoundError(target)


def _collect_all_metas_for_window(hwnd: int, cache: ElementCache) -> list[dict]:
    """Gather all cached metadata dicts for a given hwnd."""
    metas: list[dict] = []
    # Access internal structures — the cache exposes no iteration API,
    # so we reach into _windows with the lock held.
    with cache._lock:
        wc = cache._windows.get(hwnd)
        if wc is None:
            return metas
        for _key, meta in wc.items():
            metas.append({k: v for k, v in meta.items() if not k.startswith("_")})
    return metas
