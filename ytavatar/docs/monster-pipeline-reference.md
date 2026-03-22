# Monster Export Pipeline Reference

Technical reference for the Yogurting monster model export pipeline. 


## Overview

Monsters are single-mesh models with embedded skeleton and animations.

- **Total monsters**: 135 in source data
- **Exported**: 116 (configured in `monsters.yaml`)
- **Output**: `client/assets/monsters/models/ct####.glb`

### Differences from Avatar Export

| Feature | Avatar | Monster |
|---------|--------|---------|
| UV V-flip | Yes | No |
| Validation | 54-bone check | Disabled |
| Animation correction | No | Yes (auto-detect) |
| Multi-material split | No | Yes (per-vertex materials) |
| Texture embedding | External | Embedded in GLB |
| Parts/equipment | Yes | No (single mesh) |

---

## Data Format

### MLIB Motion Options (Bitmask)

The `motion.option` field is a bitmask from the original engine:

```
MOP_MOVING   = 1   // Root has locomotion translation
MOP_LOOP     = 2   // Animation loops
MOP_ROTATING = 4   // Root has rotation
MOP_SCALING  = 8   // Bone scaling
MOP_FIXY     = 16  // Fix Y position
```

All monster MLIB files use `motion_type = 4` (CGaKeyMotion — keyframe rotations, no per-bone translations).

---


## Skeleton Approach Auto-Detection

Two skeleton construction approaches, auto-selected based on bone reflection detection:

### TMD + Scale (default, no reflections)

- Uses TMD world rotation matrices for rest pose
- Extracts scale via SVD: `U, S, Vt = np.linalg.svd(R)`
- Preserves bind-pose mesh deformation (important for T-pose models like ct0013)
- Handles scaled bones correctly (ct0013: 77 scaled bones)

### MLIB Rotations (for models with structural reflections)

- Uses MLIB stand frame 0 rotations as rest pose (pure quaternions, no scale/reflection)
- TMD world positions used for bone placement
- IBMs computed from MLIB-derived rotation matrices
- Required for ct0016 (root has 90° rotation + 1.5 scale)

### Detection Logic

```python
has_reflections = any(
    np.linalg.det(bone_rotation_matrix) < 0
    for bone in model.bones
)
```

---

## Physics Bone Smoothing

Baked cloth/hair simulation data often has frame-to-frame rotation jumps. EMA (exponential moving average) bidirectional smoothing is applied to physics bones.

### Detection

Bones matching these name prefixes are smoothed:

```python
_PHYSICS_BONE_PREFIXES = (
    "@Skirt", "@skirt", "@Hair", "@Breast",
    "@necktie", "@upper", "@ribon", "@Cloth", "@Cover",
    "@Cap", "@Tail", "@Mantle", "@Feeler",
    "@Manteau", "@Rosary", "@Pipe",
    "@Tea", ...
)
```

### Smoothing Algorithm

Two-pass EMA (forward + backward) with factor 0.5, applied to quaternion rotations per bone per animation.

### Per-Model Overrides

For bones with generic names (`Bone##`) that can't be prefix-matched, use `smooth_bone_indices` parameter with explicit TMD bone indices.

---


## Texture Embedding

`_embed_textures()` reads all TMD materials, finds corresponding BMP files (case-insensitive), converts to PNG, and embeds into the GLB binary buffer.

For multi-material monsters, primitives are assigned to materials based on the face-to-material mapping from `vertex_materials`.

---

## Per-Monster Corrections

### Rotation Correction (`_correct_mlib_rotations`)

For specific monsters where TMD and MLIB rest-pose rotations differ significantly:

1. Compute TMD rest-pose local rotations
2. Find reference motion (stand)
3. Per bone: `correction = TMD_local * inverse(MLIB_stand_f0)`
4. Apply correction to ALL animation frames: `corrected = correction * MLIB[frame]`

Currently applied to: ct0032, ct0037, ct0038

### Per-Monster Zoom

`monsters.yaml` supports per-monster camera zoom distance:

```yaml
- id: ct0016
  zoom: 13.5   # Large boss
- id: ct0001
              # Default: 4.0
```

---

## Known Issues

### Issue Categories

| Code | Issue | Count | Description |
|------|-------|-------|-------------|
| OK | Good | 85 | No visible issues |
| RT | Root Translation | 24 | Model floats or clips during walk/run |
| WD | Weapon Detach | 12 | Weapon/prop drifts from hand |
| AP | Animation Pop | 10 | Sudden mesh extension in cloth/hair |
| BN | Bone Name | 5 | TMD/MLIB bone name mismatch |
| PR | Prop/Static | 3 | Static prop positioning |
| GC | Godot Crash | 3 | Crashes Godot on import |
| OR | Orientation | 3 | Model faces wrong direction |
| RF | Reflected Bone | 1 | Mirrored animation on asymmetric motion |

### Root Translation (RT)

Fixed for most cases with MOP_MOVING Y normalization. Remaining RT monsters have minor height offsets during walk/run — acceptable for gameplay.

### Weapon Detachment (WD)

Weapon bones parented to `@Root` or `@Spine` instead of hand. Positioned by rotation-only animation through the parent chain. Small quaternion precision differences cause drift. Known limitation — would require per-bone translation channels (not available in MLIB type 4).

### Godot Import Crash (GC)

ct0066, ct0074, ct0076 crash the Godot editor during import. Not included in `monsters.yaml`.

---

## Verification Status

Full visual verification completed for all 135 monsters. See `docs/monster-verification.md` for per-monster status codes.

**85 of 135 monsters (63%) look good.** Most issues are minor (RT, AP) or known limitations (WD, BN).

---

## File Paths

### Export Config

```
client/assets/monsters/monsters.yaml    # Monster list + per-monster zoom/name
```

### Output

```
client/assets/monsters/models/ct####.glb    # Exported GLB (116 files)
```

