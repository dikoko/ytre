"""Tests for tile compositor — blends tile textures into composites."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
TILE_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Tile.IRD"


def test_resolve_tile_texture_path():
    from scripts._tile_compositor import resolve_tile_dir
    # GRASS01 directory should be found (case-insensitive)
    result = resolve_tile_dir("GRASS01", TILE_DIR)
    assert result is not None, "Could not find GRASS01 directory"
    assert result.exists()


def test_load_tile_texture():
    from scripts._tile_compositor import load_tile_texture, resolve_tile_dir
    tile_dir = resolve_tile_dir("GRASS01", TILE_DIR)
    assert tile_dir is not None
    # grass011_0.tga is a known file in grass01 directory
    img = load_tile_texture(tile_dir, "grass011_0.tga")
    assert img is not None
    assert img.mode == "RGBA"
    assert img.size[0] == img.size[1]  # square


def test_composite_single_layer():
    from scripts._tile_compositor import composite_layers
    from src.parsers.tcg_parser import TCGParser
    reg = TCGParser().parse(TILE_DIR / "tileregistry.tcg")
    # A single-layer combo: just GRASS01 full fill (kind=50, idx=0xF, opt=0 -> id=0x32F0)
    tile_id = 0x32F0
    result = composite_layers([tile_id, 0, 0, 0], reg, TILE_DIR)
    assert result is not None
    assert result.mode == "RGB"
    assert result.size[0] == result.size[1]


def test_composite_two_layers():
    from scripts._tile_compositor import composite_layers
    from src.parsers.tcg_parser import TCGParser
    reg = TCGParser().parse(TILE_DIR / "tileregistry.tcg")
    # Two-layer combo from SF001001 palette[0]: (0x4DF0, 0x3230, 0, 0)
    result = composite_layers([0x4DF0, 0x3230, 0, 0], reg, TILE_DIR)
    assert result is not None
    assert result.mode == "RGB"


def test_blend_d3d_truncation_semantics():
    """Exact replica of the original client's per-channel tile blend:
    out = int(src*sa/255.) + int(dst*(1-sa/255.)) per channel, both truncated."""
    import numpy as np
    from scripts._tile_compositor import blend_d3d
    src = np.full((1, 1, 4), 128, np.uint8)
    dst = np.full((1, 1, 4), 128, np.uint8)
    out = blend_d3d(src, dst)
    # int(128*128/255.)=64 ; int(128*(1-128/255.))=63 ; 64+63=127 (NOT 128)
    assert out[0, 0].tolist() == [127, 127, 127, 255]


def test_blend_d3d_opaque_src_wins():
    import numpy as np
    from scripts._tile_compositor import blend_d3d
    src = np.zeros((1, 1, 4), np.uint8); src[0, 0] = [10, 20, 30, 255]
    dst = np.full((1, 1, 4), 200, np.uint8)
    assert blend_d3d(src, dst)[0, 0].tolist() == [10, 20, 30, 255]


def test_blend_d3d_transparent_src_keeps_dst():
    import numpy as np
    from scripts._tile_compositor import blend_d3d
    src = np.zeros((1, 1, 4), np.uint8)
    dst = np.asarray([[[50, 60, 70, 255]]], np.uint8)
    assert blend_d3d(src, dst)[0, 0].tolist() == [50, 60, 70, 255]


def test_composite_raises_on_unresolvable(tmp_path):
    import pytest
    from scripts._tile_compositor import composite_layers, TileResolutionError
    class FakeRegistry:  # kind 0x99 unknown
        tile_sets = {}
    with pytest.raises(TileResolutionError) as e:
        composite_layers([0x99F0], FakeRegistry(), tmp_path)
    assert "0x99F0" in str(e.value)


def test_composite_lenient_returns_none(tmp_path):
    from scripts._tile_compositor import composite_layers
    class FakeRegistry:
        tile_sets = {}
    assert composite_layers([0x99F0], FakeRegistry(), tmp_path, lenient=True) is None


def test_kind_zero_is_empty_layer_even_with_index_bits():
    """Kind 0x00 means 'empty layer' REGARDLESS of index/opt bits — the
    original client tests the kind byte, not the whole tile id.
    Shipped data (e.g. FD007xxx) carries ids like 0x0010 with stray
    index bits."""
    from scripts._tile_compositor import composite_layers
    from src.parsers.tcg_parser import TCGParser
    reg = TCGParser().parse(TILE_DIR / "tileregistry.tcg")
    # strict mode: no error, composites as base-layer-only
    result = composite_layers([0x32F0, 0x0010, 0, 0], reg, TILE_DIR)
    base_only = composite_layers([0x32F0, 0, 0, 0], reg, TILE_DIR)
    assert result is not None
    assert list(result.getdata()) == list(base_only.getdata())


def test_missing_texture_in_known_set_skips_layer():
    """A tile set with no art for the referenced fringe index composites
    with the layer silently skipped: the original client's tile-texture
    lookup yields nothing for unloaded ids and its compositor skips
    absent sources.
    ROCK1044 (kind 0x38) ships only full tiles; 0x3860 is a fringe ref."""
    from scripts._tile_compositor import composite_layers
    from src.parsers.tcg_parser import TCGParser
    reg = TCGParser().parse(TILE_DIR / "tileregistry.tcg")
    result = composite_layers([0x32F0, 0x3860, 0, 0], reg, TILE_DIR)
    base_only = composite_layers([0x32F0, 0, 0, 0], reg, TILE_DIR)
    assert result is not None
    assert list(result.getdata()) == list(base_only.getdata())


def test_unknown_nonzero_kind_still_raises():
    """A nonzero kind absent from the registry is data we cannot interpret —
    that stays a hard error in strict mode (no shipped map triggers this)."""
    import pytest
    from scripts._tile_compositor import composite_layers, TileResolutionError
    from src.parsers.tcg_parser import TCGParser
    reg = TCGParser().parse(TILE_DIR / "tileregistry.tcg")
    with pytest.raises(TileResolutionError):
        composite_layers([0x32F0, 0x01F0, 0, 0], reg, TILE_DIR)  # kind 0x01 unknown
