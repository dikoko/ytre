#!/usr/bin/env python3
"""
Full Avatar Export Script

Exports TMD mesh with skeleton and ALL animations from MLIB.

Output: output/04_full.glb (and copy to Godot assets)
"""

import sys
import time
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
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "04_full.glb"


def main():
    start_time = time.time()

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

    # List some animation names
    print("\n  Sample animations:")
    for motion in mlib.motions[:10]:
        print(f"    - {motion.name} ({motion.frame_count} frames)")
    print(f"    ... and {len(mlib.motions) - 10} more")

    print(f"\nExporting with ALL {len(mlib.motions)} animations...")
    print(f"  Output: {OUTPUT_PATH}")

    # Export with all animations (animation_names=None means all)
    export_with_animations(model, mlib, OUTPUT_PATH, animation_names=None, validate=True)

    elapsed = time.time() - start_time
    file_size = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"  Created: {OUTPUT_PATH}")
    print(f"  Size: {file_size:.2f} MB")
    print(f"  Time: {elapsed:.1f}s")

    print("\n" + "="*60)
    print("FULL EXPORT COMPLETE")
    print("="*60)
    print(f"  Mesh: {len(model.meshes[0].vertices)} vertices")
    print(f"  Skeleton: {len(model.bones)} bones")
    print(f"  Animations: {len(mlib.motions)}")
    print(f"  File size: {file_size:.2f} MB")
    print("\nGodot verification:")
    print("  - Open male_base.glb in Godot")
    print("  - Check AnimationPlayer has 223 animations")
    print("  - Spot-check: basic_pick, basic_run, basic_stand")
    print("  - Spot-check: attack animations, skill animations")


if __name__ == "__main__":
    main()
