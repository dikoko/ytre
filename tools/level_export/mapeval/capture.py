"""Invoke Godot to capture terrain + prop renders for a map."""
import os
import subprocess
from pathlib import Path

from mapeval.paths import CLIENT_DIR

PX_PER_CELL = 8
CAPTURE_TIMEOUT = 600


def run_capture(map_code: str, out_dir: Path) -> bool:
    """Run Godot capture. Returns False if Godot unavailable/failed (L2 skipped)."""
    godot = os.environ.get("GODOT_BIN", "godot")

    # Run import pass first to ensure Godot has a fresh import cache.
    # Godot --script runs use the project's import cache; if GLBs changed since the last
    # editor/import run, captures silently use STALE meshes. This reimport ensures fresh data.
    import_cmd = [godot, "--path", str(CLIENT_DIR), "--import", "--headless"]
    try:
        subprocess.run(import_cmd, timeout=CAPTURE_TIMEOUT, capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"L2 capture unavailable (import pass failed): {e}")
        return False

    cmd = [godot, "--path", str(CLIENT_DIR), "--script",
           "res://scripts/eval_capture.gd", "--", map_code, str(out_dir.resolve()),
           str(PX_PER_CELL)]
    try:
        r = subprocess.run(cmd, timeout=CAPTURE_TIMEOUT, capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"L2 capture unavailable: {e}")
        return False
    if r.returncode != 0:
        print(f"L2 capture failed:\n{r.stdout}\n{r.stderr}")
        return False
    return (out_dir / "terrain_topdown.png").exists()
