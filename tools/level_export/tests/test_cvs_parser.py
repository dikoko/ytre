"""Tests for CVS parser — terrain tile canvas data."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
SF001001_CVS = MAP_DIR / "SF001001" / "SF001001.cvs"


def test_cvs_parser_reads_file():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    assert data.grid_rows == 149
    assert data.grid_cols == 149


def test_cvs_palette_count():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    assert len(data.palette) == 318, f"Expected 318 palette entries, got {len(data.palette)}"


def test_cvs_palette_entries_have_four_layers():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    for i, entry in enumerate(data.palette[:5]):
        assert len(entry) == 4, f"Palette[{i}] has {len(entry)} layers, expected 4"


def test_cvs_cells_shape():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    assert len(data.cells) == 149, f"Expected 149 rows, got {len(data.cells)}"
    assert len(data.cells[0]) == 149, f"Expected 149 cols, got {len(data.cells[0])}"


def test_cvs_cell_indices_in_palette_range():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    pal_count = len(data.palette)
    for row in data.cells:
        for cell_id in row:
            assert 0 <= cell_id < pal_count, f"Cell index {cell_id} out of range [0, {pal_count})"


def test_cvs_used_tile_kinds():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    kinds = set()
    for entry in data.palette:
        for tile_id in entry:
            if tile_id != 0:
                kinds.add((tile_id >> 8) & 0xFF)
    assert len(kinds) == 8, f"Expected 8 tile kinds, got {len(kinds)}: {kinds}"


def test_cvs_visibility_shape():
    from src.parsers.cvs_parser import CVSParser
    data = CVSParser().parse(SF001001_CVS)
    assert len(data.visibility) == 149
    assert len(data.visibility[0]) == 149
