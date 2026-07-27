"""Tests for .nnn navigation-mesh parser."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
SF = MAP_DIR / "SF001001" / "SF001001.nnn"


def test_cell_size():
    from src.parsers.nnn_parser import CELL_SIZE
    assert CELL_SIZE == 88


def test_sf001001_census():
    from src.parsers.nnn_parser import parse_nnn
    nav = parse_nnn(SF)
    assert len(nav.mesh_cell_ranges) == 141
    assert len(nav.cells) == 1019
    assert len(nav.tiles) == 2285
    assert sum(len(v) for v in nav.tiles.values()) == 9239
    assert nav.bytes_consumed == SF.stat().st_size == 141192


def test_fleet_parses_byte_exact():
    from src.parsers.nnn_parser import parse_nnn
    total = 0
    empty = 0
    for d in sorted(MAP_DIR.iterdir()):
        f = d / f"{d.name}.nnn"
        if not f.is_file():
            continue
        total += 1
        nav = parse_nnn(f)
        assert nav.bytes_consumed == f.stat().st_size, d.name
        if not nav.cells:
            empty += 1
    assert total == 325
    assert empty == 49


def test_tile_refs_in_range():
    from src.parsers.nnn_parser import parse_nnn
    nav = parse_nnn(SF)
    for key, refs in nav.tiles.items():
        assert 0 <= key[0] < 149 and 0 <= key[1] < 149
        for idx in refs:
            assert 0 <= idx < len(nav.cells)


def test_vertices_are_world_space():
    from src.parsers.nnn_parser import parse_nnn
    nav = parse_nnn(SF)
    xs = [v[0] for c in nav.cells for v in c.verts]
    zs = [v[2] for c in nav.cells for v in c.verts]
    assert 5.0 < min(xs) < 7.0 and 124.0 < max(xs) < 126.0
    assert 7.0 < min(zs) < 9.0 and 116.0 < max(zs) < 118.0


def test_vertical_cells_rejected():
    from src.parsers.nnn_parser import parse_nnn, is_standable
    nav = parse_nnn(SF)
    standable = [c for c in nav.cells if is_standable(c)]
    assert len(standable) == 842
    assert len(nav.cells) - len(standable) == 177


def test_empty_navmesh():
    from src.parsers.nnn_parser import parse_nnn
    nav = parse_nnn(MAP_DIR / "FD000100" / "FD000100.nnn")
    assert nav.cells == [] and nav.tiles == {}
    assert nav.bytes_consumed == 8
