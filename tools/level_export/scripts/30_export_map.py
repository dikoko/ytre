#!/usr/bin/env python3
"""
Map Assembly Script

Parses binary map data (.qqq, .ocg, .hwt) and generates a Godot .tscn scene
with terrain and all props placed at their original positions.

Usage:
    python scripts/30_export_map.py SF001001
    python scripts/30_export_map.py SF001001 --dry-run
    python scripts/30_export_map.py SF001001 --apply-overrides
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.qqq_parser import QQQParser
from src.parsers.ocg_parser import OCGParser
from src.parsers.plt_parser import PLTParser
from scripts._map_transform import (
    format_transform, basis_det, d3d_to_godot_basis, format_transform_mirror_x,
    apply_override_to_matrix,
)
from scripts._mirror_export import negative_det_items, ensure_mirror_glb
from scripts._prop_config import TEXTURE_SEARCH_DIRS

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client"
PROPS_DIR = CLIENT_DIR / "assets" / "props" / "models"
OUTPUT_DIR = CLIENT_DIR / "scenes" / "maps"


# Props to exclude from map scene (underground geometry, non-visible in original game)
SKIP_MODELS = {
    "s_SEmotion",       # "GO" text prop
    # "s_SEhall",       # Restored - important building at (123, 92)
    # "a_SEswim02-04",  # Restored - pool wall/edge pieces
    # "a_SEpool01",     # Restored - pool structure
    # "a_SEtrack01-03",  # Restored - road/running track segments
    "p_portal003a",     # Portal pad with GO text and blue platform
}


def resolve_glb_path(entry, props_dir: Path) -> str | None:
    """Resolve OCG entry to a res:// GLB path. Case-insensitive lookup."""
    category = entry.category
    model_name = entry.model_name

    cat_dir = props_dir / category
    if not cat_dir.exists():
        return None

    target_lower = f"{model_name}.glb".lower()
    for f in cat_dir.iterdir():
        if f.name.lower() == target_lower:
            return f"res://assets/props/models/{category}/{f.name}"
    return None


def sun_metadata_lines(light_settings) -> list[str]:
    """Fixed-function sun from the map's .plt as node metadata,
    consumed by terrain_loader.gd and prop_lighting.gd.
    Direction is converted D3D -> Godot (z negated); colors are gamma-space RGB.
    """
    if light_settings is None:
        return []
    sun = light_settings.sun
    dx, dy, dz = sun.direction
    dr, dg, db = sun.diffuse[:3]
    ar, ag, ab = sun.ambient[:3]
    lines = [
        f'metadata/sun_direction = Vector3({dx:.6g}, {dy:.6g}, {-dz:.6g})',
        f'metadata/sun_diffuse = Color({dr:.6g}, {dg:.6g}, {db:.6g}, 1)',
        f'metadata/sun_ambient = Color({ar:.6g}, {ag:.6g}, {ab:.6g}, 1)',
    ]

    # Point lights from the .plt as one packed array — 13 floats per
    # light: pos.xyz (z negated D3D->Godot), diffuse.rgb, ambient.rgb,
    # max_range, attenuation a0/a1/a2. Runtime loaders feed these into
    # the FF shaders' uniform arrays. All lights are exported: the
    # filename/dummy fields are editor-only bookkeeping the original
    # client never reads (it activates every entry).
    if light_settings.point_lights:
        packed = []
        for pl in light_settings.point_lights:
            x, y, z = pl.position
            packed += [x, y, -z, *pl.diffuse[:3], *pl.ambient[:3],
                       pl.max_range, *pl.attenuation]
        floats = ", ".join(f"{v:.6g}" for v in packed)
        lines.append(
            f"metadata/point_light_count = {len(light_settings.point_lights)}")
        lines.append(f"metadata/point_lights = PackedFloat32Array({floats})")

    # Day/night alternative suns (stored after the point lights; the
    # original client swaps the active sun to one of these on demand).
    # 9 floats per light: dir.xyz (z negated), diffuse.rgb, ambient.rgb.
    # Three maps (FD014402/FD014403/FD015101) ship an authored-BLACK base
    # sun whose only real light lives here; the map editor's L key cycles
    # these for inspection.
    if light_settings.dir_light_set:
        packed = []
        for d in light_settings.dir_light_set:
            dx, dy, dz = d.direction
            packed += [dx, dy, -dz, *d.diffuse[:3], *d.ambient[:3]]
        floats = ", ".join(f"{v:.6g}" for v in packed)
        lines.append(
            f"metadata/dir_light_count = {len(light_settings.dir_light_set)}")
        lines.append(f"metadata/dir_light_set = PackedFloat32Array({floats})")
    return lines


def write_tscn(
    output_path: Path,
    map_code: str,
    objects: list,
    portals: list,
    triggers: list,
    ocg_entries: list,
    glb_paths: dict[int, str],
    hwt_path: Path | None,
    light_settings=None,
    has_water: bool = False,
) -> dict:
    """Write Godot .tscn scene file. Returns stats dict."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_items = (
        [(obj, "obj") for obj in objects]
        + [(p, "portal") for p in portals]
        + [(t, "trigger") for t in triggers]
    )

    # Collect unique GLB paths for ext_resources (original models). Left
    # exactly as before mirrored-variant support was added, so maps with
    # zero negative-determinant placements (e.g. SF001001) get byte-identical
    # ext_resource id assignment.
    unique_glbs = {}
    ext_id_counter = 1

    for model_id, res_path in sorted(glb_paths.items()):
        if res_path not in unique_glbs:
            unique_glbs[res_path] = f"ext_{ext_id_counter}"
            ext_id_counter += 1

    # Negative-determinant placements (basis_det(item.transform) < 0): the
    # object was baked with a left-handed transform. The base D3D->Godot
    # Z-mirror alone isn't enough for these — they need a mesh mirrored
    # across X (`{model}_mirrorx.glb`, generated on the fly if missing) plus
    # a matching mirrored placement transform (format_transform_mirror_x).
    # Resolved per-item (determinant is placement-specific, not
    # model-specific) and appended to unique_glbs AFTER the original-model
    # pass above, so ext ids stay append-only.
    mirror_res_by_item: dict[int, str] = {}
    mirrored_unique_ids: list[str] = []
    for item, _prefix in negative_det_items(all_items, glb_paths, ocg_entries):
        entry = ocg_entries[item.model_id]
        mirror_res = ensure_mirror_glb(entry.model_name, entry.category, PROPS_DIR, TEXTURE_SEARCH_DIRS)
        if mirror_res is None:
            print(f"  WARNING: no source TMD found for mirrored variant of "
                  f"'{entry.model_name}' (unique_id={item.unique_id}) — "
                  f"keeping original (unmirrored) mesh/transform")
            continue
        mirror_res_by_item[id(item)] = mirror_res
        mirrored_unique_ids.append(str(item.unique_id))
        if mirror_res not in unique_glbs:
            unique_glbs[mirror_res] = f"ext_{ext_id_counter}"
            ext_id_counter += 1

    if mirrored_unique_ids:
        print(f"  WARNING: {len(mirrored_unique_ids)} negative-determinant placement(s) "
              f"substituted with mirrored mesh variants (unique_ids: "
              f"{', '.join(mirrored_unique_ids)})")

    terrain_glb_id = f"ext_{ext_id_counter}"
    ext_id_counter += 1
    camera_script_id = f"ext_{ext_id_counter}"
    ext_id_counter += 1
    editor_script_id = f"ext_{ext_id_counter}"
    ext_id_counter += 1
    prop_lighting_script_id = f"ext_{ext_id_counter}"
    ext_id_counter += 1
    water_script_id = f"ext_{ext_id_counter}"
    ext_id_counter += 1

    load_steps = len(unique_glbs) + 6 + (1 if has_water else 0)

    lines = []
    lines.append(f'[gd_scene load_steps={load_steps} format=3]')
    lines.append('')

    for res_path, ext_id in sorted(unique_glbs.items(), key=lambda x: x[1]):
        lines.append(f'[ext_resource type="PackedScene" path="{res_path}" id="{ext_id}"]')

    terrain_script_res = "res://scripts/terrain_loader.gd"
    lines.append(f'[ext_resource type="Script" path="{terrain_script_res}" id="{terrain_glb_id}"]')
    lines.append(f'[ext_resource type="Script" path="res://scripts/fly_camera.gd" id="{camera_script_id}"]')
    lines.append(f'[ext_resource type="Script" path="res://scripts/map_editor.gd" id="{editor_script_id}"]')
    lines.append(f'[ext_resource type="Script" path="res://scripts/prop_lighting.gd" id="{prop_lighting_script_id}"]')
    if has_water:
        lines.append(f'[ext_resource type="Script" path="res://scripts/water_loader.gd" id="{water_script_id}"]')
    lines.append('')

    # Sub-resource: Environment with ambient light
    lines.append('[sub_resource type="Environment" id="env_1"]')
    lines.append('background_mode = 1')  # 1 = COLOR
    lines.append('background_color = Color(0.6, 0.75, 0.9, 1)')  # light sky blue
    lines.append('ambient_light_source = 2')  # 2 = COLOR (constant ambient)
    lines.append('ambient_light_color = Color(0.7, 0.7, 0.75, 1)')
    lines.append('ambient_light_energy = 0.6')
    lines.append('')

    # Root node
    lines.append(f'[node name="{map_code}" type="Node3D"]')
    lines.append(f'script = ExtResource("{editor_script_id}")')
    lines.append('')

    # Terrain as MeshInstance3D with terrain_loader script and tile metadata
    heightmap_res = f"res://assets/maps/{map_code}/{map_code}.png"
    tilemap_res = f"res://assets/maps/{map_code}/{map_code}_tilemap.png"
    tiles_res = f"res://assets/maps/{map_code}/{map_code}_tiles"
    visibility_res = f"res://assets/maps/{map_code}/{map_code}_visibility.png"
    lines.append(f'[node name="Terrain" type="MeshInstance3D" parent="."]')
    lines.append(f'script = ExtResource("{terrain_glb_id}")')
    lines.append(f'metadata/heightmap_path = "{heightmap_res}"')
    lines.append(f'metadata/tilemap_path = "{tilemap_res}"')
    lines.append(f'metadata/tiles_dir = "{tiles_res}"')
    lines.append(f'metadata/visibility_path = "{visibility_res}"')
    lines.extend(sun_metadata_lines(light_settings))
    lines.append('')

    # Fly camera
    lines.append('[node name="Camera3D" type="Camera3D" parent="."]')
    lines.append(f'script = ExtResource("{camera_script_id}")')
    lines.append('transform = Transform3D(1, 0, 0, 0, 0.707, 0.707, 0, -0.707, 0.707, 75, 60, -40)')
    lines.append('current = true')
    lines.append('fov = 60.0')
    lines.append('far = 500.0')
    lines.append('')

    # WorldEnvironment with ambient light
    lines.append('[node name="WorldEnvironment" type="WorldEnvironment" parent="."]')
    lines.append('environment = SubResource("env_1")')
    lines.append('')

    # Directional light — softer with half-opacity shadows
    lines.append('[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]')
    lines.append('transform = Transform3D(0.866025, -0.25, 0.433013, 0, 0.866025, 0.5, -0.5, -0.433013, 0.75, 50, 50, 50)')
    lines.append('light_energy = 0.8')
    lines.append('shadow_enabled = true')
    lines.append('shadow_opacity = 0.4')
    lines.append('')

    # Water surfaces from the map's .wtr (32_export_water.py); built at
    # runtime by water_loader.gd with the FF water shader.
    if has_water:
        lines.append('[node name="Water" type="Node3D" parent="."]')
        lines.append(f'script = ExtResource("{water_script_id}")')
        lines.append(f'metadata/water_json = "res://assets/maps/{map_code}/water.json"')
        lines.append('')

    # Props container — prop_lighting.gd swaps imported StandardMaterial3Ds
    # for the fixed-function port shader at runtime, using the same .plt sun
    # as the terrain (see Coordinate Conventions in CLAUDE.md).
    lines.append('[node name="Props" type="Node3D" parent="."]')
    lines.append(f'script = ExtResource("{prop_lighting_script_id}")')
    lines.extend(sun_metadata_lines(light_settings))
    lines.append('')

    # Place all objects
    placed = 0
    skipped = 0
    # node_name -> original .qqq transform (list[16] D3D row-major), for
    # every placed node. Returned so apply_overrides_to_tscn can compose
    # editor overrides on the TRUE transform (scale/shear intact) instead of
    # regex-rebuilding a lossy Y-rotation-only matrix from the .tscn text.
    node_matrices: dict[str, list[float]] = {}
    # node_names that got the mirror_x treatment (negative-determinant
    # placement + format_transform_mirror_x): apply_override_to_matrix
    # doesn't replicate the mirror_x column-negation, so overrides on these
    # nodes are skipped with a warning rather than silently mis-composed.
    mirrored_nodes: set[str] = set()

    for item, prefix in all_items:
        model_id = item.model_id
        if model_id not in glb_paths:
            skipped += 1
            continue

        mirror_res = mirror_res_by_item.get(id(item))
        res_path = mirror_res if mirror_res is not None else glb_paths[model_id]
        ext_id = unique_glbs[res_path]

        if model_id < len(ocg_entries):
            name = ocg_entries[model_id].model_name
        else:
            name = f"model{model_id}"
        node_name = f"{prefix}_{name}_{item.unique_id}"

        transform_str = (
            format_transform_mirror_x(item.transform)
            if mirror_res is not None
            else format_transform(item.transform)
        )

        lines.append(f'[node name="{node_name}" parent="Props" instance=ExtResource("{ext_id}")]')
        lines.append(f'transform = {transform_str}')
        # Emit billboard metadata if this model has m_bBillboard set
        if model_id < len(ocg_entries) and ocg_entries[model_id].billboard:
            lines.append('metadata/billboard = true')
        lines.append('')
        placed += 1

        node_matrices[node_name] = list(item.transform)
        if mirror_res is not None:
            mirrored_nodes.add(node_name)

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    return {
        "placed": placed,
        "skipped": skipped,
        "unique_models": len(unique_glbs),
        "node_matrices": node_matrices,
        "mirrored_nodes": mirrored_nodes,
    }


def load_overrides(map_code: str) -> dict:
    """Load overrides.yaml for a map. Returns dict of prop_name -> adjustments."""
    import yaml

    overrides_path = CLIENT_DIR / "assets" / "maps" / map_code / "overrides.yaml"
    if not overrides_path.exists():
        print(f"  No overrides file found: {overrides_path}")
        return {}

    with open(overrides_path) as f:
        data = yaml.safe_load(f)

    if not data or "props" not in data:
        print(f"  Overrides file has no props entries")
        return {}

    props = data["props"]
    print(f"  Loaded {len(props)} prop overrides from {overrides_path.name}")
    return props


def apply_overrides_to_tscn(
    output_path: Path,
    overrides: dict,
    node_matrices: dict[str, list[float]],
    mirrored_nodes: set[str] | None = None,
) -> int:
    """Post-process .tscn to replace transforms for overridden props.

    Composes each override onto the node's TRUE original .qqq transform
    (`node_matrices`, from write_tscn's stats) via apply_override_to_matrix,
    instead of rebuilding a pure Y-rotation matrix from scratch — that old
    path silently discarded any non-unit scale/shear baked into the
    placement (e.g. track segments).

    Returns the number of props modified.
    """
    mirrored_nodes = mirrored_nodes or set()
    lines = output_path.read_text().splitlines()
    modified = 0

    # Pattern to match node lines like:
    # [node name="obj_a_SEtrack02_4" parent="Props" instance=ExtResource("ext_35")]
    node_pattern = re.compile(r'^\[node name="([^"]+)" parent="Props"')

    i = 0
    while i < len(lines):
        m = node_pattern.match(lines[i])
        if m:
            prop_name = m.group(1)
            if prop_name in overrides:
                if prop_name in mirrored_nodes:
                    print(f"  WARNING: override for '{prop_name}' skipped — node uses the "
                          f"mirror_x variant, and apply_override_to_matrix doesn't replicate "
                          f"that column-negation; compose manually or re-export without mirror_x")
                    i += 1
                    continue

                qqq_mat = node_matrices.get(prop_name)
                if qqq_mat is None:
                    print(f"  WARNING: no original transform found for '{prop_name}', skipping override")
                    i += 1
                    continue

                new_transform = f"transform = {apply_override_to_matrix(qqq_mat, overrides[prop_name])}"

                # Replace the transform line that follows the node line
                if i + 1 < len(lines) and lines[i + 1].startswith("transform = "):
                    lines[i + 1] = new_transform
                    modified += 1

        i += 1

    output_path.write_text("\n".join(lines))
    return modified


def main():
    parser = argparse.ArgumentParser(description="Assemble map .tscn from binary data")
    parser.add_argument("map_code", help="Map code, e.g., SF001001")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing .tscn")
    parser.add_argument("--apply-overrides", action="store_true", help="Apply prop transform overrides from overrides.yaml")
    args = parser.parse_args()

    map_code = args.map_code
    map_dir = MAP_IRD / map_code

    if not map_dir.exists():
        print(f"ERROR: Map directory not found: {map_dir}")
        sys.exit(1)

    qqq_path = map_dir / f"{map_code}.qqq"
    ocg_path = map_dir / f"{map_code}.ocg"
    hwt_path = map_dir / f"{map_code}_h.bmp"

    # Parse QQQ
    print(f"Parsing {qqq_path.name}...")
    map_data = QQQParser().parse(qqq_path)
    print(f"  Objects: {len(map_data.objects)}")
    print(f"  Portals: {len(map_data.portals)}")
    print(f"  Triggers: {len(map_data.triggers)}")
    if map_data.tree_info:
        ti = map_data.tree_info
        print(f"  Map center: ({ti.center[0]:.1f}, {ti.center[1]:.1f}), extents: ({ti.extents[0]:.1f}, {ti.extents[1]:.1f})")

    # Parse OCG
    print(f"Parsing {ocg_path.name}...")
    ocg_entries = OCGParser().parse(ocg_path)
    print(f"  Model entries: {len(ocg_entries)}")

    # Parse PLT (per-map fixed-function sun; optional — older/partial map
    # dumps may lack it, in which case the terrain shader defaults apply)
    plt_path = map_dir / f"{map_code}.plt"
    light_settings = None
    if plt_path.exists():
        print(f"Parsing {plt_path.name}...")
        light_settings = PLTParser().parse(plt_path)
        sun = light_settings.sun
        print(f"  Sun dir: ({sun.direction[0]:.3f}, {sun.direction[1]:.3f}, {sun.direction[2]:.3f}), "
              f"diffuse: ({sun.diffuse[0]:.3f}, {sun.diffuse[1]:.3f}, {sun.diffuse[2]:.3f}), "
              f"ambient: ({sun.ambient[0]:.3f}, {sun.ambient[1]:.3f}, {sun.ambient[2]:.3f})")
    else:
        print(f"  WARNING: no {plt_path.name} — terrain shader will use default sun")

    # Resolve GLB paths
    glb_paths = {}
    missing = []
    skipped = []
    for entry in ocg_entries:
        if entry.model_name in SKIP_MODELS:
            skipped.append(f"  [{entry.index}] {entry.category}/{entry.model_name}")
            continue
        res_path = resolve_glb_path(entry, PROPS_DIR)
        if res_path:
            glb_paths[entry.index] = res_path
        else:
            missing.append(f"  [{entry.index}] {entry.category}/{entry.model_name}")

    print(f"  Resolved: {len(glb_paths)}/{len(ocg_entries)} models")
    if skipped:
        print(f"  Skipped: {len(skipped)} (excluded)")
    if missing:
        print(f"  Missing GLBs ({len(missing)}):")
        for m in missing[:10]:
            print(m)
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")

    # Census: negative-determinant placements (basis_det(transform) < 0)
    # that need a mesh mirrored across X to display correctly. Reported
    # here (before the dry-run early-return) so `--dry-run` also surfaces
    # this without writing anything.
    all_placement_items = (
        [(obj, "obj") for obj in map_data.objects]
        + [(p, "portal") for p in map_data.portals]
        + [(t, "trigger") for t in map_data.triggers]
    )
    neg_det = negative_det_items(all_placement_items, glb_paths, ocg_entries)
    print(f"  Negative-determinant placements: {len(neg_det)}")
    if neg_det:
        for item, prefix in neg_det[:20]:
            name = ocg_entries[item.model_id].model_name
            print(f"    {prefix} {name} (unique_id={item.unique_id})")
        if len(neg_det) > 20:
            print(f"    ... and {len(neg_det) - 20} more")

    if args.dry_run:
        print("\nDry run — no .tscn written.")
        return

    # Copy heightmap as PNG to client assets for runtime loading
    hwt_dest_dir = CLIENT_DIR / "assets" / "maps" / map_code
    hwt_dest_dir.mkdir(parents=True, exist_ok=True)
    if hwt_path.exists():
        # RG16 encoding (R=high byte, G=low byte): 22 maps ship 16bpp height
        # BMPs whose values exceed a byte — a plain PIL convert scrambles them.
        from src.parsers.heightmap_bmp import decode_height_bmp, write_height_png
        hwt_png = hwt_dest_dir / f"{map_code}.png"
        write_height_png(decode_height_bmp(hwt_path), hwt_png)
        print(f"  Converted heightmap to {hwt_png}")

    # Water (.wtr -> water.json; 98 maps ship one)
    import importlib
    export_water_mod = importlib.import_module("scripts.32_export_water")
    export_water_mod.ensure_water_textures()
    water_json = export_water_mod.export_water(map_code)
    if water_json is not None:
        print(f"  Water: {water_json}")

    # Write .tscn
    output_path = OUTPUT_DIR / f"{map_code}.tscn"
    print(f"\nWriting {output_path}...")
    stats = write_tscn(
        output_path, map_code,
        map_data.objects, map_data.portals, map_data.triggers,
        ocg_entries, glb_paths, hwt_path,
        light_settings=light_settings,
        has_water=water_json is not None,
    )
    print(f"  Placed: {stats['placed']} props")
    print(f"  Skipped: {stats['skipped']} (missing GLBs)")
    print(f"  Unique models: {stats['unique_models']}")

    if args.apply_overrides:
        print(f"\nApplying overrides...")
        overrides = load_overrides(map_code)
        if overrides:
            count = apply_overrides_to_tscn(
                output_path, overrides, stats["node_matrices"], stats["mirrored_nodes"],
            )
            print(f"  Modified {count} prop transforms")

    print(f"\nDone! Open {output_path} in Godot.")


if __name__ == "__main__":
    main()
