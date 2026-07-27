"""Tests for negative-determinant placement support (mirrored mesh variants).

negative_det_items filters placed (obj, prefix) pairs down to those needing
a mesh mirrored across X (basis_det(item.transform) < 0). ensure_mirror_glb
generates `{model_name}_mirrorx.glb` on the fly (same TMD source lookup +
export + texture embed as scripts/22_export_props.export_single_prop), or
reuses it if already on disk.
"""
from dataclasses import dataclass
from pathlib import Path

from scripts._mirror_export import negative_det_items, ensure_mirror_glb

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
PROP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Object"
ARTIFICIAL_DIR = PROP_IRD / "Artificial.IRD"


@dataclass
class _Item:
    unique_id: int
    model_id: int
    transform: list[float]


@dataclass
class _Entry:
    index: int
    category: str
    model_name: str


def _mat(det_sign: float) -> list[float]:
    """Identity-ish D3D matrix with rotation det sign flipped via one axis."""
    a = det_sign
    return [a, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def test_negative_det_items_filters_by_det_and_placement():
    items = [
        (_Item(unique_id=1, model_id=0, transform=_mat(1.0)), "obj"),   # det > 0, placed
        (_Item(unique_id=2, model_id=1, transform=_mat(-1.0)), "obj"),  # det < 0, placed
        (_Item(unique_id=3, model_id=2, transform=_mat(-1.0)), "obj"),  # det < 0, NOT placed (missing GLB)
    ]
    glb_paths = {0: "res://a.glb", 1: "res://b.glb"}  # model_id 2 unresolved
    ocg_entries = [
        _Entry(index=0, category="artificial", model_name="a"),
        _Entry(index=1, category="artificial", model_name="b"),
        _Entry(index=2, category="artificial", model_name="c"),
    ]

    result = negative_det_items(items, glb_paths, ocg_entries)

    assert [item.unique_id for item, _prefix in result] == [2]


def test_negative_det_items_empty_when_all_positive():
    items = [(_Item(unique_id=1, model_id=0, transform=_mat(1.0)), "obj")]
    glb_paths = {0: "res://a.glb"}
    ocg_entries = [_Entry(index=0, category="artificial", model_name="a")]
    assert negative_det_items(items, glb_paths, ocg_entries) == []


def test_ensure_mirror_glb_reuses_existing_file(tmp_path):
    """If {model_name}_mirrorx.glb already exists, no TMD lookup/export
    happens — the res:// path is returned directly."""
    out_dir = tmp_path / "artificial"
    out_dir.mkdir(parents=True)
    (out_dir / "already_mirrored_mirrorx.glb").write_bytes(b"stub")

    res_path = ensure_mirror_glb("already_mirrored", "artificial", tmp_path, [])

    assert res_path == "res://assets/props/models/artificial/already_mirrored_mirrorx.glb"


def test_ensure_mirror_glb_returns_none_for_unknown_model():
    res_path = ensure_mirror_glb("no_such_prop_xyz", "artificial", Path("/nonexistent"), [])
    assert res_path is None


def test_ensure_mirror_glb_generates_on_the_fly(tmp_path):
    """No existing GLB, but a real TMD is discoverable: generates the mirror
    variant end-to-end (export_prop mirror_x=True + embed_textures), same
    as 22_export_props.export_single_prop."""
    from scripts._prop_config import discover_props, TEXTURE_SEARCH_DIRS

    props = discover_props(["artificial"])
    category, prop_id, tmd_path = next(
        (c, p, t) for c, p, t in props if p.lower().startswith("a_book")
    )

    res_path = ensure_mirror_glb(prop_id, category, tmp_path, TEXTURE_SEARCH_DIRS)

    expected = f"res://assets/props/models/{category}/{prop_id}_mirrorx.glb"
    assert res_path == expected
    out_file = tmp_path / category / f"{prop_id}_mirrorx.glb"
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_prop_tmd_index_lookup_is_case_insensitive():
    """_prop_tmd_index keys must be lowercase so a model_name whose case
    doesn't match the on-disk prop_id (as resolve_glb_path in
    30_export_map.py already tolerates) still resolves. Regression test for
    the OCG model_name / discovered prop_id casing mismatch."""
    from scripts._mirror_export import _prop_tmd_index
    from scripts._prop_config import discover_props

    props = discover_props(["artificial"])
    category, prop_id, tmd_path = next(
        (c, p, t) for c, p, t in props if p.lower().startswith("a_book")
    )

    index = _prop_tmd_index()

    # Keys are stored lowercase; looking up a differently-cased variant's
    # .lower() must resolve to the same entry regardless of the original
    # prop_id's casing.
    entry = index.get(prop_id.swapcase().lower())
    assert entry is not None
    assert entry == (category, tmd_path)


def test_ensure_mirror_glb_case_insensitive_lookup(tmp_path):
    """ensure_mirror_glb must resolve model_name regardless of case, same
    as resolve_glb_path in scripts/30_export_map.py."""
    from scripts._prop_config import discover_props, TEXTURE_SEARCH_DIRS

    props = discover_props(["artificial"])
    category, prop_id, tmd_path = next(
        (c, p, t) for c, p, t in props if p.lower().startswith("a_book")
    )

    mismatched_case = prop_id.swapcase()
    assert mismatched_case != prop_id  # sanity: casing actually differs

    res_path = ensure_mirror_glb(mismatched_case, category, tmp_path, TEXTURE_SEARCH_DIRS)

    expected = f"res://assets/props/models/{category}/{mismatched_case}_mirrorx.glb"
    assert res_path == expected
    out_file = tmp_path / category / f"{mismatched_case}_mirrorx.glb"
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_ensure_mirror_glb_returns_none_and_warns_on_generation_failure(tmp_path, monkeypatch, capsys):
    """A malformed/unparseable TMD must not crash the whole map export — one
    bad prop should degrade to a warning + None, same as
    22_export_props.export_single_prop's try/except."""
    from scripts._prop_config import discover_props, TEXTURE_SEARCH_DIRS
    from src.parsers.tmd_parser import TMDParser

    props = discover_props(["artificial"])
    category, prop_id, tmd_path = next(
        (c, p, t) for c, p, t in props if p.lower().startswith("a_book")
    )

    def _broken_parse(self, path):
        raise ValueError("simulated malformed TMD")

    monkeypatch.setattr(TMDParser, "parse", _broken_parse)

    res_path = ensure_mirror_glb(prop_id, category, tmp_path, TEXTURE_SEARCH_DIRS)

    assert res_path is None
    out_file = tmp_path / category / f"{prop_id}_mirrorx.glb"
    assert not out_file.exists()

    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert prop_id in captured.out
    assert "simulated malformed TMD" in captured.out
