#!/usr/bin/env python3
"""
Debug: Compare normals at face-hair boundary vertices.

Loads the male base TMD and hair part M0101 PRT, finds vertices at shared
positions between the face material region and the hair part, and reports
normal differences.

Key coordinate conventions:
- Base mesh (material_exporter): positions [v.x, v.y, v.z], normals [n.x, n.y, n.z]
- Hair part (part_exporter): positions [-v.x, v.y, v.z], normals [-n.x, n.y, n.z]

So when comparing, we apply the part_exporter transform to hair vertices/normals.
"""

import math
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.tmd_parser import TMDParser

# Paths
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
BASE_TMD = AVATAR_IRD / "male.TMD"
HAIR_PRT = AVATAR_IRD / "swap" / "male" / "male_hair_M0101.PRT"

# Face is TMD material index 7 (MaterialSlot.FACE = 8 in the enum)
FACE_TMD_MATERIAL_INDEX = 7

# Distance tolerance for matching boundary vertices
POSITION_TOLERANCE = 0.001


def vec_distance(a, b):
    """Euclidean distance between two 3-tuples."""
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def vec_dot(a, b):
    """Dot product of two 3-tuples."""
    return sum(ai * bi for ai, bi in zip(a, b))


def vec_length(a):
    """Length of a 3-tuple vector."""
    return math.sqrt(sum(ai * ai for ai in a))


def angle_between(a, b):
    """Angle in degrees between two 3D vectors."""
    la = vec_length(a)
    lb = vec_length(b)
    if la < 1e-8 or lb < 1e-8:
        return float("nan")
    cos_angle = vec_dot(a, b) / (la * lb)
    # Clamp for numerical safety
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def main():
    parser = TMDParser()

    # --- Parse base TMD ---
    print(f"Loading base TMD: {BASE_TMD}")
    base_model = parser.parse(BASE_TMD)
    base_mesh = base_model.meshes[0]
    print(f"  Total vertices: {len(base_mesh.vertices)}")
    print(f"  Total normals:  {len(base_mesh.normals)}")
    print(f"  vertex_materials entries: {len(base_mesh.vertex_materials)}")
    print()

    # --- Extract face vertices (TMD material index 7) ---
    face_positions = []  # (position_tuple, normal_tuple, vertex_index)
    for v_idx in range(len(base_mesh.vertices)):
        mat_idx = base_mesh.vertex_materials.get(v_idx, -1)
        if mat_idx == FACE_TMD_MATERIAL_INDEX:
            v = base_mesh.vertices[v_idx]
            n = base_mesh.normals[v_idx]
            # material_exporter: pass through as [v.x, v.y, v.z], [n.x, n.y, n.z]
            pos = (v.x, v.y, v.z)
            norm = (n.x, n.y, n.z)
            face_positions.append((pos, norm, v_idx))

    print(f"Face material vertices: {len(face_positions)}")
    print()

    # --- Parse hair PRT ---
    print(f"Loading hair PRT: {HAIR_PRT}")
    hair_model = parser.parse(HAIR_PRT)
    print(f"  Meshes: {len(hair_model.meshes)}")

    hair_positions = []  # (position_tuple, normal_tuple, mesh_idx, vertex_index)
    for mi, mesh in enumerate(hair_model.meshes):
        for v_idx in range(len(mesh.vertices)):
            v = mesh.vertices[v_idx]
            n = mesh.normals[v_idx]
            # part_exporter: positions [-v.x, v.y, v.z], normals [-n.x, n.y, n.z]
            pos = (-v.x, v.y, v.z)
            norm = (-n.x, n.y, n.z)
            hair_positions.append((pos, norm, mi, v_idx))

    print(f"  Total hair vertices (after -X transform): {len(hair_positions)}")
    print()

    # --- Find boundary vertex pairs ---
    # Build a spatial grid for face vertices for faster lookup
    grid = {}
    cell_size = POSITION_TOLERANCE * 10  # grid cell size

    def grid_key(pos):
        return (
            int(math.floor(pos[0] / cell_size)),
            int(math.floor(pos[1] / cell_size)),
            int(math.floor(pos[2] / cell_size)),
        )

    for i, (pos, norm, v_idx) in enumerate(face_positions):
        key = grid_key(pos)
        if key not in grid:
            grid[key] = []
        grid[key].append(i)

    # Search for matches
    boundary_pairs = []
    for h_pos, h_norm, h_mi, h_vidx in hair_positions:
        hkey = grid_key(h_pos)
        # Check neighboring cells
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nkey = (hkey[0] + dx, hkey[1] + dy, hkey[2] + dz)
                    if nkey in grid:
                        for fi in grid[nkey]:
                            f_pos, f_norm, f_vidx = face_positions[fi]
                            dist = vec_distance(h_pos, f_pos)
                            if dist <= POSITION_TOLERANCE:
                                angle = angle_between(f_norm, h_norm)
                                boundary_pairs.append({
                                    "face_vidx": f_vidx,
                                    "hair_mesh": h_mi,
                                    "hair_vidx": h_vidx,
                                    "position": f_pos,
                                    "dist": dist,
                                    "face_normal": f_norm,
                                    "hair_normal": h_norm,
                                    "angle_deg": angle,
                                })

    # --- Report ---
    print("=" * 70)
    print(f"BOUNDARY VERTEX PAIRS FOUND: {len(boundary_pairs)}")
    print("=" * 70)
    print()

    if not boundary_pairs:
        print("No shared boundary vertices found!")
        return

    # Sort by angle difference (largest first)
    boundary_pairs.sort(key=lambda p: p["angle_deg"], reverse=True)

    # Summary statistics
    angles = [p["angle_deg"] for p in boundary_pairs if not math.isnan(p["angle_deg"])]
    if angles:
        print(f"Normal angle differences:")
        print(f"  Min:    {min(angles):.2f} deg")
        print(f"  Max:    {max(angles):.2f} deg")
        print(f"  Mean:   {sum(angles) / len(angles):.2f} deg")
        print(f"  Median: {sorted(angles)[len(angles) // 2]:.2f} deg")
        print()

        # Histogram
        buckets = [0, 1, 5, 10, 30, 90, 180]
        print("  Angle distribution:")
        for i in range(len(buckets) - 1):
            count = sum(1 for a in angles if buckets[i] <= a < buckets[i + 1])
            bar = "#" * count
            print(f"    [{buckets[i]:3d}-{buckets[i+1]:3d}) deg: {count:4d}  {bar}")
        count_180 = sum(1 for a in angles if a >= 180)
        if count_180:
            print(f"    [180+    ) deg: {count_180:4d}")
        print()

    # Show sample pairs (up to 20, largest angle first)
    print("Sample boundary pairs (sorted by angle difference, largest first):")
    print("-" * 70)
    for i, p in enumerate(boundary_pairs[:20]):
        print(f"  Pair {i+1}:")
        print(f"    Position:    ({p['position'][0]:.4f}, {p['position'][1]:.4f}, {p['position'][2]:.4f})")
        print(f"    Face vtx:    base mesh idx {p['face_vidx']}")
        print(f"    Hair vtx:    mesh {p['hair_mesh']}, idx {p['hair_vidx']}")
        print(f"    Face normal: ({p['face_normal'][0]:.4f}, {p['face_normal'][1]:.4f}, {p['face_normal'][2]:.4f})")
        print(f"    Hair normal: ({p['hair_normal'][0]:.4f}, {p['hair_normal'][1]:.4f}, {p['hair_normal'][2]:.4f})")
        print(f"    Angle diff:  {p['angle_deg']:.2f} deg")
        print(f"    Pos dist:    {p['dist']:.6f}")
        print()

    # Also show some pairs with small angle differences
    if len(boundary_pairs) > 20:
        print("Smallest angle differences:")
        print("-" * 70)
        for i, p in enumerate(boundary_pairs[-5:]):
            print(f"  Pair (small {i+1}):")
            print(f"    Position:    ({p['position'][0]:.4f}, {p['position'][1]:.4f}, {p['position'][2]:.4f})")
            print(f"    Face normal: ({p['face_normal'][0]:.4f}, {p['face_normal'][1]:.4f}, {p['face_normal'][2]:.4f})")
            print(f"    Hair normal: ({p['hair_normal'][0]:.4f}, {p['hair_normal'][1]:.4f}, {p['hair_normal'][2]:.4f})")
            print(f"    Angle diff:  {p['angle_deg']:.2f} deg")
            print()


if __name__ == "__main__":
    main()
