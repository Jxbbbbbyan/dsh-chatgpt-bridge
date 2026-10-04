"""Slice the task's long screenshot into readable, uploadable pieces.

The source is 640x8260. A chat UI downscales an image that tall until its text is
illegible, so the material is delivered as overlapping vertical slices instead: each
slice stays under ~1.8k px on its long side, which survives downscaling.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("source.jpg")
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("slices")
SLICE_HEIGHT = 1700
OVERLAP = 100


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(SOURCE)
    width, height = image.size
    step = SLICE_HEIGHT - OVERLAP
    print(f"source {SOURCE.name} {width}x{height} -> slices of {SLICE_HEIGHT}px, overlap {OVERLAP}px")

    paths = []
    index = 0
    top = 0
    while top < height:
        bottom = min(height, top + SLICE_HEIGHT)
        crop = image.crop((0, top, width, bottom))
        path = OUT_DIR / f"slice-{index + 1:02d}.png"
        crop.save(path, "PNG", optimize=True)
        paths.append(path)
        print(f"  {path.name}  rows {top}-{bottom}  {crop.size[0]}x{crop.size[1]}  {path.stat().st_size} bytes")
        index += 1
        if bottom >= height:
            break
        top += step

    print(f"\n{len(paths)} slices in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
