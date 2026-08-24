# YTAvatar - Avatar Tools

Avatar, monster, and NPC model export pipeline for Yogurting revival project. 
Converts proprietary game formats (TMD, MLIB, PRT) to GLTF/GLB for Godot 4.

### 1. Open in Godot

Open `client/project.godot` in Godot 4.6. (or above)

## Avatar Tool

The main viewer scene: **`client/scenes/avatar_tool.tscn`**

**→ [Avatar Tool User Guide](docs/user-guide.md)** — all UI and key bindings in one page.

### Character Modes

Select from the top-left dropdown:

| Mode | Description |
|------|-------------|
| **Male** | Male avatar with parts, equipment, face customization |
| **Female** | Female avatar with parts, equipment, face customization |
| **Monster** | Monster model viewer (116 models from `monsters.yaml`) |
| **NPC** | NPC model viewer (78 models from `npcs.yaml`) |

### Avatar Mode (Male / Female)

**Top bar:**
- Character selector (Male/Female/Monster/NPC)
- Animation mode (T-pose / Basic / Equip)
- Animation dropdown + Play/Pause

**Left panel** — swap parts and equipment:
- Hair, Upper, Lower, Hands, Feet (click `<` / `>` to cycle variants)
- Face type
- Equipment: Blade, Glorb, Mura, Spirit

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| `` ` `` | Switch Male/Female |
| Tab | Cycle animation mode (T-pose -> Basic -> Equip) |
| Space | Pause/resume animation |
| Left/Right | Cycle animations |
| 1-5 | Cycle parts forward (hair, upper, lower, hands, feet) |
| Q-T | Cycle parts backward |
| F/V | Cycle face type |
| 6-9 | Equip equipment (blade, glorb, mura, spirit) |
| P | Unequip all |

### Skills

Equipping a weapon (keys **6-9**) switches the avatar into that weapon
style's battle stance and fills the **Skills** dock's *Equipped* tab with
the item's own skill set — basic-attack combo, named skills, and weapon
glow. The *All* tab browses all 742 converted skill scripts with synced
effect models, caster motion, and sound. See the
[user guide](docs/user-guide.md#skills) for details.

### Monster / NPC Mode

**Top bar:**
- Character selector
- Model selector (`<` dropdown `>` — cycle or jump to any model)
- Animation dropdown + Play/Pause

**Left panel** is hidden (no parts/equipment for monsters/NPCs).

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| Left/Right | Cycle models |
| Tab | Cycle animations |
| Space | Pause/resume |
| `` ` `` | Return to Male avatar |

### Camera Controls (All Modes)

| Control | Action |
|---------|--------|
| Left mouse drag | Orbit camera |
| Scroll wheel | Zoom in/out |
| Trackpad pinch | Zoom in/out |

### Config Files

Monster and NPC lists are controlled by YAML config files:

**`client/assets/monsters/monsters.yaml`**
```yaml
monsters:
- id: ct0001
- id: ct0016
  zoom: 13.5    # Camera distance (default: 4.0)
- id: ct0060
  name: Horse   # Display name (default: model ID)
```

**`client/assets/npcs/npcs.yaml`** — same format with `npcs:` key.

