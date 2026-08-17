# Yogurting Re

A revival project for the Yogurting online game, built with Godot 4.

**Current release: 0.7.0** — see [CHANGELOG.md](CHANGELOG.md) for the update history.

## Projects

### [YTAvatar](ytavatar/)

Avatar, monster, and NPC model viewer and asset pipeline. Converts proprietary game formats (TMD, MLIB, PRT) to GLTF/GLB for use in Godot 4.

- Customizable male/female avatars with swappable parts and equipment
- 135 monster models and 78 NPC models
- Interactive 3D viewer with animation playback, orbit camera, and keyboard shortcuts

**Quick start:** Open `ytavatar/client/project.godot` in Godot 4.6+, press F5.
**User guide:** [`ytavatar/docs/user-guide.md`](ytavatar/docs/user-guide.md)

### [YTLevel](ytlevel/)

Level/map viewer and terrain export pipeline. Converts the game's proprietary terrain data (QQQ, OCG, CVS, TCG) and prop models (TMD) to Godot 4 scenes.

- In-game level tool: browse the school and episode maps, fly-camera exploration, portal travel with warp effects, walkable Run mode with the avatar
- Terrain with original tile textures, ~5,200 placed props per campus map (187 props animated with their authored keyframes), water and shore-wave rendering, fixed-function sun/point lighting
- Run mode uses the original game's own movement grid for walkability, navigation-mesh ground contact, and camera-occlusion ghosting for props that hide the character

**Quick start:** Open `ytlevel/client/project.godot` in Godot 4.6+, press F5.
**User guide:** [`ytlevel/docs/user-guide.md`](ytlevel/docs/user-guide.md)

Note: many levels are not fully tested yet — expect rough edges outside the main school campus maps.

## Repository layout

```
ytre/
├── ytavatar/    Godot 4 client — model viewer + game-ready asset library
├── ytlevel/     Godot 4 client — level tool + exported map scenes
├── tools/       Asset conversion pipelines and developer tooling
├── docs/        Reconstructed documentation of the original game's systems
├── refs/        Original Yogurting game assets (read-only reference data)
├── LICENSE      CC BY-NC-SA 4.0 (this project's code and original work)
└── NOTICE.md    IP attribution and third-party-asset terms
```

### [`ytavatar/`](ytavatar/) — Godot client

The main Godot 4 project. Contains the avatar / monster / NPC viewer scene, runtime scripts (GDScript), and the converted asset library under `ytavatar/client/assets/` (avatars, monsters, npcs, weapons, textures, faces). Open `ytavatar/client/project.godot` in Godot 4.6+ to run it. Technical pipeline docs live in [`ytavatar/docs/`](ytavatar/docs/).

### [`ytlevel/`](ytlevel/) — Godot client (levels)

The level-tool Godot 4 project: exported map scenes under `ytlevel/client/scenes/maps/`, terrain/prop/water assets under `ytlevel/client/assets/`, and the runtime scripts (terrain and water renderers, fixed-function lighting, navmesh ground contact, run-mode avatar). Open `ytlevel/client/project.godot` in Godot 4.6+ to run it. See [`ytlevel/README.md`](ytlevel/README.md).

### [`tools/`](tools/) — asset conversion + tooling

Developer tooling. Currently contains a single subproject:

- [`tools/avatar_export/`](tools/avatar_export/) — Python (uv-managed) pipeline that converts Yogurting's proprietary `.TMD`, `.mlib`, `.PRT`, `.SWP`, and `.BMP` files from `refs/` into the GLB / PNG / JSON assets consumed by the Godot client. Includes 19 numbered pipeline scripts (export + verification gates), debug visualizers, and a pytest suite. See [`tools/avatar_export/README.md`](tools/avatar_export/README.md).
- [`tools/level_export/`](tools/level_export/) — Python pipeline that converts the terrain data (`.qqq`, `.ocg`, `.cvs`, `.tcg`, `.wtr`, `.plt`, height BMPs) and prop TMDs from `refs/` into the map scenes, tile textures, GLB props, and navmesh/wall blobs consumed by the level tool, plus a map evaluation harness (data checks + rendered-capture detectors).

### [`docs/`](docs/) — reconstructed documentation

Write-ups of how the original game worked, for rebuilding its systems faithfully. [`docs/original/design/`](docs/original/design/) holds game-system specifications (rules, data models, state machines, UI flows) and [`docs/original/protocol/`](docs/original/protocol/) the network protocol. See [`docs/original/README.md`](docs/original/README.md) for the index.

### [`refs/`](refs/) — original game assets

Raw Yogurting asset data, organized as `refs/models/raw/{Avatar,Monster,NPC,Terrain,...}.IRD/`. The export pipelines in `tools/` read from here; the Godot client does **not** load anything from this folder directly.

These assets are © Neowiz and are **not** covered by this project's CC BY-NC-SA license — they are included under a separate non-commercial-use permission obtained from Neowiz. See [`NOTICE.md`](NOTICE.md) for the full terms.

## Requirements

- [Godot 4.6](https://godotengine.org/) or newer

## License

This project's original code and content is licensed under **CC BY-NC-SA 4.0** — non-commercial use only, share-alike for derivatives. See [`LICENSE`](LICENSE) for the full text.

The game assets under `refs/` (and their derivatives under `ytavatar/client/assets/` and `ytlevel/client/assets/`) are © Neowiz and are included under a separate non-commercial redistribution permission. See [`NOTICE.md`](NOTICE.md) for the full breakdown of what is licensed how, and what non-commercial means in practice.
