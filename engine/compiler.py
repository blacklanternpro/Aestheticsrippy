"""
Aestheticsrippy - CLI compiler.

Renders Design Packs to vector PDF (and a PNG preview) with headless Chromium.

    python -m engine.compiler --pack studio-neue
    python -m engine.compiler --all
    python -m engine.compiler --pack studio-neue --output ~/Desktop/invoice.pdf --png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine.render import Renderer  # noqa: E402
from engine.schema import DesignPackSpec  # noqa: E402

PACKS_DIR = BASE_DIR / "design-packs"
EXPORT_DIR = BASE_DIR / "export"


def list_packs() -> List[str]:
    return sorted(p.name for p in PACKS_DIR.iterdir()
                  if p.is_dir() and (p / "pack.json").exists())


def validate_pack(pack_id: str) -> DesignPackSpec:
    spec_path = PACKS_DIR / pack_id / "pack.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"Pack '{pack_id}' not found at {spec_path}")
    return DesignPackSpec.from_dict(json.loads(spec_path.read_text(encoding="utf-8")))


def compile_pack(renderer: Renderer, pack_id: str, output_pdf: Optional[Path] = None,
                 png: bool = False) -> Dict:
    spec = validate_pack(pack_id)
    result = renderer.render_pack(PACKS_DIR / pack_id, pdf=True)

    EXPORT_DIR.mkdir(exist_ok=True)
    output_pdf = Path(output_pdf).expanduser() if output_pdf else EXPORT_DIR / f"{pack_id}.pdf"
    output_pdf.write_bytes(result.pdf)
    if png:
        output_pdf.with_suffix(".png").write_bytes(result.png)

    dims = spec.target.dimensions
    size_ok = (abs(result.width_mm - dims.width_mm) < 1.0
               and abs(result.height_mm - dims.height_mm) < 1.0)
    status = "OK" if result.single_sheet and size_ok else "WARN"
    notes = []
    if result.pages != 1:
        notes.append(f"{result.pages} pages")
    if result.overflow:
        notes.append("content overflows sheet")
    if not size_ok:
        notes.append(f"sheet {result.width_mm}x{result.height_mm}mm, "
                     f"spec {dims.width_mm}x{dims.height_mm}mm")
    notes += result.errors
    print(f"[{status}] {pack_id:34s} -> {output_pdf.name}"
          + (f"  ({'; '.join(notes)})" if notes else ""))
    return {"pack": pack_id, "status": status, "pages": result.pages, "notes": notes}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Aestheticsrippy compiler")
    parser.add_argument("--pack", help="Design Pack id to compile")
    parser.add_argument("--all", action="store_true", help="Compile every pack")
    parser.add_argument("--output", help="Output PDF path (single pack only)")
    parser.add_argument("--png", action="store_true", help="Also write a PNG preview")
    args = parser.parse_args(argv)

    packs = [args.pack] if args.pack and not args.all else list_packs()
    with Renderer() as renderer:
        results = [compile_pack(renderer, p,
                                args.output if len(packs) == 1 else None,
                                png=args.png)
                   for p in packs]

    warned = [r for r in results if r["status"] != "OK"]
    print(f"\n{len(results) - len(warned)}/{len(results)} packs compiled to a single clean sheet.")
    return 1 if warned else 0


if __name__ == "__main__":
    sys.exit(main())
