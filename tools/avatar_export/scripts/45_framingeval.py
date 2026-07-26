#!/usr/bin/env python3
"""
framingeval — initial camera framing check for the avatar tool's
monster/NPC viewer.

Drives the REAL avatar_tool through every model (godot_probe/
framing_probe.gd) and validates each model's initial view: the projected
screen bbox must cover a sane fraction of the viewport, sit roughly
centered, and not wrap the camera (corners behind the eye). Catches the
"default zoom inside the boss" class (ct0017: camera inside the model)
and stale-rotation/pivot bugs — things no data-level eval can see.

Usage (from tools/avatar_export/):
    python scripts/45_framingeval.py                # monsters + NPCs
    python scripts/45_framingeval.py --kind monster

Needs a display (the tool renders windowed; parked offscreen).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLIENT = ROOT.parent.parent / "ytavatar" / "client"
GODOT = os.environ.get("GODOT_BIN", "/Applications/Godot.app/Contents/MacOS/Godot")
PROBE = ROOT / "godot_probe" / "framing_probe.gd"
OUT = ROOT / "reports" / "framing"

# PIXEL metrics (framing_probe.gd renders each model against a chroma
# key with GUI and ground hidden, then measures the silhouette bbox).
# Calibrated 2026-07-26 against user-flagged cases: ct0002/ct0009 framed
# at the frame edge, small monsters face-filling, oversized hand zooms.
HEIGHT_MIN = 0.10     # silhouette shorter than ~1/10 frame: too far
HEIGHT_MAX = 0.85     # taller than ~85%: too close
CENTER_OFF_MAX = 0.20 # silhouette center within middle 40% of the frame


def run_probe(kind: str) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    out_json = OUT / f"framing_{kind}.json"
    subprocess.run(
        [GODOT, "--path", str(CLIENT), "-s", str(PROBE),
         "--position", "4400,100", "--", str(out_json), kind],
        check=True, capture_output=True, timeout=1800)
    return json.loads(out_json.read_text())


def evaluate(rows: list[dict]) -> tuple[int, int]:
    n_pass = 0
    for r in rows:
        mid = r.get("id", "?")
        if "error" in r:
            print(f"  FAIL {mid}: {r['error']}")
            continue
        hf = r.get("height_frac", 0.0)
        wf = r.get("width_frac", 0.0)
        cx, cy = r.get("center_off", [1.0, 1.0])
        size_ok = HEIGHT_MIN <= max(hf, wf) and hf <= HEIGHT_MAX
        ok = (size_ok and not r.get("touches_edge", False)
              and abs(cx) <= CENTER_OFF_MAX and abs(cy) <= CENTER_OFF_MAX)
        if ok:
            n_pass += 1
        else:
            print(f"  FAIL {mid}: size {wf:.2f}x{hf:.2f} "
                  f"center ({cx:+.2f},{cy:+.2f}) "
                  f"edge={r.get('touches_edge')} zoom {r.get('zoom', 0):.1f}")
    return n_pass, len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=["monster", "npc", "all"], default="all")
    args = ap.parse_args()
    kinds = ["monster", "npc"] if args.kind == "all" else [args.kind]
    total_pass = total = 0
    for kind in kinds:
        rows = run_probe(kind)
        p, n = evaluate(rows)
        print(f"framingeval [{kind}]: {p}/{n} pass")
        total_pass += p
        total += n
    sys.exit(0 if total_pass == total else 1)


if __name__ == "__main__":
    main()
