#!/usr/bin/env python3
"""
bindparity — IBM parity: exported GLB inverse bind matrices vs the
original client's skinning bind.

The original client skins vertices with W_runtime @ inv(TMD static world)
— the authored bone world transforms VERBATIM (embedded scale and
reflections included). Node-position parity checks are blind to IBM
defects: bone world positions barely move when a bind is wrong, while
every skinned vertex is fully skewed — the ct0016/cn0090 "walking
library" distortion (2026-07-26).

Mapping is ORDINAL (joint k <-> TMD bone k), matching how the exporter
and the original client bind — shipped rigs carry duplicate bone names
(ct0039 has six "@Hair00"), so name-keyed comparison both masks real
errors and invents false ones.

Usage (from tools/avatar_export/):
    python scripts/44_bindparity.py                 # NPCs
    python scripts/44_bindparity.py --kind monster  # monsters
    python scripts/44_bindparity.py --kind all
    python scripts/44_bindparity.py --ids ct0016 cn0090
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from pygltflib import GLTF2

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.exporters.animation_exporter import _extend_bones_with_animation_targets

YTREF = PROJECT_ROOT.parent.parent / "refs" / "models" / "raw"
CLIENT = PROJECT_ROOT.parent.parent / "ytavatar" / "client"
KINDS = {
    "npc": (YTREF / "NPC.IRD", CLIENT / "assets" / "npcs" / "models"),
    "monster": (YTREF / "Monster.IRD", CLIENT / "assets" / "monsters" / "models"),
}
TOL = 1e-3


def _read_mat4_accessor(gltf, blob, idx):
    acc = gltf.accessors[idx]
    bv = gltf.bufferViews[acc.bufferView]
    off = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    raw = np.frombuffer(blob, dtype=np.float32, count=acc.count * 16,
                        offset=off).reshape(-1, 4, 4)
    return np.transpose(raw, (0, 2, 1))  # glTF column-major -> row-major


def bind_parity(kind_dir: Path, glb_dir: Path, model_id: str) -> dict:
    d = kind_dir / model_id
    tmd_path = next((p for p in d.iterdir() if p.suffix.lower() == ".tmd"), None)
    mlib_path = next((p for p in d.iterdir() if p.suffix.lower() == ".mlib"), None)
    glb_path = glb_dir / f"{model_id}.glb"
    if tmd_path is None or mlib_path is None or not glb_path.exists():
        return {"id": model_id, "ok": False, "error": "missing TMD/MLIB or GLB"}
    tmd = TMDParser().parse(tmd_path)
    # The exporter extends the bone list with animation-target objects
    # BEFORE building skins — joint k maps to the EXTENDED list's bone k.
    _extend_bones_with_animation_targets(tmd, MLIBParser().parse(mlib_path))

    S4 = np.diag([1.0, 1.0, -1.0, 1.0])
    truth_inv = []
    for b in tmd.bones:
        R = np.array(b.world_transform.rotation.data).reshape(3, 3).T
        M = np.eye(4)
        M[:3, :3] = R
        t = b.world_transform.translation
        M[:3, 3] = [t.x, t.y, t.z]
        truth_inv.append(np.linalg.inv(S4 @ M @ S4))

    gltf = GLTF2().load(str(glb_path))
    blob = gltf.binary_blob()
    worst = 0.0
    worst_joint = ""
    for skin in gltf.skins:
        ibms = _read_mat4_accessor(gltf, blob, skin.inverseBindMatrices)
        for k in range(min(len(truth_inv), len(skin.joints))):
            err = float(np.abs(ibms[k] - truth_inv[k]).max())
            if err > worst:
                worst = err
                worst_joint = gltf.nodes[skin.joints[k]].name
    return {"id": model_id, "ok": worst < TOL,
            "max_err": round(worst, 5), "worst_joint": worst_joint}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", default="npc", choices=["npc", "monster", "all"])
    ap.add_argument("--ids", nargs="*", default=None)
    args = ap.parse_args()

    kinds = ["npc", "monster"] if args.kind == "all" else [args.kind]
    n_pass = n_total = 0
    for kind in kinds:
        kind_dir, glb_dir = KINDS[kind]
        if args.ids:
            prefix = "cn" if kind == "npc" else "ct"
            ids = [i for i in args.ids if i.startswith(prefix)]
        else:
            ids = sorted(d.name for d in kind_dir.iterdir()
                         if d.is_dir() and (glb_dir / f"{d.name}.glb").exists())
        for mid in ids:
            r = bind_parity(kind_dir, glb_dir, mid)
            n_total += 1
            if r["ok"]:
                n_pass += 1
            else:
                print(f"  FAIL {mid}: max IBM err {r.get('max_err')} "
                      f"({r.get('worst_joint', r.get('error', ''))})")
    print(f"\nbindparity: {n_pass}/{n_total} pass (tol {TOL})")
    sys.exit(0 if n_pass == n_total else 1)


if __name__ == "__main__":
    main()
