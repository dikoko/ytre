# Addon Integration Guide

How to use the YTAvatar, YTMonster, and YTNPC addons in your Godot 4 project.

## Quick Start

### 1. Copy the addon

Copy the addon folder into your project's `addons/` directory:

```
your_project/
├── addons/
│   ├── ytavatar/       # Avatar characters (parts, equipment, face)
│   ├── ytmonster/      # Monster characters
│   └── ytnpc/          # NPC characters
```

### 2. Copy the assets

Each addon needs its corresponding assets. Copy them to your project (default paths shown):

| Addon | Assets source | Default path in your project |
|-------|--------------|------------------------------|
| ytavatar | `client/assets/avatars/` | `res://assets/avatars/` |
| ytmonster | `client/assets/monsters/` | `res://assets/monsters/` |
| ytnpc | `client/assets/npcs/` | `res://assets/npcs/` |

You can place assets anywhere — set the `assets_path` export on each node to match.

### 3. Enable the plugin (optional)

In Godot: **Project > Project Settings > Plugins** — enable the addon. This registers the custom node type so it appears in the **Add Node** dialog.

If you skip this step, the `class_name` declarations still make `AvatarCharacter`, `MonsterCharacter`, and `NPCCharacter` available globally for scripting and scenes.

---

## AvatarCharacter

A fully-featured avatar with swappable parts, equipment, face types with blink animation, and skin color.

### Asset structure

```
{assets_path}/
├── base/
│   ├── male_base_materials.glb
│   └── female_base_materials.glb
├── parts/
│   ├── male/           # male_hair_M0101.glb, male_upper_M0001.glb, ...
│   ├── female/         # female_hair_F0101.glb, ...
│   ├── parts_metadata.json
│   └── parts_metadata_female.json
├── textures/
│   ├── base/           # male_upper_M0000.tga, ...
│   ├── parts/          # male_hair_M0101.tga, ...
│   ├── weapons/        # weapon_blade_A0001.bmp, ...
│   └── faces/          # male_face_M0010.tga, ...
└── weapons/
    ├── blade/          # weapon_blade_A0001.glb, ...
    ├── mura/           # weapon_mura_A0001.glb, ...
    └── spirit/         # weapon_spirit_A0001.glb, ...
```

### Inspector setup

Add an `AvatarCharacter` node to your scene and configure in the inspector:

| Property | Example | Description |
|----------|---------|-------------|
| `assets_path` | `res://assets/avatars/` | Root path to avatar assets |
| `gender` | `male` or `female` | Character gender |
| `hair_variant` | `M0101` | Hair part variant code |
| `upper_variant` | `M0001` | Upper body part |
| `lower_variant` | `M0001` | Lower body part |
| `hands_variant` | `M0004` | Hands part |
| `feet_variant` | `M0001` | Feet part |
| `face_type` | `0` | Face type index |
| `skin_color` | `Color(0.99, 0.81, 0.64)` | Skin color applied to all shaders |
| `equipment_type` | `blade` | `blade`, `glorb`, `mura`, `spirit`, or empty |
| `equipment_variant` | `A0001` | Weapon variant code |
| `default_animation` | `basic_stand` | Animation to play on load |
| `blink_enabled` | `true` | Automatic blink animation |

### Scripting API

```gdscript
# Get reference
@onready var avatar: AvatarCharacter = $Avatar

# Gender
avatar.set_gender("female")          # Rebuilds entire avatar

# Parts — variant codes like "M0101", "F0301"
avatar.set_part("hair", "M0101")
avatar.set_part("upper", "M0001")
avatar.remove_part("hair")
avatar.remove_all_parts()

# Equipment
avatar.equip_weapon("blade", "A0001")   # Sword on @Sword bone
avatar.equip_weapon("mura", "A0001")    # Shield on @Head bone
avatar.equip_weapon("spirit", "A0001")  # Staff on @Spine3 bone
avatar.equip_weapon("glorb", "A0001")   # Hand replacement (removes hands part)
avatar.unequip_weapon()

# Face
avatar.set_face(3)                       # Face type by index
avatar.set_skin_color(Color(0.87, 0.66, 0.48))

# Animation
avatar.play_animation("basic_stand")
avatar.pause_animation()
avatar.resume_animation()
avatar.stop_animation()                  # Stops and resets to bind pose
var anims = avatar.get_animation_list()  # All animations
var anims = avatar.get_animation_list("blade")  # Filtered by prefix

# State save/restore
var state = avatar.get_current_state()   # Returns Dictionary
avatar.load_state(state)                 # Restores from Dictionary
```

### Signals

```gdscript
avatar.part_changed.connect(func(slot, variant): print(slot, " -> ", variant))
avatar.equipment_changed.connect(func(type, variant): print(type, " ", variant))
avatar.animation_started.connect(func(name): print("Playing: ", name))
avatar.animation_finished.connect(func(name): print("Finished: ", name))
avatar.gender_changed.connect(func(gender): print("Gender: ", gender))
```

### Variant code convention

Parts use short codes that map to filenames based on gender:

| Call | Loads |
|------|-------|
| `set_part("hair", "M0101")` on male | `male_hair_M0101.glb` |
| `set_part("hair", "F0301")` on female | `female_hair_F0301.glb` |
| `equip_weapon("blade", "A0001")` | `weapon_blade_A0001.glb` |
| `equip_weapon("glorb", "A0001")` on male | `male_glorb_A0001.glb` |

### Runtime instantiation

```gdscript
var avatar = AvatarCharacter.new()
avatar.gender = "female"
avatar.hair_variant = "F0101"
avatar.upper_variant = "F0001"
avatar.lower_variant = "F0001"
avatar.default_animation = "febasic_stand"
add_child(avatar)
```

---

## MonsterCharacter

Displays a single monster from a self-contained GLB file.

### Asset structure

```
{assets_path}/
└── models/
    ├── ct0001.glb
    ├── ct0002.glb
    └── ...            # 116 monster GLBs
```

Each GLB contains mesh, skeleton, animations, and embedded textures.

### Inspector setup

| Property | Example | Description |
|----------|---------|-------------|
| `assets_path` | `res://assets/monsters/` | Root path to monster assets |
| `monster_id` | `ct0001` | Monster to load |
| `auto_play` | `stand` | Auto-play first animation containing this string |

### Scripting API

```gdscript
@onready var monster: MonsterCharacter = $Monster

# Load / swap
monster.set_monster("ct0039")
monster.clear_monster()
var id = monster.get_monster_id()

# Animation
monster.play_animation("attack")         # Loops by default
monster.play_animation("death", false)   # One-shot (emits animation_finished)
monster.pause_animation()
monster.resume_animation()
monster.stop_animation()
var anims = monster.get_animation_list()
var current = monster.get_current_animation()

# Skeleton access (for BoneAttachment3D, particles, etc.)
var skel = monster.get_skeleton()
```

### Signals

```gdscript
monster.monster_loaded.connect(func(id): print("Loaded: ", id))
monster.monster_cleared.connect(func(): print("Cleared"))
monster.animation_started.connect(func(name): print("Playing: ", name))
monster.animation_finished.connect(func(name): print("Finished: ", name))
```

### Runtime instantiation

```gdscript
var monster = MonsterCharacter.new()
monster.monster_id = "ct0039"
monster.auto_play = "walk"
add_child(monster)
```

---

## NPCCharacter

Identical API to MonsterCharacter, with `npc_id` / `set_npc()` / `clear_npc()` naming.

### Asset structure

```
{assets_path}/
└── models/
    ├── cn0001.glb
    ├── cn0002.glb
    └── ...            # 78 NPC GLBs
```

### Inspector setup

| Property | Example | Description |
|----------|---------|-------------|
| `assets_path` | `res://assets/npcs/` | Root path to NPC assets |
| `npc_id` | `cn0001` | NPC to load |
| `auto_play` | `stand` | Auto-play animation |

### Scripting API

```gdscript
@onready var npc: NPCCharacter = $NPC

npc.set_npc("cn0043")
npc.play_animation("walk")
npc.clear_npc()
# ... same animation API as MonsterCharacter
```

### Signals

```gdscript
npc.npc_loaded.connect(func(id): print("Loaded: ", id))
npc.npc_cleared.connect(func(): print("Cleared"))
```

---

## Example: Game level with multiple characters

```gdscript
extends Node3D

func _ready():
    # Player avatar
    var player = AvatarCharacter.new()
    player.gender = "male"
    player.hair_variant = "M0301"
    player.upper_variant = "M0011"
    player.lower_variant = "M0011"
    player.hands_variant = "M0004"
    player.feet_variant = "M0001"
    player.default_animation = "basic_stand"
    player.position = Vector3(0, 0, 0)
    add_child(player)

    # NPC shopkeeper
    var shopkeeper = NPCCharacter.new()
    shopkeeper.npc_id = "cn0043"
    shopkeeper.position = Vector3(3, 0, 0)
    add_child(shopkeeper)

    # Monster enemy
    var enemy = MonsterCharacter.new()
    enemy.monster_id = "ct0039"
    enemy.auto_play = "walk"
    enemy.position = Vector3(-3, 0, 2)
    add_child(enemy)

    # Equip the player later
    player.equip_weapon("blade", "A0001")
    player.play_animation("blade_stand")
```

## Reference

- `client/scripts/avatar_tool.gd` — Full viewer using all three addons as a consumer reference
- `client/scripts/test_avatar_character.gd` — Multi-avatar test scene with keyboard controls
- `docs/superpowers/specs/2026-03-22-monster-character-addon-design.md` — MonsterCharacter design spec
