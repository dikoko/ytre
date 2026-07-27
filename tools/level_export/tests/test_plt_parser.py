"""Tests for PLT parser — per-map light settings (sun direction + colors)."""
import math
from pathlib import Path

import pytest

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
SF001001_PLT = MAP_DIR / "SF001001" / "SF001001.plt"


def test_plt_parser_reads_sf001001_sun():
    from src.parsers.plt_parser import PLTParser
    settings = PLTParser().parse(SF001001_PLT)
    sun = settings.sun
    # values verified by hand against the 68-byte file
    assert sun.direction == pytest.approx((-0.11, -1.0, 0.29), abs=1e-3)
    assert sun.diffuse[:3] == pytest.approx((1.0, 0.996, 0.933), abs=1e-3)
    assert sun.ambient[:3] == pytest.approx((0.816, 0.792, 0.69), abs=1e-3)
    assert settings.point_light_count == 0


def test_sun_metadata_lines_convert_d3d_to_godot():
    """Exporter emits the .plt sun as node metadata (terrain + props nodes):
    direction z negated (D3D->Godot), colors passed through."""
    import importlib
    export_map = importlib.import_module("scripts.30_export_map")
    from src.parsers.plt_parser import PLTParser
    settings = PLTParser().parse(SF001001_PLT)
    lines = export_map.sun_metadata_lines(settings)
    assert len(lines) == 3
    assert lines[0].startswith("metadata/sun_direction = Vector3(-0.11, -1, -0.29")
    assert lines[1].startswith("metadata/sun_diffuse = Color(1, 0.996078, 0.933333")
    assert lines[2].startswith("metadata/sun_ambient = Color(0.815686, 0.792157, 0.690196")
    assert export_map.sun_metadata_lines(None) == []


def test_terrain_vertex_diffuse_saturates_on_flat_ground():
    """D3D FF lighting for the terrain material (Ambient=0.7, Diffuse=1.0,
    matching retail client behavior) with the SF001001 sun saturates to white
    on flat ground — the original lawn was the raw tile texture."""
    from src.parsers.plt_parser import PLTParser
    sun = PLTParser().parse(SF001001_PLT).sun
    dx, dy, dz = sun.direction
    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
    n_dot_l = max(0.0, -dy / mag)  # flat ground, N = +Y
    for i in range(3):
        channel = 0.7 * sun.ambient[i] + 1.0 * sun.diffuse[i] * n_dot_l
        assert channel >= 1.0, f"channel {i} = {channel} did not saturate"


def test_plt_parser_reads_sf001002_point_lights():
    """Each point-light record is 324 bytes (booleans stored as int32).
    First-light values verified by hand against the 2336-byte file."""
    from src.parsers.plt_parser import PLTParser
    settings = PLTParser().parse(MAP_DIR / "SF001002" / "SF001002.plt")
    assert settings.point_light_count == 7
    assert len(settings.point_lights) == 7
    pl = settings.point_lights[0]
    assert pl.position == pytest.approx((81.0, 1.0, 125.0), abs=0.1)
    assert pl.diffuse[:3] == pytest.approx((1.0, 1.0, 128 / 255), abs=1e-4)
    assert pl.ambient[:3] == pytest.approx((0.48, 0.5, 0.7), abs=0.01)
    assert pl.max_range == pytest.approx(20.0)
    assert pl.attenuation == pytest.approx((0.0, 1.0, 0.0))
    assert pl.dummy == 1  # editor flag; runtime lights the scene regardless


def test_plt_parser_reads_fd000100_red_light():
    from src.parsers.plt_parser import PLTParser
    settings = PLTParser().parse(MAP_DIR / "FD000100" / "FD000100.plt")
    assert settings.point_light_count == 5
    pl = settings.point_lights[0]
    assert pl.diffuse[:3] == pytest.approx((1.0, 0.0, 0.0), abs=1e-3)
    assert pl.max_range == pytest.approx(5.0)


def test_plt_parser_zero_point_lights_keeps_empty_list():
    from src.parsers.plt_parser import PLTParser
    settings = PLTParser().parse(SF001001_PLT)
    assert settings.point_lights == []


def test_point_light_metadata_lines():
    """Exporter emits point lights as packed metadata (13 floats per light:
    pos.xyz Godot-space, diffuse.rgb, ambient.rgb, max_range, a0, a1, a2)."""
    import importlib
    export_map = importlib.import_module("scripts.30_export_map")
    from src.parsers.plt_parser import PLTParser

    settings = PLTParser().parse(MAP_DIR / "SF001002" / "SF001002.plt")
    lines = export_map.sun_metadata_lines(settings)
    assert len(lines) == 5
    assert lines[3] == "metadata/point_light_count = 7"
    assert lines[4].startswith("metadata/point_lights = PackedFloat32Array(")
    floats = [float(v) for v in lines[4].split("(")[1].rstrip(")").split(",")]
    assert len(floats) == 7 * 13
    # first light: pos z negated (D3D 125 -> Godot -125)
    assert floats[0:3] == pytest.approx((81.0, 1.0, -125.0), abs=0.1)
    assert floats[3:6] == pytest.approx((1.0, 1.0, 128 / 255), abs=1e-4)
    assert floats[9] == pytest.approx(20.0)      # max_range
    assert floats[10:13] == pytest.approx((0.0, 1.0, 0.0))  # attenuation

    # sun-only map: no point-light metadata at all
    sun_only = export_map.sun_metadata_lines(PLTParser().parse(SF001001_PLT))
    assert len(sun_only) == 3


def test_dir_light_set_metadata_lines():
    """Day/night alternative lights (stored after the point lights; the
    original client swaps the active sun on demand) are exported as
    packed metadata — 9 floats per light: dir.xyz (z negated), diffuse.rgb,
    ambient.rgb. FD015101 has an authored-black sun whose only real light
    lives in the set."""
    import importlib
    export_map = importlib.import_module("scripts.30_export_map")
    from src.parsers.plt_parser import PLTParser

    settings = PLTParser().parse(MAP_DIR / "FD015101" / "FD015101.plt")
    lines = export_map.sun_metadata_lines(settings)
    dl = [l for l in lines if l.startswith("metadata/dir_light_")]
    assert dl[0] == "metadata/dir_light_count = 1"
    assert dl[1].startswith("metadata/dir_light_set = PackedFloat32Array(")
    floats = [float(v) for v in dl[1].split("(")[1].rstrip(")").split(",")]
    assert len(floats) == 9
    assert floats[2] == pytest.approx(-0.06, abs=0.01)   # dir z negated
    assert floats[3:6] == pytest.approx((0.588, 0.588, 0.588), abs=1e-3)
    assert floats[6:9] == pytest.approx((0.2, 0.8, 1.0), abs=1e-3)

    # maps without a dir-light set emit nothing
    sun_only = export_map.sun_metadata_lines(PLTParser().parse(SF001001_PLT))
    assert not any(l.startswith("metadata/dir_light_") for l in sun_only)
