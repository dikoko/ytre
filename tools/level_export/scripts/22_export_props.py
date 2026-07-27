#!/usr/bin/env python3
"""
Prop Export Script

Exports terrain prop TMD models to GLB with embedded textures.
Props are static meshes — no skeleton or animation.

Usage:
    python scripts/22_export_props.py --all                     # Export all props
    python scripts/22_export_props.py --ids a_bookcase01        # Export specific props
    python scripts/22_export_props.py --category artificial     # Export by category
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
from scripts._export_common import embed_textures
from scripts._prop_config import (
    TEXTURE_SEARCH_DIRS, OUTPUT_BASE, OUTPUT_MODELS, CATEGORIES,
    discover_props,
)


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

        return True, f"{prop_id}: {glb_size:.0f}KB", entry

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
    args = parser.parse_args()

    if not args.all and not args.ids and not args.category:
        parser.print_help()
        sys.exit(1)

    # Discover props
    cat_filter = args.category if args.category else None
    all_props = discover_props(cat_filter)

    # Filter by IDs if specified
    if args.ids:
        id_set = set(args.ids)
        all_props = [(c, p, t) for c, p, t in all_props if p in id_set]

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

    elapsed = time.time() - start
    print(f"Done: {success_count}/{len(all_props)} exported in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
