#!/usr/bin/env python3
"""
Skeleton Export Script

Exports TMD mesh with skeleton binding (no animations).
Used to verify skeleton structure before adding animations.

Output: output/02_with_skeleton.glb

Godot checkpoint: Skeleton visible, mesh in T-pose, no deformation.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.exporters.skeleton_exporter import export_with_skeleton
from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "02_with_skeleton.glb"


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)
    print(f"  Bones: {len(model.bones)}")

    print(f"Parsing MLIB: {MLIB_PATH}")
    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)
    print(f"  MLIB Bones: {len(mlib.bones)}")
    print(f"  Motions: {len(mlib.motions)}")

    print(f"\nExporting with skeleton: {OUTPUT_PATH}")
    export_with_skeleton(model, mlib, OUTPUT_PATH, validate=True)
    print(f"  Created: {OUTPUT_PATH}")

    print("\nGodot checkpoint:")
    print("  - Open 02_with_skeleton.glb in Godot")
    print("  - Verify mesh is in T-pose")
    print("  - Select skeleton and verify 54 bones visible")
    print("  - No animations should be present")
    print("  - Mesh should not be deformed (no broken/stretched parts)")


if __name__ == "__main__":
    main()
