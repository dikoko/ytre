# NPC Export Pipeline Reference

Technical reference for the Yogurting NPC model export pipeline.

---

## Overview

NPCs are character models that appear in the game world. Like monsters, they are single-mesh models with embedded skeleton and animations, but NPCs often hold weapons, tools, or props that require special handling during export.

- **Total NPCs**: 78 in source data
- **Exported**: 78 (all)
- **Output**: `client/assets/npcs/models/cn####.glb`

### Differences from Monster Export

| Feature | Monster | NPC |
|---------|---------|-----|
| ID prefix | `ct####` | `cn####` |
| Source dir | `Monster.IRD` | `NPC.IRD` |
| Per-model config | None | Skeleton-approach pin for 3 NPCs |
| Equip handling | Full key tracks (none needed) | Full key tracks (none needed) |
| Physics smoothing | Prefix-based only | Prefix + per-model bone indices |

---

## Data Format

### NPC Bone Naming

NPCs use two naming conventions for their skeleton:

1. **@-prefixed** (modern): `@Root`, `@Pelvis`, `@Spine1`, `@HandL`, `@Sword`, etc.
2. **Bip01-prefixed** (3ds Max): `Bip01 Pelvis`, `Bip01 L Hand`, `Bip01 Prop1`, etc.

Both conventions can appear in the same model. Equip bones use both: `@Sword`, `@fan`, `@Book`, `@broom`, `Bip01 Prop1`.

### Common Equip Bone Types

| Bone Name | Type | Example NPCs |
|-----------|------|-------------|
| `@Sword` | Sword/blade | cn0009, cn0045, cn0069 |
| `@fan01` | Fan | cn0011 |
| `@Book` / `@book` | Book | cn0042, cn0043, cn0049 |
| `@broom-stick` | Broom | cn0039, cn0040 |
| `@Pipe01` | Pipe/staff | cn0007 |
| `@abacus` | Abacus | cn0021 |
| `@bucket` | Bucket | cn0076 |
| `@Tea` | Tea cup | cn0047 |
| `Bip01 Prop1` | Generic prop | cn0005, cn0024 |

---

## Animation Track Fidelity

MLIB motion type 4 stores full per-bone key tracks: rotations, translations,
scales, and scale axes. The exporter expands all four track types and emits
them as GLTF animation channels, using the same interpolation the retail
client uses (nearest-previous key lookup + shortest-path slerp for
rotations/scale-axes, linear for translations/scales; before the first key a
track evaluates to zero/identity/unit).

Two details matter for correctness:

- **Skeleton bind offsets are dead data during animated motions** — bone
  translations come from the motion's own translation tracks. Exports that
  ignore the translation tracks and reuse bind offsets detach every animated
  prop (pipes, swords, fans, books) even though the body looks fine.
- **Scale sampling is gated** by bit 3 of the motion option flags; scale keys
  in motions without the flag are dead data and must not be applied.

With the full tracks exported, equips stay attached through every animation
with **zero per-NPC configuration** — the earlier reparenting, equip
correction, and bone-tweak systems are retired.

### Scale-Axis Factor Chain

Some bones animate anisotropic scale about a rotated axis: the bone's local
transform is `T * R * (Rsa * S * Rsa^T)`, which a single GLTF TRS node cannot
express. The exporter emits a chain of nodes, one per factor:

```
bone (T * R)  ->  {name}_SAS (Rsa * S)  ->  {name}_SA (Rsa^T)
```

with the skin joint and child bones attached to the last node. Because each
factor lives on its own node, Godot's per-node interpolation (slerp for
rotations, lerp for scales) reproduces the engine-style per-factor
interpolation exactly — at every playback time, not just on key frames.
Fusing or re-factorizing these tracks into fewer nodes is only correct ON
keys and shimmers between them (the factorization gauge can spin quickly
where scale eigenvalues cross while the composed transform barely moves).

### Physics-Only Reflections

Some NPCs (cn0007, cn0047, cn0109) have negative-determinant rest rotations
only in physics bones (breast, skirt), not the structural skeleton. The
reflection auto-detection would incorrectly switch the whole skeleton to the
MLIB rest-pose approach; `FORCE_TMD_SCALE` in `_npc_config.py` pins these
three to the TMD approach. This is the only per-NPC configuration left.

---

## Playback Fidelity in Godot

Godot's scene importer runs a lossy animation-key optimizer by default,
which can remove a large fraction of keys from smooth tracks (observed: a
61-key track reduced to 12). The committed `.glb.import` files disable it
(`optimizer/enabled=false` under the AnimationPlayer subresource) and bake
at 30 fps to match the authored key rate. If you re-import from scratch,
keep these settings — otherwise animations degrade.

---

## Verification

All 78 NPCs pass three automated checks:

1. **Node-FK parity** — every bone's world position from the exported GLB
   matches a full-track FK oracle within 1 cm, all motions.
2. **Silhouette match** — a Godot screenshot is compared against a software-
   skinned reference render of the same pose (point/pixel hit >= 0.99).
3. **Sub-frame parity** — the imported Godot animation is sampled at
   arbitrary times between key frames and matches the GLB tracks to
   numerical precision; this catches interpolation and import-baking defects
   that on-key checks miss.

Equip attachment (pipe, swords, fan, abacus, books, broom, bucket) verified
visually in the viewer across the fleet.

---

## File Paths

### Export Config

```
tools/avatar_export/scripts/_npc_config.py    # FORCE_TMD_SCALE only
client/assets/npcs/npcs.yaml                  # NPC list for avatar tool viewer
```

### Output

```
client/assets/npcs/models/cn####.glb    # Exported GLB (78 files)
```

