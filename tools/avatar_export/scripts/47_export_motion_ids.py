#!/usr/bin/env python3
"""Export motion_ids.json: MLIB motion id -> imported base-GLB clip name.

The skill scripts reference caster motion by INTEGER id; the original
client resolves it as a sparse map into the gender's MLIB and the
lib-name string is editor-only. Our GLB clips are named by the animation
exporter's rule (motion.name.replace("male_", "") — 'female_' becomes
'fe'); Godot's
importer dedupes duplicate names by appending 2,3,... in file order.
This mapping lets the runtime resolve ids without reverse-engineering names.
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.mlib_parser import MLIBParser

YTREF = PROJECT_ROOT.parent.parent / "refs"
MOTION_DIR = YTREF / "models" / "raw" / "Avatar.IRD" / "motion"
DEFAULT_OUT = PROJECT_ROOT.parent.parent / "ytavatar" / "client" / "assets" / "avatars" / "base"


def clip_names(gender: str) -> dict:
    mlib = MLIBParser().parse(MOTION_DIR / gender / f"{gender}.mlib")
    seen: dict = {}
    out: dict = {}
    for motion in mlib.motions:                    # file order = import order
        name = motion.name.replace("male_", "")    # exporter's exact rule
        n = seen.get(name, 0) + 1
        seen[name] = n
        out[str(motion.motion_id)] = name if n == 1 else f"{name}{n}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    doc = {"version": 1,
           "female": clip_names("female"),
           "male": clip_names("male")}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "motion_ids.json"
    out.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {out} ({len(doc['female'])} female / {len(doc['male'])} male ids)")


if __name__ == "__main__":
    main()
