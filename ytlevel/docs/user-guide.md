# YTLevel — Level Tool User Guide

The level tool is a browser and walker for the exported Yogurting maps: pick a
school or episode, fly around the map, click a portal to travel, or drop into
Run mode and walk the map as an avatar.

**Launch:** open `ytlevel/client/project.godot` in Godot 4.6+ and press **F5**
(the main scene is `scenes/level_tool.tscn`).

> This repository ships assets for the school and early-episode maps. Maps
> without shipped assets are skipped by the selector; the rest of the fleet can
> be exported locally with the pipeline in `tools/level_export/`.
>
> **Note:** many levels are not fully tested yet — outside the main school
> campus maps you may still run into visual glitches or rough Run-mode ground
> contact.

## Choosing a level

The top bar has two selector groups with Korean level names:

- **Schools / Episodes** — pick the group first, then the level dropdown.
  Changing the school or episode loads that group's first available map.
- **`[` / `]`** — cycle backward / forward through the level dropdown.

All selection UI is disabled while in Run mode — travel through portals there
instead.

## Explore camera (default mode)

A free-flying camera:

| Input | Action |
|---|---|
| **W / S** | Move along the view direction (pitch down + W dives into the map — that is the zoom) |
| **A / D** | Strafe left / right |
| **Q / E** | Down / up |
| **Right-drag** | Look around |
| **Middle-drag** | Pan |
| **Mouse wheel** / two-finger scroll / pinch | Dolly in / out |
| **Double-click** | Fly to the clicked point |
| **Home** | Reset to the map overview |
| **T** | Toggle top-down orthographic view (WASD pans there) |
| **Shift** | Hold for 3× speed |
| **G** | Toggle terrain visibility |

Camera speed scales with altitude, and the camera is kept above the terrain.

## Minimap

The corner minimap shows the shipped in-game map with your current view:

- **Click** anywhere on the minimap to focus the camera there.
- In Run mode it tracks the avatar instead of the camera.

## Portals

Portal markers (gate model or a ring with a destination label) stand where the
original maps link to each other:

- **Single click** a portal to travel to its destination map.
- Any camera navigation before the travel fires cancels it.

## Run mode

Press **Tab** (or the Run button) to spawn an avatar and walk the map.

| Input | Action |
|---|---|
| **W / S** | Run forward / backpedal |
| **A / D** | Turn left / right (the avatar always faces her movement direction; W+A curves) |
| **Right-drag** / two-finger drag | Orbit the camera around the avatar (yaw and pitch) |
| **Mouse wheel** / pinch | Zoom (0.33×–1× of the map's authored camera distance) |
| **♀ / ♂ button** | Switch the runner avatar's gender (appears in Run mode) |
| **Tab** | Leave Run mode |

Walking into a portal and standing in it briefly (~0.6 s) travels to the linked
map. Ground height comes from the original navigation mesh — stairs, floors,
and bridges are walkable where the original game allowed it, and walls block
movement.

## Legacy prop editor

Opening a map scene directly (e.g. `scenes/maps/SF001001.tscn` with F6) runs a
diagnostic prop editor instead of the level tool. It is an inspection tool; the
export pipeline reproduces the original data without manual fix-ups.

| Key | Action |
|---|---|
| **Tab** | Toggle Edit mode |
| **[ / ]** | Cycle props; **Click** selects |
| **Arrows / PgUp / PgDn** | Move the selected prop (XZ / Y) |
| **R / T** | Rotate ±15°; **+ / −** step size |
| **M** | Mirror left-right |
| **F / N** | Lighting/normal diagnostics |
| **L** | Cycle the map's authored day/night light sets |
| **P / C** | Prop list panel / category filter |
| **Ctrl+S** | Save overrides to YAML |
| **Delete** | Reset prop |
