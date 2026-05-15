#!/usr/bin/env python3
"""
Export Base Mesh with Body Regions

Exports the male base avatar as separate mesh nodes per body region.
Each region can be independently hidden when a corresponding part is equipped.

Output: client/assets/avatars/base/male_base_regions.glb

Usage:
    cd tools/avatar_export
    python scripts/11_export_regions.py
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.exporters.region_exporter import export_with_regions

# Paths
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"
OUTPUT_PATH = CLIENT_DIR / "assets" / "avatars" / "base" / "male_base_regions.glb"


def main():
    print("=" * 60)
    print("Export Base Mesh with Body Regions")
    print("=" * 60)

    # Parse TMD
    print(f"\nParsing TMD: {TMD_PATH.name}")
    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)
    print(f"  Meshes: {len(model.meshes)}")
    print(f"  Vertices: {len(model.meshes[0].vertices)}")
    print(f"  Bones: {len(model.bones)}")

    # Parse MLIB
    print(f"\nParsing MLIB: {MLIB_PATH.name}")
    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)
    print(f"  Bones: {len(mlib.bones)}")

    # Export with regions
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nExporting to: {OUTPUT_PATH}")
    region_stats = export_with_regions(model, mlib, OUTPUT_PATH)

    print(f"\nRegion statistics:")
    total_verts = 0
    for region, count in sorted(region_stats.items(), key=lambda x: x[0].value):
        print(f"  {region.value:12}: {count:4} vertices")
        total_verts += count
    print(f"  {'TOTAL':12}: {total_verts:4} vertices")

    print("\nDone!")
    print("\nNext steps:")
    print("  1. Open Godot and reimport assets")
    print("  2. Update test_avatar_parts.tscn to use male_base_regions.glb")
    print("  3. Test region visibility with part swapping")


if __name__ == "__main__":
    main()
