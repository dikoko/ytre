# YTLevel - Level Tools

Level/map viewer and export pipeline for the Yogurting revival project.
Converts the game's proprietary terrain data (QQQ, OCG, CVS, TCG) and prop
models (TMD) into Godot 4 scenes, browsable and walkable through an in-game
level tool.

### 1. Open in Godot

Open `client/project.godot` in Godot 4.6 (or above) and press F5.

The main scene is **`client/scenes/level_tool.tscn`** — pick a school or
episode, fly around with the explore camera, click portals to travel, or press
**Tab** to walk the map in Run mode.

> **Note:** many levels are not fully tested yet. The main school campus maps
> have been checked in depth, but on less-traveled maps you may still hit
> visual glitches (missing or misplaced props, lighting quirks, terrain seams)
> or rough Run-mode ground contact. Issue reports are welcome.

**→ [Level Tool User Guide](docs/user-guide.md)** — all UI and key bindings.

## What ships here

- **Map scenes** for the school maps and the first episode
  (`client/scenes/maps/`, assets under `client/assets/maps/`): terrain with
  the original tile textures, ~5,200 placed props, water surfaces and beach
  shore-waves, fixed-function sun and point lighting, and per-map
  navigation data for Run mode (navigation mesh, wall grid, and the
  movement grid — the same walkability data the original game used).
- **1,576 prop models** (`client/assets/props/`) exported from TMD with
  embedded textures — 187 of them with their authored keyframe animation
  (looping fires, portals, crystals) and per-object alpha fade curves.
- **Portal travel effects**: the warp depart/arrive puffs and sounds play
  when the Run-mode avatar takes a portal.
- **Camera occlusion fading** in Run mode: props that block the camera's
  view of the character ghost to half-transparent (mesh-accurate, with
  anti-flicker hysteresis).
- **The export pipeline** (`../tools/level_export/`) that produced all of it
  from the original data in `../refs/` — any remaining map of the 325-map
  fleet can be exported locally.

## Export pipeline (from `tools/level_export/`)

```bash
# Run all tests
pytest tests/ -v

# Export terrain props to GLB
python scripts/22_export_props.py --all

# Assemble a map scene from binary .qqq/.ocg data
python scripts/30_export_map.py SF001001

# Export terrain tiles from .cvs/.tcg data
python scripts/31_export_terrain.py SF001001

# Export per-map navigation blobs (navmesh, wall grid, movement grid)
python scripts/34_export_navmesh.py

# Re-export the animated props (all 187 in one pass)
python scripts/22_export_props.py --animated

# Regenerate viewer heightmap PNGs from {code}_h.bmp
python scripts/35_export_heightmaps.py --all
```

The level catalog (`client/assets/levels/levels.yaml` / `.json`) ships
pre-generated: level names, per-map camera parameters, minimap rects, and
portal links between maps.

## Notes

- Tile texture folders (`client/assets/maps/*/*_tiles/`) carry a `.gdignore`:
  the viewer loads them directly at runtime, and keeping the Godot editor's
  importer out of ~77k small PNGs keeps the editor fast and stable. Leave
  those files in place.
- The Run-mode avatar reuses the YTAvatar addon; if runner animations ever
  look degraded on a fresh clone, re-import with the animation optimizer
  disabled (see the YTAvatar docs).
