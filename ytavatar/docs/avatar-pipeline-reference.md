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

Binary format driving the part-swap system. The original client swaps
whole meshes by slot: every base-body material mesh is a swap slot, and
each part's entry lists the slots the part replaces. Equipping removes
those base meshes entirely (nothing is hidden per-vertex); slots left
uncovered fall back to the naked default pieces named in the header
table. Entries also carry authored seam-weld normals: part-vertex
indices whose normals are replaced at equip time so boundary shading
matches the base body.

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
  ├── def_data: list[DefData]           (slot -> naked default part table)
  └── swp_data: list[SwpData]           (one entry per part)
        ├── swp_id[mesh]: list[int]     (base slots this part mesh replaces)
        ├── clone_idx/clone_nor[mesh]   (seam-weld: part vertex indices +
        │                                authored replacement normals)
        └── tmd_name / obj_name
```

Slot ID == base TMD material index. NOTE: the male and female base
models order their slots differently (male slot 0 = upper, 5 = lower;
female slot 0 = lower, 5 = upper) — always derive the mapping from the
base TMD's material order. Shipped weld counts can exceed the format's
fixed 50-entry per-mesh rows; the values continue row-major into the
next row (read them with flat indexing, exactly as the game does).

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

### Swap Slots (8 per gender)

The base body is split into 8 material meshes; each is one swap slot.
Parts replace whole slots (from their SWP entries), e.g. a sleeveless
shirt replaces only `upper` while a long coat replaces `upper` + `arm`;
thigh-high boots replace `foot` + `leg`.

| Slot (male) | Slot (female) | Material mesh |
|------|------|------|
| 0 | 5 | upper (default top + torso/neck skin) |
| 1 | 1 | arm |
| 2 | 2 | foot |
| 3 | 3 | hand |
| 4 | 4 | leg |
| 5 | 0 | lower (default bottom) |
| 6 | 6 | hair (viewer splits into scalp cap + strands) |
| 7 | 7 | face |

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

## Coordinate Conventions (left-handed source -> right-handed glTF)

The game's renderer is a left-handed Direct3D pipeline that draws the
authored data verbatim. Importing that data unchanged into right-handed
glTF/Godot renders every model left-right mirrored (visible on clothing
text). All character exporters therefore apply one coherent Z-mirror:

| Component | Conversion |
|-----------|------------|
| Positions / normals | `(x, y, -z)` |
| Triangle winding | reversed `(v0, v2, v1)` |
| Rig transforms / IBMs | conjugated by `S = diag(1, 1, -1)`: matrices `S*M*S` |
| Quaternions | `(x, y, z, w) -> (-x, -y, z, w)` |
| Translations (bind + tracks) | `(x, y, -z)` |
| Weapon bone-local vertices | `(x, y, -z)` |
| Quaternion (MLIB) | `[w, x, y, z] -> [x, y, z, w]` reorder |

Models face -Z after conversion; viewers rotate them PI about Y to face
the camera. The mirror must be applied to EVERY factor coherently
(mesh, bind pose, inverse bind matrices, all animation tracks) or
skinning breaks — mirroring only the mesh is how the old
"X-negation broke skinning" conclusion came about.

**UV V-flip**: Only `skeleton_exporter` applies V-flip (`v = 1.0 - v`). Part exporter, material exporter, and weapon exporter do NOT flip.

---

## Parts System

### Part Loading in Godot

1. Load GLB as PackedScene
2. Find MeshInstance3D in scene
3. Reparent mesh to shared Skeleton3D (remove from part's own skeleton)
4. Restore skin reference (bone names must match)
5. Apply texture material (skin-blend shader; hair variant is two-sided)
6. Hide exactly the base material meshes the part's swap slots replace
   (`hides_materials` in the parts metadata)

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

## Materials & Lighting (viewer)

### Skin tone: alpha-mask blend

The original engine colors avatar skin by blending a 1x1 skin-color
texture into every part material, using the part texture's ALPHA channel
as a smooth mask: `rgb = mix(skin_color, tex.rgb, tex.a)`, then the
lighting modulate. In the avatar pass alpha means "skin", never
transparency (hair strands are geometry). Hard alpha thresholds turn the
authored feathering (hairlines, armholes) into visible seam lines — keep
the blend smooth. Default tones are authored per gender (the flat fills
of the base-body textures): male (253, 207, 162), female (255, 221, 183).

### Portrait lighting: fixed-function, gamma space

Character shading replicates the original fixed-function rig in gamma
space (unshaded shader, per-vertex diffuse): material ambient 0.7 x
(world ambient 0.502 + light ambient 0.1) + 0.5 * max(N.L, 0), one
directional light direction (-1, -0.5, -3), specular disabled. Ambient
dominance visually welds most part-boundary normal differences; the SWP
weld normals handle the rest.

---

## File Paths & Naming

### Output Files (client/)

```
client/assets/avatars/
├── base/
│   ├── male_base_materials.glb       # Material-split base + 223 anims
│   └── female_base_materials.glb     # Female base + animations
├── parts/
│   ├── male/male_*.glb               # Skinned part GLBs (weld normals baked)
│   ├── female/female_*.glb           # Female part GLBs
│   ├── parts_metadata.json           # Per-part swap-slot data (male)
│   └── parts_metadata_female.json    # Per-part swap-slot data (female)
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
- Female parts: `female_{type}_F{NNNN}.PRT`
- Weapons: `weapon_{type}_A{NNNN}.PRT` (A-prefix = shared, NNNN = variant)
- A0xxx = base variants, A1xxx = upgraded/alternate variants

---

