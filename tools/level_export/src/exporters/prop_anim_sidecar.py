"""Per-prop `{prop}.anim.json` — what glTF cannot express.

Carries the clip table with loop intent and the per-object alpha fade
curves from VISIBILITYOBJECT (spec 1.5 — these are alpha, not booleans).
"""
from __future__ import annotations

import json
from pathlib import Path

from src.exporters.prop_animation import PropAnimationPlan


def build_sidecar(plan: PropAnimationPlan) -> dict | None:
    """Return the sidecar payload, or None when the prop has nothing to say."""
    if not plan.animated:
        return None

    clips: dict[str, dict] = {}
    for rng in plan.clips:
        clips[f"range_{rng.range_id}"] = {
            "start": float(rng.start_frame),
            "end": float(rng.end_frame),
            # Ranges are driven explicitly (day/night plays range 1 once,
            # then loops range 2), so loop intent is decided at play time.
            "loop": False,
        }

    default_clip = f"range_{plan.clips[0].range_id}" if plan.clips else "default"

    if default_clip not in clips:
        # No ANIMATION property -> the whole timeline force-loops.
        clips["default"] = {
            "start": 0.0,
            "end": float(plan.total_frames),
            "loop": True,
        }
        default_clip = "default"

    visibility: dict[str, list[list[float]]] = {}
    for obj_index, keys in plan.visibility.items():
        node = plan.animated.get(obj_index)
        if node is None:
            continue
        visibility[node.node_name] = [[float(f), float(a)] for f, a in keys]

    return {
        "fps": float(plan.fps),
        "total_frames": float(plan.total_frames),
        "default_clip": default_clip,
        "clips": clips,
        "visibility": visibility,
    }


def write_sidecar(plan: PropAnimationPlan, glb_path: Path) -> Path | None:
    """Write `{glb_stem}.anim.json` next to the GLB. Returns the path or None."""
    data = build_sidecar(plan)
    if data is None:
        return None
    out = Path(glb_path).with_suffix("")
    out = out.with_name(out.name + ".anim.json")
    out.write_text(json.dumps(data, indent=1, sort_keys=True))
    return out
