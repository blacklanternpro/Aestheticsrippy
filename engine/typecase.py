"""
The type cabinet: every typeface a Rip pack can use, with the metrics the
harvester needs to match type in a reference image.

The cabinet is the single source for fonts/fonts.css and fonts/catalogue.json:

    python -m engine.typecase        # rewrite both from the woff2 files

Everything here is self-hosted and SIL OFL 1.1 (see fonts/README.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

FONTS = Path(__file__).resolve().parent.parent / "fonts"

# family, category, CSS fallback, faces: (file, weights "lo hi" or single, style),
# stretch range (Archivo only), and the weights/widths the matcher tries.
CABINET: List[Dict] = [
    {"family": "Inter", "category": "neo-grotesque", "generic": "sans-serif",
     "faces": [("Inter-var.woff2", (100, 900), "normal"), ("Inter-Italic-var.woff2", (100, 900), "italic")],
     "try": {"weight": [300, 400, 500, 600, 700, 800, 900]}},
    {"family": "Inter Tight", "category": "neo-grotesque", "generic": "sans-serif",
     "faces": [("InterTight-var.woff2", (100, 900), "normal")],
     "try": {"weight": [400, 500, 700, 800, 900]}},
    {"family": "Arimo", "category": "neo-grotesque", "generic": "sans-serif",
     "faces": [("Arimo-var.woff2", (400, 700), "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "Archivo", "category": "grotesque", "generic": "sans-serif",
     "faces": [("Archivo-var.woff2", (100, 900), "normal")], "stretch": (62, 125),
     "try": {"weight": [400, 600, 800], "stretch": [62, 75, 100, 125]}},
    {"family": "Archivo Black", "category": "grotesque", "generic": "sans-serif",
     "faces": [("ArchivoBlack-Regular.woff2", 400, "normal")],
     "try": {"weight": [400]}},
    {"family": "Space Grotesk", "category": "grotesque", "generic": "sans-serif",
     "faces": [("SpaceGrotesk-var.woff2", (300, 700), "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "Jost", "category": "geometric", "generic": "sans-serif",
     "faces": [("Jost-var.woff2", (100, 900), "normal"), ("Jost-Italic-var.woff2", (100, 900), "italic")],
     "try": {"weight": [300, 400, 500, 700]}},
    {"family": "Unbounded", "category": "wide", "generic": "sans-serif",
     "faces": [("Unbounded-var.woff2", (200, 900), "normal")],
     "try": {"weight": [400, 700, 900]}},
    {"family": "Oswald", "category": "condensed", "generic": "sans-serif",
     "faces": [("Oswald-var.woff2", (200, 700), "normal")],
     "try": {"weight": [300, 500, 700]}},
    {"family": "Anton", "category": "condensed", "generic": "sans-serif",
     "faces": [("Anton-Regular.woff2", 400, "normal")],
     "try": {"weight": [400]}},
    {"family": "Big Shoulders Display", "category": "condensed", "generic": "sans-serif",
     "faces": [("BigShouldersDisplay-var.woff2", (100, 900), "normal")],
     "try": {"weight": [400, 700, 900]}},
    {"family": "Big Shoulders Stencil Display", "category": "stencil", "generic": "sans-serif",
     "faces": [("BigShouldersStencilDisplay-var.woff2", (100, 900), "normal")],
     "try": {"weight": [700, 900]}},
    {"family": "Tinos", "category": "serif", "generic": "serif",
     "faces": [("Tinos-Regular.woff2", 400, "normal"), ("Tinos-Bold.woff2", 700, "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "Newsreader", "category": "serif", "generic": "serif",
     "faces": [("Newsreader-var.woff2", (200, 800), "normal")],
     "try": {"weight": [400, 600]}},
    {"family": "EB Garamond", "category": "oldstyle", "generic": "serif",
     "faces": [("EBGaramond-var.woff2", (400, 800), "normal")],
     "try": {"weight": [400, 600]}},
    {"family": "Bodoni Moda", "category": "didone", "generic": "serif",
     "faces": [("BodoniModa-var.woff2", (400, 900), "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "JetBrains Mono", "category": "mono", "generic": "monospace",
     "faces": [("JetBrainsMono-var.woff2", (100, 800), "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "Space Mono", "category": "mono", "generic": "monospace",
     "faces": [("SpaceMono-Regular.woff2", 400, "normal"), ("SpaceMono-Bold.woff2", 700, "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "Courier Prime", "category": "typewriter", "generic": "monospace",
     "faces": [("CourierPrime-Regular.woff2", 400, "normal"), ("CourierPrime-Bold.woff2", 700, "normal")],
     "try": {"weight": [400, 700]}},
    {"family": "Mrs Saint Delafield", "category": "script", "generic": "cursive",
     "faces": [("MrsSaintDelafield-Regular.woff2", 400, "normal")],
     "try": {"weight": [400]}, "match": False},
]


def _metrics(path: Path) -> Dict:
    from fontTools.ttLib import TTFont

    t = TTFont(str(path))
    upm = t["head"].unitsPerEm
    os2 = t["OS/2"]
    # Chromium uses the typo metrics when USE_TYPO_METRICS is set, else hhea.
    if os2.fsSelection & (1 << 7):
        asc, desc = os2.sTypoAscender, -os2.sTypoDescender
    else:
        asc, desc = t["hhea"].ascent, -t["hhea"].descent
    cap = getattr(os2, "sCapHeight", 0) or 0
    xh = getattr(os2, "sxHeight", 0) or 0
    glyf = t.getGlyphSet()
    cmap = t.getBestCmap()
    if not cap and ord("H") in cmap:
        from fontTools.pens.boundsPen import BoundsPen
        pen = BoundsPen(glyf)
        glyf[cmap[ord("H")]].draw(pen)
        cap = pen.bounds[3] if pen.bounds else 0
    return {"upm": upm, "ascent": round(asc / upm, 4), "descent": round(desc / upm, 4),
            "cap": round(cap / upm, 4), "x": round(xh / upm, 4)}


def build() -> Dict:
    """Rewrite fonts/catalogue.json and fonts/fonts.css from the cabinet."""
    families = []
    css = ["/* Self-hosted fonts (SIL Open Font License 1.1, see README.md).",
           "   Generated by `python -m engine.typecase`; edit the cabinet there. */"]
    for fam in CABINET:
        faces = []
        for file, weight, style in fam["faces"]:
            path = FONTS / file
            if not path.exists():
                raise FileNotFoundError(path)
            w = f"{weight[0]} {weight[1]}" if isinstance(weight, tuple) else str(weight)
            rule = [f"  font-family: '{fam['family']}';", f"  src: url('{file}') format('woff2');",
                    f"  font-weight: {w};", f"  font-style: {style};"]
            if fam.get("stretch"):
                rule.append(f"  font-stretch: {fam['stretch'][0]}% {fam['stretch'][1]}%;")
            rule.append("  font-display: block;")
            css.append("@font-face {\n" + "\n".join(rule) + "\n}")
            faces.append({"file": file, "weight": list(weight) if isinstance(weight, tuple) else [weight, weight],
                          "style": style})
        m = _metrics(FONTS / fam["faces"][0][0])
        families.append({
            "family": fam["family"], "category": fam["category"], "generic": fam["generic"],
            "faces": faces, "stretch": list(fam["stretch"]) if fam.get("stretch") else None,
            "try": fam["try"], "match": fam.get("match", True), "metrics": m,
        })
    catalogue = {"families": families}
    (FONTS / "catalogue.json").write_text(json.dumps(catalogue, indent=2) + "\n")
    (FONTS / "fonts.css").write_text("\n".join(css) + "\n")
    return catalogue


_CACHE: Optional[Dict] = None


def catalogue() -> Dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads((FONTS / "catalogue.json").read_text())
    return _CACHE


def family(name: str) -> Dict:
    for fam in catalogue()["families"]:
        if fam["family"] == name:
            return fam
    raise KeyError(name)


def metrics(name: str) -> Dict:
    return family(name)["metrics"]


if __name__ == "__main__":
    cat = build()
    print(f"{len(cat['families'])} families -> fonts/catalogue.json, fonts/fonts.css")
