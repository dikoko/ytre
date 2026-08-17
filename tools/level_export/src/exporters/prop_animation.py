"""Animated-prop resolution: TMD XFORM tracks -> Godot-space node animation.

Semantics (verified against retail client behavior):

  * XFORM tracks are LOCAL transforms that REPLACE the object's static
    matrix; they do not compose with it.
  * The original client builds, per frame:
        xform = Scale(s)                      (optionally about ScaleAxis)
        xform *= Rotate(q)
        xform.Translate(t)                    -> sets the translation row
    then accumulates childXform *= parentXform up the hierarchy.
  * Objects are addressed by APPEND ORDINAL, and some files carry one extra
    leading animation for the object group; the offset is derived from the
    counts.

PLACEMENT (settled during implementation, 2026-08-02). The authored
WORLDMATRIX cannot be re-derived from the local tracks alone: the object
group carries a transform that is absent from the animation data, and
solving for it is inconsistent across objects in 19 of the 176 props. So we
do not try. Each animated object gets a static PIVOT node

    P = L(0)^-1 . W . W_parent^-1          (row-vector, D3D)

with the animated node as its child. At frame 0 this collapses to exactly
W — bit-for-bit the placement the static bake produces today — and as the
frame advances the object animates in its authored frame. Objects whose
parent also animates nest under it, so inheritance is preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.parsers.tmd_parser import Quaternion, TMDAnimation, TMDAnimRange, TMDModel

# D3D -> Godot mirror. M_godot = S . M_d3d^T . S
S = np.diag([1.0, 1.0, -1.0])

# Below this |det| a basis cannot be inverted, so no pivot exists.
SINGULAR_DET = 1e-9


def d3d_rotation_matrix(q: Quaternion) -> np.ndarray:
    """Quaternion -> 3x3 rotation in the D3D row-vector convention.

    Matches the convention TMDObject.world_transform.rotation is stored in.
    """
    x, y, z, w = q.x, q.y, q.z, q.w
    n = (x * x + y * y + z * z + w * w) ** 0.5
    if n == 0.0:
        return np.eye(3)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)],
        [2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)],
        [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)],
    ])


def quat_from_d3d_matrix(m: np.ndarray) -> tuple[float, float, float, float]:
    """3x3 rotation (D3D row-vector) -> quaternion (x, y, z, w).

    Inverse of d3d_rotation_matrix. Shepperd's method, branching on the
    largest diagonal term for numerical stability.
    """
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0.0:
        s = (t + 1.0) ** 0.5 * 2.0
        w = 0.25 * s
        x = (m[1, 2] - m[2, 1]) / s
        y = (m[2, 0] - m[0, 2]) / s
        z = (m[0, 1] - m[1, 0]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = (1.0 + m[0, 0] - m[1, 1] - m[2, 2]) ** 0.5 * 2.0
        w = (m[1, 2] - m[2, 1]) / s
        x = 0.25 * s
        y = (m[1, 0] + m[0, 1]) / s
        z = (m[2, 0] + m[0, 2]) / s
    elif m[1, 1] > m[2, 2]:
        s = (1.0 + m[1, 1] - m[0, 0] - m[2, 2]) ** 0.5 * 2.0
        w = (m[2, 0] - m[0, 2]) / s
        x = (m[1, 0] + m[0, 1]) / s
        y = 0.25 * s
        z = (m[2, 1] + m[1, 2]) / s
    else:
        s = (1.0 + m[2, 2] - m[0, 0] - m[1, 1]) ** 0.5 * 2.0
        w = (m[0, 1] - m[1, 0]) / s
        x = (m[2, 0] + m[0, 2]) / s
        y = (m[2, 1] + m[1, 2]) / s
        z = 0.25 * s
    n = (x * x + y * y + z * z + w * w) ** 0.5
    return (x / n, y / n, z / n, w / n)


def to_godot_basis(m_d3d: np.ndarray) -> np.ndarray:
    """M_godot = S . M_d3d^T . S — the project-wide conversion rule."""
    return S @ m_d3d.T @ S


def to_godot_translation(t) -> tuple[float, float, float]:
    """Positions mirror on Z."""
    return (float(t[0]), float(t[1]), -float(t[2]))


def mat4_d3d(basis: np.ndarray, trans) -> np.ndarray:
    """Row-vector 4x4: basis in the top-left 3x3, translation in ROW 3."""
    m = np.eye(4)
    m[:3, :3] = basis
    m[3, :3] = np.asarray(trans, dtype=np.float64)
    return m


def to_godot_matrix(m_d3d: np.ndarray) -> np.ndarray:
    """Row-vector D3D 4x4 -> column-vector Godot 4x4.

    Applies the same S-conjugation as to_godot_basis, and mirrors the
    translation. Column-vector output means composition reverses:
    (A . B)_d3d converts to godot(B) @ godot(A).
    """
    out = np.eye(4)
    out[:3, :3] = to_godot_basis(m_d3d[:3, :3])
    out[:3, 3] = to_godot_translation(m_d3d[3, :3])
    return out


def object_matrix_d3d(obj, which: str = "world_transform") -> np.ndarray:
    """The authored world (or local) matrix of a TMD object, row-vector."""
    tr = getattr(obj, which)
    return mat4_d3d(np.array(tr.rotation.data).reshape(3, 3),
                    tr.translation.to_tuple())


def _scale_matrix(anim: TMDAnimation, key_index: int) -> np.ndarray:
    """Scale, optionally applied about an authored axis.

    The original client composes it as:
        xform = axis_inverse * Scale(s) * axis
    """
    if not anim.scale_keys:
        return np.eye(3)
    idx = min(key_index, len(anim.scale_keys) - 1)
    s = np.diag(anim.scale_keys[idx].scale.to_list())
    if not anim.scale_axis_keys:
        return s
    aidx = min(key_index, len(anim.scale_axis_keys) - 1)
    axis = d3d_rotation_matrix(anim.scale_axis_keys[aidx].rotation)
    return axis.T @ s @ axis


def local_trs_d3d(anim: TMDAnimation, key_index: int = 0
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Local (basis, translation) in D3D space at the given key index."""
    basis = _scale_matrix(anim, key_index)
    if anim.rotation_keys:
        r_idx = min(key_index, len(anim.rotation_keys) - 1)
        basis = basis @ d3d_rotation_matrix(anim.rotation_keys[r_idx].rotation)
    if anim.position_keys:
        p_idx = min(key_index, len(anim.position_keys) - 1)
        trans = np.array(anim.position_keys[p_idx].position.to_list())
    else:
        trans = np.zeros(3)
    return basis, trans


def local_matrix_d3d(anim: TMDAnimation, key_index: int = 0) -> np.ndarray:
    basis, trans = local_trs_d3d(anim, key_index)
    return mat4_d3d(basis, trans)


# Relative off-diagonal stretch above which a basis cannot be carried by a
# glTF TRS node and needs the factor chain below.
SHEAR_TOL = 1e-4


def stretch_offdiagonal(basis: np.ndarray) -> float:
    """Relative size of the non-diagonal part of the polar stretch factor.

    0 for anything a TRS node can hold (rotation x diagonal scale, including
    mirrors); grows as an authored scale-about-an-axis tilts away from the
    object axes.
    """
    if not np.all(np.isfinite(basis)):
        return 0.0
    try:
        _u, s, vt = np.linalg.svd(basis)
    except np.linalg.LinAlgError:
        return 0.0
    p = vt.T @ np.diag(s) @ vt
    denom = max(float(np.abs(np.diag(p)).max()), 1e-9)
    return float(np.abs(p - np.diag(np.diag(p))).max()) / denom


def has_shear(anim: TMDAnimation) -> bool:
    """True if ANY key needs the factor chain (SCALEAXISLIST tilted off-axis).

    Checked across every key, not just frame 0: 724 of the 885 scale-axis
    objects have a scale matrix that changes over time, so a frame-0-only
    test would miss objects that acquire shear mid-animation.
    """
    if not anim.scale_axis_keys:
        return False
    n_keys = max(len(anim.scale_keys), len(anim.scale_axis_keys), 1)
    for k in range(n_keys):
        basis, _t = local_trs_d3d(anim, k)
        if stretch_offdiagonal(to_godot_basis(basis)) > SHEAR_TOL:
            return True
    return False


def godot_local_factors(anim: TMDAnimation, key_index: int = 0):
    """Factor the Godot-space local basis into TRS-representable pieces.

    The engine builds the D3D basis as `Ssc . Rrot` where a scale-about-axis
    is `Ssc = axis^T . D . axis`. Converting:

        M_godot = S . (Ssc . Rrot)^T . S
                = (S . Rrot^T . S) . (S . Ssc . S)
                = A . (Q^T . D . Q)          with Q = S . axis . S

    Each factor is individually TRS-representable, and each maps 1:1 onto one
    authored track — A to the rotation keys, D to the scale keys, Q/Q^T to the
    scale-axis keys — so all four can carry animation channels.

    Returns (A, Q_transpose, D_diagonal, Q) as 3x3 arrays / a length-3 vector.
    """
    rot = np.eye(3)
    if anim.rotation_keys:
        r_idx = min(key_index, len(anim.rotation_keys) - 1)
        rot = d3d_rotation_matrix(anim.rotation_keys[r_idx].rotation)
    a = to_godot_basis(rot)

    if anim.scale_keys:
        s_idx = min(key_index, len(anim.scale_keys) - 1)
        diag = np.array(anim.scale_keys[s_idx].scale.to_list(), dtype=np.float64)
    else:
        diag = np.ones(3)

    if anim.scale_axis_keys:
        a_idx = min(key_index, len(anim.scale_axis_keys) - 1)
        axis = d3d_rotation_matrix(anim.scale_axis_keys[a_idx].rotation)
        q = S @ axis @ S
    else:
        q = np.eye(3)

    return a, q.T, diag, q


@dataclass
class AnimatedObject:
    object_index: int            # index into model.objects
    anim_index: int              # index into model.animations
    parent_object_index: int     # -1 == no ANIMATED parent
    node_name: str               # the animated node (carries the mesh)
    pivot_name: str              # the static parent node
    animation: TMDAnimation
    pivot_d3d: np.ndarray        # row-vector 4x4


@dataclass
class PropAnimationPlan:
    animated: dict[int, AnimatedObject] = field(default_factory=dict)
    anim_offset: int = 0
    fps: float = 30.0
    total_frames: float = 0.0
    clips: list[TMDAnimRange] = field(default_factory=list)
    visibility: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    # Objects that carry keys but whose frame-0 basis is singular, so no
    # pivot exists. They fall back to the static bake. 6 library-wide.
    demoted: list[int] = field(default_factory=list)


def _tracks_are_finite(anim: TMDAnimation) -> bool:
    """False if any authored key holds NaN/inf (a_SWAball03_01 does)."""
    for key in anim.position_keys:
        if not all(np.isfinite(key.position.to_list())):
            return False
    for key in anim.scale_keys:
        if not all(np.isfinite(key.scale.to_list())):
            return False
    for keys in (anim.rotation_keys, anim.scale_axis_keys):
        for key in keys:
            q = key.rotation
            if not all(np.isfinite([q.x, q.y, q.z, q.w])):
                return False
    return True


def _has_real_keys(anim: TMDAnimation) -> bool:
    return (len(anim.position_keys) + len(anim.rotation_keys)
            + len(anim.scale_keys)) > 1


def build_animation_plan(model: TMDModel, prop_id: str) -> PropAnimationPlan:
    """Resolve which objects animate, their pivots, and their node names."""
    offset = 1 if len(model.animations) == len(model.objects) + 1 else 0

    # Pass 1: which objects carry real keys and can be inverted at frame 0.
    candidates: dict[int, TMDAnimation] = {}
    demoted: list[int] = []
    for obj_index in range(len(model.objects)):
        anim_index = obj_index + offset
        if anim_index >= len(model.animations):
            continue
        anim = model.animations[anim_index]
        if not _has_real_keys(anim):
            continue
        if not _tracks_are_finite(anim):
            # a_SWAball03_01 carries NaN in its authored tracks; animating it
            # would poison the node transform and every child under it.
            demoted.append(obj_index)
            continue
        basis, _t = local_trs_d3d(anim, 0)
        if abs(np.linalg.det(basis)) < SINGULAR_DET:
            demoted.append(obj_index)
            continue
        candidates[obj_index] = anim

    # Pass 2: pivots. A parent only counts if it is itself animated.
    animated: dict[int, AnimatedObject] = {}
    for obj_index, anim in candidates.items():
        parent_anim = anim.parent_id
        parent_object_index = (parent_anim - offset) if parent_anim >= offset else -1
        if parent_object_index not in candidates:
            parent_object_index = -1

        w = object_matrix_d3d(model.objects[obj_index])
        if parent_object_index == -1:
            w_parent_inv = np.eye(4)
        else:
            w_parent_inv = np.linalg.inv(
                object_matrix_d3d(model.objects[parent_object_index])
            )
        l0_inv = np.linalg.inv(local_matrix_d3d(anim, 0))

        animated[obj_index] = AnimatedObject(
            object_index=obj_index,
            anim_index=anim.object_id if anim.object_id >= 0 else obj_index + offset,
            parent_object_index=parent_object_index,
            node_name=f"{prop_id}_obj{obj_index}",
            pivot_name=f"{prop_id}_obj{obj_index}_pivot",
            animation=anim,
            pivot_d3d=l0_inv @ w @ w_parent_inv,
        )

    visibility = {
        t.object_ordinal - offset: list(t.keys)
        for t in model.visibility_tracks
        if (t.object_ordinal - offset) in animated
    }

    return PropAnimationPlan(
        animated=animated,
        anim_offset=offset,
        fps=model.frame_speed or 30.0,
        total_frames=model.total_frames,
        clips=list(model.anim_ranges),
        visibility=visibility,
        demoted=demoted,
    )


def has_visible_animation(model: TMDModel, plan: PropAnimationPlan) -> bool:
    """True when the animation can actually move something on screen.

    49 of the 3,348 animated objects are mesh-free helpers (`Dummy02` and
    friends — authoring rig nodes). An object like that is only worth
    exporting if an animated DESCENDANT carries geometry; alone it emits no
    node, no channel, and no AnimationPlayer, so the GLB comes out
    byte-identical to a static export. One prop library-wide is animated
    exclusively on such helpers (a_SWAptameet01), and flagging it `animated`
    would promise motion the scene cannot deliver.
    """
    def has_geometry(obj_index: int) -> bool:
        mesh = model.objects[obj_index].mesh
        return mesh is not None and len(mesh.vertices) > 0

    for obj_index in plan.animated:
        if has_geometry(obj_index):
            return True
        # Walk the animated children of this helper, if any.
        stack = [i for i, n in plan.animated.items()
                 if n.parent_object_index == obj_index]
        seen = {obj_index}
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            if has_geometry(child):
                return True
            stack.extend(i for i, n in plan.animated.items()
                         if n.parent_object_index == child)
    return False


def world_matrix_d3d(plan: PropAnimationPlan, object_index: int,
                     key_index: int = 0) -> np.ndarray:
    """Compose an animated object's world matrix at a key index (D3D)."""
    node = plan.animated[object_index]
    m = local_matrix_d3d(node.animation, key_index) @ node.pivot_d3d
    parent = node.parent_object_index
    seen = {object_index}
    while parent != -1 and parent in plan.animated and parent not in seen:
        seen.add(parent)
        pnode = plan.animated[parent]
        m = m @ local_matrix_d3d(pnode.animation, key_index) @ pnode.pivot_d3d
        parent = pnode.parent_object_index
    return m


def verify_frame0_invariant(model: TMDModel, plan: PropAnimationPlan,
                            tol: float = 1e-4) -> list[str]:
    """Frame-0 node chain must reproduce each object's authored world matrix.

    True by construction of the pivot, but asserted anyway: it catches a
    wrong multiplication order, a mis-resolved parent, or an off-by-one in
    the animation<->object ordinal mapping — none of which are visible in
    the pivot formula itself.
    """
    failures: list[str] = []
    for obj_index, node in plan.animated.items():
        got = world_matrix_d3d(plan, obj_index, 0)
        want = object_matrix_d3d(model.objects[obj_index])
        err = float(np.abs(got - want).max())
        if err > tol:
            failures.append(f"obj{obj_index}({node.node_name}) err={err:.5f}")
    return failures
