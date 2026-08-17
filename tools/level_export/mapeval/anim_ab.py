"""A/B eval: does the animation runtime degrade any prop's look?

For every animated prop, `anim_ab_capture.gd` renders the same GLB twice —
A: FF lighting only (pixel-identical to the pre-animation origin/main look;
verified on p_portal003a: main's GLB and HEAD's GLB render the same raw) and
B: lighting + PropAnimator (clips, held idles, fade curves).

The diff between A and B is exactly what the animation feature changes.
Expected differences are motion (pose shift) and authored idle fades
(geometry hidden because its curve says alpha 0 at the held frame).
Pathologies show up as large NEW saturated areas: pure white (material lost
its shader/texture), or large dark areas that were glowing in A (additive
pass broken). Those metrics are flagged for eyeball review.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

CAPTURE_TIMEOUT = 1800
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "client"

# Background is (30, 30, 200)-ish after tonemap; match generously.
BG_TOL = 40

FLAG_DIFF = 0.25       # >25% of the prop's own pixels changed
FLAG_WHITE_NEW = 0.10  # >10% of prop pixels became near-white in B


def _load(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int16)


def _prop_mask(img: np.ndarray) -> np.ndarray:
    bg = np.array([31, 31, 199], dtype=np.int16)
    return np.abs(img - bg).max(axis=2) > BG_TOL


def compare_pair(a_path: Path, b_path: Path) -> dict:
    a, b = _load(a_path), _load(b_path)
    mask = _prop_mask(a) | _prop_mask(b)
    denom = max(int(mask.sum()), 1)
    diff = (np.abs(a - b).max(axis=2) > 12) & mask
    white_a = (a.min(axis=2) > 235) & mask
    white_b = (b.min(axis=2) > 235) & mask
    return {
        "prop_pixels": int(mask.sum()),
        "diff_frac": float(diff.sum()) / denom,
        "white_new_frac": float((white_b & ~white_a).sum()) / denom,
    }


def run(out_dir: Path, ids: list[str] | None = None) -> list[dict]:
    godot = os.environ.get("GODOT_BIN")
    if not godot:
        raise RuntimeError("GODOT_BIN is not set")
    out_dir = Path(out_dir)
    cmd = [godot, "--path", str(CLIENT_DIR), "--script",
           "scripts/tests/anim_ab_capture.gd", "--position", "4000,4000",
           "--", str(out_dir)] + (ids or [])
    subprocess.run(cmd, timeout=CAPTURE_TIMEOUT, check=True)

    rows = []
    for a_path in sorted(out_dir.glob("*_a.png")):
        prop_id = a_path.name[:-6]  # "{category}.{prop_id}"
        b_path = out_dir / f"{prop_id}_b.png"
        if not b_path.exists():
            rows.append({"prop": prop_id, "error": "no B capture"})
            continue
        m = compare_pair(a_path, b_path)
        m["prop"] = prop_id
        m["flag"] = (m["diff_frac"] > FLAG_DIFF
                     or m["white_new_frac"] > FLAG_WHITE_NEW)
        rows.append(m)
    return rows


def write_report(rows: list[dict], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    rows = sorted(rows, key=lambda r: -r.get("diff_frac", 1.0))
    parts = ["<html><body style='background:#222;color:#ddd;font-family:sans-serif'>",
             "<h2>anim A/B — A: lighting only (origin/main look), B: + animator</h2>",
             f"<p>{sum(1 for r in rows if r.get('flag'))} flagged / {len(rows)}</p>"]
    for r in rows:
        if "error" in r:
            parts.append(f"<h3 style='color:#f66'>{r['prop']}: {r['error']}</h3>")
            continue
        color = "#f66" if r["flag"] else "#8c8"
        parts.append(
            f"<h3 style='color:{color}'>{r['prop']} — diff {r['diff_frac']:.1%}, "
            f"new-white {r['white_new_frac']:.1%}</h3>"
            f"<img src='{r['prop']}_a.png' width='300'>"
            f"<img src='{r['prop']}_b.png' width='300'>")
    parts.append("</body></html>")
    path = out_dir / "report.html"
    path.write_text("\n".join(parts))
    return path
