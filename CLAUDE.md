# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Yogurting Revival project, two Godot 4 sub-projects plus their asset pipelines:

- **YTAvatar** — avatar/character viewer: customizable male/female avatars with swappable parts and equipment, plus 135 monster models and 78 NPC models, converted from proprietary binary formats (TMD, MLIB, PRT) to GLTF/GLB.
- **YTLevel** — level/map viewer: the school and early-episode maps converted from proprietary terrain data (QQQ, OCG, CVS, TCG) into Godot scenes, browsable and walkable via an in-game level tool.

## Running the Projects

- Requires **Godot 4.6+**
- Avatar tool: open `ytavatar/client/project.godot`; main scene `ytavatar/client/scenes/avatar_tool.tscn` — press F5
- Level tool: open `ytlevel/client/project.godot`; main scene `ytlevel/client/scenes/level_tool.tscn` — press F5
- User guides (UI + keys): `ytavatar/docs/user-guide.md`, `ytlevel/docs/user-guide.md`
- The Python pipelines under `tools/` have pytest suites (`cd tools/level_export && pytest tests/ -v`, same for `tools/avatar_export`)

## Architecture

### Data Pipeline

Proprietary binary formats are pre-converted to GLB (binary GLTF):
- **TMD** → 3D models (meshes, materials, bones, animations)
- **MLIB** → Animation libraries (skeleton hierarchy, motion clips)
- **PRT** → Swappable body parts (subset meshes)
- **SWP** → Vertex hiding maps for part layering
- **SKL** → Skill scripts (effect/motion/sound/color tracks, decoded by `tools/avatar_export/src/parsers/skl_parser.py`)

Pipeline documentation lives in `ytavatar/docs/` (avatar, monster, and NPC pipeline references).

### Character Composition System

Avatars are assembled from:
- **Base skeleton**: 54-bone male/female rig (`@Root`, `@Pelvis`, `@Spine1-3`, etc.)
- **5 part slots**: Hair, Upper body, Lower body, Hands, Feet — each with multiple swappable variants
- **4 weapon types**: Blade, Glorb, Mura, Spirit — with 20+ variants each
- **Face types**: Switchable with blink animation support

Part metadata (`parts_metadata.json`, `parts_metadata_female.json`) maps which base mesh vertices each part hides.

### Level Pipeline (YTLevel)

`tools/level_export/` converts terrain data from `refs/models/raw/Terrain/` into the level tool's assets:
- **QQQ** → prop placements (quadtree binary, 4x4 transforms), **OCG** → model index, **CVS/TCG** → terrain tile canvas + registry, **WTR** → water, **PLT** → lighting, `{code}_h.bmp` → heightmaps
- Key scripts: `22_export_props.py` (prop GLBs), `30_export_map.py` (map scene assembly), `31_export_terrain.py` (tiles), `34_export_navmesh.py` (navmesh + wall + movement grids), `35_export_heightmaps.py`
- `mapeval/` — evaluation harness: data invariants + Godot rendered-capture detectors
- The shipped level catalog (`ytlevel/client/assets/levels/levels.yaml`/`.json`) is pre-generated data
- Tile texture folders (`ytlevel/client/assets/maps/*/*_tiles/`) are `.gdignore`d on purpose — the runtime loads them raw; do not route them through the Godot importer

### Code Structure

All runtime logic is GDScript under `ytavatar/client/scripts/`:
- `avatar_tool.gd` — Main viewer: character selection, part swapping, equipment, animation controls, Skills dock, orbit camera
- `skill_player.gd` — Plays a `skills.json` entry against a character: effect models, caster motion (by motion id, per gender), sound, color flash, on one 30 fps clock; independent glow loop; bone-anchored effect wrappers
- `skill_catalog.gd` — Read-only wrapper over `skills.json` / `weapons.json` / `bones.json` (skill sets per weapon, families, bone names)
- `test_avatar_parts.gd`, `test_avatar_female.gd` — Standalone avatar test scripts
- `test_monster.gd` — Monster viewer test

Scene: `ytavatar/client/scenes/avatar_tool.tscn`
Tool (WIP): `ytavatar/client/tools/avatar_composer/`

### Asset Organization

```
ytavatar/client/assets/
├── avatars/
│   ├── base/          # Base skeletons + bone_names.json (54 bones) + motion_ids.json
│   ├── parts/         # Male/female swappable parts + metadata JSONs
│   └── weapons/       # blade/, mura/, spirit/ GLB variants
├── effects/           # skills.json + weapons.json + bones.json + models/effects/ (skill-effect GLBs + fade sidecars)
├── sounds/            # combat/skill .wav sound effects
├── monsters/          # monsters.yaml config + models/ + textures/
└── npcs/              # npcs.yaml config + models/ + textures/
```

### Configuration Files

- `monsters.yaml` / `npcs.yaml` — Model registries with optional per-model overrides (zoom, name, bone corrections)
- `bone_names.json` — 54-bone skeleton definition with positions and parent IDs
- `parts_metadata.json` / `parts_metadata_female.json` — Per-part swap-slot data: which base material meshes each part replaces
