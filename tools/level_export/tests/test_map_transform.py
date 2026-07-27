"""Hand-computed fixtures for the D3D row-major -> Godot conversion.

Ground truth: .qqq matrices are D3D row-vector world matrices the original
client applies verbatim; conversion M_godot = S * R_d3d^T * S with
S=diag(1,1,-1).
"""
import math
import re
import numpy as np
from scripts._map_transform import (
    d3d_to_godot_basis, format_transform, basis_det, format_transform_mirror_x,
    apply_override_to_matrix,
)


def _flat(rows):  # 4 rows of 4 -> list[16]
    return [v for row in rows for v in row]

IDENTITY = _flat([[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])


def test_identity():
    r0, r1, r2, origin = d3d_to_godot_basis(IDENTITY)
    assert (r0, r1, r2, origin) == ((1,0,0),(0,1,0),(0,0,1),(0,0,0))


def test_translation_z_negated():
    mat = _flat([[1,0,0,0],[0,1,0,0],[0,0,1,0],[3,4,5,1]])
    assert d3d_to_godot_basis(mat)[3] == (3, 4, -5)


def test_rotation_y_90():
    # D3D row-vector yaw+90 (left-handed): row0=(0,0,-1) row1=(0,1,0) row2=(1,0,0)...
    # Hand-derived: a point on +X in D3D maps to -Z_d3d = +Z_godot.
    c, s = 0.0, 1.0
    mat = _flat([[c,0,-s,0],[0,1,0,0],[s,0,c,0],[0,0,0,1]])
    r0, r1, r2, origin = d3d_to_godot_basis(mat)
    basis = np.array([r0, r1, r2])          # Godot basis rows
    p = basis @ np.array([1, 0, 0])          # transform Godot +X point
    # D3D: (1,0,0)*M = (0,0,-1) -> Godot z-negated = (0,0,1)
    assert np.allclose(p, [0, 0, 1], atol=1e-12)


def test_uniform_scale_preserved():
    mat = _flat([[2,0,0,0],[0,2,0,0],[0,0,2,0],[0,0,0,1]])
    assert math.isclose(basis_det(mat), 8.0)


def test_mirror_detected():
    mat = _flat([[-1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
    assert basis_det(mat) < 0


def test_format_transform_string():
    s = format_transform(IDENTITY)
    assert s == "Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)"


def test_format_transform_mirror_x_negates_first_basis_column():
    """T' = T . diag(-1,1,1) for a negative-determinant placement: negate the
    FIRST BASIS COLUMN (not row) of the Godot basis, origin unchanged, so
    T'.(mirror_x . v) == T . v for every source vertex v (mirror_x negates x
    on the model side; this negates the matching column on the placement
    side to cancel it back out)."""
    s = format_transform_mirror_x(IDENTITY)
    assert s == "Transform3D(-1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)"


def test_format_transform_mirror_x_keeps_origin():
    mat = _flat([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [3, 4, 5, 1]])
    s = format_transform_mirror_x(mat)
    assert s == "Transform3D(-1, 0, 0, 0, 1, 0, 0, 0, 1, 3, 4, -5)"


def test_format_transform_mirror_x_cancels_model_mirror():
    """End-to-end sign-convention check: applying the base D3D->Godot
    rotation (via d3d_to_godot_basis) to a mirror_x'd point
    (mirror_x . v = (-x, y, -z) in D3D/model space, exported to Godot as
    (-x, y, z) by the base -z convention) through T' must equal applying the
    ORIGINAL (unmirrored) point through the ORIGINAL basis — i.e. the extra
    basis-column negation exactly cancels the model-side mirror_x."""
    # A non-trivial rotation (D3D row-vector 90-deg yaw, det = +1 in D3D).
    c, s_ = 0.0, 1.0
    mat = _flat([[c, 0, -s_, 0], [0, 1, 0, 0], [s_, 0, c, 0], [0, 0, 0, 1]])

    r0, r1, r2, origin = d3d_to_godot_basis(mat)
    basis = np.array([r0, r1, r2])

    # Original point v in D3D/model space, and its Godot-space export under
    # the base (non-mirrored) convention (x, y, -z).
    v = np.array([1.0, 2.0, 3.0])
    v_godot = np.array([v[0], v[1], -v[2]])
    p_original = basis @ v_godot

    # mirror_x'd export of the SAME point: (-x, y, -z) in Godot space.
    v_mirrored_godot = np.array([-v[0], v[1], -v[2]])

    r0m, r1m, r2m, origin_m = d3d_to_godot_basis(mat)
    basis_m = np.array([r0m, r1m, r2m])
    basis_m[:, 0] *= -1
    p_mirrored = basis_m @ v_mirrored_godot

    assert np.allclose(p_original, p_mirrored)
    assert origin == origin_m


def test_override_preserves_original_basis_when_only_position():
    mat = _flat([[2,0,0,0],[0,2,0,0],[0,0,2,0],[1,1,1,1]])  # scaled prop
    s = apply_override_to_matrix(mat, {"position": [9, 9, 9]})
    assert s.startswith("Transform3D(2, 0, 0, 0, 2, 0, 0, 0, 2, ")  # scale kept!
    assert s.endswith("9, 9, 9)")


def test_override_rotation_composes_not_replaces():
    mat = _flat([[2,0,0,0],[0,2,0,0],[0,0,2,0],[0,0,0,1]])
    s = apply_override_to_matrix(mat, {"rotation_y": 90.0, "position": [0, 0, 0]})
    # rotate the scaled basis; scale magnitude must survive (basis columns len 2)
    import re
    # NOTE: parse only the numbers *inside* the parens — the literal "3" in
    # the "Transform3D(" prefix is itself a regex match for [-\d.e+]+ and
    # would otherwise shift vals[:9] off by one for every implementation.
    vals = [float(v) for v in re.findall(r"[-\d.e+]+", s[s.index("(") + 1:])]
    basis = np.array(vals[:9]).reshape(3, 3)
    assert np.allclose(np.linalg.det(basis), 8.0, atol=1e-6)


def test_override_flip_object_negates_z_column():
    s_plain = apply_override_to_matrix(IDENTITY, {"position": [0, 0, 0]})
    s_flip = apply_override_to_matrix(IDENTITY, {"position": [0, 0, 0], "flip_object": True})
    assert s_plain != s_flip


def test_override_mirror_flips_scale_x():
    s = apply_override_to_matrix(IDENTITY, {"position": [0, 0, 0], "mirror": True})
    # See NOTE in test_override_rotation_composes_not_replaces: skip the
    # "Transform3D(" prefix so its literal "3" doesn't pollute vals[0].
    vals = [float(v) for v in __import__("re").findall(r"[-\d.e+]+", s[s.index("(") + 1:])]
    assert np.linalg.det(np.array(vals[:9]).reshape(3, 3)) < 0


def test_override_rotation_preserves_nonuniform_scale_on_prerotated_prop():
    """Non-uniform scale + baked yaw + rotation_y override: per-axis scale
    (Godot basis COLUMN norms — columns are the axis vectors) must survive.
    This fixture distinguishes column-norm scale extraction (correct) from
    row-norm extraction (silently corrupts scale: rows would give
    ~[2.386, 1, 2.075] here)."""
    th = math.radians(40)
    c, s = math.cos(th), math.sin(th)
    # D3D row-vector matrix: object X axis scaled 3x, yawed 40 degrees
    mat = [3 * c, 0, -3 * s, 0,   0, 1, 0, 0,   s, 0, c, 0,   5, 6, 7, 1]
    out = apply_override_to_matrix(mat, {"rotation_y": 90.0, "position": [0, 0, 0]})
    vals = [float(v) for v in re.findall(r"[-\d.e+]+", out[out.index("(") + 1:])]
    basis = np.array(vals[:9]).reshape(3, 3)
    assert np.allclose(np.linalg.norm(basis, axis=0), [3, 1, 1])   # per-axis scale kept
    assert np.allclose(np.linalg.det(basis), 3.0)
    assert np.allclose(basis[:, 0] / 3.0, [0, 0, -1])              # yaw actually set to 90
