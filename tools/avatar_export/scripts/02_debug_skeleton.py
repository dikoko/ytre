#!/usr/bin/env python3
"""
Debug Skeleton Cube Visualizer Script

Creates a GLB file with 3cm cubes at each bone's world position.
Used to verify skeleton structure and bone positions.

Output: output/debug_skeleton.glb

Godot checkpoint: Cubes should form a human T-pose shape.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.debug.skeleton_viz import create_skeleton_viz
from src.parsers.tmd_parser import TMDParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "debug_skeleton.glb"


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    parser = TMDParser()
    model = parser.parse(TMD_PATH)
    print(f"  Bones: {len(model.bones)}")

    print(f"Creating skeleton visualization: {OUTPUT_PATH}")
    create_skeleton_viz(model, OUTPUT_PATH)
    print(f"  Created: {OUTPUT_PATH}")

    print("\nBone list:")
    for i, bone in enumerate(model.bones):
        parent = model.bones[bone.parent_id].name.strip() if bone.parent_id >= 0 else "ROOT"
        print(f"  {i:2d}: {bone.name.strip():20s} (parent: {parent})")

    print("\nGodot checkpoint:")
    print("  - Open debug_skeleton.glb in Godot")
    print("  - Verify cubes form a human T-pose shape")
    print("  - Check bone positions are reasonable (not at origin)")


if __name__ == "__main__":
    main()
