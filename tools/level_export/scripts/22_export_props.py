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
    python scripts/22_export_props.py --effects --out-dir PATH  # Full battle-effects set, elsewhere
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
    discover_props, discover_skill_effects, discover_effects,
)


def _is_animated(tmd_path: Path, prop_id: str) -> bool:
    model = TMDParser().parse(tmd_path)
    plan = build_animation_plan(model, prop_id)
    return bool(plan.animated) and has_visible_animation(model, plan)


def export_single_prop(
    category: str, prop_id: str, tmd_path: Path, models_dir: Path = OUTPUT_MODELS,
) -> tuple[bool, str, dict | None]:
    """Export a single prop to GLB. Returns (success, message, catalog_entry)."""
    try:
        model = TMDParser().parse(tmd_path)

        out_dir = models_dir / category
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


def catalog_skip_reason(effects: bool, out_dir: Path | None) -> str | None:
    """Why (if at all) this run should skip the props.yaml catalog write.

    Returns None when the catalog should be written normally. Any run using
    --out-dir (not just --effects) redirects the GLBs away from this repo's
    shipped client/assets/props/models/ tree, so a props.yaml entry pointing
    at OUTPUT_MODELS would claim models exist there that don't.
    """
    if effects:
        return "--effects exports out-of-repo"
    if out_dir is not None:
        return "--out-dir redirects output away from the shipped tree"
    return None


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
    parser.add_argument("--effects", action="store_true",
                        help="Export the opt-in full battle-effects set "
                             "(352 Skill.IRD/TMD models, sub-project C)")
    parser.add_argument("--out-dir", type=Path,
                        help="Override the models output directory for this "
                             "run (e.g. to export --effects straight into "
                             "another repo's asset tree)")
    args = parser.parse_args()

    if not (args.all or args.ids or args.category or args.animated
            or args.skillfx or args.effects):
        parser.print_help()
        sys.exit(1)

    if args.effects and (args.all or args.ids or args.skillfx):
        parser.error("--effects is mutually exclusive with --all/--ids/--skillfx")

    # Discover props. Skill effects and battle effects are opt-in only:
    # never part of --all / --animated sweeps, so the terrain censuses stay
    # untouched.
    cat_filter = args.category if args.category else None
    if args.effects:
        all_props = discover_effects()
    elif args.skillfx:
        all_props = discover_skill_effects()
    else:
        all_props = discover_props(cat_filter)

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

    models_dir = args.out_dir if args.out_dir else OUTPUT_MODELS
    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(all_props)} props...")
    start = time.time()
    success_count = 0
    catalog_entries = []

    for cat, prop_id, tmd_path in all_props:
        ok, msg, entry = export_single_prop(cat, prop_id, tmd_path, models_dir)
        print(f"  {'OK' if ok else 'FAIL'} [{cat}] {msg}")
        if ok:
            success_count += 1
            if entry:
                catalog_entries.append(entry)

    # Write catalog — partial exports merge into the existing catalog.
    skip_reason = catalog_skip_reason(args.effects, args.out_dir)
    if skip_reason:
        print(f"\nCatalog write skipped ({skip_reason}, "
              f"{len(catalog_entries)} models this run)")
    else:
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
