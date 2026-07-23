# Yogurting Re

A revival project for the Yogurting online game, built with Godot 4.

## Projects

### [YTAvatar](ytavatar/)

Avatar, monster, and NPC model viewer and asset pipeline. Converts proprietary game formats (TMD, MLIB, PRT) to GLTF/GLB for use in Godot 4.

- Customizable male/female avatars with swappable parts and equipment
- 135 monster models and 78 NPC models
- Interactive 3D viewer with animation playback, orbit camera, and keyboard shortcuts

**Quick start:** Open `ytavatar/client/project.godot` in Godot 4.6+, press F5.

## Repository layout

```
ytre/
├── ytavatar/    Godot 4 client — model viewer + game-ready asset library
├── tools/       Asset conversion pipelines and developer tooling
├── refs/        Original Yogurting game assets (read-only reference data)
├── LICENSE      CC BY-NC-SA 4.0 (this project's code and original work)
└── NOTICE.md    IP attribution and third-party-asset terms
```

### [`ytavatar/`](ytavatar/) — Godot client

The main Godot 4 project. Contains the avatar / monster / NPC viewer scene, runtime scripts (GDScript), and the converted asset library under `ytavatar/client/assets/` (avatars, monsters, npcs, weapons, textures, faces). Open `ytavatar/client/project.godot` in Godot 4.6+ to run it. Technical pipeline docs live in [`ytavatar/docs/`](ytavatar/docs/).

### [`tools/`](tools/) — asset conversion + tooling

Developer tooling. Currently contains a single subproject:

- [`tools/avatar_export/`](tools/avatar_export/) — Python (uv-managed) pipeline that converts Yogurting's proprietary `.TMD`, `.mlib`, `.PRT`, `.SWP`, and `.BMP` files from `refs/` into the GLB / PNG / JSON assets consumed by the Godot client. Includes 17 numbered pipeline scripts, debug visualizers, and a pytest suite. See [`tools/avatar_export/README.md`](tools/avatar_export/README.md).

### [`refs/`](refs/) — original game assets

Raw Yogurting asset data, organized as `refs/models/raw/{Avatar,Monster,NPC,Terrain,...}.IRD/`. The export pipeline in `tools/avatar_export/` reads from here; the Godot client does **not** load anything from this folder directly.

These assets are © Neowiz and are **not** covered by this project's CC BY-NC-SA license — they are included under a separate non-commercial-use permission obtained from Neowiz. See [`NOTICE.md`](NOTICE.md) for the full terms.

## Requirements

- [Godot 4.6](https://godotengine.org/) or newer

## License

This project's original code and content is licensed under **CC BY-NC-SA 4.0** — non-commercial use only, share-alike for derivatives. See [`LICENSE`](LICENSE) for the full text.

The game assets under `refs/` (and their derivatives under `ytavatar/client/assets/`) are © Neowiz and are included under a separate non-commercial redistribution permission. See [`NOTICE.md`](NOTICE.md) for the full breakdown of what is licensed how, and what non-commercial means in practice.
