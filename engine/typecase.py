"""
The type cabinet: every typeface a Rip pack can use, and the measurements the
harvester needs to match type in a reference image.

    python -m engine.typecase              # rebuild fonts.css + catalogues from fonts/
    python -m engine.typecase --fetch DIR  # (maintainers) copy faces in from unpacked
                                           # npm Fontsource packages in DIR, then rebuild

Three generated files:

    fonts/fonts.css         @font-face for every file
    fonts/catalogue.json    families, faces, axes, categories (the studio reads this)
    fonts/matcher.json      per instance (family x weight x width): cap and x-height,
                            and every glyph's advance and ink area, so the harvester can
                            shortlist faces before it renders any

Everything here is SIL OFL 1.1 (Latin subsets from Google Fonts via Fontsource).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FONTS = Path(__file__).resolve().parent.parent / "fonts"

# slug, family, category. Order is the order the studio lists them in, within a category.
SOURCES: List[Tuple[str, str, str]] = [
    # neo-grotesque and grotesque
    ("inter", "Inter", "neo-grotesque"), ("inter-tight", "Inter Tight", "neo-grotesque"),
    ("arimo", "Arimo", "neo-grotesque"), ("public-sans", "Public Sans", "neo-grotesque"),
    ("ibm-plex-sans", "IBM Plex Sans", "neo-grotesque"), ("geist", "Geist", "neo-grotesque"),
    ("roboto-flex", "Roboto Flex", "neo-grotesque"),
    ("work-sans", "Work Sans", "grotesque"), ("manrope", "Manrope", "grotesque"),
    ("schibsted-grotesk", "Schibsted Grotesk", "grotesque"), ("hanken-grotesk", "Hanken Grotesk", "grotesque"),
    ("instrument-sans", "Instrument Sans", "grotesque"), ("familjen-grotesk", "Familjen Grotesk", "grotesque"),
    ("bricolage-grotesque", "Bricolage Grotesque", "grotesque"), ("host-grotesk", "Host Grotesk", "grotesque"),
    ("onest", "Onest", "grotesque"), ("red-hat-display", "Red Hat Display", "grotesque"),
    ("space-grotesk", "Space Grotesk", "grotesque"), ("archivo", "Archivo", "grotesque"),
    ("archivo-black", "Archivo Black", "grotesque"), ("chivo", "Chivo", "grotesque"),
    ("mona-sans", "Mona Sans", "grotesque"), ("hubot-sans", "Hubot Sans", "grotesque"),
    ("epilogue", "Epilogue", "grotesque"), ("barlow", "Barlow", "grotesque"),
    ("encode-sans", "Encode Sans", "grotesque"),
    # geometric and humanist
    ("jost", "Jost", "geometric"), ("figtree", "Figtree", "geometric"), ("dm-sans", "DM Sans", "geometric"),
    ("albert-sans", "Albert Sans", "geometric"), ("sora", "Sora", "geometric"), ("poppins", "Poppins", "geometric"),
    ("montserrat", "Montserrat", "geometric"), ("outfit", "Outfit", "geometric"), ("urbanist", "Urbanist", "geometric"),
    ("league-spartan", "League Spartan", "geometric"), ("raleway", "Raleway", "geometric"),
    ("josefin-sans", "Josefin Sans", "geometric"), ("questrial", "Questrial", "geometric"),
    ("rubik", "Rubik", "geometric"), ("tenor-sans", "Tenor Sans", "humanist"),
    # condensed
    ("oswald", "Oswald", "condensed"), ("anton", "Anton", "condensed"), ("bebas-neue", "Bebas Neue", "condensed"),
    ("league-gothic", "League Gothic", "condensed"), ("archivo-narrow", "Archivo Narrow", "condensed"),
    ("ibm-plex-sans-condensed", "IBM Plex Sans Condensed", "condensed"),
    ("barlow-condensed", "Barlow Condensed", "condensed"), ("barlow-semi-condensed", "Barlow Semi Condensed", "condensed"),
    ("roboto-condensed", "Roboto Condensed", "condensed"), ("saira", "Saira", "condensed"),
    ("fjalla-one", "Fjalla One", "condensed"), ("pathway-gothic-one", "Pathway Gothic One", "condensed"),
    ("antonio", "Antonio", "condensed"), ("teko", "Teko", "condensed"),
    ("sofia-sans-condensed", "Sofia Sans Condensed", "condensed"),
    ("sofia-sans-extra-condensed", "Sofia Sans Extra Condensed", "condensed"),
    ("mohave", "Mohave", "condensed"), ("six-caps", "Six Caps", "condensed"),
    ("big-shoulders-display", "Big Shoulders Display", "condensed"),
    # wide
    ("unbounded", "Unbounded", "wide"), ("syne", "Syne", "wide"), ("krona-one", "Krona One", "wide"),
    ("lexend-zetta", "Lexend Zetta", "wide"), ("michroma", "Michroma", "wide"),
    ("dela-gothic-one", "Dela Gothic One", "wide"), ("rubik-mono-one", "Rubik Mono One", "wide"),
    ("bowlby-one", "Bowlby One", "wide"), ("syncopate", "Syncopate", "wide"), ("orbitron", "Orbitron", "wide"),
    ("zen-dots", "Zen Dots", "wide"),
    # serif
    ("tinos", "Tinos", "serif"), ("newsreader", "Newsreader", "serif"), ("source-serif-4", "Source Serif 4", "serif"),
    ("literata", "Literata", "serif"), ("lora", "Lora", "serif"), ("libre-baskerville", "Libre Baskerville", "serif"),
    ("spectral", "Spectral", "serif"), ("ibm-plex-serif", "IBM Plex Serif", "serif"), ("pt-serif", "PT Serif", "serif"),
    ("instrument-serif", "Instrument Serif", "serif"), ("fraunces", "Fraunces", "serif"),
    ("young-serif", "Young Serif", "serif"), ("libre-caslon-text", "Libre Caslon Text", "serif"),
    ("libre-caslon-display", "Libre Caslon Display", "serif"),
    # old-style
    ("eb-garamond", "EB Garamond", "oldstyle"), ("cormorant", "Cormorant", "oldstyle"),
    ("cormorant-garamond", "Cormorant Garamond", "oldstyle"), ("crimson-pro", "Crimson Pro", "oldstyle"),
    # didone
    ("bodoni-moda", "Bodoni Moda", "didone"), ("playfair-display", "Playfair Display", "didone"),
    ("dm-serif-display", "DM Serif Display", "didone"), ("abril-fatface", "Abril Fatface", "didone"),
    ("gloock", "Gloock", "didone"), ("noto-serif-display", "Noto Serif Display", "didone"),
    ("old-standard-tt", "Old Standard TT", "didone"),
    # slab
    ("bitter", "Bitter", "slab"), ("roboto-slab", "Roboto Slab", "slab"), ("zilla-slab", "Zilla Slab", "slab"),
    ("arvo", "Arvo", "slab"), ("josefin-slab", "Josefin Slab", "slab"), ("alfa-slab-one", "Alfa Slab One", "slab"),
    ("ultra", "Ultra", "slab"),
    # mono and typewriter
    ("jetbrains-mono", "JetBrains Mono", "mono"), ("space-mono", "Space Mono", "mono"),
    ("ibm-plex-mono", "IBM Plex Mono", "mono"), ("dm-mono", "DM Mono", "mono"), ("geist-mono", "Geist Mono", "mono"),
    ("fira-code", "Fira Code", "mono"), ("source-code-pro", "Source Code Pro", "mono"),
    ("roboto-mono", "Roboto Mono", "mono"), ("martian-mono", "Martian Mono", "mono"),
    ("azeret-mono", "Azeret Mono", "mono"), ("red-hat-mono", "Red Hat Mono", "mono"),
    ("spline-sans-mono", "Spline Sans Mono", "mono"), ("chivo-mono", "Chivo Mono", "mono"),
    ("xanh-mono", "Xanh Mono", "mono"), ("major-mono-display", "Major Mono Display", "mono"),
    ("share-tech-mono", "Share Tech Mono", "mono"), ("anonymous-pro", "Anonymous Pro", "mono"),
    ("courier-prime", "Courier Prime", "typewriter"), ("cutive-mono", "Cutive Mono", "typewriter"),
    ("special-elite", "Special Elite", "typewriter"),
    # pixel and dot
    ("vt323", "VT323", "pixel"), ("silkscreen", "Silkscreen", "pixel"), ("press-start-2p", "Press Start 2P", "pixel"),
    ("pixelify-sans", "Pixelify Sans", "pixel"), ("dotgothic16", "DotGothic16", "pixel"), ("doto", "Doto", "pixel"),
    ("jersey-10", "Jersey 10", "pixel"),
    # stencil
    ("big-shoulders-stencil-display", "Big Shoulders Stencil Display", "stencil"),
    ("stardos-stencil", "Stardos Stencil", "stencil"), ("allerta-stencil", "Allerta Stencil", "stencil"),
    ("saira-stencil-one", "Saira Stencil One", "stencil"),
    # display
    ("tilt-warp", "Tilt Warp", "display"), ("bungee", "Bungee", "display"), ("bungee-shade", "Bungee Shade", "display"),
    ("bungee-inline", "Bungee Inline", "display"), ("monoton", "Monoton", "display"),
    ("rubik-glitch", "Rubik Glitch", "display"), ("climate-crisis", "Climate Crisis", "display"),
    # bubble
    ("rubik-bubbles", "Rubik Bubbles", "bubble"), ("bagel-fat-one", "Bagel Fat One", "bubble"),
    ("modak", "Modak", "bubble"), ("titan-one", "Titan One", "bubble"), ("shrikhand", "Shrikhand", "bubble"),
    ("chango", "Chango", "bubble"),
    # blackletter
    ("unifrakturmaguntia", "UnifrakturMaguntia", "blackletter"), ("unifrakturcook", "UnifrakturCook", "blackletter"),
    ("pirata-one", "Pirata One", "blackletter"), ("grenze-gotisch", "Grenze Gotisch", "blackletter"),
    ("new-rocker", "New Rocker", "blackletter"), ("jacquard-24", "Jacquard 24", "blackletter"),
    # script and hand
    ("mrs-saint-delafield", "Mrs Saint Delafield", "script"), ("pinyon-script", "Pinyon Script", "script"),
    ("great-vibes", "Great Vibes", "script"), ("herr-von-muellerhoff", "Herr Von Muellerhoff", "script"),
    ("monsieur-la-doulaise", "Monsieur La Doulaise", "script"), ("allura", "Allura", "script"),
    ("parisienne", "Parisienne", "script"), ("italianno", "Italianno", "script"),
    ("caveat", "Caveat", "hand"), ("homemade-apple", "Homemade Apple", "hand"),
    ("reenie-beanie", "Reenie Beanie", "hand"), ("permanent-marker", "Permanent Marker", "hand"),
    ("rock-salt", "Rock Salt", "hand"), ("la-belle-aurore", "La Belle Aurore", "hand"),
]

GENERIC = {"serif": "serif", "oldstyle": "serif", "didone": "serif", "slab": "serif",
           "mono": "monospace", "typewriter": "monospace", "script": "cursive", "hand": "cursive"}
CATEGORY_NAMES = {
    "neo-grotesque": "Neo-grotesque", "grotesque": "Grotesque", "geometric": "Geometric", "humanist": "Humanist",
    "condensed": "Condensed", "wide": "Wide", "serif": "Serif", "oldstyle": "Old-style", "didone": "Didone",
    "slab": "Slab", "mono": "Mono", "typewriter": "Typewriter", "pixel": "Pixel", "stencil": "Stencil",
    "display": "Display", "bubble": "Bubble", "blackletter": "Blackletter", "script": "Script", "hand": "Hand",
}
# Characters the matcher predicts widths and ink for.
CHARS = [chr(c) for c in range(32, 127)] + list("éèàüöä€£©®°–—‘’“”•×")
TRY_WEIGHTS = (300, 400, 500, 700, 900)
TRY_WIDTHS = (62.5, 75, 87.5, 100, 112.5, 125, 150)


def _file_stem(family: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", family)


# ------------------------------------------------------------------- fetch

def fetch(npm_dir: Path) -> List[str]:
    """Copy Latin woff2 faces from unpacked Fontsource packages into fonts/."""
    missing = []
    for slug, family, _ in SOURCES:
        pkgs = sorted(p for p in npm_dir.glob(f"fontsource-variable-{slug}-[0-9]*") if p.is_dir()) or \
            sorted(p for p in npm_dir.glob(f"fontsource-{slug}-[0-9]*") if p.is_dir())
        if not pkgs:
            missing.append(slug)
            continue
        files = pkgs[-1] / "package" / "files"
        stem = _file_stem(family)
        variable = "variable" in pkgs[-1].name
        for style in ("normal", "italic"):
            if variable:
                for kind in ("full", "standard", "wght"):
                    src = files / f"{slug}-latin-{kind}-{style}.woff2"
                    if src.exists():
                        shutil.copyfile(src, FONTS / f"{stem}-{'Italic-' if style == 'italic' else ''}var.woff2")
                        break
            else:
                for src in sorted(files.glob(f"{slug}-latin-[0-9]*-{style}.woff2")):
                    w = re.search(r"-latin-(\d+)-", src.name).group(1)
                    if style == "italic" and w not in ("400", "700"):
                        continue
                    shutil.copyfile(src, FONTS / f"{stem}-{w}{'-Italic' if style == 'italic' else ''}.woff2")
    return missing


# ------------------------------------------------------------------- build

def _faces(family: str) -> List[Dict]:
    """Discover a family's files: [{file, style, weight: [lo, hi], axes}]."""
    from fontTools.ttLib import TTFont

    stem = _file_stem(family)
    out = []
    for path in sorted(FONTS.glob(f"{stem}-*.woff2")):
        name = path.name[len(stem) + 1:-6]
        if not re.fullmatch(r"(Italic-)?var|\d+(-Italic)?", name):
            continue  # another family that shares a prefix (Inter vs InterTight)
        style = "italic" if "Italic" in name else "normal"
        t = TTFont(str(path), lazy=True)
        axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in t["fvar"].axes} if "fvar" in t else {}
        if "wght" in axes:
            weight = [int(axes["wght"][0]), int(axes["wght"][2])]
        else:
            w = int(t["OS/2"].usWeightClass) if not name[0].isdigit() else int(name.split("-")[0])
            weight = [w, w]
        out.append({"file": path.name, "style": style, "weight": weight,
                    "axes": {k: [v[0], v[2]] for k, v in axes.items()}})
    return out


def _metrics(path: Path) -> Dict:
    from fontTools.ttLib import TTFont

    t = TTFont(str(path))
    upm = t["head"].unitsPerEm
    os2 = t["OS/2"]
    if os2.fsSelection & (1 << 7):  # USE_TYPO_METRICS: Chromium uses typo, else hhea
        asc, desc = os2.sTypoAscender, -os2.sTypoDescender
    else:
        asc, desc = t["hhea"].ascent, -t["hhea"].descent
    return {"upm": upm, "ascent": round(asc / upm, 4), "descent": round(desc / upm, 4)}


def _instance_metrics(path: Path, location: Dict[str, float]) -> Optional[Dict]:
    """cap, x and per-character advance and ink area (em units) at one design-space location."""
    from fontTools.pens.areaPen import AreaPen
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    t = TTFont(str(path))
    upm = t["head"].unitsPerEm
    cmap = t.getBestCmap()
    gs = t.getGlyphSet(location=location) if location else t.getGlyphSet()

    def bounds(ch):
        if ord(ch) not in cmap:
            return None
        pen = BoundsPen(gs)
        gs[cmap[ord(ch)]].draw(pen)
        return pen.bounds

    def height(chars):
        hs = [b[3] for b in (bounds(c) for c in chars) if b]
        return sorted(hs)[len(hs) // 2] / upm if hs else None

    cap = height("HEIZT")
    xh = height("xzvwu")
    if not cap:
        return None
    adv, area = {}, {}
    for ch in CHARS:
        if ord(ch) not in cmap:
            continue
        g = gs[cmap[ord(ch)]]
        adv[ch] = round(g.width / upm, 4)
        if ch == " ":
            area[ch] = 0.0
            continue
        pen = AreaPen(gs)
        g.draw(pen)
        area[ch] = round(abs(pen.value) / upm / upm, 5)
    return {"cap": round(cap, 4), "x": round(xh, 4) if xh else round(cap * 0.7, 4), "adv": adv, "area": area}


def _tries(face: Dict) -> List[Tuple[int, Optional[float]]]:
    lo, hi = face["weight"]
    weights = [w for w in TRY_WEIGHTS if lo <= w <= hi] or [lo]
    if lo == hi:
        weights = [lo]
    wd = face["axes"].get("wdth")
    widths: List[Optional[float]] = [None]
    if wd:
        inside = [w for w in TRY_WIDTHS if wd[0] <= w <= wd[1]]
        picks = {inside[0], inside[-1], 100.0 if wd[0] <= 100 <= wd[1] else inside[len(inside) // 2]}
        if len(inside) >= 5:
            picks.add(inside[1])
            picks.add(inside[-2])
        widths = sorted(picks)
    return [(w, s) for w in weights for s in widths]


def build(verbose: bool = False) -> Dict:
    families = []
    css = ["/* Self-hosted fonts (SIL Open Font License 1.1, see README.md).",
           "   Generated by `python -m engine.typecase`; edit SOURCES there. */"]
    matcher = []
    for slug, family, category in SOURCES:
        faces = _faces(family)
        if not faces:
            if verbose:
                print(f"  (no files) {family}")
            continue
        for f in faces:
            w = f"{f['weight'][0]} {f['weight'][1]}" if f["weight"][0] != f["weight"][1] else str(f["weight"][0])
            rule = [f"  font-family: '{family}';", f"  src: url('{f['file']}') format('woff2');",
                    f"  font-weight: {w};", f"  font-style: {f['style']};"]
            if "wdth" in f["axes"]:
                rule.append(f"  font-stretch: {f['axes']['wdth'][0]:g}% {f['axes']['wdth'][1]:g}%;")
            rule.append("  font-display: block;")
            css.append("@font-face {\n" + "\n".join(rule) + "\n}")
        upright = [f for f in faces if f["style"] == "normal"] or faces
        lo = min(f["weight"][0] for f in upright)
        hi = max(f["weight"][1] for f in upright)
        wdth = next((f["axes"]["wdth"] for f in upright if "wdth" in f["axes"]), None)
        base = _metrics(FONTS / upright[0]["file"])
        tries = []
        for face in upright:
            for weight, width in _tries(face):
                loc = {}
                if "wght" in face["axes"]:
                    loc["wght"] = weight
                if width is not None:
                    loc["wdth"] = width
                if "opsz" in face["axes"]:
                    loc["opsz"] = max(face["axes"]["opsz"][0], min(face["axes"]["opsz"][1], 14))
                m = _instance_metrics(FONTS / face["file"], loc)
                if m:
                    tries.append({"weight": weight, "stretch": width})
                    matcher.append({"family": family, "weight": weight, "stretch": width, **m})
        cap = next((x for x in matcher if x["family"] == family), {})
        families.append({
            "family": family, "category": category, "generic": GENERIC.get(category, "sans-serif"),
            "faces": [{"file": f["file"], "style": f["style"], "weight": f["weight"]} for f in faces],
            "weights": [lo, hi], "stretch": wdth, "italic": any(f["style"] == "italic" for f in faces),
            "metrics": {**base, "cap": cap.get("cap", 0.7), "x": cap.get("x", 0.5)},
            "try": tries,
        })
        if verbose:
            print(f"  {family}: {len(faces)} files, {len(tries)} instances")
    cat = {"categories": CATEGORY_NAMES, "families": families}
    (FONTS / "catalogue.json").write_text(json.dumps(cat, indent=1) + "\n")
    (FONTS / "matcher.json").write_text(json.dumps({"chars": "".join(CHARS), "instances": matcher}) + "\n")
    (FONTS / "fonts.css").write_text("\n".join(css) + "\n")
    _write_generic_map(families)
    return cat


def _write_generic_map(families: List[Dict]) -> None:
    """Keep the renderer's fallback map (family -> generic) in step with the cabinet."""
    renderer = FONTS.parent / "studio" / "js" / "rip-renderer.js"
    s = renderer.read_text()
    lines, cur = [], "   "
    for f in families:
        if f["generic"] == "sans-serif":
            continue  # the default
        e = f' "{f["family"]}": "{f["generic"]}",'
        if len(cur) + len(e) > 100:
            lines.append(cur)
            cur = "   "
        cur += e
    lines.append(cur)
    block = "const GENERIC = { // generated by engine/typecase.py; anything else falls back to sans-serif\n" + \
        "\n".join(lines) + "\n  };"
    s = re.sub(r"const GENERIC = \{.*?\};", lambda m: block, s, count=1, flags=re.S)
    renderer.write_text(s)


# ------------------------------------------------------------------- read

_CACHE: Dict[str, Dict] = {}


def catalogue() -> Dict:
    if "cat" not in _CACHE:
        _CACHE["cat"] = json.loads((FONTS / "catalogue.json").read_text())
    return _CACHE["cat"]


def matcher_data() -> Dict:
    if "m" not in _CACHE:
        _CACHE["m"] = json.loads((FONTS / "matcher.json").read_text())
    return _CACHE["m"]


def family(name: str) -> Dict:
    for fam in catalogue()["families"]:
        if fam["family"] == name:
            return fam
    raise KeyError(name)


def metrics(name: str) -> Dict:
    return family(name)["metrics"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", type=Path, help="folder of unpacked Fontsource npm packages")
    a = ap.parse_args()
    if a.fetch:
        missing = fetch(a.fetch)
        if missing:
            print("missing packages:", ", ".join(missing))
    cat = build(verbose=True)
    n = len(json.loads((FONTS / "matcher.json").read_text())["instances"])
    print(f"{len(cat['families'])} families, {n} matcher instances")
