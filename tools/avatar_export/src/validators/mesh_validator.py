"""
Mesh Validator

Validates mesh data before export to catch issues early.
Returns ValidationResult with pass/fail and message.

Checks:
- Vertex count > 0
- No NaN/Inf values in vertices
- Bounds within reasonable range (0.1m - 5m extent)
- Face indices within valid range
"""

import math
from dataclasses import dataclass
from typing import Sequence

from src.parsers.tmd_parser import TMDModel


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    message: str
    check_name: str = ""


def validate_vertex_count(count: int) -> ValidationResult:
    """Validate that vertex count is positive."""
    if count <= 0:
        return ValidationResult(
            valid=False,
            message=f"Vertex count is {count}, must be > 0",
            check_name="vertex_count",
        )
    return ValidationResult(
        valid=True,
        message=f"Vertex count OK: {count}",
        check_name="vertex_count",
    )


def validate_no_nan(vertices: Sequence[Sequence[float]]) -> ValidationResult:
    """Validate that no vertices contain NaN or Inf values."""
    for i, v in enumerate(vertices):
        for j, component in enumerate(v):
            if math.isnan(component):
                return ValidationResult(
                    valid=False,
                    message=f"NaN found at vertex {i}, component {j}",
                    check_name="no_nan",
                )
            if math.isinf(component):
                return ValidationResult(
                    valid=False,
                    message=f"Inf found at vertex {i}, component {j}",
                    check_name="no_nan",
                )
    return ValidationResult(
        valid=True,
        message=f"No NaN/Inf values in {len(vertices)} vertices",
        check_name="no_nan",
    )


def validate_bounds(
    min_bound: Sequence[float],
    max_bound: Sequence[float],
    min_extent: float = 0.1,
    max_extent: float = 5.0,
) -> ValidationResult:
    """Validate that mesh bounds are within reasonable range."""
    extent = [max_bound[i] - min_bound[i] for i in range(3)]
    max_dim = max(extent)

    if max_dim < min_extent:
        return ValidationResult(
            valid=False,
            message=f"Mesh too small: max extent {max_dim:.3f}m < {min_extent}m",
            check_name="bounds",
        )
    if max_dim > max_extent:
        return ValidationResult(
            valid=False,
            message=f"Mesh too large: max extent {max_dim:.3f}m > {max_extent}m",
            check_name="bounds",
        )
    return ValidationResult(
        valid=True,
        message=f"Bounds OK: extent ({extent[0]:.2f}, {extent[1]:.2f}, {extent[2]:.2f})m",
        check_name="bounds",
    )


def validate_faces(
    faces: Sequence[Sequence[int]],
    vertex_count: int,
) -> ValidationResult:
    """Validate that face indices are within valid range."""
    for i, face in enumerate(faces):
        for j, idx in enumerate(face):
            if idx < 0:
                return ValidationResult(
                    valid=False,
                    message=f"Invalid negative index {idx} at face {i}, vertex {j}",
                    check_name="faces",
                )
            if idx >= vertex_count:
                return ValidationResult(
                    valid=False,
                    message=f"Index {idx} out of range (vertex_count={vertex_count}) at face {i}",
                    check_name="faces",
                )
    return ValidationResult(
        valid=True,
        message=f"Face indices OK: {len(faces)} faces",
        check_name="faces",
    )


def validate_mesh(model: TMDModel) -> ValidationResult:
    """
    Validate all meshes in a TMD model.

    Runs all validation checks and returns first failure or success.
    """
    # Collect all vertices and faces across meshes
    all_vertices = []
    all_faces = []
    vertex_offset = 0

    for mesh in model.meshes:
        for v in mesh.vertices:
            all_vertices.append([v.x, v.y, v.z])
        for face in mesh.faces:
            # Offset face indices by accumulated vertex count
            all_faces.append([f + vertex_offset for f in face])
        vertex_offset += len(mesh.vertices)

    # Run checks
    result = validate_vertex_count(len(all_vertices))
    if not result.valid:
        return result

    result = validate_no_nan(all_vertices)
    if not result.valid:
        return result

    # Calculate bounds
    if all_vertices:
        min_bound = [
            min(v[0] for v in all_vertices),
            min(v[1] for v in all_vertices),
            min(v[2] for v in all_vertices),
        ]
        max_bound = [
            max(v[0] for v in all_vertices),
            max(v[1] for v in all_vertices),
            max(v[2] for v in all_vertices),
        ]
        result = validate_bounds(min_bound, max_bound)
        if not result.valid:
            return result

    result = validate_faces(all_faces, len(all_vertices))
    if not result.valid:
        return result

    return ValidationResult(
        valid=True,
        message=f"Mesh validation passed: {len(all_vertices)} vertices, {len(all_faces)} faces",
        check_name="mesh",
    )
