# YTAvatar — Avatar Tool User Guide

The avatar tool is an interactive viewer for the converted Yogurting characters:
dress up the male/female avatar, equip weapons, play animations, and browse the
full monster and NPC fleets.

**Launch:** open `ytavatar/client/project.godot` in Godot 4.6+ and press **F5**
(the main scene is `scenes/avatar_tool.tscn`).

## Modes

The **character dropdown** (top of the panel) switches between four modes:
**Male**, **Female**, **Monster**, **NPC**. The **`** (backtick) key toggles
gender in avatar mode and exits back to the avatar from monster/NPC mode.

## Camera (all modes)

| Input | Action |
|---|---|
| **Left-drag** | Orbit around the model |
| **Two-finger trackpad drag** | Orbit (macOS trackpads) |
| **Mouse wheel** / pinch | Zoom in / out |

In monster/NPC mode the initial camera auto-frames each model; a `zoom:` entry
in `assets/monsters/monsters.yaml` / `assets/npcs/npcs.yaml` overrides it per
model.

## Avatar mode (Male / Female)

Parts cycle through every converted asset for the active gender:

| Key | Next | Previous | Slot |
|---|---|---|---|
| **1** | ✓ | **Q** | Hair |
| **2** | ✓ | **W** | Upper body |
| **3** | ✓ | **E** | Lower body |
| **4** | ✓ | **R** | Hands |
| **5** | ✓ | **T** | Feet |

| Key | Action |
|---|---|
| **F / V** | Next / previous face |
| **6** or **Y** | Equip Blade |
| **7** or **U** | Equip Glorb |
| **8** or **I** | Equip Mura |
| **9** or **O** | Equip Spirit |
| **P** | Unequip weapon |
| **0** | Unequip and remove all parts (base body) |
| **Tab** | Cycle animation mode: T-pose → Basic → Equip (also a dropdown) |
| **Space** | Pause / resume the animation |
| **← / →** | Previous / next animation (in Basic/Equip modes) |
| **`** | Switch gender |

The GUI panel mirrors all of this: part pickers, equipment buttons, an
animation-mode dropdown, and an animation selector.

## Monster / NPC mode

Pick a model with the **`[<]` dropdown `[>]`** selector, or:

| Key | Action |
|---|---|
| **← / →** | Previous / next model |
| **Tab** | Next animation for the current model |
| **Space** | Pause / resume the animation |
| **`** | Back to avatar mode |

135 monsters and 78 NPCs ship with their full animation sets; models are
cached around the current selection so cycling is fast.
