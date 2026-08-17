"""Two-frame liveness detector: prove animated props actually move.

A still capture cannot distinguish "animated" from "exported but frozen".
This captures two frame pairs 2 s apart — one with props visible, one with
them hidden — and measures how much of the image changed. The props-hidden
pair is the control: it must stay still, which is what rules out camera
drift or per-frame render churn masquerading as animation.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

CAPTURE_TIMEOUT = 300
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "client"

# Fraction of pixels that must differ between the two frames.
#
# The floor is deliberately tiny. The capture is a full-map top-down ortho, so
# a map with a few small looping props paints motion across very few pixels —
# SF002008's four floating crystals manage 0.01% of the frame now that its
# trigger-driven props (doors, chests, shrines) correctly hold their idle
# pose. What makes the measure decisive is not the magnitude but the control:
# with water hidden, a scene whose props are frozen measures exactly 0.0, so
# any nonzero animated delta is motion and nothing else.
MIN_ANIMATED_DELTA = 0.00005
MAX_CONTROL_DELTA = 0.0001
# ...unless the control itself moves, in which case the animated measure has to
# clear it by a wide margin to mean anything.
MIN_SIGNAL_RATIO = 10.0


def _changed_fraction(a: np.ndarray, b: np.ndarray, tol: int = 6) -> float:
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    return float((diff > tol).mean())


def _load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def check_map(map_code: str, out_dir: Path) -> dict:
    godot = os.environ.get("GODOT_BIN")
    if not godot:
        raise RuntimeError("GODOT_BIN is not set")
    out_dir = Path(out_dir)
    subprocess.run(
        [godot, "--path", str(CLIENT_DIR), "--script",
         "scripts/tests/anim_liveness_capture.gd", "--", map_code, str(out_dir)],
        timeout=CAPTURE_TIMEOUT, check=True,
    )
    animated = _changed_fraction(_load(out_dir / "anim_a.png"),
                                 _load(out_dir / "anim_b.png"))
    control = _changed_fraction(_load(out_dir / "control_a.png"),
                                _load(out_dir / "control_b.png"))
    ok = (animated >= MIN_ANIMATED_DELTA
          and control <= MAX_CONTROL_DELTA
          and (control == 0.0 or animated / control >= MIN_SIGNAL_RATIO))
    return {
        "map": map_code,
        "animated_delta": animated,
        "control_delta": control,
        "pass": ok,
    }
