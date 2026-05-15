#!/usr/bin/env python3
"""
Debug Axis Rotation Visualizer Script

Creates a GLB file with procedural animations that rotate Spine1 and Spine2
around X, Y, Z axes by 45 degrees. Used to verify bone coordinate systems.

Output: output/debug_axes.glb

Godot checkpoint: Play each animation and verify bones rotate in expected direction.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.debug.axis_viz import create_axis_viz
from src.parsers.tmd_parser import TMDParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "debug_axes.glb"


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    parser = TMDParser()
    model = parser.parse(TMD_PATH)
    print(f"  Bones: {len(model.bones)}")

    print(f"Creating axis visualization: {OUTPUT_PATH}")
    create_axis_viz(model, OUTPUT_PATH)
    print(f"  Created: {OUTPUT_PATH}")

    print("\nGodot checkpoint:")
    print("  - Open debug_axes.glb in Godot")
    print("  - Play debug_rot_X, debug_rot_Y, debug_rot_Z animations")
    print("  - Verify Spine1 and Spine2 rotate 45° around each axis")


if __name__ == "__main__":
    main()
