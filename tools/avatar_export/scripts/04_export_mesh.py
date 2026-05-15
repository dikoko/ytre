#!/usr/bin/env python3
"""
Mesh-Only Export Script

Exports TMD mesh data without skeleton or animations.
Used to verify mesh geometry before adding skeletal binding.

Output: output/01_mesh_only.glb

Godot checkpoint: Open GLB, verify mesh shape looks human.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.exporters.mesh_exporter import export_mesh_only
from src.parsers.tmd_parser import TMDParser

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "01_mesh_only.glb"


def main():
    print(f"Parsing TMD: {TMD_PATH}")
    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    total_vertices = sum(len(m.vertices) for m in model.meshes)
    total_faces = sum(len(m.faces) for m in model.meshes)
    print(f"  Meshes: {len(model.meshes)}")
    print(f"  Vertices: {total_vertices}")
    print(f"  Faces: {total_faces}")

    print(f"\nExporting mesh-only GLB: {OUTPUT_PATH}")
    export_mesh_only(model, OUTPUT_PATH, validate=True)
    print(f"  Created: {OUTPUT_PATH}")

    print("\nGodot checkpoint:")
    print("  - Open 01_mesh_only.glb in Godot")
    print("  - Verify mesh shape looks like a human")
    print("  - Check normals are facing outward (not inside-out)")
    print("  - No skeleton or animations should be present")


if __name__ == "__main__":
    main()
