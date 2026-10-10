"""
Aestheticsrippy - type fitting.

Measures real rendered text with the self-hosted fonts and solves for the
point size that makes a line match a width measured off a reference. This is
the deterministic half of ripping: a model can say "light geometric caps", but
only measurement can say "43.6pt".

    from engine.fit import size_for_width
    size_for_width("JULIANA", 62.0, font="Jost", weight=300)      # -> point size

Width scales linearly with size when tracking is in em, so one measurement at
100pt per sample is exact.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_CSS = BASE_DIR / "fonts" / "fonts.css"
PX_PER_MM = 96 / 25.4


def measure(samples: Sequence[Dict]) -> List[Dict]:
    """
    Each sample: {"text", "font", "weight"?, "stretch"?, "tracking"? (em), "case"?, "italic"?,
    "size"? (pt, default 100)}.
    Returns per sample: width_mm normalised to 100pt (advance width, trailing tracking removed).

    Measure near the real size: fonts with an optical-size axis (Inter) set
    wider at text sizes than at display sizes, so a 100pt measurement can be
    several percent off for 10pt text. The solvers below iterate for this.
    """
    spans = []
    for i, s in enumerate(samples):
        css = [
            f"font-family:'{s['font']}'", f"font-size:{s.get('size', 100)}pt", "white-space:pre",
            "text-rendering:geometricPrecision", "font-optical-sizing:auto",
            f"font-weight:{s.get('weight', 400)}", f"letter-spacing:{s.get('tracking', 0)}em",
            "font-kerning:normal",
        ]
        if s.get("stretch"):
            css.append(f"font-stretch:{s['stretch']}%")
        if s.get("italic"):
            css.append("font-style:italic")
        if s.get("case") == "upper":
            css.append("text-transform:uppercase")
        spans.append(f'<div><span id="s{i}" style="{";".join(css)}">{html.escape(s["text"])}</span></div>')

    page_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS_CSS.as_uri()}"></head><body style="margin:0">{''.join(spans)}</body></html>"""

    tmp = BASE_DIR / "fonts" / ".measure.html"
    tmp.write_text(page_html, encoding="utf-8")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(tmp.as_uri())
            page.evaluate("document.fonts.ready.then(() => true)")
            results = page.evaluate("""(n) => {
              const out = [];
              for (let i = 0; i < n; i++) {
                const el = document.getElementById('s' + i);
                const cs = getComputedStyle(el);
                const tracking = parseFloat(cs.letterSpacing) || 0;
                const range = document.createRange();
                range.selectNodeContents(el);
                const r = range.getBoundingClientRect();
                out.push({ width: r.width - tracking });
              }
              return out;
            }""", len(samples))
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)

    return [{"width_mm": r["width"] / PX_PER_MM * 100.0 / s.get("size", 100)}
            for r, s in zip(results, samples)]


def size_for_width(text: str, width_mm: float, **style) -> float:
    """Point size at which `text` sets exactly `width_mm` wide."""
    return sizes_for_widths([dict(style, text=text, width_mm=width_mm)])[0]


def sizes_for_widths(items: Sequence[Dict], rounds: int = 3) -> List[float]:
    """Batch version: each item has the sample keys plus 'width_mm' (target)."""
    sizes = [it.get("size", 100.0) for it in items]
    for _ in range(rounds):  # re-measure at the solved size (optical sizing)
        widths = measure([dict(it, size=sz) for it, sz in zip(items, sizes)])
        sizes = [100.0 * it["width_mm"] / w["width_mm"] for it, w in zip(items, widths)]
    return [round(s, 2) for s in sizes]


CAP_HEIGHT = {"Inter": 0.7275, "Inter Tight": 0.7275, "Jost": 0.70, "Archivo": 0.705}


def size_for_cap_height(cap_mm: float, font: str) -> float:
    """Point size whose capital height is `cap_mm` (from the font's OS/2 table)."""
    return round(cap_mm / (CAP_HEIGHT[font] * 25.4 / 72), 2)


def size_range_for_breaks(lines: Sequence[str], width_mm: float, **style) -> tuple:
    """
    Given the line breaks of a ragged or justified paragraph in a reference,
    return the (min, max) point size that reproduces them in a column of
    `width_mm`: every line must fit, and no line may also fit its successor's
    first word. Exact break points pin the size far tighter than glyph heights
    measured off a low-resolution image.
    """
    guess = style.pop("size", None)
    lo = hi = None
    for _ in range(2 if guess is None else 1):  # second pass at the solved size
        lo, hi = _break_bounds(lines, width_mm, guess or 100.0, style)
        guess = (lo + hi) / 2 if hi != float("inf") else lo
    return round(lo, 2), round(hi, 2)


def _break_bounds(lines: Sequence[str], width_mm: float, size: float, style: Dict) -> tuple:
    samples, kinds = [], []
    for i, line in enumerate(lines):
        # A laid-out line also carries the tracking after its last glyph.
        samples.append(dict(style, text=line.rstrip(), size=size))
        kinds.append(("fits", i))
        if i + 1 < len(lines):
            nxt = lines[i + 1].split()[0]
            samples.append(dict(style, text=f"{line.rstrip()} {nxt}", size=size))
            kinds.append(("overflows", i))
    widths = measure(samples)
    lo, hi = 0.0, float("inf")
    track_mm = style.get("tracking", 0) * size * 25.4 / 72
    for (kind, _), w in zip(kinds, widths):
        size_at_width = 100.0 * (width_mm - track_mm) / w["width_mm"]
        if kind == "fits":
            hi = min(hi, size_at_width)
        else:
            lo = max(lo, size_at_width)
    return lo, hi


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(measure(json.loads(sys.argv[1])), indent=2))
