# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**YTAvatar** is a Godot 4 avatar/character viewer and asset pipeline tool for the Yogurting Revival project. It displays customizable male/female avatars with swappable parts and equipment, plus 116 monster models and 58 NPC models — all converted from proprietary binary formats (TMD, MLIB, PRT) to GLTF/GLB.

## Running the Project

- Requires **Godot 4.6+**
- Open `ytavatar/client/project.godot` in the Godot editor
- Main scene: `ytavatar/client/scenes/avatar_tool.tscn` — press F5 to run
- No build step, package manager, or test framework — testing is visual/manual in the editor

## Architecture

### Data Pipeline

Proprietary binary formats are pre-converted to GLB (binary GLTF):
- **TMD** → 3D models (meshes, materials, bones, animations)
- **MLIB** → Animation libraries (skeleton hierarchy, motion clips)
- **PRT** → Swappable body parts (subset meshes)
- **SWP** → Vertex hiding maps for part layering

Pipeline documentation lives in `ytavatar/docs/` (avatar, monster, and NPC pipeline references).

### Character Composition System

Avatars are assembled from:
- **Base skeleton**: 54-bone male/female rig (`@Root`, `@Pelvis`, `@Spine1-3`, etc.)
- **5 part slots**: Hair, Upper body, Lower body, Hands, Feet — each with multiple swappable variants
- **4 weapon types**: Blade, Glorb, Mura, Spirit — with 20+ variants each
- **Face types**: Switchable with blink animation support

Part metadata (`parts_metadata.json`, `parts_metadata_female.json`) maps which base mesh vertices each part hides.

### Code Structure

All runtime logic is GDScript under `ytavatar/client/scripts/`:
- `avatar_tool.gd` (2,215 LOC) — Main viewer: character selection, part swapping, equipment, animation controls, orbit camera
- `test_avatar_parts.gd`, `test_avatar_female.gd` — Standalone avatar test scripts
- `test_monster.gd` — Monster viewer test

Scene: `ytavatar/client/scenes/avatar_tool.tscn`
Tool (WIP): `ytavatar/client/tools/avatar_composer/`

### Asset Organization

```
ytavatar/client/assets/
├── avatars/
│   ├── base/          # Base skeletons + bone_names.json (54 bones)
│   ├── parts/         # Male/female swappable parts + metadata JSONs
│   └── weapons/       # blade/, mura/, spirit/ GLB variants
├── monsters/          # monsters.yaml config + models/ + textures/
└── npcs/              # npcs.yaml config + models/ + textures/
```

### Configuration Files

- `monsters.yaml` / `npcs.yaml` — Model registries with optional per-model overrides (zoom, name, bone corrections)
- `bone_names.json` — 54-bone skeleton definition with positions and parent IDs
- `parts_metadata.json` / `parts_metadata_female.json` — Part-to-vertex-region hiding maps
