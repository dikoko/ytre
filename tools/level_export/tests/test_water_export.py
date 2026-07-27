"""Tests for water export (scripts/32_export_water.py)."""
import importlib
import json
from pathlib import Path

import pytest

export_water = importlib.import_module("scripts.32_export_water")

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"


def test_export_sf001001_water_json(tmp_path):
    out = export_water.export_water("SF001001", out_root=tmp_path)
    data = json.loads((tmp_path / "SF001001" / "water.json").read_text())
    assert out is not None
    obj = data["objects"][0]
    assert obj["type"] == 1
    assert len(obj["mat_info"]) == 4
    # textures are shared indices into the fleet-wide water texture set
    assert obj["texture0"] == 0 and obj["texture1"] == 0
    assert data["textures"][0].endswith(".png")
    mesh = data["meshes"][0]
    # positions are Godot-space: D3D z=74 -> godot z=-74 (hand-verified v0)
    assert mesh["positions"][0:3] == pytest.approx([19.0, -0.4, -74.0])
    # 4 verts, 1 quad strip -> 2 triangles -> 6 indices
    assert len(mesh["indices"]) == 6
    # baked diffuse 0xAAFFFFFF -> RGBA floats, alpha 170/255
    assert mesh["colors"][3] == pytest.approx(170 / 255, abs=1e-4)


def test_export_beach_emitter_data(tmp_path):
    """Beach shore-wave emitter (Tier 2): file-level params + per-object
    shore points, all z-negated into Godot space (positions AND the N/U
    direction vectors)."""
    export_water.export_water("SF001001", out_root=tmp_path)
    data = json.loads((tmp_path / "SF001001" / "water.json").read_text())
    beach = data["beach"]
    assert beach["size_u"] == 1 and beach["size_n"] == 1
    assert beach["delta"] == pytest.approx(0.5)
    assert beach["frequency"] == pytest.approx(0.5)
    assert beach["velocity"] == pytest.approx(0.5)
    assert beach["life"] == pytest.approx(0.5)
    assert beach["texture_ids"] == [2, 2]  # pado1
    pts = data["objects"][0]["beach_points"]
    assert len(pts["positions"]) == 91 * 3
    assert len(pts["normals"]) == 91 * 3
    assert len(pts["us"]) == 91 * 3
    # first point, hand-verified from the .wtr (D3D z negated)
    assert pts["positions"][0:3] == pytest.approx(
        [23.74041748046875, -0.39000001549720764, -73.94032287597656])
    assert pts["normals"][0:3] == pytest.approx(
        [0.7065643072128296, 0.0, -0.7076488137245178])
    assert pts["us"][0:3] == pytest.approx(
        [0.2984851598739624, 0.0, 0.2977992296218872])


def test_export_map_without_wtr_returns_none(tmp_path):
    # FD000802 is a shipped-empty folder
    assert export_water.export_water("FD000802", out_root=tmp_path) is None
    assert not (tmp_path / "FD000802").exists()


def test_shared_water_textures_written():
    """The 5 fleet-wide Water.IRD textures convert into client/assets/water
    with ASCII-safe names."""
    written = export_water.ensure_water_textures()
    names = sorted(p.name for p in written)
    assert names == ["2a.png", "2b.png", "line.png", "pado1.png", "pado2.png"]
    for p in written:
        assert p.exists()


def test_write_tscn_emits_water_node(tmp_path):
    export_map = importlib.import_module("scripts.30_export_map")
    out = tmp_path / "TEST.tscn"
    export_map.write_tscn(out, "TEST", [], [], [], [], {}, None,
                          has_water=True)
    content = out.read_text()
    assert '[node name="Water" type="Node3D" parent="."]' in content
    assert 'metadata/water_json = "res://assets/maps/TEST/water.json"' in content
    assert 'water_loader.gd' in content

    out2 = tmp_path / "DRY.tscn"
    export_map.write_tscn(out2, "DRY", [], [], [], [], {}, None)
    assert "Water" not in out2.read_text()
