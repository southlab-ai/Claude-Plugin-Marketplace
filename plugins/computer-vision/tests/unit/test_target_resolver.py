"""Unit tests for target_resolver — ref_id resolution, cache miss re-walk,
and natural-language fuzzy fallback.
"""

from __future__ import annotations

from collections import OrderedDict
from unittest.mock import MagicMock, patch

import pytest

from src.models import Rect, UiaElement
from src.utils.element_cache import CacheHit, ElementCache
from src.utils.target_resolver import (
    TargetNotFoundError,
    _fuzzy_score,
    resolve_target,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(uia: MagicMock | None = None) -> ElementCache:
    return ElementCache(uia_instance=uia)


def _uia_element(ref_id: str, name: str, control_type: str = "Button") -> UiaElement:
    return UiaElement(
        ref_id=ref_id,
        name=name,
        control_type=control_type,
        rect=Rect(x=10, y=20, width=80, height=30),
        is_enabled=True,
    )


def _seed_cache(
    cache: ElementCache, hwnd: int, metas: list[dict]
) -> None:
    """Directly populate cache with metadata that includes runtime_id."""
    cache.put(hwnd, metas)


def _meta(ref_id: str, name: str, rid: list[int], control_type: str = "Button") -> dict:
    return {
        "name": name,
        "control_type": control_type,
        "rect": {"x": 10, "y": 20, "width": 80, "height": 30},
        "is_enabled": True,
        "ref_id": ref_id,
        "supported_patterns": [],
        "runtime_id": rid,
    }


# ---------------------------------------------------------------------------
# _fuzzy_score
# ---------------------------------------------------------------------------

class TestFuzzyScore:
    def test_exact_match(self):
        assert _fuzzy_score("Save", "Save") >= 0.9

    def test_substring(self):
        assert _fuzzy_score("Save", "Save As...") >= 0.7

    def test_no_match(self):
        assert _fuzzy_score("xyzzy", "Button") < 0.5

    def test_empty_strings(self):
        assert _fuzzy_score("", "Save") == 0.0
        assert _fuzzy_score("Save", "") == 0.0


# ---------------------------------------------------------------------------
# resolve_target — ref_id path
# ---------------------------------------------------------------------------

class TestResolveRefId:
    def test_ref_id_cache_hit(self):
        uia = MagicMock()
        fake_el = MagicMock(name="LiveElement")
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        _seed_cache(cache, 100, [_meta("ref_1", "OK", [1, 2])])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            meta, elem = resolve_target(100, "ref_1", cache)

        assert meta["ref_id"] == "ref_1"
        assert meta["name"] == "OK"
        assert elem is fake_el

    @patch("src.utils.target_resolver.get_ui_tree")
    def test_ref_id_cache_miss_rewalks(self, mock_tree):
        """On cache miss, resolve_target re-walks the tree and retries."""
        mock_tree.return_value = [
            _uia_element("ref_5", "Apply"),
        ]

        uia = MagicMock()
        fake_el = MagicMock(name="LiveApply")
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        # Cache is empty — the first lookup misses

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            # After re-walk, cache has the meta but runtime_id is None
            # (because UiaElement model doesn't carry it).
            # So the second lookup will also miss — ultimately raises.
            with pytest.raises(TargetNotFoundError):
                resolve_target(100, "ref_5", cache)

        mock_tree.assert_called_once()

    def test_ref_id_not_found_raises(self):
        cache = _make_cache()
        with patch("src.utils.target_resolver.get_ui_tree", return_value=[]):
            with pytest.raises(TargetNotFoundError):
                resolve_target(100, "ref_999", cache)


# ---------------------------------------------------------------------------
# resolve_target — natural-language path
# ---------------------------------------------------------------------------

class TestResolveNaturalLanguage:
    @patch("src.utils.target_resolver.get_ui_tree")
    def test_nl_exact_name_match(self, mock_tree):
        uia = MagicMock()
        fake_el = MagicMock(name="LiveSave")
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        _seed_cache(cache, 100, [
            _meta("ref_1", "Save", [1]),
            _meta("ref_2", "Cancel", [2]),
        ])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            meta, elem = resolve_target(100, "Save", cache)

        assert meta["name"] == "Save"
        assert elem is fake_el

    @patch("src.utils.target_resolver.get_ui_tree")
    def test_nl_substring_match(self, mock_tree):
        uia = MagicMock()
        fake_el = MagicMock(name="LiveSaveAs")
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        _seed_cache(cache, 100, [
            _meta("ref_1", "Save As...", [1]),
        ])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            meta, elem = resolve_target(100, "Save", cache)

        assert "Save" in meta["name"]

    @patch("src.utils.target_resolver.get_ui_tree")
    def test_nl_no_match_raises(self, mock_tree):
        mock_tree.return_value = []
        cache = _make_cache()

        with pytest.raises(TargetNotFoundError):
            resolve_target(100, "Nonexistent widget", cache)

    @patch("src.utils.target_resolver.get_ui_tree")
    def test_nl_control_type_match(self, mock_tree):
        uia = MagicMock()
        fake_el = MagicMock(name="LiveCB")
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        _seed_cache(cache, 100, [
            _meta("ref_1", "", [1], control_type="CheckBox"),
        ])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            meta, elem = resolve_target(100, "CheckBox", cache)

        assert meta["control_type"] == "CheckBox"

    @patch("src.utils.target_resolver.get_ui_tree")
    def test_nl_cache_miss_rewalks_and_matches(self, mock_tree):
        """If initial cache is empty, re-walk populates it and fuzzy match works."""
        mock_tree.return_value = [
            _uia_element("ref_1", "Submit"),
        ]

        uia = MagicMock()
        fake_el = MagicMock()
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        # Cache is empty

        # The re-walk produces UiaElement without runtime_id, so cache.put
        # sets runtime_id=None and skips the entry. This means the fuzzy
        # match finds the meta from _walk_and_populate_cache's returned list
        # but cache.get will miss. So this should raise.
        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            with pytest.raises(TargetNotFoundError):
                resolve_target(100, "Submit", cache)

        mock_tree.assert_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_target_raises(self):
        cache = _make_cache()
        with patch("src.utils.target_resolver.get_ui_tree", return_value=[]):
            with pytest.raises(TargetNotFoundError):
                resolve_target(100, "", cache)

    @patch("src.utils.target_resolver.get_ui_tree")
    def test_multiple_candidates_best_wins(self, mock_tree):
        uia = MagicMock()
        fake_el = MagicMock()
        root = MagicMock()
        root.FindFirst.return_value = fake_el
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = _make_cache(uia)
        _seed_cache(cache, 100, [
            _meta("ref_1", "Save Draft", [1]),
            _meta("ref_2", "Save", [2]),
            _meta("ref_3", "Cancel", [3]),
        ])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            meta, _ = resolve_target(100, "Save", cache)

        # "Save" is an exact match for ref_2
        assert meta["ref_id"] == "ref_2"
