# Avatar Export Pipeline Reference

Technical reference for the Yogurting avatar tools. 

---

## File Formats

### TMD (3D Model)

Binary format storing meshes, materials, bones, and animations.

- **Version**: `0x20041124`
- **Contains**: objects (geometry/bone/dummy), materials, bone hierarchy, mesh skinning data, keyframe animations
- **Chunk-based**: mesh (`0x3411`), skinning (`0x341A`/`0x341B`), bones (`0x3800`), animations (`0x6000+`)

### MLIB (Animation Library)

Binary format storing skeleton hierarchy and animation motions.

- **Header magic**: `0x2385ADCE` (extended) or `0x2385ADBF` (old)
- **Contains**: bone list with parent IDs, motion clips with per-bone rotations/translations
- **Motion types**:
  - `0` basic — rotations only
  - `1` extended — rotations + per-bone translations
  - `2` extended — + scales
  - `3` extended — + scale axes
  - `4` keyframe tracks — per-bone rotation/translation/scale keys

### PRT (Part)

Same binary format as TMD. Contains a subset mesh (hair, clothing, weapon) with optional skinning. Parsed by `TMDParser`.

### SWP (Swap Mapping)

Binary format mapping part files to base mesh vertex indices. Used to determine which base mesh vertices a part hides.

---

## File Formats 

### TMD

**Key data structures:**

```
TMDModel
  ├── version, total_frames, frame_speed, ticks_per_frame
  ├── materials: list[TMDMaterial]
  │     └── texture_filename, ambient/diffuse/specular, two_sided, alpha_map
  ├── objects: list[TMDObject]
  │     ├── object_id, name, object_type (geometry/bone/dummy)
  │     ├── world_transform: Transform (rotation Matrix3x3 + translation Vector3)
  │     ├── local_transform: Transform
  │     └── mesh: TMDMesh (optional)
  │           ├── vertices, normals, uvs: list[Vector3/Vector2]
  │           ├── faces: list[tuple[int,int,int]]
  │           ├── vertex_skinning: dict[int, list[(bone_idx, weight)]]
  │           │     └── bone indices are MLIB indices
  │           └── vertex_materials: dict[int, int]
  ├── bones: list[TMDBone]
  │     ├── name, object_id, parent_id
  │     ├── world_transform, local_transform
  │     └── (world_transform.rotation stored row-major, needs .T for column-major)
  └── animations: list[TMDAnimation]
```

**Transform convention**: `Matrix3x3.data` is row-major. Use `np.array(data).reshape(3,3).T` to get usable column-major rotation matrix.

### MLIB

```
MLIBFile
  ├── bones: list[MLIBBone]
  │     └── name, parent_id, position (Vector3)
  ├── motions: list[MLIBMotion]
  │     ├── name, motion_type, frame_count, bone_count, fps, option
  │     ├── root_positions: list[Vector3]  (per-frame root movement)
  │     ├── rotations: list[list[Quaternion]]  ([frame][bone])
  │     ├── translations: list[list[Vector3]]  (MotionEx types only)
  │     └── scales: list[list[Vector3]]  (MotionEx2+ only)
  └── ground_vector
```

### SWP (Parts Swap file)


```
SWPFile
  └── swp_data: list[SwpData]
        └── clone_idx: list[int]  (vertex indices in base mesh hidden by this part)
```

---

## Skeleton & Bones

### Bone List (54 bones, male.TMD)

```
[0]  @Root           [1]  @Pelvis         [2]  @Spine1         [3]  @Spine2
[4]  @Spine3         [5]  @Neck           [6]  @Head
[7]  @Hair01B        [8]  @Hair02B        [9]  @Hair01RF       [10] @Hair00RF
[11] @Hair01LF       [12] @Hair00LF
[13] @ClavicleL      [14] @Arm1L          [15] @Arm2L          [16] @HandL
[17] @Finger1L       [18] @Finger2L       [19] @Finger3L       [20] @Finger4L
[21] @ClavicleR      [22] @Arm1R          [23] @Arm2R          [24] @HandR
[25] @Finger1R       [26] @Finger2R       [27] @Finger3R       [28] @Finger4R
[29] @Sword
[30] @Leg1L          [31] @Leg2L          [32] @FootL          [33] @ToeL
[34] @Leg1R          [35] @Leg2R          [36] @FootR          [37] @ToeR
[38] @Skirt01RF      [39] @Skirt02RF      [40] @Skirt03RF      [41] @Skirt00RF
[42] @Skirt01LB      [43] @Skirt02LB      [44] @Skirt03LB      [45] @Skirt00LB
[46] @Skirt01RB      [47] @Skirt02RB      [48] @Skirt03RB      [49] @Skirt00RB
[50] @Skirt01LF      [51] @Skirt02LF      [52] @Skirt03LF      [53] @Skirt00LF
```

### Body Regions (12 regions)

| Region | Bones | Hidden By |
|--------|-------|-----------|
| HEAD | @Head, @Hair0* | — (always visible) |
| HAIR_SCALP | (material 6, near center) | Hair parts |
| HAIR_STRANDS | (material 6, outer) | Hair parts |
| NECK | @Neck | Upper parts |
| ARM_UPPER | @ClavicleL/R, @Arm1L/R | Upper parts (long sleeves) |
| FOREARM | @Arm2L/R | Upper parts (long sleeves) |
| HAND | @HandL/R, @Finger*L/R | Hand parts |
| TORSO | @Spine1-3 | Upper parts |
| WAIST | @Pelvis, @Skirt* | Lower parts |
| LEG_UPPER | @Leg1L/R | Lower parts |
| LEG_LOWER | @Leg2L/R | Lower parts (long pants) |
| FOOT | @FootL/R, @ToeL/R | Foot parts |

### Bone Hierarchy Construction

- **MLIB** provides the authoritative parent-child hierarchy via `parent_id`
- **TMD** provides world-space transforms for each bone
- Local transforms computed: `local_pos = parent_R_inv * (child_world_pos - parent_world_pos)`
- Local rotation: `local_rot = parent_rot_inv * child_world_rot`

### Inverse Bind Matrices

Computed from TMD bone world transforms:
```python
R = bone.world_transform.rotation  # 3x3 column-major after .T
t = bone.world_transform.translation
IBM = [R^T | -R^T * t]  # 4x4, stored column-major for GLTF
```

### Bone Index Mapping

- PRT meshes store skinning with **MLIB bone indices**. 
- The skeleton in exported GLBs uses **TMD bone order**. 
- Remapping is done by matching bone names between MLIB and TMD.

---

## Coordinate Conventions

| Component | TMD/PRT Format | GLTF Output | Notes |
|-----------|---------------|-------------|-------|
| Positions | [x, y, z] | [x, y, z] | No conversion needed |
| Normals | [x, y, z] | [x, y, z] | No conversion needed |
| UVs | [u, v] | [u, v] | No V-flip in part/material exporters |
| Face winding | CCW | CCW | Original winding preserved |
| Quaternion (TMD) | [x, y, z, w] | [x, y, z, w] | Same order |
| Quaternion (MLIB) | [w, x, y, z] | [x, y, z, w] | Reorder needed |
| X-negation | — | — | NOT applied anywhere |

**Critical**: X-negation was removed from all exporters. It broke skinning because vertices ended up in a different coordinate space than the skeleton/IBMs.

**UV V-flip**: Only `skeleton_exporter` applies V-flip (`v = 1.0 - v`). Part exporter, material exporter, and weapon exporter do NOT flip.

---

## Parts System

### Part Loading in Godot

1. Load GLB as PackedScene
2. Find MeshInstance3D in scene
3. Reparent mesh to shared Skeleton3D (remove from part's own skeleton)
4. Restore skin reference (bone names must match)
5. Apply texture material (hair shader or clothing alpha shader)
6. Update base mesh material visibility based on regions hidden

---

## Equipment System

### Equipment Types

| Type | Key | Mechanism | Bone | Variants |
|------|-----|-----------|------|----------|
| Blade | 6/Y | BoneAttachment3D (static mesh) | @Sword | 27 |
| Glorb | 7/U | Skinned part (_swap_part) | skeleton | 26 |
| Mura | 8/I | BoneAttachment3D (static mesh) | @Head | 24 |
| Spirit | 9/O | BoneAttachment3D (static mesh) | @Spine3 | 23 |

### Weapon Attachment (Blade, Mura, Spirit)

Weapons are static meshes with no bones or skinning. Vertices are pre-transformed to bone-local space at export time. In Godot:

1. Create `BoneAttachment3D` with target `bone_name`
2. Add as child of `Skeleton3D`
3. Instantiate weapon GLB as child of BoneAttachment3D
4. Apply texture material
5. Hide trail anchor meshes (blade_low, blade_high) if present

### Weapon-specific Notes

**Blades**: 3 objects per GLB (weapon mesh + blade_low + blade_high trail anchors). All share `local_t = [1.166, -0.012, 0.572]` — includes grip alignment offset. Trail anchors hidden in Godot.

**Muras**: 1 object per GLB. Headphone-style accessories. All share `local_t = [-1.262, 0, 0.201]`. Exported with `use_local_transform=True`.

**Spirits**: 1 object per GLB. Backpack-style accessories. Exported with `use_local_transform=True` on `@Spine3`. Two variants excluded (A0019, A1019) — different local_transform, mispositioned.

### Glorb (Body Part Equipment)

Glorbs are skinned parts (not static weapons). They use the existing part system:
- Loaded via `_swap_part("glorb", index)`
- Mutually exclusive with hands parts
- Equipping glorb removes hands; equipping hands removes glorb

### Animation Filtering by Equipment

Each equipment type restricts which animations play:

```
NONE:   ["basic"]
BLADE:  ["basic", "blade"]
GLORB:  ["basic", "glorb"]
MURA:   ["basic", "mura"]
SPIRIT: ["basic", "spirit"]
```

Animations whose name starts with any listed prefix are available.

---

## Animation System

### MLIB Animation Catalog (223 animations, male)

Categories by prefix:
- `basic_*` — idle, walk, run, jump, sit, emotes
- `blade_*` — sword attacks, skills
- `glorb_*` — gauntlet attacks, skills
- `mura_*` — mura attacks, skills
- `spirit_*` — spirit attacks, skills

### Animation Mode in Godot

- Toggle with Tab key
- Starts playing `basic_stand`
- Left/Right arrows cycle through filtered animation list
- Space pauses/resumes
- Equipment type filters available animations

---

## File Paths & Naming

### Output Files (client/)

```
client/assets/avatars/
├── base/
│   └── male_base_materials.glb       # Material-split base + 223 anims
├── parts/
│   ├── male/male_*.glb               # Skinned part GLBs
│   └── parts_metadata.json           # Region/visibility metadata
├── weapons/
│   ├── blade/weapon_blade_*.glb      # 27 blade GLBs
│   ├── mura/weapon_mura_*.glb        # 24 mura GLBs
│   └── spirit/weapon_spirit_*.glb    # 23 spirit GLBs
└── textures/
    ├── base/                          # Base mesh textures
    ├── parts/                         # Part textures (.tga/.bmp)
    ├── faces/                         # Face textures
    └── weapons/                       # Weapon textures (.bmp/.tga)
```

### Naming Conventions

- Male parts: `male_{type}_M{NNNN}.PRT` (M-prefix = male, NNNN = variant)
- Weapons: `weapon_{type}_A{NNNN}.PRT` (A-prefix = shared, NNNN = variant)
- A0xxx = base variants, A1xxx = upgraded/alternate variants
- Female parts would follow: `female_{type}_F{NNNN}.PRT`

---

