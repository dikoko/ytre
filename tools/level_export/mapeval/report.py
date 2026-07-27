"""HTML report + scores.json writer. Worst-N thumbnails per detector."""
import html
import json
from pathlib import Path

WORST_N = 20


def write_report(scores: dict, out_dir: Path, previous: dict | None) -> None:
    (out_dir / "scores.json").write_text(json.dumps(scores, indent=2))
    l1, l2 = scores.get("l1", {}), scores.get("l2", {})
    rows = []
    props = sorted(l2.get("props", []), key=lambda p: -p["dark_ratio"])[:WORST_N]
    for p in props:
        name = html.escape(str(p["name"]))
        img = f'<img src="captures/prop_{name}.png" width="160">'
        rows.append(f'<tr><td>{img}</td><td>{name}</td>'
                    f'<td>{p["dark_ratio"]:.3f}</td><td>{p["magenta_ratio"]:.3f}</td></tr>')
    prev_seam = (previous or {}).get("l2", {}).get("terrain_seam_score")
    seam = l2.get("terrain_seam_score")
    seam_line = f"terrain seam score: <b>{seam}</b>"
    if prev_seam is not None:
        seam_line += f" (previous: {prev_seam})"
    closeup_seam = l2.get("terrain_closeup_seam_score")
    if closeup_seam is not None:
        prev_closeup_seam = (previous or {}).get("l2", {}).get("terrain_closeup_seam_score")
        seam_line += f"<br>terrain closeup seam score (64px/cell): <b>{closeup_seam}</b>"
        if prev_closeup_seam is not None:
            seam_line += f" (previous: {prev_closeup_seam})"
    l1_lines = "".join(
        f"<li>{html.escape(str(name))}: {len(check.get('violations', []))} violations</li>"
        for name, check in l1.items())
    map_name = html.escape(str(scores.get('map')))
    timestamp = html.escape(str(scores.get('timestamp')))
    scene_topdown_html = ""
    if l2.get("scene_topdown"):
        scene_topdown_html = (
            '<p><img src="captures/scene_topdown.png" width="600"><br>'
            'scene (props visible) — check prop orientation against reference</p>'
        )
    html_doc = f"""<!doctype html><meta charset="utf-8">
<title>mapeval {map_name} {timestamp}</title>
<h1>{map_name} — {timestamp}</h1>
<h2>L1 data checks</h2><ul>{l1_lines}</ul>
<h2>L2 visual</h2><p>{seam_line}</p>
<p><img src="captures/terrain_topdown.png" width="600"></p>
{scene_topdown_html}
<h3>Worst {WORST_N} props by dark ratio</h3>
<table border="1"><tr><th>capture</th><th>prop</th><th>dark</th><th>magenta</th></tr>
{''.join(rows)}</table>
"""
    (out_dir / "report.html").write_text(html_doc)
