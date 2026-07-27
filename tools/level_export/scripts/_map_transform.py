"""D3D row-major .qqq matrix -> Godot Transform3D conversion.

QQQ stores row-vector D3D world matrices (rows = U/V/N basis, row3 = position)
which the original client applies verbatim as each object's world transform.
Conversion: M_godot = S * R_d3d^T * S, S = diag(1,1,-1).
"""
import math

import numpy as np


def d3d_to_godot_basis(mat: list[float]):
    r0 = (mat[0], mat[4], -mat[8])
    r1 = (mat[1], mat[5], -mat[9])
    r2 = (-mat[2], -mat[6], mat[10])
    origin = (mat[12], mat[13], -mat[14])
    return r0, r1, r2, origin


def basis_det(mat: list[float]) -> float:
    m = np.array(mat).reshape(4, 4)
    return float(np.linalg.det(m[:3, :3]))


def format_transform(mat: list[float]) -> str:
    r0, r1, r2, origin = d3d_to_godot_basis(mat)
    values = [*r0, *r1, *r2, *origin]
    formatted = ", ".join(f"{v:.6g}" for v in values)
    return f"Transform3D({formatted})"


def format_transform_mirror_x(mat: list[float]) -> str:
    """Transform for a negative-determinant placement (basis_det(mat) < 0)
    instancing the `{model}_mirrorx.glb` variant: T' = T . diag(-1,1,1),
    i.e. negate the FIRST BASIS COLUMN of the Godot basis, origin unchanged.
    This exactly cancels the mirror_x export's model-space x-negation, so
    T'.(mirror_x(v)) == T.v for every source vertex v (see
    export_prop(..., mirror_x=True) in src/exporters/prop_exporter.py and
    scripts/30_export_map.py write_tscn)."""
    r0, r1, r2, origin = d3d_to_godot_basis(mat)
    basis = np.array([r0, r1, r2], dtype=np.float64)
    basis[:, 0] *= -1.0
    basis += 0.0  # normalize -0.0 -> 0.0 (IEEE 754: -0.0 + 0.0 == 0.0)
    values = [*basis[0].tolist(), *basis[1].tolist(), *basis[2].tolist(), *origin]
    formatted = ", ".join(f"{v:.6g}" for v in values)
    return f"Transform3D({formatted})"


def apply_override_to_matrix(qqq_mat: list[float], override: dict) -> str:
    """Compose editor overrides ON TOP of the true converted transform.

    Replaces the old lossy path in apply_overrides_to_tscn that rebuilt a
    pure Y-rotation matrix from scratch and discarded the original
    scale/shear baked into the .qqq placement (e.g. non-unit-scale track
    segments). flip_object/mirror replicate map_editor.gd's own edit
    semantics; flip_normals is superseded by the corrected normal formula
    (see d3d_to_godot_basis / prop_exporter normal negation) and is warned +
    ignored rather than applied here.

    Yaw-SET semantics: map_editor.gd:409-413 `_record_override` writes
    `ov["rotation_y"] = snapped(node.rotation_degrees.y, 0.01)` — the
    node's ABSOLUTE world rotation.y at edit time, not a delta. So
    `override["rotation_y"]` here is an absolute yaw to rebuild around the
    prop's original per-axis scale, not an additional rotation to compose
    onto the existing basis.
    """
    r0, r1, r2, origin = d3d_to_godot_basis(qqq_mat)
    basis = np.array([r0, r1, r2], dtype=np.float64)
    if "rotation_y" in override:
        # Absolute yaw (see docstring above): rebuild the rotation part
        # around the original basis' per-column scale magnitudes so scale
        # survives, but the recorded absolute rotation.y replaces (rather
        # than composes with) whatever yaw the original basis encoded.
        a = math.radians(override["rotation_y"])
        c, s = math.cos(a), math.sin(a)
        scale = np.linalg.norm(basis, axis=0)
        ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        basis = ry @ np.diag(scale)
    if override.get("flip_object"):
        basis[:, 2] *= -1.0
    if override.get("mirror"):
        basis[:, 0] *= -1.0
    if override.get("flip_normals"):
        print("WARNING: flip_normals override ignored (superseded by normal fix)")
    pos = override.get("position", origin)
    vals = [*basis[0], *basis[1], *basis[2], *pos]
    return "Transform3D(" + ", ".join(f"{v:.6g}" for v in vals) + ")"
