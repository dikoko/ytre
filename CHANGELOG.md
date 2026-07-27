# Changelog

Notable changes to the Yogurting Re project. Versions follow a simple
scheme: **minor** bumps for content/tool releases (new or re-exported
assets, pipeline features), **patch** bumps for documentation-only fixes.

## [0.6.4] - 2026-07-26

### Added
- **Static content database schema**
  (`docs/original/design/db/static-content-schema.md`) — the ~110 content
  tables the original game was authored in: schools, fields and lobbies;
  episodes with their scoring, pacing, party-scaling and calorie rules;
  monsters, their stat templates and field spawning; the levelled skill
  trees; item, socket and upgrade-stone types; NPCs, dialogue and shops;
  quests and their grade-scaled rewards; progression curves, promotion
  conditions and titles; and the live-ops event, promotion and scheduling
  tables. Documents the shared enumerations (item categories, equip
  bitmasks, weapon classes, status effects, time-of-day flags) that every
  content table depends on, and the formula columns evaluated by the
  script engine.

## [0.6.3] - 2026-07-26

### Added
- **Game state database schema**
  (`docs/original/design/db/game-state-schema.md`) — the live
  per-character schema of the original service: character, stats,
  equipment, the five inventory classes, upgrade slots, locker, quests,
  episode records and high scores, the phone-based social layer, guilds,
  the auction book, and account-scoped premium state. Each table carries
  its columns, types, keys, meaning and a confidence tag, plus the
  procedure-level access pattern, the 2005 → 2006 schema evolution, and
  notes on what to do differently in a re-implementation.

## [0.6.2] - 2026-07-26

### Added
- **Server architecture overview**
  (`docs/original/protocol/ARCHITECTURE.md`) — the original service's
  server components and what each owned (session, world, battle,
  community, the in-memory authority tier, service broker, admin control
  plane), how they discovered and routed to each other, a session from
  login to logout, and how the roles map onto modern components.

## [0.6.1] - 2026-07-26

### Added
- **Auction house design specification**
  (`docs/original/design/auction-system.md`) — a complete, implementable
  write-up of the original game's auction house: listing and bid data
  models, listing/bid state machines, the category filter encoding, fee
  and timer rules (6/12/24 h durations, tiered listing fee, 72 h claim
  window), the client/server protocol, the auction-window UX, and a list
  of the original's weak points worth fixing rather than reproducing.

### Changed
- **Documentation reorganized** under `docs/original/`, split into
  `design/` (game-system specifications) and `protocol/` (network
  protocol), with an index at `docs/original/README.md`. The legacy
  network protocol document moved to
  `docs/original/protocol/LEGACY_PROTOCOL.md`.

## [0.6.0] - 2026-07-26

First public release of **YTLevel** — the level/map viewer and its export
pipeline — plus user guides for both Godot tools.

### Added
- **`ytlevel/` Godot client**: the in-game level tool. Browse the school
  and early-episode maps with Korean level names, fly around with the
  explore camera, click portals to travel between maps, and press Tab to
  walk the map in Run mode (navmesh ground contact, wall blocking, portal
  dwell travel, gender-switchable runner avatar).
- **Map assets** for the school maps and first episode: terrain meshes
  with the original tile textures, ~5,200 placed props per campus map,
  water surfaces with animated flow and beach shore-waves, per-map
  minimaps, and the fixed-function sun / point-light model matching
  retail client rendering.
- **1,576 static prop models** exported from TMD with embedded textures
  (including mirrored variants and additive self-illuminated glows).
- **`tools/level_export/` pipeline**: parsers for QQQ / OCG / CVS / TCG /
  WTR / PLT / height-BMP data, prop exporter, map assembly, terrain tile
  compositor, navmesh + wall-grid export, and a map evaluation harness
  (data invariants + rendered-capture detectors). Terrain reference data
  ships under `refs/models/raw/Terrain/`, so any of the 325 maps can be
  exported locally.
- **User guides**: `ytavatar/docs/user-guide.md` and
  `ytlevel/docs/user-guide.md` — every UI element and key binding for the
  avatar tool and the level tool.

### Changed
- Street-lamp glow sprites are dimmed to 40% of authored strength in the
  level viewer — at full strength they read as daylight spotlights.

## [0.5.0] - 2026-07-26

Character skinning and locomotion now match the original game; the viewer
frames every model correctly.

### Fixed
- **Skinning distortion on reflection rigs**: models whose rigs contain
  mirrored bones (the ct0016/cn0090 "walking library" bosses, ct0024, and
  seven others) rendered with collapsed, faceted limbs and tentacles, and
  shimmering where mis-skinned faces overlapped. Their inverse bind
  matrices were derived from a re-posed skeleton; the original client
  skins against the authored static bind (embedded scale and reflections
  included), and the exporter now does the same. All 135 monsters, 78
  NPCs, and both avatar bases were re-exported.
- **Walk/run height**: every moving animation hovered at standing height
  (ct0021 floated 0.45 above its feet). The skeleton root now follows the
  authored per-frame root pose — the separate root-position track is
  entity displacement (per-frame travel deltas), which viewers play in
  place, matching retail client behavior. Crouched walk cycles and ground
  contact are restored across the fleet.
- **Viewer initial camera**: models without a hand-tuned zoom entry could
  spawn the camera inside their geometry (large monsters were invisible).
  The viewer now auto-frames each model from its bounding sphere, centers
  the pivot, and resets rotation on model switch; the fit waits for the
  animated pose to settle so effect meshes can't inflate the framing.
- **Trackpad camera rotate**: two-finger drag now orbits the camera on
  macOS trackpads (they emit pan gestures, not mouse-wheel events); pinch
  zoom limits unified.

### Added
- Two pipeline verification gates: inverse-bind parity against the
  authored static bind for all 213 rigged models, and an automated
  initial-view framing check that drives the real viewer across the whole
  fleet.

## [0.4.0] - 2026-07-24

The character fleets now render as the original game intended.

### Fixed
- **Handedness**: the game's data is authored for a left-handed renderer;
  importing it verbatim into right-handed glTF rendered every model
  left-right mirrored (visible on clothing text such as the jersey
  numbers). All character exporters now apply one coherent Z-mirror —
  positions, winding, rig conjugation, and every animation track. All
  avatar bases, 394 parts, weapons, 78 NPCs, and 135 monsters were
  re-exported. Models face −Z; viewers rotate them to face the camera.
- **Avatar skin-tone seams**: skin is colored by the engine's smooth
  alpha-mask blend (part texture alpha = skin mask) with per-gender
  authored default tones — hairline, armhole, and thigh seam lines are
  gone.
- **Skin poking through clothing**: part equipping now uses the exact
  swap-slot mechanism from the game's swap data — each part replaces
  whole base material meshes. The old region heuristics (and the
  clothing shell offset that papered over them) are retired. Fixes
  z-fighting under long coats, thigh-high boots, and gloves.

### Added
- Fixed-function portrait lighting for characters (gamma space,
  ambient-dominant, per-vertex diffuse).
- Authored seam-weld normals from the swap data baked into part GLBs.
- Base avatar `.glb.import` files tracked (they carry required animation
  import settings: key optimizer off, 30 fps).

### Changed
- Export tools brought fully current with the shipped assets: MLIB
  parser with full keyframe tracks, SWP parser with slot/weld semantics,
  updated animation/part/material/weapon exporters.

## [0.3.0] - 2026-07-23

### Added
- All 78 NPCs and all 135 monsters in the browser — previously omitted
  models restored after animation fixes.

### Fixed
- Full animation track fidelity for NPC/monster motions: per-bone
  translation and scale keys, scale-axis handling via per-factor node
  chains, engine-matching key interpolation (shortest-path slerp). Cape
  and sleeve flicker eliminated; equipment no longer detaches.
- Godot's lossy animation-key import optimizer disabled for all animated
  models via tracked `.glb.import` settings.

## [0.2.1] - 2026-07-12

### Added
- Legacy (2006) network protocol specification document.

## [0.2.0] - 2026-05-14

### Added
- Extracted game art assets under `refs/`.
- Asset export tooling (`tools/avatar_export`): TMD/MLIB/PRT/SWP parsers
  and GLB exporters for avatars, parts, weapons, monsters, and NPCs.
- License (CC BY-NC-SA 4.0).

## [0.1.0] - 2026-03-23

### Added
- Initial Godot 4 client with the avatar viewer tool and addons.
