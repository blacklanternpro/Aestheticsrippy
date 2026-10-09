"""
Aestheticsrippy - eval harness.

Renders every Design Pack that has a reference image, scores the render
against it, and writes a report plus a diff image per pack.

    python -m eval.run                    # score everything, compare to baseline
    python -m eval.run --pack lsd-event-poster
    python -m eval.run --save-baseline    # record current scores as the baseline

Outputs land in eval/out/ (git-ignored):
    report.md        ranked table with sub-scores and deltas vs baseline
    report.json      the same, machine-readable
    <pack>.png       reference | render | ink overlay (red = missing, blue = extra)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import cv2

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine.render import Renderer  # noqa: E402
from eval.fidelity import diff_image, score  # noqa: E402

PACKS_DIR = BASE_DIR / "design-packs"
OUT_DIR = BASE_DIR / "eval" / "out"
BASELINE = BASE_DIR / "eval" / "baseline.json"
REFERENCE_NAMES = ("reference.jpg", "reference.jpeg", "reference.png", "reference.webp")


def find_reference(pack_dir: Path) -> Optional[Path]:
    for name in REFERENCE_NAMES:
        p = pack_dir / "assets" / name
        if p.exists():
            return p
    return None


def evaluate(pack_ids: Optional[List[str]] = None) -> List[Dict]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pack_dirs = [p for p in sorted(PACKS_DIR.iterdir()) if (p / "template.html").exists()]
    if pack_ids:
        pack_dirs = [p for p in pack_dirs if p.name in pack_ids]

    rows: List[Dict] = []
    with Renderer() as renderer:
        for pack_dir in pack_dirs:
            ref_path = find_reference(pack_dir)
            result = renderer.render_pack(pack_dir, pdf=True)
            row: Dict = {
                "pack": pack_dir.name,
                "pages": result.pages,
                "overflow": result.overflow,
                "sheet_mm": [result.width_mm, result.height_mm],
                "errors": result.errors,
            }
            if ref_path:
                ref_bytes = ref_path.read_bytes()
                row.update(score(ref_bytes, result.png).as_dict())
                cv2.imwrite(str(OUT_DIR / f"{pack_dir.name}.png"), diff_image(ref_bytes, result.png))
            rows.append(row)
            label = f"{row['score']:5.1f}" if "score" in row else "  n/a"
            print(f"  {label}  {pack_dir.name}", flush=True)
    return rows


def load_baseline() -> Dict[str, float]:
    if not BASELINE.exists():
        return {}
    return {k: v["score"] for k, v in json.loads(BASELINE.read_text()).get("packs", {}).items()}


def write_report(rows: List[Dict], baseline: Dict[str, float]) -> str:
    scored = sorted((r for r in rows if "score" in r), key=lambda r: -r["score"])
    unscored = [r for r in rows if "score" not in r]

    def delta(r: Dict) -> str:
        if r["pack"] not in baseline:
            return ""
        d = r["score"] - baseline[r["pack"]]
        return f"{d:+.1f}" if abs(d) >= 0.05 else "0.0"

    mean = sum(r["score"] for r in scored) / len(scored) if scored else 0.0
    base_mean = (sum(baseline[r["pack"]] for r in scored if r["pack"] in baseline)
                 / max(1, sum(1 for r in scored if r["pack"] in baseline))) if baseline else None

    lines = [
        f"# Fidelity report — {date.today().isoformat()}",
        "",
        f"Mean score **{mean:.1f}** across {len(scored)} referenced packs"
        + (f" (baseline {base_mean:.1f}, {mean - base_mean:+.1f})" if base_mean is not None else "")
        + ".",
        "",
        "Score: 0 = no better than blank paper in the right colour, 100 = identical. "
        "Sub-scores are raw 0-100: layout (where ink sits), structure (edges), "
        "tone (palette), aspect (proportions).",
        "",
        "| Pack | Score | Δ | Layout | Structure | Tone | Aspect | Sheet |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in scored:
        sheet = "1 page" if r["pages"] == 1 and not r["overflow"] else (
            f"{r['pages']} pages" if r["pages"] != 1 else "overflows")
        lines.append(
            f"| {r['pack']} | {r['score']:.1f} | {delta(r)} | {r['layout']:.0f} | "
            f"{r['structure']:.0f} | {r['tone']:.0f} | {r['aspect']:.0f} | {sheet} |"
        )
    if unscored:
        lines += ["", "Packs without a reference image (render checks only): "
                  + ", ".join(f"{r['pack']} ({r['pages']} page{'s' if r['pages'] != 1 else ''})"
                              for r in unscored) + "."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Aestheticsrippy fidelity eval")
    parser.add_argument("--pack", action="append", help="Only evaluate this pack (repeatable)")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Record these scores as eval/baseline.json")
    args = parser.parse_args(argv)

    print("Rendering and scoring packs...")
    rows = evaluate(args.pack)
    baseline = load_baseline()

    report = write_report(rows, baseline)
    (OUT_DIR / "report.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("\n" + report)
    print(f"Diff images and report: {OUT_DIR}")

    if args.save_baseline:
        payload = {
            "recorded": date.today().isoformat(),
            "packs": {r["pack"]: {k: r[k] for k in ("score", "layout", "structure", "tone", "aspect")}
                      for r in rows if "score" in r},
        }
        BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline saved to {BASELINE.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
