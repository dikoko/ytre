# Monster Export Pipeline Reference

Technical reference for the Yogurting monster model export pipeline. 


## Overview

Monsters are single-mesh models with embedded skeleton and animations.

- **Total monsters**: 135 in source data
- **Exported**: 135 (all configured in `monsters.yaml`)
- **Output**: `client/assets/monsters/models/ct####.glb`

#### Handedness (2026-07 refresh)

The source data is authored for a left-handed renderer; all models are
now exported with a coherent Z-mirror into right-handed glTF (positions,
winding, rig conjugation, all animation tracks — see the avatar pipeline
reference for the full convention). Textures with text read correctly,
and models face -Z (viewers rotate them PI to face the camera).

## Differences from Avatar Export

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

The `motion.option` field is a bitmask:

```
MOTION_FLAG_MOVING   = 1   // Root has locomotion translation
MOTION_FLAG_LOOP     = 2   // Animation loops
MOTION_FLAG_ROTATING = 4   // Root has rotation
MOTION_FLAG_SCALING  = 8   // Bone scaling
MOTION_FLAG_FIXY     = 16  // Fix Y position
```

All monster MLIB files use `motion_type = 4` (keyframe tracks). Each bone
carries rotation, translation, scale, and scale-axis key tracks; the exporter
expands and exports all of them (see the NPC pipeline reference for the
track-fidelity and scale-axis factor-chain details — monsters use the same
path). Scale sampling is gated by bit 3 of the motion option flags.

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

### Rotation Correction (retired)

Earlier versions corrected TMD/MLIB rest-pose mismatches per monster
(ct0032, ct0037, ct0038). With full translation tracks exported, the
correction is no longer needed and is retired.

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

The earlier issue census (root translation drift, weapon detachment,
animation pops, import crashes) predates the full-track exporter; those
categories are resolved:

- **Weapon detachment** — fixed by exporting per-bone translation tracks
  (weapon bones are positioned by their own tracks, not by rotation-only
  FK through the spine).
- **Root translation drift** — locomotion-flag Y normalization.
- **Animation pops / cloth shimmer** — full scale + scale-axis tracks with
  the per-factor node chain; physics-bone smoothing remains only for baked
  cloth simulation jumps.
- **Import crashes** — no longer reproduce; all 135 monsters import and
  play in Godot 4.6+.

Remaining deliberate deviation: EMA smoothing on physics bone chains
(skirt/hair/tail prefixes), kept to soften baked-simulation frame jumps.

---

## Verification

All 135 monsters pass the same automated checks as NPCs: node-FK parity vs
a full-track oracle (<= 1 cm, every motion), silhouette match vs a
software-skinned reference render (>= 0.99), and sub-frame parity of the
imported Godot animation at arbitrary sample times. The 19 monsters
previously excluded from the browser (ct0037, ct0038, ct0060, ct0069,
ct0070, ct0079, ct0083, ct0102, ct0118, ct0119, ct0138-ct0141,
ct0143-ct0146, ct0151) were re-verified and restored.

---

## File Paths

### Export Config

```
client/assets/monsters/monsters.yaml    # Monster list + per-monster zoom/name
```

### Output

```
client/assets/monsters/models/ct####.glb    # Exported GLB (135 files)
```

