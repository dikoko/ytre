#!/usr/bin/env python3
"""
Debug Bone Names Visualizer Script

Creates a JSON file with bone names and positions.
Use alongside debug_skeleton.glb to identify bones.

Output: output/bone_names.json

Usage in Godot: Load JSON to display floating labels above each bone cube.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.debug.bone_names_viz import create_bone_names_json
from src.parsers.tmd_parser import TMDParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "bone_names.json"


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    parser = TMDParser()
    model = parser.parse(TMD_PATH)
    print(f"  Bones: {len(model.bones)}")

    print(f"Creating bone names JSON: {OUTPUT_PATH}")
    create_bone_names_json(model, OUTPUT_PATH)
    print(f"  Created: {OUTPUT_PATH}")

    # Print bone hierarchy
    print("\nBone hierarchy summary:")
    print("  Key bones:")
    key_bones = ["@Root", "@Pelvis", "@Spine1", "@Head", "@HandL", "@HandR"]
    for bone in model.bones:
        name = bone.name.strip()
        if name in key_bones:
            pos = bone.world_transform.translation
            print(f"    {name}: pos=({pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f})")

    print("\nGodot usage:")
    print("  1. Load debug_skeleton.glb to see cube positions")
    print("  2. Load bone_names.json for label data")
    print("  3. Create Label3D nodes at each bone position")


if __name__ == "__main__":
    main()
