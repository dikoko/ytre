"""
Validate map prop positions by plotting QQQ object coordinates over the OPG minimap.

Usage:
    python scripts/validate_map_positions.py SF001001
    python scripts/validate_map_positions.py SF001001 --include-portals --include-triggers
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.parsers.qqq_parser import QQQParser


MAP_IRD = Path("refs/models/raw/Terrain/Map.IRD")


def main():
    parser = argparse.ArgumentParser(description="Plot QQQ positions over OPG minimap")
    parser.add_argument("map_code", help="Map code (e.g. SF001001)")
    parser.add_argument("--include-portals", action="store_true", help="Plot portal positions")
    parser.add_argument("--include-triggers", action="store_true", help="Plot trigger positions")
    parser.add_argument("--dot-size", type=int, default=2, help="Dot radius in pixels (default: 2)")
    parser.add_argument("-o", "--output", help="Output path (default: /tmp/{map_code}_validation.png)")
    args = parser.parse_args()

    map_dir = MAP_IRD / args.map_code
    qqq_path = map_dir / f"{args.map_code}.qqq"
    opg_path = map_dir / f"{args.map_code}.opg"

    if not qqq_path.exists():
        print(f"ERROR: {qqq_path} not found")
        return 1
    if not opg_path.exists():
        print(f"ERROR: {opg_path} not found")
        return 1

    # Parse QQQ
    qqq = QQQParser()
    data = qqq.parse(str(qqq_path))
    print(f"Parsed {args.map_code}: {len(data.objects)} objects, "
          f"{len(data.portals)} portals, {len(data.triggers)} triggers")
    print(f"Tree: center=({data.tree_info.center[0]}, {data.tree_info.center[1]}), "
          f"extents=({data.tree_info.extents[0]}, {data.tree_info.extents[1]})")

    # Load minimap
    minimap = Image.open(str(opg_path)).convert("RGB")
    w, h = minimap.size
    print(f"Minimap: {w}x{h}")

    # World bounds from tree info
    cx, cz = data.tree_info.center
    ex, ez = data.tree_info.extents
    world_min_x = cx - ex
    world_max_x = cx + ex
    world_min_z = cz - ez
    world_max_z = cz + ez

    def world_to_pixel(wx, wz):
        px = (wx - world_min_x) / (world_max_x - world_min_x) * (w - 1)
        py = (wz - world_min_z) / (world_max_z - world_min_z) * (h - 1)
        return int(px), int(py)

    # Create side-by-side comparison: minimap | overlay | dots-only
    out_w = w * 3 + 4  # 2px gap between each
    out = Image.new("RGB", (out_w, h), (32, 32, 32))

    # Left panel: original minimap
    out.paste(minimap, (0, 0))

    # Middle panel: minimap with dots overlaid
    overlay = minimap.copy()
    draw_overlay = ImageDraw.Draw(overlay)

    # Right panel: dots on black background
    dots_only = Image.new("RGB", (w, h), (0, 0, 0))
    draw_dots = ImageDraw.Draw(dots_only)

    r = args.dot_size

    # Plot objects (yellow)
    for obj in data.objects:
        px, py = world_to_pixel(obj.transform[12], obj.transform[14])
        draw_overlay.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 0))
        draw_dots.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 0))

    # Plot portals (cyan)
    if args.include_portals:
        for portal in data.portals:
            px, py = world_to_pixel(portal.transform[12], portal.transform[14])
            draw_overlay.ellipse([px - r, py - r, px + r, py + r], fill=(0, 255, 255))
            draw_dots.ellipse([px - r, py - r, px + r, py + r], fill=(0, 255, 255))

    # Plot triggers (magenta)
    if args.include_triggers:
        for trigger in data.triggers:
            px, py = world_to_pixel(trigger.transform[12], trigger.transform[14])
            draw_overlay.ellipse([px - r, py - r, px + r, py + r], fill=(255, 0, 255))
            draw_dots.ellipse([px - r, py - r, px + r, py + r], fill=(255, 0, 255))

    out.paste(overlay, (w + 2, 0))
    out.paste(dots_only, (w * 2 + 4, 0))

    output_path = args.output or f"/tmp/{args.map_code}_validation.png"
    out.save(output_path)
    print(f"Saved: {output_path} ({out_w}x{h})")
    print(f"Layout: [minimap] | [minimap + dots] | [dots only]")
    print(f"Colors: yellow=objects ({len(data.objects)})", end="")
    if args.include_portals:
        print(f", cyan=portals ({len(data.portals)})", end="")
    if args.include_triggers:
        print(f", magenta=triggers ({len(data.triggers)})", end="")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
