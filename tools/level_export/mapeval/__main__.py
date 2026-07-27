"""Eval runner: python -m mapeval SF001001 [--skip-capture]"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from mapeval.l1_checks import run_l1
from mapeval.detectors import dark_ratio, magenta_ratio, seam_score
from mapeval.capture import run_capture, PX_PER_CELL
from mapeval.report import write_report
from mapeval.paths import REPORTS_DIR

BG = (30, 30, 200)  # keep in sync with eval_capture.gd


def _find_previous(map_dir: Path) -> dict | None:
    runs = sorted(d for d in map_dir.glob("*") if (d / "scores.json").exists())
    if not runs:
        return None
    return json.loads((runs[-1] / "scores.json").read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("map_code")
    ap.add_argument("--skip-capture", action="store_true")
    args = ap.parse_args()

    map_dir = REPORTS_DIR / args.map_code
    previous = _find_previous(map_dir)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = map_dir / ts
    cap_dir = out_dir / "captures"
    cap_dir.mkdir(parents=True)

    scores = {"map": args.map_code, "timestamp": ts, "l1": run_l1(args.map_code),
              "l2": {"terrain_seam_score": None, "props": []}, "l2_skipped": True}

    if not args.skip_capture and run_capture(args.map_code, cap_dir):
        scores["l2_skipped"] = False
        terrain = np.asarray(Image.open(cap_dir / "terrain_topdown.png").convert("RGB"))
        scores["l2"]["terrain_seam_score"] = round(seam_score(terrain, PX_PER_CELL), 3)
        closeup_path = cap_dir / "terrain_closeup.png"
        if closeup_path.exists():
            closeup_img = np.asarray(Image.open(closeup_path).convert("RGB"))
            scores["l2"]["terrain_closeup_seam_score"] = round(seam_score(closeup_img, 64), 3)
        # Presence flag only -- no detector score. Human-review artifact for prop
        # orientation bugs (misrotations/mirrors) that the dark-ratio detector can't see.
        scores["l2"]["scene_topdown"] = (cap_dir / "scene_topdown.png").exists()
        for png in sorted(cap_dir.glob("prop_*.png")):
            img = np.asarray(Image.open(png).convert("RGB"))
            scores["l2"]["props"].append({
                "name": png.stem.removeprefix("prop_"),
                "dark_ratio": round(dark_ratio(img, BG), 4),
                "magenta_ratio": round(magenta_ratio(img), 4),
            })

    write_report(scores, out_dir, previous)
    print(f"report: {out_dir / 'report.html'}")
    l1v = sum(len(c.get("violations", [])) for c in scores["l1"].values())
    print(f"L1 violations: {l1v}; L2 {'SKIPPED' if scores['l2_skipped'] else 'ok'}")


if __name__ == "__main__":
    main()
