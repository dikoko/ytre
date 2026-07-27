#!/usr/bin/env python3
"""
Terrain Tile Export Script

Parses binary .cvs canvas and tileregistry.tcg, generates per-map YAML,
composites tile textures, and writes an index map image.

Usage:
    python scripts/31_export_terrain.py SF001001
    python scripts/31_export_terrain.py SF001001 --dry-run
"""

import argparse
import sys
import time
from pathlib import Path

import yaml
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.cvs_parser import CVSParser
from src.parsers.tcg_parser import TCGParser
from scripts._tile_compositor import composite_layers, COMPOSITE_SIZE, TileResolutionError

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
TILE_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Tile.IRD"
TCG_PATH = TILE_IRD / "tileregistry.tcg"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client"
OUTPUT_DIR = CLIENT_DIR / "assets" / "maps"


def export_terrain(map_code: str, dry_run: bool = False, lenient: bool = False) -> dict:
    """Export terrain tile data for a single map. Returns stats dict."""
    t0 = time.time()

    cvs_path = MAP_IRD / map_code / f"{map_code}.cvs"
    if not cvs_path.exists():
        print(f"ERROR: CVS file not found: {cvs_path}")
        return {"error": "cvs_not_found"}

    # Parse binary data
    print(f"Parsing {map_code}.cvs ...")
    canvas = CVSParser().parse(cvs_path)
    print(f"  Grid: {canvas.grid_rows}x{canvas.grid_cols}, palette: {len(canvas.palette)} combos")

    print(f"Parsing tileregistry.tcg ...")
    registry = TCGParser().parse(TCG_PATH)
    print(f"  {len(registry.tile_sets)} tile sets")

    # Identify tile sets used by this map
    used_kinds: dict[int, str] = {}
    for entry in canvas.palette:
        for tile_id in entry:
            if tile_id != 0:
                kind = (tile_id >> 8) & 0xFF
                if kind not in used_kinds and kind in registry.tile_sets:
                    used_kinds[kind] = registry.tile_sets[kind].name
    print(f"  Tile types used: {len(used_kinds)} — {list(used_kinds.values())}")

    if dry_run:
        print("Dry run — skipping output generation")
        return {
            "grid": (canvas.grid_rows, canvas.grid_cols),
            "palette_count": len(canvas.palette),
            "tile_types": len(used_kinds),
        }

    # Output directories
    map_dir = OUTPUT_DIR / map_code
    tiles_dir = map_dir / f"{map_code}_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    # Keep the Godot editor out of the tiles dirs: the viewer loads combos as
    # raw Images (terrain_loader.gd), and letting the editor scan/import/
    # thumbnail ~77k combo PNGs exhausts its texture RID pool and crashes it
    # (Godot 4.7 FileSystemDock tree mode queues previews for every file).
    (tiles_dir / ".gdignore").write_text("")

    # Composite tile textures
    print(f"Compositing {len(canvas.palette)} tile combos ...")
    composited = 0
    failed = 0
    for i, entry in enumerate(canvas.palette):
        try:
            img = composite_layers(list(entry), registry, TILE_IRD, lenient=lenient)
        except TileResolutionError as e:
            print(f"ERROR: Combo index {i}: {e}")
            return {"error": "tile_resolution", "detail": str(e)}
        if img is not None:
            img.save(tiles_dir / f"combo_{i:03d}.png")
            composited += 1
        else:
            # Create a magenta fallback for missing textures
            fallback = Image.new("RGB", (COMPOSITE_SIZE, COMPOSITE_SIZE), (255, 0, 255))
            fallback.save(tiles_dir / f"combo_{i:03d}.png")
            failed += 1
    print(f"  Composited: {composited}, fallback: {failed}")

    # Generate index map (RG-encoded PNG for 16-bit index range)
    print("Generating index map ...")
    idx_img = Image.new("RGB", (canvas.grid_cols, canvas.grid_rows))
    for r, row in enumerate(canvas.cells):
        for c, pal_id in enumerate(row):
            lo = pal_id & 0xFF
            hi = (pal_id >> 8) & 0xFF
            idx_img.putpixel((c, r), (lo, hi, 0))
    tilemap_path = map_dir / f"{map_code}_tilemap.png"
    idx_img.save(tilemap_path)
    print(f"  Saved: {tilemap_path}")

    # Generate visibility map (white=visible, black=invisible for prop cutouts)
    print("Generating visibility map ...")
    vis_img = Image.new("L", (canvas.grid_cols, canvas.grid_rows))
    for r in range(canvas.grid_rows):
        for c in range(canvas.grid_cols):
            vis_img.putpixel((c, r), 255 if canvas.visibility[r][c] else 0)
    vis_path = map_dir / f"{map_code}_visibility.png"
    vis_img.save(vis_path)
    print(f"  Saved: {vis_path}")

    # Build YAML
    print("Writing terrain YAML ...")
    tile_sets_yaml = []
    for local_id, (kind, name) in enumerate(sorted(used_kinds.items())):
        ts = registry.tile_sets[kind]
        textures = {}
        for (idx, opt), tex_name in sorted(ts.tiles.items()):
            textures[f"{idx}_{opt}"] = tex_name
        tile_sets_yaml.append({
            "id": local_id,
            "kind": kind,
            "name": name,
            "textures": textures,
        })

    palette_yaml = []
    for i, entry in enumerate(canvas.palette):
        layers = []
        for tile_id in entry:
            if tile_id != 0:
                kind = (tile_id >> 8) & 0xFF
                layers.append(used_kinds.get(kind, f"UNKNOWN_{kind}"))
        palette_yaml.append({
            "index": i,
            "layers": layers,
            "tile_ids": [f"0x{t:04X}" for t in entry],
        })

    yaml_data = {
        "grid": {"rows": canvas.grid_rows, "cols": canvas.grid_cols},
        "tile_sets": tile_sets_yaml,
        "palette": palette_yaml,
        "cells": [row for row in canvas.cells],
    }

    yaml_path = map_dir / f"{map_code}_terrain.yaml"
    with open(yaml_path, "w") as f:
        f.write(f"# {map_code}_terrain.yaml\n")
        f.write(f"# Terrain tile data — parsed from {map_code}.cvs + tileregistry.tcg\n\n")
        yaml.dump(yaml_data, f, default_flow_style=None, sort_keys=False, width=200)
    print(f"  Saved: {yaml_path}")

    elapsed = time.time() - t0
    stats = {
        "grid": (canvas.grid_rows, canvas.grid_cols),
        "palette_count": len(canvas.palette),
        "tile_types": len(used_kinds),
        "composited": composited,
        "failed": failed,
        "elapsed": f"{elapsed:.1f}s",
    }
    print(f"Done in {elapsed:.1f}s")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Export terrain tile data for a map")
    parser.add_argument("map_code", help="Map code (e.g., SF001001)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no output")
    parser.add_argument("--lenient", action="store_true", help="Skip unresolvable tiles (fallback to magenta)")
    args = parser.parse_args()

    stats = export_terrain(args.map_code, dry_run=args.dry_run, lenient=args.lenient)
    if "error" in stats:
        sys.exit(1)


if __name__ == "__main__":
    main()
