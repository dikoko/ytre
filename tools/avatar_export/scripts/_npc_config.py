"""NPC export configuration — shared between 21_export_npcs.py and tweak_test.py.

As of 2026-07-19 the NPC pipeline exports the faithful MLIB pose
(mlib_translations=True): translation tracks come from the MLIB skeleton's
parent-local bind offsets — the same data the original engine FKs.
The equip-placement heuristics this file used to
drive (auto-reparenting, EQUIP_CORRECTION, BONE_TWEAKS, SKIP_REPARENT) are
retired: the shipped data needs ZERO overrides. The empty dicts stay as
documented extension points for genuine data defects only.
"""

# NPCs where reflection auto-detect is wrong (physics-only reflections)
FORCE_TMD_SCALE = {
    'cn0007',
    'cn0047',  # Reflections only in skirt physics bones
    'cn0109',  # Reflections only in skirt physics bones
}

# Skip auto-reparenting (retired — mlib_translations never reparents)
SKIP_REPARENT: set[str] = set()

# Per-model bone index overrides for physics smoothing.
# cn0007's cape override RETIRED 2026-07-22: it was compensation for the
# dropped translation/scale key tracks; with full key tracks the authored
# cape is smooth and EMA only injected sleeve wobble vs engine truth.
SMOOTH_BONES: dict[str, set[int]] = {}

# Equip bones needing targeted rotation correction (retired; keep empty)
EQUIP_CORRECTION: dict[str, set[int]] = {}

# Per-bone tweaks: "rot" [rx,ry,rz] euler degrees, "pos" [x,y,z] offset
# (retired; keep empty)
BONE_TWEAKS: dict[str, dict[int, dict]] = {}
