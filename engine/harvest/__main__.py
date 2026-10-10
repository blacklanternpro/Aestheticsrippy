"""
python -m engine.harvest path/to/reference.jpg --name "My Poster" [--id my-poster]
       [--out design-packs/my-poster] [--crop x0,y0,x1,y1] [--rounds 3]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import harvest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rip a reference image into a Rip pack")
    ap.add_argument("image", type=Path)
    ap.add_argument("--name", help="pack name (default: the file name)")
    ap.add_argument("--id", help="pack id (default: from the name)")
    ap.add_argument("--out", type=Path, help="output folder (default: design-packs/<id>)")
    ap.add_argument("--crop", help="sheet crop in the image: x0,y0,x1,y1")
    ap.add_argument("--rounds", type=int, default=3, help="render-and-verify rounds (0 to skip)")
    a = ap.parse_args(argv)
    name = a.name or a.image.stem.replace("-", " ").replace("_", " ").title()
    crop = [int(v) for v in a.crop.split(",")] if a.crop else None
    res = harvest(a.image, name, out_dir=a.out, pack_id=a.id, crop=crop, refine_rounds=a.rounds,
                  progress=lambda m: print(f"  {m}", flush=True))
    print(f"{res.pack_dir}  score {res.score:.1f}  ({res.seconds:.0f}s)")
    for n in res.notes:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
