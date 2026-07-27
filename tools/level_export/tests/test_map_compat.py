"""Tests for the map compatibility classifier (scripts/_map_compat.py).

Pins classification against real refs map data: SF001001 is the known-good
map; SF001002 has 7 point lights; SF001009 has unresolvable tile kinds.
"""
from pathlib import Path

import pytest

from scripts._map_compat import classify_map, MAP_IRD

pytestmark = pytest.mark.skipif(
    not MAP_IRD.exists(), reason="refs map data not available"
)


def test_sf001001_is_clean():
    result = classify_map("SF001001")
    assert result["blockers"] == []
    assert result["detail"]["models_total"] > 0
    assert result["detail"]["models_missing"] == []


def test_point_light_map_is_clean_and_counted():
    # Point lights are supported (parsed + FF-shader port); the count stays
    # informational in detail but no longer blocks export.
    result = classify_map("SF001002")
    assert result["blockers"] == []
    assert result["detail"]["point_lights"] == 7


def test_missing_tile_art_map_is_clean():
    # Fringe refs into full-only tile sets and kind-0x00 ids are legal
    # shipped data (layers the original silently skipped) — not blockers.
    result = classify_map("SF001009")
    assert result["blockers"] == []
    assert result["detail"]["tile_texture_failures"] == []


def test_missing_glbs_are_informational_not_blockers():
    """Unresolvable OCG refs rendered NOTHING in the original client:
    unknown category -> object skipped; missing/misnamed TMD -> the
    exact-name IRD lookup fails into an empty renderer. 30_export_map
    already skips them; they are not export blockers. FD015802 has 1
    such ref (A_SEstoneimage)."""
    result = classify_map("FD015802")
    assert result["blockers"] == []
    assert result["detail"]["models_missing"] == ["active/A_SEstoneimage"]


def test_empty_map_dir_reports_no_data():
    # FD000802 is one of the five shipped-empty map folders.
    result = classify_map("FD000802")
    assert result["blockers"] == ["no_data"]


def test_unknown_map_reports_no_data():
    result = classify_map("ZZ999999")
    assert result["blockers"] == ["no_data"]
