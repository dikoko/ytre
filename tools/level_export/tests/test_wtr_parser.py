"""Tests for WTR parser — per-map water mesh + region data.

Format = the original client's water serialization field order with NO
archive class header (validated byte-level: SF001001.wtr starts 4,0,1,0).
See the 2026-07-17 water design spec for the full layout.
"""
from pathlib import Path

import pytest

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"


def test_parses_sf001001_pool():
    from src.parsers.wtr_parser import WTRParser
    info = WTRParser().parse(MAP_DIR / "SF001001" / "SF001001.wtr")
    assert len(info.vertices) == 4
    assert len(info.side_vertices) == 0
    assert len(info.meshes) == 1
    assert len(info.side_meshes) == 0
    v0 = info.vertices[0]
    # hand-verified against the hex dump
    assert v0.position == pytest.approx((19.0, -0.4, 74.0))
    assert v0.normal == pytest.approx((0.0, 1.0, 0.0))
    assert v0.diffuse == 0xAAFFFFFF  # translucent white, D3D ARGB
    # 1 strip mesh: num_triangle + 2 indices
    assert len(info.meshes[0].strip_indices) == info.meshes[0].num_triangles + 2
    assert len(info.water_objects) >= 1
    obj = info.water_objects[0]
    assert obj.type in (0, 1)
    assert len(obj.mat_info) == 4
    assert all(len(row) == 12 for row in obj.mat_info)
    assert info.textures, "texture name list must be non-empty"


def test_parses_largest_water_map_fully():
    """FD006001 (72KB — mostly beach-point arrays; the mesh itself is tiny).
    The parser must consume the file EXACTLY to the last byte."""
    from src.parsers.wtr_parser import WTRParser
    info = WTRParser().parse(MAP_DIR / "FD006001" / "FD006001.wtr")
    assert info.textures == ["2b.tga", "2a.tga", "파도1.tga", "파도2.tga", "line.tga"]
    assert info.bytes_consumed == (MAP_DIR / "FD006001" / "FD006001.wtr").stat().st_size
    for mesh in info.meshes + info.side_meshes:
        assert max(mesh.strip_indices) < len(info.vertices) + len(info.side_vertices)


def test_all_98_water_maps_parse():
    """Every shipped .wtr parses to the exact byte count — the format holds
    fleet-wide, not just on the two pinned maps."""
    from src.parsers.wtr_parser import WTRParser
    wtrs = sorted(MAP_DIR.glob("*/*.wtr")) + sorted(MAP_DIR.glob("*/*.WTR"))
    assert len(wtrs) == 98
    for p in wtrs:
        info = WTRParser().parse(p)
        assert info.bytes_consumed == p.stat().st_size, p.name


def test_beach_emitter_params_sf001001():
    """File-level beach params + per-object shore-point arrays (Tier 2).
    The serialized order is Normal[], U[], Position[] — three contiguous
    arrays, NOT interleaved triples."""
    from src.parsers.wtr_parser import WTRParser
    info = WTRParser().parse(MAP_DIR / "SF001001" / "SF001001.wtr")
    assert info.beach_size_u == 1
    assert info.beach_size_n == 1
    assert info.beach_delta == pytest.approx(0.5)
    assert info.beach_frequency == pytest.approx(0.5)
    assert info.beach_velocity == pytest.approx(0.5)
    assert info.beach_life == pytest.approx(0.5)
    assert info.beach_texture_ids == (2, 2)  # 파도1.tga
    obj = info.water_objects[0]
    assert obj.num_beach == 91
    assert len(obj.beach_normals) == 91
    assert len(obj.beach_us) == 91
    assert len(obj.beach_positions) == 91
    # hand-verified first entries (raw-read against the serialize order)
    assert obj.beach_normals[0] == pytest.approx(
        (0.7065643072128296, 0.0, 0.7076488137245178))
    assert obj.beach_us[0] == pytest.approx(
        (0.2984851598739624, 0.0, -0.2977992296218872))
    assert obj.beach_positions[0] == pytest.approx(
        (23.74041748046875, -0.39000001549720764, 73.94032287597656))


def test_beach_arrays_empty_when_no_beach():
    """A map whose objects have num_beach == 0 gets empty arrays."""
    from src.parsers.wtr_parser import WTRParser
    info = WTRParser().parse(MAP_DIR / "FD000104" / "FD000104.wtr")
    assert any(o.num_beach == 0 for o in info.water_objects)
    for o in info.water_objects:
        if o.num_beach == 0:
            assert o.beach_normals == []
            assert o.beach_us == []
            assert o.beach_positions == []


def test_strip_to_triangles():
    from src.parsers.wtr_parser import strip_to_triangles
    # strip 0,1,2,3 -> (0,1,2), (2,1,3) with D3D alternation (odd = b,a,c)
    assert strip_to_triangles([0, 1, 2, 3]) == [(0, 1, 2), (2, 1, 3)]
    assert strip_to_triangles([5, 6, 7, 8, 9]) == [
        (5, 6, 7), (7, 6, 8), (7, 8, 9)]
    # degenerate triangles (repeated index) are dropped
    assert strip_to_triangles([0, 1, 1, 2]) == []
