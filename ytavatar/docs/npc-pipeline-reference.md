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
| Per-model config | Minimal (zoom, 3 corrections) | Extensive (tweaks per NPC) |
| Equip reparenting | Not used | Auto-detected + manual tweaks |
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

## Equip Bone Reparenting

### Problem

Many NPC equip bones (sword, broom, book) are parented to `@Root` or `@Spine3` in the TMD hierarchy instead of the hand bone. The original engine positions these through precise rotation-only animation, but small quaternion differences in GLTF cause the equip to drift from the hand.

### Solution

Auto-detect equip chain roots and reparent them to the nearest hand bone:

1. **Detection**: Bones matching `_EQUIP_BONE_PREFIXES` that are NOT already on a hand chain
2. **Skip**: Bones parented to `@Pelvis` (back-mounted) or `@Head` (head-mounted)
3. **Chain roots only**: If a bone's ancestor is already reparented, skip it
4. **Skeleton**: Change parent in GLTF node hierarchy
5. **Animation**: FK rotation (local rot relative to new hand parent) + bind-pose translation offset

---

### Alternative: Blender Refinement

For complex positioning that's hard to dial in with the export tweak tool, import the GLB into Blender and adjust bone transforms visually in pose mode, then re-export. This is recommended for cases like cn0040 (broom) where the local-space axes don't align intuitively with world directions.

---

## Known Issues

### Equip Detachment During Walk

Several NPCs have equips that look correct in stand/idle but detach during walk/move animations. This is caused by accumulated rotation errors in the parent chain (hand → forearm → arm) that compound differently between the original engine and our GLTF export. Constant position/rotation tweaks fix the stand pose but can't account for per-frame variation.

**Affected**: cn0007 (pipe), cn0021 (abacus), cn0009 (sword)

**Workaround**: Accept minor walk detachment. NPCs primarily stand in the game.

### Spine-Chain Weapon Positioning

cn0009's sword is parented to `@Spine3 → @FixBlade → @Sword` and swings between hands during idle animations. This rotation-based positioning can't be perfectly replicated in GLTF due to quaternion precision differences. Reparenting breaks back-mounted swords.

**Status**: Known limitation, recorded as acceptable.

### Physics-Only Reflections

Some NPCs (cn0007, cn0047, cn0109) have negative determinant rotation matrices only in physics bones (breast, skirt), not structural skeleton. The reflection auto-detection incorrectly triggers MLIB approach for the entire skeleton.

**Fix**: Add to `FORCE_TMD_SCALE` in `_npc_config.py`.

### Generic Bone Names

Some NPCs use `Bone##` and `connectBone##` for physics chains (cn0007 breast ribbons) AND structural skeleton (cn0090). Physics bone smoothing by prefix can't safely use `"Bone"` as a prefix.

**Fix**: Use `smooth_bone_indices` with explicit TMD bone indices per model.

---

## Verification Status

### Batch 1 (cn0001–cn0047): Verified

| Status | Count | NPCs |
|--------|-------|------|
| OK | 28 | Most NPCs look good |
| WD (weapon detach) | 9 | cn0009, cn0011, cn0021, cn0024, cn0039, cn0040, cn0042, cn0043, cn0045 |
| AP (animation pop) | 2 | cn0007 (breast), cn0038 (cape — FIXED) |
| BN (broken mesh) | 1 | cn0014 (leg) |

All WD issues addressed with equip correction + bone tweaks. cn0042/cn0043 books work perfectly with reparenting.

### Batch 2 (cn0048–cn0110): Partially Verified

Reported issues:
- cn0047: T-pose fixed (force_tmd_scale), cup detached (known limitation)
- cn0049: Book reparented to hand
- cn0062: Sword on pelvis (back-mounted, intentional)
- cn0069: Cigarette on head (skip reparent for @Head)
- cn0076: Bucket reparented to hand
- cn0109: T-pose fixed (force_tmd_scale)

---

## File Paths

### Export Config

```
tools/avatar_export/scripts/_npc_config.py    # Per-NPC tweaks
client/assets/npcs/npcs.yaml                  # NPC list for avatar tool viewer
```

### Output

```
client/assets/npcs/models/cn####.glb    # Exported GLB (78 files)
```

