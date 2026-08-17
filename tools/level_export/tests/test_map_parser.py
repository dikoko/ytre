"""Tests for map_parser — the movement attribute grid (.map)."""
import struct
from pathlib import Path

import pytest

from src.parsers.map_parser import parse_map, CELL_RECORD_SIZE

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"


def _map_path(code: str):
    p = MAP_IRD / code / f"{code}.map"
    if not p.exists():
        pytest.skip(f"{code}.map not available")
    return p


def _synthetic(dx: int, dy: int, attrs: bytes) -> bytes:
    return (struct.pack("<2i", 0, 0)
            + struct.pack("<2i", dx, dy) + bytes(dx * dy * CELL_RECORD_SIZE)
            + struct.pack("<2i", dx, dy) + attrs)


def test_synthetic_roundtrip(tmp_path):
    attrs = bytes([0, 2, 205, 13, 1, 0])  # 205 == -51 signed
    p = tmp_path / "T.map"
    p.write_bytes(_synthetic(3, 2, attrs))
    g = parse_map(p)
    assert (g.width, g.height) == (3, 2)
    assert g.attr(0, 0) == 0
    assert g.attr(1, 0) == 2
    assert g.attr(2, 0) == -51
    assert g.attr(0, 1) == 13
    assert not g.movable(0, 0)      # zero blocked
    assert g.movable(1, 0)          # open ground
    assert not g.movable(2, 0)      # negative blocked (signed test)
    assert g.movable(0, 1)          # sit attr walkable
    assert not g.movable(-1, 0)     # out of bounds blocked...
    assert not g.movable(0, 2)      # ...both axes


def test_dims_mismatch_rejected(tmp_path):
    data = (struct.pack("<2i", 0, 0)
            + struct.pack("<2i", 2, 2) + bytes(2 * 2 * CELL_RECORD_SIZE)
            + struct.pack("<2i", 3, 2) + bytes(6))
    p = tmp_path / "bad.map"
    p.write_bytes(data)
    with pytest.raises(ValueError, match="cell record size assumption"):
        parse_map(p)


def test_sf001001_known_cells():
    g = parse_map(_map_path("SF001001"))
    assert (g.width, g.height) == (149, 149)
    # School front stairs (the 2026-08-11 LOS-wall false block): movable.
    for x in range(121, 125):
        for z in range(74, 78):
            assert g.movable(x, z), f"school stair cell ({x},{z})"
    # Stray plaza islands (2026-08-16 report): blocked in the ORIGINAL too.
    for x, z in [(61, 98), (66, 102), (70, 107), (65, 108)]:
        assert not g.movable(x, z), f"stray ({x},{z})"
    # Open plaza row.
    assert all(g.movable(x, 100) for x in range(60, 96))
    # Sit attributes are walkable.
    assert g.attr(126, 22) == 13 and g.movable(126, 22)


def test_sf002013_trapped_spawn_fixture():
    g = parse_map(_map_path("SF002013"))
    assert (g.width, g.height) == (79, 79)
    assert not g.movable(64, 68)   # default spawn cell — blocked
    assert not g.movable(65, 68)   # east neighbor — blocked
    assert g.movable(64, 67)       # north neighbor — open


def test_fleet_parses():
    parsed = 0
    for map_dir in sorted(MAP_IRD.iterdir()):
        p = map_dir / f"{map_dir.name}.map"
        if not p.exists():
            continue
        g = parse_map(p)
        assert g.width > 0 and g.height > 0
        parsed += 1
    assert parsed >= 300  # 325 shipped; tolerate partial local trees
