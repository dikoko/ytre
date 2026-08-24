# avatar_export

Python pipeline that converts Yogurting's proprietary game assets — `.TMD` meshes, `.mlib` animation libraries, `.PRT` part meshes, `.SWP` vertex-swap maps, and `.BMP` textures — into GLTF/GLB models for the Godot 4 client under `ytavatar/client/`.

It targets three asset families:

- **Avatar** — male/female base meshes, swappable parts (hair, upper/lower body, hands, feet), weapons, and faces
- **Monsters** — 116 creature models with skeletons and animations
- **NPCs** — 58 NPC models, same TMD + MLIB pipeline as monsters

Pipeline reference docs live in [`ytavatar/docs/`](../../ytavatar/docs/) (`avatar-pipeline-reference.md`, `monster-pipeline-reference.md`, `npc-pipeline-reference.md`).

## Requirements

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) for environment + dependency management

Dependencies are pinned in `pyproject.toml` (`numpy`, `pillow`, `pygltflib`, `pytest`). `uv run …` will materialize the venv on first use.

## Source assets

The pipeline reads from `<repo-root>/refs/models/raw/` (sibling of `tools/`). All scripts derive this path via `Path(__file__).parent.parent.parent.parent / "refs"`, so the layout must look like:

```
ytre/
├── refs/
│   └── models/raw/
│       ├── Avatar.IRD/       # male/female TMD + MLIB + textures, PRT subdirs
│       ├── Monster.IRD/      # ct####.TMD + ct####.mlib + textures
│       ├── NPC.IRD/          # cn####.TMD + cn####.mlib + textures
│       └── Terrain/Object/   # prop TMDs by category
├── ytavatar/client/assets/   # ← export targets land here
└── tools/avatar_export/      # this directory
```

Outputs land in `ytavatar/client/assets/{avatars,monsters,npcs,props}/` (created on demand). Debug viewer GLBs land in `tools/avatar_export/output/`.

## Directory layout

```
tools/avatar_export/
├── pyproject.toml       # uv project config + pytest config
├── scripts/             # runnable pipeline + debug scripts (see below)
├── src/
│   ├── parsers/         # tmd_parser, mlib_parser, swp_parser, skl_parser
│   ├── exporters/       # mesh / skeleton / animation / part / material /
│   │                    # weapon / prop
│   ├── validators/      # mesh + skeleton sanity checks (used by tests)
│   └── debug/           # axis / skeleton / bone-name visualizers
├── tests/               # pytest suite, runs against real `refs/` data
└── output/              # debug-script GLB outputs
```

## Quick start

From `tools/avatar_export/`:

```bash
# Smoke test — produces a small axis-visualization GLB
uv run python scripts/01_debug_axes.py

# Full avatar pipeline (run in order; each writes into ytavatar/client/assets/)
uv run python scripts/10_export_parts.py
uv run python scripts/12_export_textures.py
uv run python scripts/13_export_materials.py
uv run python scripts/14_generate_metadata.py
uv run python scripts/15_export_faces.py
uv run python scripts/16_export_weapons.py

# Monsters and NPCs (independent of the avatar pipeline)
uv run python scripts/20_export_monsters.py
uv run python scripts/21_export_npcs.py

# Motion-id map for the skill system (reads the MLIBs, writes
# ytavatar/client/assets/avatars/base/motion_ids.json)
uv run python scripts/47_export_motion_ids.py
```

The skill and weapon catalogs (`ytavatar/client/assets/effects/skills.json`,
`weapons.json`, `bones.json`) ship pre-generated — their generator depends
on tooling not included here. The `.skl` skill-script parser
(`src/parsers/skl_parser.py`) and its test suite run against the bundled
`refs/` data directly.

## Scripts reference

### Debug / sanity (write to `output/`)

| Script | Purpose |
| --- | --- |
| `01_debug_axes.py` | GLB with procedural ±45° rotation anims on Spine1/Spine2 to verify bone axes |
| `02_debug_skeleton.py` | GLB with 3 cm cubes at each bone position to verify skeleton structure |
| `03_debug_bone_names.py` | JSON of bone names + positions — pair with `debug_skeleton.glb` to identify bones |
| `06_debug_anim.py` | Skeleton cubes + `basic_pick` animation — isolates animation math from mesh skinning |

### Standalone exports (incremental verification, write to `output/`)

| Script | Purpose |
| --- | --- |
| `04_export_mesh.py` | TMD mesh only — no skeleton, no animations |
| `05_export_skeleton.py` | TMD mesh + skeleton binding — no animations |
| `07_export_with_anim.py` | TMD mesh + skeleton + a curated set of animations |
| `08_export_full.py` | TMD mesh + skeleton + **all** MLIB animations |

### Avatar production pipeline (write to `ytavatar/client/assets/avatars/`)

| Script | Purpose |
| --- | --- |
| `10_export_parts.py` | Convert PRT files (hair, upper, lower, hands, feet — male + female) to GLB |
| `12_export_textures.py` | Copy avatar base + part textures into Godot assets |
| `13_export_materials.py` | Export base mesh split by material index (for correct UV mapping) |
| `14_generate_metadata.py` | Generate `parts_metadata.json` — per-part swap slots (base meshes each part replaces) |
| `15_export_faces.py` | Copy face textures (with blink-frame variants) into Godot assets |
| `16_export_weapons.py` | Convert weapon PRT files to GLB and copy weapon textures |

### Monster / NPC / prop pipeline

| Script | Purpose |
| --- | --- |
| `20_export_monsters.py` | Export all monster TMD+MLIB pairs to GLB with embedded BMP→PNG textures |
| `21_export_npcs.py` | Same pipeline for NPCs; uses `_npc_config.py` for per-model overrides |
| `tweak_test.py` | Iterate on NPC/monster bone tweaks — exports model variants for inspection in Godot |
| `validate_map_positions.py` | Plot QQQ object positions over an OPG minimap to validate map data |

### Shared modules

| File | Purpose |
| --- | --- |
| `_export_common.py` | TMD+MLIB export logic + texture embedding + per-bone tweak application — used by monster, NPC, and tweak scripts |
| `_npc_config.py` | Per-NPC overrides: `FORCE_TMD_SCALE`, `SKIP_REPARENT`, `SMOOTH_BONES`, `EQUIP_CORRECTION`, `BONE_TWEAKS` |
| `_prop_config.py` | Prop categories (Artificial / Nature / Structure / …) and source/output paths |

## Tests

```bash
uv run pytest                # full suite (~27s, 91 tests)
uv run pytest -q             # quiet
uv run pytest tests/test_tmd_parser.py        # one file
uv run pytest -k skeleton    # by keyword
```

Tests load real assets from `refs/models/raw/Avatar.IRD/` and `refs/models/raw/Monster.IRD/`, so they require the `refs/` tree to be in place. There is no mocking layer.

## Notes

- All path constants resolve relative to `__file__`, so scripts work regardless of the shell's working directory.
- Numbered prefixes (`01_`, `04_`, `10_`, `20_`) indicate logical pipeline order, not strict dependencies — most scripts are independently runnable once `refs/` is populated.
- Re-running an export overwrites the prior GLB; outputs are deterministic given the same source assets.
