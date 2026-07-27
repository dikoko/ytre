"""Tests for TCG parser — tile registry data."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
TILE_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Tile.IRD"
TCG_PATH = TILE_DIR / "tileregistry.tcg"


def test_tcg_parser_reads_file():
    from src.parsers.tcg_parser import TCGParser
    data = TCGParser().parse(TCG_PATH)
    assert len(data.tile_sets) == 105, f"Expected 105 tile sets, got {len(data.tile_sets)}"


def test_tcg_tile_set_has_name():
    from src.parsers.tcg_parser import TCGParser
    data = TCGParser().parse(TCG_PATH)
    # Kind 50 should be GRASS01
    ts = data.tile_sets[50]
    assert ts.name == "GRASS01", f"Expected GRASS01, got {ts.name}"


def test_tcg_tile_set_has_textures():
    from src.parsers.tcg_parser import TCGParser
    data = TCGParser().parse(TCG_PATH)
    ts = data.tile_sets[50]  # GRASS01
    assert len(ts.tiles) > 0, "GRASS01 should have texture entries"
    # Index 1, opt 0 should be a .tga filename
    tex = ts.tiles.get((1, 0))
    assert tex is not None, "GRASS01 index=1 opt=0 missing"
    assert tex.endswith(".tga"), f"Expected .tga filename, got {tex}"


def test_tcg_texture_files_exist():
    from src.parsers.tcg_parser import TCGParser
    data = TCGParser().parse(TCG_PATH)
    ts = data.tile_sets[50]  # GRASS01
    set_dir = TILE_DIR / ts.name.lower()
    if not set_dir.exists():
        # Try case variations
        for d in TILE_DIR.iterdir():
            if d.name.lower() == ts.name.lower():
                set_dir = d
                break
    for (idx, opt), filename in list(ts.tiles.items())[:3]:
        tex_path = set_dir / filename
        assert tex_path.exists(), f"Tile texture not found: {tex_path}"


def test_tcg_known_sf001_sets():
    from src.parsers.tcg_parser import TCGParser
    data = TCGParser().parse(TCG_PATH)
    # SF001001 uses kinds: 50, 70, 71, 77, 78, 79, 80, 81
    expected = {50: "GRASS01", 78: "SE001", 79: "SE002", 77: "SE003"}
    for kind_id, name in expected.items():
        assert kind_id in data.tile_sets, f"Kind {kind_id} missing"
        assert data.tile_sets[kind_id].name == name


def test_tcg_palettes():
    from src.parsers.tcg_parser import TCGParser
    data = TCGParser().parse(TCG_PATH)
    assert len(data.palettes) > 0, "Expected at least 1 palette"
