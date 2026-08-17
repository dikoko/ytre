"""Regression gate: props with no animation must export byte-identically.

The animated-prop work (spec 2026-08-02) un-bakes per-object transforms for
188 props. The other 1,388 must not move a single byte — that is what makes
the un-baking safe to land.
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._export_common import embed_textures
from scripts._prop_config import OUTPUT_MODELS, TEXTURE_SEARCH_DIRS, discover_props
from src.exporters.prop_animation import build_animation_plan
from src.exporters.prop_exporter import export_prop
from src.parsers.tmd_parser import TMDParser


def has_animation(model, prop_id: str = "p") -> bool:
    """True if ANY object of this model carries real keyframe animation.

    Delegates to the exporter's own plan so the gate and the exporter can
    never disagree about what "animated" means. The original design used a
    model-level heuristic (total keys > 2 x track count); it was wrong in
    both directions — it missed 12 props that really animate (s_SWCshrine
    has 8 animated objects and would have shipped frozen) and falsely
    flagged 3 that have none (a_SWAlever01, a_SWAtreasure01, sky_Dome0001).
    """
    return bool(build_animation_plan(model, prop_id).animated)


def animated_props() -> set[tuple[str, str]]:
    """(category, prop_id) pairs carrying real keyframe animation.

    Keyed on the PAIR, never on the id alone: 23 prop ids exist in two
    categories at once, and three of them (c_SWGchair02A_b01,
    c_SWGchair02A_b02, c_SWGchair05A_b) are animated as `active` but static
    as `chair`, with different file bytes. An id-keyed set silently merges
    them — it under-counts the census (187 vs 188, a_SWFtower03) and drops
    genuinely static props out of this gate.
    """
    out = set()
    for cat, prop_id, tmd_path in discover_props():
        if has_animation(TMDParser().parse(tmd_path), prop_id):
            out.add((cat, prop_id))
    return out


def animated_prop_ids() -> set[str]:
    """Bare ids of animated props — for callers that only need a name filter."""
    return {p for _c, p in animated_props()}


def _static_props():
    animated = animated_props()
    return [(c, p, t) for c, p, t in discover_props() if (c, p) not in animated]


# Deterministic sample for the default run; the full sweep is opt-in via
# ANIM_FULL_SWEEP=1 (~75 s for all 1,388).
_ALL_STATIC = _static_props()
_SAMPLE = _ALL_STATIC[:: max(1, len(_ALL_STATIC) // 40)]
_CASES = _ALL_STATIC if os.environ.get("ANIM_FULL_SWEEP") == "1" else _SAMPLE


def test_census():
    assert len(animated_props()) == 188
    assert len(_ALL_STATIC) == 1388
    # 187 distinct ids for 188 animated files: a_SWFtower03 ships in both
    # Artificial.IRD and Active.IRD (identical bytes, both animated).
    assert len(animated_prop_ids()) == 187


def test_duplicate_ids_have_distinct_categories():
    """Guard the (category, prop_id) keying this whole feature depends on."""
    pairs = [(c, p) for c, p, _t in discover_props()]
    assert len(pairs) == len(set(pairs)), "a (category, id) pair is not unique"

    seen: dict[str, set[str]] = {}
    for cat, prop_id in pairs:
        seen.setdefault(prop_id, set()).add(cat)
    multi = {k: v for k, v in seen.items() if len(v) > 1}
    assert len(multi) == 23, f"expected 23 cross-category ids, got {len(multi)}"

    animated = animated_props()
    mixed = {
        prop_id for prop_id, cats in multi.items()
        if len({(cat, prop_id) in animated for cat in cats}) > 1
    }
    assert mixed == {
        "c_SWGchair02A_b01", "c_SWGchair02A_b02", "c_SWGchair05A_b",
    }, f"mixed-state id set changed: {mixed}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("category,prop_id,tmd_path", _CASES,
                         ids=[c[1] for c in _CASES])
def test_static_prop_bytes_unchanged(tmp_path, category, prop_id, tmd_path):
    committed = OUTPUT_MODELS / category / f"{prop_id}.glb"
    if not committed.exists():
        pytest.skip(f"{prop_id} not committed (local-only map asset)")

    model = TMDParser().parse(tmd_path)
    out = tmp_path / f"{prop_id}.glb"
    export_prop(model, out, prop_id=prop_id)
    embed_textures(out, tmd_path.parent, model, texture_dirs=TEXTURE_SEARCH_DIRS)

    assert _sha256(out) == _sha256(committed), f"{prop_id} export drifted"
