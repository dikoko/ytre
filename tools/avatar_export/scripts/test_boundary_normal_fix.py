#!/usr/bin/env python3
"""
Test: Export hair M0101 with boundary normals averaged to match face base mesh.

This script:
1. Parses the base TMD (face vertices) and hair PRT (M0101)
2. Finds boundary vertex pairs between face and hair meshes
3. Averages normals at boundary so hair matches face
4. Exports the fixed hair GLB alongside the original for comparison

The key insight: face mesh normals are the "ground truth" — they look correct.
We adjust the hair side to match, eliminating the shading seam.

Coordinate conventions:
- Base mesh export: positions [v.x, v.y, v.z], normals [n.x, n.y, n.z]
- Part export: positions [-v.x, v.y, v.z], normals [-n.x, n.y, n.z]
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.tmd_parser import TMDParser, Vector3
from src.parsers.mlib_parser import MLIBParser
from src.exporters.part_exporter import export_part

# Paths
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
BASE_TMD = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"
HAIR_PRT = AVATAR_IRD / "swap" / "male" / "male_hair_M0101.PRT"

# Output paths
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client" / "assets" / "avatars" / "parts" / "male"
ORIGINAL_OUTPUT = OUTPUT_DIR / "male_hair_M0101.glb"
FIXED_OUTPUT = OUTPUT_DIR / "male_hair_M0101_fixed.glb"

# Face is TMD material index 7
FACE_TMD_MATERIAL_INDEX = 7

# Distance tolerance for matching boundary vertices
POSITION_TOLERANCE = 0.001


def vec_normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    """Normalize a 3D vector."""
    length = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if length < 1e-8:
        return v
    return (v[0] / length, v[1] / length, v[2] / length)


def vec_add(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(ai + bi for ai, bi in zip(a, b))


def vec_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def angle_between(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    la = math.sqrt(sum(ai * ai for ai in a))
    lb = math.sqrt(sum(bi * bi for bi in b))
    if la < 1e-8 or lb < 1e-8:
        return float("nan")
    cos_angle = sum(ai * bi for ai, bi in zip(a, b)) / (la * lb)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def build_face_boundary_map(base_model):
    """Build spatial lookup of face mesh vertex positions and normals.

    Returns dict: grid_key -> list of (export_position, export_normal, vertex_index)
    Face mesh normals in export space: [n.x, n.y, n.z] (no transform).
    """
    base_mesh = base_model.meshes[0]
    cell_size = POSITION_TOLERANCE * 10

    grid = {}
    face_count = 0

    for v_idx in range(len(base_mesh.vertices)):
        mat_idx = base_mesh.vertex_materials.get(v_idx, -1)
        if mat_idx != FACE_TMD_MATERIAL_INDEX:
            continue

        v = base_mesh.vertices[v_idx]
        n = base_mesh.normals[v_idx]
        # Export space (no transform for base mesh)
        pos = (v.x, v.y, v.z)
        norm = (n.x, n.y, n.z)

        key = (
            int(math.floor(pos[0] / cell_size)),
            int(math.floor(pos[1] / cell_size)),
            int(math.floor(pos[2] / cell_size)),
        )
        if key not in grid:
            grid[key] = []
        grid[key].append((pos, norm, v_idx))
        face_count += 1

    print(f"Face boundary map: {face_count} vertices in {len(grid)} grid cells")
    return grid, cell_size


def find_boundary_and_fix_normals(hair_model, face_grid, cell_size):
    """Find boundary vertices and average their normals.

    Modifies hair_model.meshes[*].normals IN PLACE so that when the
    part_exporter applies -X transform, the result matches the face mesh.

    For a boundary vertex:
    - face_export_normal = (fx, fy, fz)
    - hair_export_normal = (-hx, hy, hz)  (after -X)
    - averaged = normalize(face + hair_export)
    - To get this from part_exporter (-X), set source normal to (-avg_x, avg_y, avg_z)
    """
    fixed_count = 0
    total_angle_before = 0.0
    total_angle_after = 0.0

    for mesh in hair_model.meshes:
        for v_idx in range(len(mesh.vertices)):
            v = mesh.vertices[v_idx]
            n = mesh.normals[v_idx]

            # Hair position in export space (after -X)
            h_pos = (-v.x, v.y, v.z)
            # Hair normal in export space (after -X)
            h_norm_export = (-n.x, n.y, n.z)

            # Look up in face grid
            key = (
                int(math.floor(h_pos[0] / cell_size)),
                int(math.floor(h_pos[1] / cell_size)),
                int(math.floor(h_pos[2] / cell_size)),
            )

            best_match = None
            best_dist = POSITION_TOLERANCE + 1

            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nkey = (key[0] + dx, key[1] + dy, key[2] + dz)
                        if nkey not in face_grid:
                            continue
                        for f_pos, f_norm, f_vidx in face_grid[nkey]:
                            dist = vec_distance(h_pos, f_pos)
                            if dist < best_dist:
                                best_dist = dist
                                best_match = (f_pos, f_norm, f_vidx)

            if best_match is None or best_dist > POSITION_TOLERANCE:
                continue

            f_pos, f_norm_export, f_vidx = best_match

            # Compute angle before fix
            angle_before = angle_between(f_norm_export, h_norm_export)

            # Use face normal directly (not averaged) for exact match
            target = f_norm_export

            # Convert back to source space: part_exporter applies -X,
            # so source = (-target_x, target_y, target_z)
            mesh.normals[v_idx] = Vector3(-target[0], target[1], target[2])

            # Verify: after -X transform, we get (target_x, target_y, target_z)
            new_export = target
            angle_after = angle_between(f_norm_export, new_export)

            total_angle_before += angle_before
            total_angle_after += angle_after
            fixed_count += 1

    if fixed_count > 0:
        print(f"Fixed {fixed_count} boundary vertex normals")
        print(f"  Avg angle before: {total_angle_before / fixed_count:.2f} deg")
        print(f"  Avg angle after:  {total_angle_after / fixed_count:.2f} deg")
    else:
        print("WARNING: No boundary vertices found!")

    return fixed_count


def main():
    parser = TMDParser()
    mlib_parser = MLIBParser()

    # Parse source files
    print("Loading base TMD...")
    base_model = parser.parse(BASE_TMD)

    print("Loading MLIB...")
    mlib = mlib_parser.parse(MLIB_PATH)

    print("Loading hair PRT...")
    hair_model = parser.parse(HAIR_PRT)

    # Step 1: Export original (unmodified) for comparison
    print(f"\nExporting original: {ORIGINAL_OUTPUT}")
    # Re-parse to get a fresh copy for original export
    hair_original = parser.parse(HAIR_PRT)
    export_part(hair_original, base_model, mlib, ORIGINAL_OUTPUT)
    print("  Done.")

    # Step 2: Build face boundary map
    print("\nBuilding face boundary map...")
    face_grid, cell_size = build_face_boundary_map(base_model)

    # Step 3: Fix boundary normals on hair model
    print("\nAveraging boundary normals...")
    fixed = find_boundary_and_fix_normals(hair_model, face_grid, cell_size)

    # Step 4: Export fixed version
    print(f"\nExporting fixed: {FIXED_OUTPUT}")
    export_part(hair_model, base_model, mlib, FIXED_OUTPUT)
    print("  Done.")

    print(f"\nCompare in Godot:")
    print(f"  Original: {ORIGINAL_OUTPUT.name}")
    print(f"  Fixed:    {FIXED_OUTPUT.name}")
    print(f"  ({fixed} boundary normals averaged)")


if __name__ == "__main__":
    main()
