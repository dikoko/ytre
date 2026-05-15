#!/usr/bin/env python3
"""
Animation Export Script

Exports TMD mesh with skeleton and test animations.

Output: output/03_with_animation.glb
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.exporters.animation_exporter import export_with_animations
from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "03_with_animation.glb"

# Test animations
TEST_ANIMATIONS = [
    "male_basic_pick",
    "male_basic_run",
    "male_basic_stand",
]


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)
    print(f"  Bones: {len(model.bones)}")
    print(f"  Vertices: {len(model.meshes[0].vertices)}")

    print(f"Parsing MLIB: {MLIB_PATH}")
    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)
    print(f"  MLIB Bones: {len(mlib.bones)}")
    print(f"  Motions: {len(mlib.motions)}")

    print(f"\nExporting with animations: {OUTPUT_PATH}")
    print(f"  Animations: {TEST_ANIMATIONS}")
    export_with_animations(model, mlib, OUTPUT_PATH, animation_names=TEST_ANIMATIONS, validate=True)
    print(f"  Created: {OUTPUT_PATH}")

    print("\nGodot checkpoint:")
    print("  - Open 03_with_animation.glb in Godot")
    print("  - Verify mesh is in T-pose at rest")
    print("  - Play basic_pick animation - arm should reach down")
    print("  - Play basic_run animation - running motion")
    print("  - Play basic_stand animation - idle stance")
    print("  - Mesh should deform correctly with skeleton")


if __name__ == "__main__":
    main()
