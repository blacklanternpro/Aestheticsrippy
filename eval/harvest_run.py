"""
Score the harvester: rip every reference from scratch and score the result.

    python -m eval.harvest_run                 # all references
    python -m eval.harvest_run lsd-event-poster drumaq-tour-poster
    python -m eval.harvest_run --save          # record eval/harvest-baseline.json

Packs are written to eval/harvest-out/<pack>/ (git-ignored) with a diff image
beside each, so the hand-made packs in design-packs/ are never touched.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from engine.harvest.pipeline import harvest  # noqa: E402
from engine.render import Renderer  # noqa: E402
from eval.fidelity import diff_image  # noqa: E402
from eval.run import PACKS_DIR, find_reference, load_baseline, reference_crop  # noqa: E402

OUT = BASE / "eval" / "harvest-out"
SAVED = BASE / "eval" / "harvest-baseline.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("packs", nargs="*")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args(argv)
    dirs = [p for p in sorted(PACKS_DIR.iterdir()) if find_reference(p)]
    if a.packs:
        dirs = [p for p in dirs if p.name in a.packs]
    base = load_baseline()
    prev = json.loads(SAVED.read_text())["packs"] if SAVED.exists() else {}
    rows = {}
    OUT.mkdir(parents=True, exist_ok=True)
    with Renderer() as r:
        for p in dirs:
            t = time.time()
            try:
                res = harvest(find_reference(p), p.name.replace("-", " ").title(), out_dir=OUT / p.name,
                              pack_id=p.name, crop=reference_crop(p), renderer=r, refine_rounds=a.rounds)
            except Exception as e:  # keep going; report it
                print(f"  FAIL  {p.name}: {e}", flush=True)
                rows[p.name] = {"error": str(e)}
                continue
            ref = (res.pack_dir / "assets" / "reference.jpg").read_bytes()
            from engine.harvest.refine import render_rip
            import numpy as np
            img = cv2.imdecode(np.frombuffer(ref, np.uint8), cv2.IMREAD_COLOR)
            ren = render_rip(res.rip, res.data, res.pack_dir, r, (img.shape[1], img.shape[0]))
            cv2.imwrite(str(OUT / f"{p.name}.png"),
                        diff_image(ref, cv2.imencode(".png", ren)[1].tobytes(), height=900))
            n_text = sum(1 for f in res.rip["frames"] if f.get("type") == "text")
            rows[p.name] = {"score": round(res.score, 1), "live": round(res.live, 3), "styles": len(res.rip["styles"]),
                            "text_frames": n_text, "frames": len(res.rip["frames"]),
                            "seconds": round(time.time() - t, 1)}
            b = base.get(p.name)
            was = prev.get(p.name, {}).get("score")
            print(f"  {res.score:5.1f}  (hand/legacy {b if b is not None else '-':>5}"
                  f"{'' if was is None else f', last {was:5.1f}'})  {p.name}  "
                  f"[live {res.live:4.0%}, {len(res.rip['styles'])} styles, {n_text} texts, {time.time() - t:.0f}s]", flush=True)
    scores = [v["score"] for v in rows.values() if "score" in v]
    if scores:
        lives = [v["live"] for v in rows.values() if "live" in v]
        print(f"  mean {sum(scores) / len(scores):.1f} over {len(scores)}, live {sum(lives) / len(lives):.0%}")
    if a.save:
        SAVED.write_text(json.dumps({"recorded": time.strftime("%Y-%m-%d"), "packs": {**prev, **rows}},
                                    indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
