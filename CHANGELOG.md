# Changelog

Notable changes to the Yogurting Re project. Versions follow a simple
scheme: **minor** bumps for content/tool releases (new or re-exported
assets, pipeline features), **patch** bumps for documentation-only fixes.

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
