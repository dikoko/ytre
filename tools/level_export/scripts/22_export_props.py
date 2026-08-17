#!/usr/bin/env python3
"""
Prop Export Script

Exports terrain prop TMD models to GLB with embedded textures. Most props
are static meshes; 187 carry per-object keyframe animation, exported as
glTF node animation plus a {prop}.anim.json sidecar. No skeletons — prop
animation is rigid per object.

Usage:
    python scripts/22_export_props.py --all                     # Export all props
    python scripts/22_export_props.py --ids a_bookcase01        # Export specific props
    python scripts/22_export_props.py --category artificial     # Export by category
    python scripts/22_export_props.py --animated                # Only animated props
    python scripts/22_export_props.py --all --dry-run           # List without exporting
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.tmd_parser import TMDParser
from src.exporters.prop_exporter import export_prop
from src.exporters.prop_anim_sidecar import write_sidecar
from src.exporters.prop_animation import build_animation_plan, has_visible_animation
from scripts._export_common import embed_textures
from scripts._prop_config import (
    TEXTURE_SEARCH_DIRS, OUTPUT_BASE, OUTPUT_MODELS, CATEGORIES,
    discover_props, discover_skill_effects,
)


def _is_animated(tmd_path: Path, prop_id: str) -> bool:
    model = TMDParser().parse(tmd_path)
    plan = build_animation_plan(model, prop_id)
    return bool(plan.animated) and has_visible_animation(model, plan)


def export_single_prop(
    category: str, prop_id: str, tmd_path: Path,
) -> tuple[bool, str, dict | None]:
    """Export a single prop to GLB. Returns (success, message, catalog_entry)."""
    try:
        model = TMDParser().parse(tmd_path)

        out_dir = OUTPUT_MODELS / category
        out_dir.mkdir(parents=True, exist_ok=True)
        glb_path = out_dir / f"{prop_id}.glb"

        # Embed textures from model directory + central Texture.IRD + siblings
        model_dir = tmd_path.parent

        export_prop(model, glb_path, prop_id=prop_id)

        embed_textures(glb_path, model_dir, model, texture_dirs=TEXTURE_SEARCH_DIRS)

        # Clip table + alpha fade curves, which glTF cannot carry. Skipped
        # when the only animated objects are mesh-free helpers: nothing is
        # emitted for them, so the sidecar would promise motion the scene
        # cannot show.
        plan = build_animation_plan(model, prop_id)
        animated = bool(plan.animated) and has_visible_animation(model, plan)
        if animated:
            write_sidecar(plan, glb_path)

        glb_size = glb_path.stat().st_size / 1024

        # Build catalog entry
        textures = []
        for mat in model.materials:
            if mat.texture_filename:
                basename = mat.texture_filename.replace("\\", "/").split("/")[-1]
                tex_stem = Path(basename).stem
                if tex_stem not in textures:
                    textures.append(tex_stem)

        entry = {"id": prop_id, "category": category}
        if textures:
            entry["textures"] = textures
        if animated:
            entry["animated"] = True

        tag = " [anim]" if animated else ""
        return True, f"{prop_id}: {glb_size:.0f}KB{tag}", entry

    except Exception as e:
        return False, f"{prop_id}: ERROR - {e}", None


def write_catalog(entries: list[dict], output_path: Path, merge: bool = False) -> None:
    """Write props.yaml catalog.

    With merge=True (partial exports), entries replace same-id rows in the
    existing catalog in place and unseen ids are appended — never clobbering
    the full catalog with a partial one. merge=False rewrites from scratch
    (--all, the authoritative full export).
    """
    if merge and output_path.exists():
        with open(output_path) as f:
            existing = (yaml.safe_load(f) or {}).get("props") or []
        by_id = {e["id"]: e for e in entries}
        merged = [by_id.pop(e["id"], e) for e in existing]
        merged.extend(by_id.values())
        entries = merged

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"props": entries}
    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main():
    parser = argparse.ArgumentParser(description="Export terrain props to GLB")
    parser.add_argument("--all", action="store_true", help="Export all props")
    parser.add_argument("--ids", nargs="+", help="Export specific prop IDs")
    parser.add_argument("--category", nargs="+", help="Export props from specific categories")
    parser.add_argument("--dry-run", action="store_true", help="List props without exporting")
    parser.add_argument("--animated", action="store_true",
                        help="Export only props that carry keyframe animation")
    parser.add_argument("--skillfx", action="store_true",
                        help="Export the opt-in skill-effect props (warp puffs)")
    args = parser.parse_args()

    if not (args.all or args.ids or args.category or args.animated or args.skillfx):
        parser.print_help()
        sys.exit(1)

    # Discover props. Skill effects are opt-in only: never part of --all /
    # --animated sweeps, so the terrain censuses stay untouched.
    cat_filter = args.category if args.category else None
    all_props = discover_skill_effects() if args.skillfx else discover_props(cat_filter)

    # Filter by IDs if specified
    if args.ids:
        id_set = set(args.ids)
        all_props = [(c, p, t) for c, p, t in all_props if p in id_set]

    if args.animated:
        all_props = [
            (cat, prop_id, tmd_path)
            for cat, prop_id, tmd_path in all_props
            if _is_animated(tmd_path, prop_id)
        ]

    if args.dry_run:
        print(f"Would export {len(all_props)} props:")
        for cat, prop_id, tmd_path in all_props:
            print(f"  [{cat}] {prop_id}")
        return

    OUTPUT_MODELS.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(all_props)} props...")
    start = time.time()
    success_count = 0
    catalog_entries = []

    for cat, prop_id, tmd_path in all_props:
        ok, msg, entry = export_single_prop(cat, prop_id, tmd_path)
        print(f"  {'OK' if ok else 'FAIL'} [{cat}] {msg}")
        if ok:
            success_count += 1
            if entry:
                catalog_entries.append(entry)

    # Write catalog — partial exports merge into the existing catalog
    catalog_path = OUTPUT_BASE / "props.yaml"
    write_catalog(catalog_entries, catalog_path, merge=not args.all)
    print(f"\nCatalog {'merged' if not args.all else 'written'}: "
          f"{catalog_path} ({len(catalog_entries)} entries this run)")

    animated_count = sum(1 for e in catalog_entries if e.get("animated"))
    elapsed = time.time() - start
    print(f"Done: {success_count}/{len(all_props)} exported in {elapsed:.1f}s "
          f"({animated_count} animated, {success_count - animated_count} static)")


if __name__ == "__main__":
    main()
