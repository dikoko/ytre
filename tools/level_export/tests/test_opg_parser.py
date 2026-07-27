"""Tests for .opg wall-grid parser."""
import struct
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"


def _ifo_dims(code: str) -> tuple[int, int]:
    data = (MAP_DIR / code / f"{code}.ifo").read_bytes()
    row, col = struct.unpack_from("<2i", data, 0)
    return row, col


def test_sf001001_dims_and_values():
    from src.parsers.opg_parser import parse_opg, wall_count
    g = parse_opg(MAP_DIR / "SF001001" / "SF001001.opg")
    assert (g.width, g.height) == (149, 149)
    assert len(g.cells) == 149 * 149
    assert set(g.cells) <= {0, 1}
    assert 0 < wall_count(g) < 149 * 149


def test_fleet_dims_match_ifo():
    from src.parsers.opg_parser import parse_opg
    seen = 0
    for d in sorted(MAP_DIR.iterdir()):
        f = d / f"{d.name}.opg"
        if not f.is_file():
            continue
        seen += 1
        g = parse_opg(f)
        row, col = _ifo_dims(d.name)
        assert (g.width, g.height) == (row - 1, col - 1), d.name
        assert set(g.cells) <= {0, 1}, d.name
    assert seen == 320


def test_garbage_values_normalise_to_open():
    # SF001009.opg carries MSVC heap fill (0xDDDD/0xCDCD/...); the original
    # tests `== PROPERTY_WALL` so anything else is open ground.
    from src.parsers.opg_parser import parse_opg
    g = parse_opg(MAP_DIR / "SF001009" / "SF001009.opg")
    assert set(g.cells) <= {0, 1}
