#!/usr/bin/env python3
"""
Export Base Mesh by Material

Exports the base avatar split by material index for correct UV mapping.
Each material becomes a separate mesh node sharing the same skeleton.

Output: client/assets/avatars/base/{gender}_base_materials.glb

Usage:
    cd tools/avatar_export
    python scripts/13_export_materials.py
    python scripts/13_export_materials.py --gender female
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.exporters.material_exporter import export_with_materials, MaterialSlot

# Paths
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"


def get_paths(gender: str):
    """Get source and output paths for the given gender."""
    if gender == "male":
        return {
            "tmd": AVATAR_IRD / "male.TMD",
            "mlib": AVATAR_IRD / "motion" / "male" / "male.mlib",
            "output": CLIENT_DIR / "assets" / "avatars" / "base" / "male_base_materials.glb",
        }
    else:
        return {
            "tmd": AVATAR_IRD / "female.TMD",
            "mlib": AVATAR_IRD / "motion" / "female" / "female.mlib",
            "output": CLIENT_DIR / "assets" / "avatars" / "base" / "female_base_materials.glb",
        }


def main():
    parser = argparse.ArgumentParser(description="Export base mesh by material")
    parser.add_argument("--gender", choices=["male", "female"], default="male")
    args = parser.parse_args()

    paths = get_paths(args.gender)

    print("=" * 60)
    print(f"Export Base Mesh by Material ({args.gender})")
    print("=" * 60)

    # Parse TMD
    print(f"\nParsing TMD: {paths['tmd'].name}")
    tmd_parser = TMDParser()
    model = tmd_parser.parse(paths["tmd"])
    print(f"  Meshes: {len(model.meshes)}")
    print(f"  Vertices: {len(model.meshes[0].vertices)}")
    print(f"  Bones: {len(model.bones)}")

    # Parse MLIB
    print(f"\nParsing MLIB: {paths['mlib'].name}")
    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(paths["mlib"])
    print(f"  Bones: {len(mlib.bones)}")
    print(f"  Motions: {len(mlib.motions)}")

    # Export with materials
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    print(f"\nExporting to: {paths['output']}")
    material_stats = export_with_materials(model, mlib, paths["output"], gender=args.gender)

    print(f"\nMaterial statistics:")
    total_verts = 0
    for slot, count in sorted(material_stats.items(), key=lambda x: x[0].value):
        print(f"  {slot.name:8}: {count:4} vertices")
        total_verts += count
    print(f"  {'TOTAL':8}: {total_verts:4} vertices")

    print("\nDone!")


if __name__ == "__main__":
    main()
