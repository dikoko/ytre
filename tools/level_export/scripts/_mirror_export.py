"""Negative-determinant map placements — mirrored mesh variant support.

.qqq placements whose D3D rotation determinant is negative were baked with
a left-handed world transform. The base D3D->Godot conversion already
performs one Z-mirror (see src/exporters/prop_exporter.py), which is not
enough on its own for these: they need a mesh mirrored across X
(`{model_name}_mirrorx.glb`, exported via export_prop(..., mirror_x=True))
instanced with a matching mirrored placement transform
(scripts._map_transform.format_transform_mirror_x). See
scripts/30_export_map.py write_tscn for where this is wired in.
"""
from pathlib import Path

from scripts._map_transform import basis_det
from scripts._prop_config import discover_props

_PROP_TMD_INDEX: dict[str, tuple[str, Path]] | None = None


def _prop_tmd_index() -> dict[str, tuple[str, Path]]:
    """Lazy, cached prop_id.lower() -> (category, tmd_path) index via
    discover_props. Keyed lowercase for case-insensitive lookup, same as
    resolve_glb_path in scripts/30_export_map.py (OCG model_name casing
    doesn't always match the on-disk/discovered prop_id casing)."""
    global _PROP_TMD_INDEX
    if _PROP_TMD_INDEX is None:
        _PROP_TMD_INDEX = {
            prop_id.lower(): (category, tmd_path)
            for category, prop_id, tmd_path in discover_props()
        }
    return _PROP_TMD_INDEX


def negative_det_items(all_items, glb_paths: dict[int, str], ocg_entries: list) -> list:
    """(item, prefix) pairs among all_items that are actually placed (model
    resolved in glb_paths) with a negative rotation determinant — these need
    a `{model}_mirrorx.glb` substitute to display correctly."""
    result = []
    for item, prefix in all_items:
        if item.model_id not in glb_paths:
            continue
        if item.model_id >= len(ocg_entries):
            continue
        if basis_det(item.transform) < 0.0:
            result.append((item, prefix))
    return result


def ensure_mirror_glb(
    model_name: str,
    category: str,
    props_dir: Path,
    texture_search_dirs: list[Path],
) -> str | None:
    """Ensure `{model_name}_mirrorx.glb` exists under props_dir/category,
    generating it on the fly if missing (same TMD source lookup + export +
    texture embed as scripts/22_export_props.export_single_prop, but with
    mirror_x=True). Returns its res:// path, or None if no source TMD can
    be located for model_name.
    """
    out_dir = Path(props_dir) / category
    out_path = out_dir / f"{model_name}_mirrorx.glb"
    res_path = f"res://assets/props/models/{category}/{model_name}_mirrorx.glb"

    if out_path.exists():
        return res_path

    index = _prop_tmd_index()
    entry = index.get(model_name.lower())
    if entry is None:
        return None
    _tmd_category, tmd_path = entry

    from src.parsers.tmd_parser import TMDParser
    from src.exporters.prop_exporter import export_prop
    from scripts._export_common import embed_textures

    try:
        model = TMDParser().parse(tmd_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        export_prop(model, out_path, prop_id=f"{model_name}_mirrorx", mirror_x=True)
        embed_textures(out_path, tmd_path.parent, model, texture_dirs=texture_search_dirs)
    except Exception as e:
        print(f"  WARNING: failed to generate mirrored variant of "
              f"'{model_name}' — {e}")
        return None

    return res_path
