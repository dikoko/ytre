"""Tests for 34_export_navmesh blob writer."""
import importlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
export_navmesh = importlib.import_module("34_export_navmesh")


def test_navmesh_blob_roundtrip(tmp_path):
    from src.parsers.nnn_parser import parse_nnn
    refs = Path(__file__).parent.parent.parent.parent / "refs"
    src = refs / "models" / "raw" / "Terrain" / "Map.IRD" / "SF001001" / "SF001001.nnn"
    nav = parse_nnn(src)
    out = tmp_path / "navmesh.bin"
    written = export_navmesh.write_navmesh_blob(nav, out)
    data = out.read_bytes()
    assert written == len(data)
    assert data[:4] == b"YTNV"
    assert struct.unpack_from("<I", data, 4)[0] == 1
    cell_count = struct.unpack_from("<I", data, 8)[0]
    assert cell_count == len(nav.cells)
    # first cell's 13 floats match the parsed cell
    got = struct.unpack_from("<13f", data, 12)
    c = nav.cells[0]
    want = (c.normal[0], c.normal[1], c.normal[2], c.d,
            c.verts[0][0], c.verts[0][1], c.verts[0][2],
            c.verts[1][0], c.verts[1][1], c.verts[1][2],
            c.verts[2][0], c.verts[2][1], c.verts[2][2])
    for g, w in zip(got, want):
        assert abs(g - w) < 1e-4
    tile_off = 12 + cell_count * 13 * 4
    assert struct.unpack_from("<I", data, tile_off)[0] == len(nav.tiles)


def test_walls_blob_roundtrip(tmp_path):
    from src.parsers.opg_parser import parse_opg
    refs = Path(__file__).parent.parent.parent.parent / "refs"
    src = refs / "models" / "raw" / "Terrain" / "Map.IRD" / "SF001001" / "SF001001.opg"
    grid = parse_opg(src)
    out = tmp_path / "walls.bin"
    written = export_navmesh.write_walls_blob(grid, out)
    data = out.read_bytes()
    assert written == len(data)
    assert data[:4] == b"YTWL"
    assert struct.unpack_from("<I", data, 4)[0] == 1
    assert struct.unpack_from("<2H", data, 8) == (grid.width, grid.height)
    assert bytes(data[12:]) == bytes(grid.cells)


def test_empty_navmesh_writes_nothing(tmp_path):
    result = export_navmesh.export_map("FD000100", tmp_path)
    assert result["navmesh"] == 0
    assert not (tmp_path / "navmesh.bin").exists()
