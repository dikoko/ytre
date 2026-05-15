"""
Boundary Normal Fixer

Fixes vertex normal discontinuities at mesh boundaries between avatar parts
and the base mesh. When two separate meshes share vertices at the same position
but have different normals, it creates a visible shading seam.

This module replaces part boundary normals with the corresponding base mesh
normals so both sides shade identically at the seam.

Currently used for: hair parts vs face base mesh.
"""

import math

from src.parsers.tmd_parser import TMDModel, Vector3

# Distance tolerance for matching boundary vertices
POSITION_TOLERANCE = 0.001


def build_boundary_map(
    base_model: TMDModel,
    material_index: int,
) -> tuple[dict, float]:
    """Build spatial lookup of base mesh boundary vertices.

    Args:
        base_model: Parsed base TMD model
        material_index: TMD material index to extract (e.g., 7 for face)

    Returns:
        (grid, cell_size) where grid maps grid_key -> list of (position, normal)
        Positions and normals are in base mesh export space (no transform).
    """
    base_mesh = base_model.meshes[0]
    cell_size = POSITION_TOLERANCE * 10

    grid: dict[tuple[int, int, int], list[tuple[tuple[float, ...], tuple[float, ...]]]] = {}

    for v_idx in range(len(base_mesh.vertices)):
        mat_idx = base_mesh.vertex_materials.get(v_idx, -1)
        if mat_idx != material_index:
            continue

        v = base_mesh.vertices[v_idx]
        n = base_mesh.normals[v_idx]
        pos = (v.x, v.y, v.z)
        norm = (n.x, n.y, n.z)

        key = (
            int(math.floor(pos[0] / cell_size)),
            int(math.floor(pos[1] / cell_size)),
            int(math.floor(pos[2] / cell_size)),
        )
        if key not in grid:
            grid[key] = []
        grid[key].append((pos, norm))

    return grid, cell_size


def fix_part_boundary_normals(
    part_model: TMDModel,
    boundary_grid: dict,
    cell_size: float,
) -> int:
    """Replace part boundary normals with base mesh normals.

    Part vertices are compared in export space (after -X position/normal transform).
    When a match is found, the part's source normal is set so that after the
    part_exporter's -X transform, it equals the base mesh normal.

    Args:
        part_model: Parsed PRT model (modified in place)
        boundary_grid: Grid from build_boundary_map()
        cell_size: Cell size from build_boundary_map()

    Returns:
        Number of normals fixed
    """
    fixed_count = 0

    for mesh in part_model.meshes:
        for v_idx in range(len(mesh.vertices)):
            v = mesh.vertices[v_idx]

            # Part position in export space (after -X)
            h_pos = (-v.x, v.y, v.z)

            key = (
                int(math.floor(h_pos[0] / cell_size)),
                int(math.floor(h_pos[1] / cell_size)),
                int(math.floor(h_pos[2] / cell_size)),
            )

            best_norm = None
            best_dist = POSITION_TOLERANCE + 1

            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nkey = (key[0] + dx, key[1] + dy, key[2] + dz)
                        if nkey not in boundary_grid:
                            continue
                        for f_pos, f_norm in boundary_grid[nkey]:
                            dist = math.sqrt(sum(
                                (a - b) ** 2 for a, b in zip(h_pos, f_pos)
                            ))
                            if dist < best_dist:
                                best_dist = dist
                                best_norm = f_norm

            if best_norm is None or best_dist > POSITION_TOLERANCE:
                continue

            # Set source normal so that after part_exporter's -X transform,
            # it equals the base mesh normal: source = (-target_x, target_y, target_z)
            mesh.normals[v_idx] = Vector3(-best_norm[0], best_norm[1], best_norm[2])
            fixed_count += 1

    return fixed_count
