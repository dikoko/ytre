#!/usr/bin/env python3
"""
Map Sweep Driver — breadth smoke-test across all Map.IRD maps.

For every map: classify compatibility (scripts/_map_compat.py); export the
clean ones (31_export_terrain + 30_export_map as subprocesses); evaluate with
mapeval (L1 + L2 Godot captures); accumulate everything into a resumable
results JSON and render a markdown compatibility matrix.

One map must never abort the sweep: subprocess failures are recorded as that
map's status and the sweep continues. Zero silent skips — every map in
Map.IRD gets a row.

Usage:
    python scripts/40_sweep_maps.py                  # full sweep (resumes)
    python scripts/40_sweep_maps.py --maps SF002001 SF001007
    python scripts/40_sweep_maps.py --limit 5        # first 5 pending maps
    python scripts/40_sweep_maps.py --skip-eval      # export only
    python scripts/40_sweep_maps.py --force --maps SF002001   # redo
    python scripts/40_sweep_maps.py --write-matrix   # just re-render the .md
"""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts._map_compat import classify_map, list_map_codes

REPO_ROOT = PROJECT_ROOT.parent.parent
BASELINES_DIR = REPO_ROOT / "docs" / "eval-baselines"
DEFAULT_RESULTS = BASELINES_DIR / "2026-07-15-map-sweep.json"
REPORTS_DIR = PROJECT_ROOT / "reports"
EXPORT_TIMEOUT = 600

TERMINAL_STATUSES = {"ok", "blocked", "export_failed", "eval_failed"}


def run_export(map_code: str) -> tuple[bool, str]:
    """Run terrain + map export subprocesses. Returns (ok, error_message)."""
    for script in ("31_export_terrain.py", "30_export_map.py"):
        cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / script), map_code]
        try:
            r = subprocess.run(
                cmd, cwd=PROJECT_ROOT, capture_output=True, text=True,
                timeout=EXPORT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False, f"{script}: timeout after {EXPORT_TIMEOUT}s"
        if r.returncode != 0:
            tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-3:]
            return False, f"{script}: " + " | ".join(tail)
    return True, ""


def run_eval(map_code: str) -> tuple[dict | None, str]:
    """Run mapeval; return (scores dict from the newest run, error_message)."""
    cmd = [sys.executable, "-m", "mapeval", map_code]
    try:
        r = subprocess.run(
            cmd, cwd=PROJECT_ROOT, capture_output=True, text=True,
            timeout=3 * EXPORT_TIMEOUT, env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return None, f"mapeval: timeout after {3 * EXPORT_TIMEOUT}s"
    if r.returncode != 0:
        tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-3:]
        return None, "mapeval: " + " | ".join(tail)

    runs = sorted(
        d for d in (REPORTS_DIR / map_code).glob("*")
        if (d / "scores.json").exists()
    )
    if not runs:
        return None, "mapeval: no scores.json produced"
    return json.loads((runs[-1] / "scores.json").read_text()), ""


def summarize_scores(scores: dict) -> dict:
    """Flatten a mapeval scores.json into matrix columns."""
    l1 = scores.get("l1", {})
    violations = 0
    for check in l1.values():
        if isinstance(check, dict):
            violations += len(check.get("violations") or [])
    out = {"l1_violations": violations}

    l2 = scores.get("l2", {})
    if not scores.get("l2_skipped", True):
        out["seam_topdown"] = l2.get("terrain_seam_score")
        out["seam_closeup"] = l2.get("terrain_closeup_seam_score")
        dark = [p["dark_ratio"] for p in l2.get("props", [])]
        out["worst_prop_dark_ratio"] = max(dark) if dark else None
    return out


def render_matrix(results: dict) -> str:
    """Render the results dict to the markdown compatibility matrix."""
    statuses = Counter(r.get("status", "?") for r in results.values())
    blockers = Counter(
        b for r in results.values() for b in r.get("blockers", [])
    )

    lines = [
        "# Map Sweep Compatibility Matrix",
        "",
        f"{len(results)} maps swept. Status counts: "
        + ", ".join(f"{s}: {n}" for s, n in sorted(statuses.items())),
        "",
        "Blocker histogram: "
        + (", ".join(f"{b}: {n}" for b, n in blockers.most_common()) or "none"),
        "",
        "| Map | Status | Blockers | Models | L1 viol. | Seam td | Seam cu | Worst dark | Export s | Error |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for code in sorted(results):
        r = results[code]

        def fmt(key, spec="{}"):
            v = r.get(key)
            return spec.format(v) if v is not None else ""

        models = ""
        if r.get("models_total") is not None:
            models = f"{r.get('models_resolved', '?')}/{r['models_total']}"
        lines.append(
            f"| {code} | {r.get('status', '?')} | "
            f"{', '.join(r.get('blockers', []))} | {models} | "
            f"{fmt('l1_violations')} | {fmt('seam_topdown')} | "
            f"{fmt('seam_closeup')} | {fmt('worst_prop_dark_ratio')} | "
            f"{fmt('export_seconds', '{:.0f}')} | {r.get('error', '')} |"
        )
    return "\n".join(lines) + "\n"


def load_results(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_results(results: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=1, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser(description="Sweep-export and evaluate maps")
    ap.add_argument("--maps", nargs="+", help="Only these map codes")
    ap.add_argument("--limit", type=int, help="Stop after N pending maps")
    ap.add_argument("--skip-eval", action="store_true", help="Export only")
    ap.add_argument("--force", action="store_true",
                    help="Re-run maps that already have results")
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--write-matrix", action="store_true",
                    help="Only re-render the markdown matrix and exit")
    args = ap.parse_args()

    results = load_results(args.results)
    matrix_path = args.results.with_suffix(".md")

    if args.write_matrix:
        matrix_path.write_text(render_matrix(results))
        print(f"Matrix written: {matrix_path}")
        return

    codes = args.maps or list_map_codes()
    pending = [
        c for c in codes
        if args.force or results.get(c, {}).get("status") not in TERMINAL_STATUSES
    ]
    if args.limit:
        pending = pending[: args.limit]
    print(f"Sweep: {len(pending)} pending of {len(codes)} maps")

    for i, code in enumerate(pending, 1):
        start = time.time()
        entry: dict = {}

        cls = classify_map(code)
        entry["blockers"] = cls["blockers"]
        detail = cls["detail"]
        if detail.get("models_total") is not None:
            entry["models_total"] = detail["models_total"]
            entry["models_resolved"] = (
                detail["models_total"] - len(detail["models_missing"])
            )
        if detail.get("point_lights"):
            entry["point_lights"] = detail["point_lights"]

        if cls["blockers"]:
            entry["status"] = "blocked"
        else:
            ok, err = run_export(code)
            entry["export_seconds"] = round(time.time() - start, 1)
            if not ok:
                entry["status"] = "export_failed"
                entry["error"] = err
            elif args.skip_eval:
                entry["status"] = "exported"
            else:
                scores, err = run_eval(code)
                if scores is None:
                    entry["status"] = "eval_failed"
                    entry["error"] = err
                else:
                    entry.update(summarize_scores(scores))
                    entry["status"] = "ok"

        results[code] = entry
        save_results(results, args.results)
        print(f"[{i}/{len(pending)}] {code}: {entry['status']} "
              f"{entry.get('error', '')}".rstrip())

    matrix_path.write_text(render_matrix(results))
    statuses = Counter(r.get("status") for r in results.values())
    print(f"\nDone. {dict(statuses)}")
    print(f"Results: {args.results}\nMatrix:  {matrix_path}")


if __name__ == "__main__":
    main()
