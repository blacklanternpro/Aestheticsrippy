"""
Aestheticsrippy - the Rip document and its renderer.

A Rip separates a design into three things that change at different rates:

  styles   the typography: named type styles (font, size in pt, weight,
           width, tracking, leading, case, alignment, colour)
  frames   the layout: absolutely placed boxes in millimetres, and flowing
           stacks/rows/repeats inside them
  data     the content: plain JSON that frames bind to by path

So a ripped resume is a real template: swap the data and the design holds.

Frame types
-----------
  text    {"type":"text", "style":"body", "bind":"person.name" | "text":"Hi {person.first}"}
  image   {"type":"image", "bind":"person.photo", "fit":"cover", "filter":"grayscale"}
  rule    {"type":"rule", "w":8, "weight":0.6, "align":"center"}      # w in mm, weight in pt
  space   {"type":"space", "h":4}                                      # mm
  stack   {"type":"stack", "gap":2, "children":[...]}                  # vertical flow
  row     {"type":"row", "cols":["16mm","1fr"], "gap":3, "children":[...]}   # grid
          {"type":"row", "justify":"space-between", "children":[...]}       # flex
  repeat  {"type":"repeat", "bind":"experience", "gap":4, "item":{...}}    # one item per list entry

Any frame may be placed with x/y/w/h (mm) at the top level (or "place":"absolute"
inside a stack), and may carry "z", "id" and "with" (inline style overrides).
Inside a repeat, a bind starting with "." is relative to the current item.
A frame whose bound value is missing or empty is left out ("keep": true keeps it).

A stack with a fixed height may declare "fit": {"min": 0.85}; its type then
shrinks in 1% steps until it fits, never below the minimum. Anything that still
overflows is reported.

CLI
---
  python -m engine.rip build saraiva-resume          # write template.html from default data
  python -m engine.rip build --all
  python -m engine.rip render saraiva-resume --data content/private/resume.json --out export/resume.pdf --png
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

PACKS_DIR = BASE_DIR / "design-packs"
FONTS_CSS = BASE_DIR / "fonts" / "fonts.css"

GENERIC = {"Inter": "sans-serif", "Inter Tight": "sans-serif", "Archivo": "sans-serif", "Jost": "sans-serif",
           "Mrs Saint Delafield": "cursive"}

_MISSING = object()


class RipError(ValueError):
    pass


# --------------------------------------------------------------------------
# Data binding
# --------------------------------------------------------------------------

def resolve(path: str, root: Any, item: Any = None) -> Any:
    """Resolve 'a.b.0.c' against root, or '.c' against the current repeat item."""
    if path in (".", "$item"):
        return item
    if path.startswith("."):
        node, parts = item, path[1:].split(".")
    else:
        node, parts = root, path.lstrip("$").lstrip(".").split(".")
    for part in parts:
        if part == "":
            continue
        if isinstance(node, dict):
            node = node.get(part, _MISSING)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return _MISSING
        if node is _MISSING:
            return _MISSING
    return node


_TEMPLATE_RE = re.compile(r"\{([^{}]+)\}")


def interpolate(template: str, root: Any, item: Any) -> str:
    def sub(m):
        v = resolve(m.group(1).strip(), root, item)
        return "" if v is _MISSING or v is None else str(v)
    return _TEMPLATE_RE.sub(sub, template)


def is_empty(v: Any) -> bool:
    return v is _MISSING or v is None or v == "" or v == [] or v == {}


# --------------------------------------------------------------------------
# Styles -> CSS
# --------------------------------------------------------------------------

STYLE_KEYS = {
    "font", "size", "weight", "stretch", "italic", "leading", "tracking", "case",
    "align", "align_last", "color", "hyphenate", "wrap", "word_spacing", "numeric",
    "scale_x", "scale_y", "extends", "indent", "opacity",
}


def resolve_style(styles: Dict[str, Dict], name_or_names: Any, overrides: Optional[Dict] = None) -> Dict:
    names = name_or_names if isinstance(name_or_names, list) else ([name_or_names] if name_or_names else [])
    out: Dict[str, Any] = {}

    def apply(name: str, seen: tuple = ()):
        if name in seen:
            raise RipError(f"style cycle at '{name}'")
        if name not in styles:
            raise RipError(f"unknown style '{name}'")
        s = styles[name]
        if "extends" in s:
            apply(s["extends"], seen + (name,))
        out.update({k: v for k, v in s.items() if k != "extends"})

    for n in names:
        apply(n)
    if overrides:
        out.update(overrides)
    unknown = set(out) - STYLE_KEYS
    if unknown:
        raise RipError(f"unknown style keys: {sorted(unknown)}")
    return out


def color_value(c: Optional[str], tokens: Dict[str, str]) -> Optional[str]:
    if c is None:
        return None
    return tokens.get(c, c)


def style_css(s: Dict, tokens: Dict[str, str]) -> List[str]:
    css: List[str] = []
    if "font" in s:
        fam = s["font"]
        css.append(f"font-family: '{fam}', {GENERIC.get(fam, 'sans-serif')}")
    if "size" in s:
        css.append(f"font-size: calc({s['size']}pt * var(--fit, 1))")
    if "weight" in s:
        css.append(f"font-weight: {s['weight']}")
    if "stretch" in s:
        css.append(f"font-stretch: {s['stretch']}%")
    if s.get("italic"):
        css.append("font-style: italic")
    if "leading" in s:
        css.append(f"line-height: {s['leading']}")
    if "tracking" in s:
        css.append(f"letter-spacing: {s['tracking']}em")
    if "word_spacing" in s:
        css.append(f"word-spacing: {s['word_spacing']}em")
    case = s.get("case")
    if case in ("upper", "lower"):
        css.append(f"text-transform: {case}case")
    elif case == "title":
        css.append("text-transform: capitalize")
    if "align" in s:
        css.append(f"text-align: {s['align']}")
    if "align_last" in s:
        css.append(f"text-align-last: {s['align_last']}")
    if s.get("hyphenate"):
        css.append("hyphens: manual")  # soft hyphens are inserted by hyphenate()
    if "wrap" in s:  # balance | pretty
        css.append(f"text-wrap: {s['wrap']}")
    if s.get("numeric") == "tabular":
        css.append("font-variant-numeric: tabular-nums")
    if "indent" in s:
        css.append(f"text-indent: {s['indent']}mm")
    if "opacity" in s:
        css.append(f"opacity: {s['opacity']}")
    col = color_value(s.get("color"), tokens)
    if col:
        css.append(f"color: {col}")
    return css


NBSP, WJ = "\u00a0", "\u2060"


def typeset(text: str) -> str:
    """
    Small typographic courtesies that hold for any content:
    - a spaced en dash binds to the word before it ("LF – Forklift" never
      starts a line with the dash);
    - an em dash binds to the word before it, so lines break after it, not before;
    - a lone short word at a paragraph end binds to its neighbour (no one-letter orphans).
    """
    text = re.sub(r" ([–-]) ", NBSP + r"\1 ", text)
    text = re.sub(r"(\S)—", r"\1" + WJ + "—", text)
    text = re.sub(r" (\S{1,2}[.,;:!?]?)$", NBSP + r"\1", text, flags=re.M)
    return text


_HYPHENATORS: Dict[str, Any] = {}
SHY = "\u00ad"


def hyphenate(text: str, lang: str = "en") -> str:
    """
    Insert soft hyphens (shown only where a line breaks). Done here rather than
    with CSS hyphens:auto because headless Chromium on Linux ships without
    hyphenation dictionaries, and output must be identical on every machine.
    """
    try:
        import pyphen
    except ImportError:  # optional dependency: fall back to no hyphenation
        return text
    code = {"en": "en_GB"}.get(lang, lang)
    if code not in _HYPHENATORS:
        _HYPHENATORS[code] = pyphen.Pyphen(lang=code, left=3, right=3)
    hy = _HYPHENATORS[code]

    def word(m):
        w = m.group(0)
        return hy.inserted(w, hyphen=SHY) if len(w) >= 7 else w

    return re.sub(r"[A-Za-z\u00C0-\u024F]+", word, text)


def mm(v: Any) -> str:
    if isinstance(v, (int, float)):
        return f"{v}mm"
    return str(v)


# --------------------------------------------------------------------------
# Frame rendering
# --------------------------------------------------------------------------

class Builder:
    def __init__(self, rip: Dict, data: Dict, asset_dirs: List[Path], out_dir: Path):
        self.rip = rip
        self.data = data
        self.styles = rip.get("styles", {})
        self.tokens = rip.get("tokens", {})
        self.asset_dirs = asset_dirs
        self.out_dir = out_dir
        self._auto_id = 0

    # -- helpers -----------------------------------------------------------

    def next_id(self, kind: str) -> str:
        self._auto_id += 1
        return f"{kind}-{self._auto_id}"

    def place_css(self, f: Dict, absolute: bool) -> List[str]:
        css: List[str] = []
        if absolute:
            css.append("position: absolute")
            if "x" in f:
                css.append(f"left: {mm(f['x'])}")
            if "y" in f:
                css.append(f"top: {mm(f['y'])}")
            if "right" in f:
                css.append(f"right: {mm(f['right'])}")
            if "bottom" in f:
                css.append(f"bottom: {mm(f['bottom'])}")
        if "w" in f:
            css.append(f"width: {mm(f['w'])}")
        if "h" in f:
            css.append(f"height: {mm(f['h'])}")
        if "z" in f:
            css.append(f"z-index: {int(f['z'])}")
        for side in ("mt", "mb"):
            if side in f:
                css.append(f"margin-{'top' if side == 'mt' else 'bottom'}: {mm(f[side])}")
        if "pad" in f:
            css.append(f"padding: {mm(f['pad'])}")
        if "rotate" in f:
            css.append(f"transform: rotate({f['rotate']}deg)")
        return css

    def bound_value(self, f: Dict, item: Any) -> Any:
        if "bind" in f:
            return resolve(f["bind"], self.data, item)
        if "text" in f:
            return interpolate(f["text"], self.data, item)
        return _MISSING

    def find_asset(self, ref: str) -> Optional[str]:
        if re.match(r"^(https?:|data:)", ref):
            return ref
        for d in self.asset_dirs:
            p = (d / ref).resolve()
            if p.exists():
                return Path(os.path.relpath(p, self.out_dir)).as_posix()
        return None

    # -- frames ------------------------------------------------------------

    def render(self, f: Dict, item: Any = None, absolute: bool = False, inherited: Optional[Dict] = None) -> str:
        kind = f.get("type", "text")
        fn = getattr(self, f"r_{kind}", None)
        if fn is None:
            raise RipError(f"unknown frame type '{kind}'")
        return fn(f, item, absolute or f.get("place") == "absolute")

    def attrs(self, f: Dict, kind: str, css: List[str], extra_class: str = "") -> str:
        fid = f.get("id") or self.next_id(kind)
        cls = f"rip-{kind}" + (f" {extra_class}" if extra_class else "") + (
            f" {f['class']}" if f.get("class") else "")
        style = "; ".join(css)
        return f'data-frame="{html.escape(fid)}" class="{cls}"' + (f' style="{style}"' if style else "")

    def r_text(self, f: Dict, item: Any, absolute: bool) -> str:
        value = self.bound_value(f, item)
        if is_empty(value) and not f.get("keep"):
            return ""
        if isinstance(value, list):
            value = f.get("join", "\n").join(str(v) for v in value if not is_empty(v))
        text = "" if is_empty(value) else str(value)
        if f.get("prefix") and text:
            text = f["prefix"] + text
        if f.get("suffix") and text:
            text = text + f["suffix"]

        s = resolve_style(self.styles, f.get("style"), f.get("with"))
        css = self.place_css(f, absolute) + style_css(s, self.tokens)
        if f.get("typeset", True):
            text = typeset(text)
        if s.get("hyphenate"):
            text = hyphenate(text, self.rip.get("lang", "en"))
        body = "<br>".join(html.escape(line) for line in text.split("\n"))

        sx, sy = s.get("scale_x"), s.get("scale_y")
        if sx or sy:
            origin = {"center": "center", "right": "right"}.get(s.get("align", "left"), "left")
            tf = f"scale({sx or 1}, {sy or 1})"
            body = (f'<span class="rip-scaled" style="display:inline-block; transform:{tf}; '
                    f'transform-origin:{origin} bottom">{body}</span>')
        tag = f.get("tag", "div")
        return f"<{tag} {self.attrs(f, 'text', css)}>{body}</{tag}>"

    def r_image(self, f: Dict, item: Any, absolute: bool) -> str:
        ref = self.bound_value(f, item) if ("bind" in f or "text" in f) else f.get("src", _MISSING)
        if is_empty(ref):
            return ""
        src = self.find_asset(str(ref))
        if not src:
            raise RipError(f"image asset not found: {ref}")
        css = self.place_css(f, absolute)
        img_css = [f"object-fit: {f.get('fit', 'cover')}",
                   f"object-position: {f.get('position', 'center')}",
                   "width: 100%", "height: 100%", "display: block"]
        if f.get("filter") == "grayscale":
            img_css.append("filter: grayscale(1)")
        elif f.get("filter"):
            img_css.append(f"filter: {f['filter']}")
        return (f"<div {self.attrs(f, 'image', css)}>"
                f'<img src="{html.escape(src)}" alt="" style="{"; ".join(img_css)}"></div>')

    def r_rule(self, f: Dict, item: Any, absolute: bool) -> str:
        css = self.place_css({k: v for k, v in f.items() if k != "w"}, absolute)
        weight = f.get("weight", 0.5)
        col = color_value(f.get("color", "ink"), self.tokens) or "currentColor"
        css += [f"border-top: {weight}pt solid {col}", "height: 0"]
        w = f.get("w")
        css.append(f"width: {mm(w)}" if w is not None else "width: 100%")
        align = f.get("align", "left")
        if align == "center":
            css.append("margin-left: auto; margin-right: auto")
        elif align == "right":
            css.append("margin-left: auto")
        return f"<div {self.attrs(f, 'rule', css)}></div>"

    def r_space(self, f: Dict, item: Any, absolute: bool) -> str:
        return f'<div class="rip-space" style="height: {mm(f.get("h", 2))}; flex: none"></div>'

    def _children(self, f: Dict, item: Any) -> str:
        return "".join(self.render(c, item) for c in f.get("children", []))

    def r_stack(self, f: Dict, item: Any, absolute: bool) -> str:
        inner = self._children(f, item)
        if not inner and not f.get("keep"):
            return ""
        s = resolve_style(self.styles, f.get("style"), f.get("with")) if (f.get("style") or f.get("with")) else {}
        css = self.place_css(f, absolute) + style_css(s, self.tokens)
        css += ["display: flex", "flex-direction: column", f"gap: {mm(f.get('gap', 0))}"]
        if f.get("justify"):
            css.append(f"justify-content: {f['justify']}")
        if f.get("items"):
            css.append(f"align-items: {f['items']}")
        extra = ""
        fit = f.get("fit")
        if fit:
            css += ["overflow: hidden", "--fit: 1"]
            extra = "rip-fit"
        fid_attr = self.attrs(f, "stack", css, extra)
        if fit:
            fid_attr += f' data-fit-min="{float(fit.get("min", 0.85))}"'
            if fit.get("group"):
                fid_attr += f' data-fit-group="{html.escape(str(fit["group"]))}"'
        return f"<div {fid_attr}>{inner}</div>"

    def r_row(self, f: Dict, item: Any, absolute: bool) -> str:
        inner = self._children(f, item)
        if not inner and not f.get("keep"):
            return ""
        s = resolve_style(self.styles, f.get("style"), f.get("with")) if (f.get("style") or f.get("with")) else {}
        css = self.place_css(f, absolute) + style_css(s, self.tokens)
        if "cols" in f:
            cols = " ".join(mm(c) for c in f["cols"])
            css += ["display: grid", f"grid-template-columns: {cols}",
                    f"column-gap: {mm(f.get('gap', 0))}", f"align-items: {f.get('align', 'start')}"]
        else:
            css += ["display: flex", f"justify-content: {f.get('justify', 'space-between')}",
                    f"align-items: {f.get('align', 'baseline')}", f"gap: {mm(f.get('gap', 0))}"]
        return f"<div {self.attrs(f, 'row', css)}>{inner}</div>"

    def r_repeat(self, f: Dict, item: Any, absolute: bool) -> str:
        items = resolve(f["bind"], self.data, item)
        if is_empty(items):
            return ""
        if not isinstance(items, list):
            raise RipError(f"repeat bind '{f['bind']}' is not a list")
        template = f.get("item")
        if not template:
            raise RipError("repeat needs an 'item' frame")
        parts = []
        for entry in items:
            child = copy.deepcopy(template)
            child.pop("id", None)
            parts.append(self.render(child, entry))
        css = self.place_css(f, absolute) + ["display: flex", "flex-direction: column",
                                             f"gap: {mm(f.get('gap', 0))}"]
        return f"<div {self.attrs(f, 'repeat', css)}>{''.join(parts)}</div>"

    # -- document ----------------------------------------------------------

    def document(self) -> str:
        page = self.rip["page"]
        w, h = page["width_mm"], page["height_mm"]
        paper = color_value(page.get("paper", "#ffffff"), self.tokens)
        ink = color_value(page.get("ink", "ink"), self.tokens) or "#000"
        base = resolve_style(self.styles, "base") if "base" in self.styles else {}
        base_css = "; ".join(style_css(base, self.tokens))

        frames = "\n".join(self.render(f, None, absolute=True) for f in self.rip.get("frames", []))
        fonts_href = Path(os.path.relpath(FONTS_CSS, self.out_dir)).as_posix()
        title = html.escape(self.rip.get("name", self.rip.get("id", "Rip")))

        return f"""<!DOCTYPE html>
<html lang="{html.escape(self.rip.get('lang', 'en'))}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<!-- Generated by engine/rip.py from rip.json. Edit the rip or the data, not this file. -->
<link rel="stylesheet" href="{fonts_href}">
<style>
@page {{ size: {w}mm {h}mm; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: #d9d9d6; }}
body {{ display: flex; justify-content: center; -webkit-print-color-adjust: exact; print-color-adjust: exact;
        text-rendering: geometricPrecision; -webkit-font-smoothing: antialiased; font-kerning: normal;
        font-optical-sizing: auto; }}
.page-sheet {{ position: relative; width: {w}mm; height: {h}mm; overflow: hidden;
              background: {paper}; color: {ink}; {base_css} }}
.rip-text {{ overflow-wrap: break-word; }}
.rip-image img {{ user-select: none; }}
@media print {{
  html, body {{ background: transparent; }}
  body {{ display: block; }}
}}
</style>
</head>
<body>
<main class="page-sheet" data-rip="{html.escape(self.rip.get('id', ''))}">
{frames}
</main>
<script>
{FIT_SCRIPT}
</script>
</body>
</html>
"""


FIT_SCRIPT = r"""
(function () {
  function overflows(el) {
    return el.scrollHeight > el.clientHeight + 0.5 || el.scrollWidth > el.clientWidth + 0.5;
  }
  function run() {
    var report = { fit: {}, overflow: [] };
    document.querySelectorAll('.rip-fit').forEach(function (el) {
      var min = parseFloat(el.dataset.fitMin || '0.85');
      var scale = 1;
      el.style.setProperty('--fit', '1');
      while (overflows(el) && scale - 0.01 >= min - 1e-9) {
        scale = Math.round((scale - 0.01) * 100) / 100;
        el.style.setProperty('--fit', String(scale));
      }
      report.fit[el.dataset.frame] = scale;
    });
    // Frames in a fit group share the smallest scale, so body type stays one size.
    var groups = {};
    document.querySelectorAll('.rip-fit[data-fit-group]').forEach(function (el) {
      var g = el.dataset.fitGroup, s = report.fit[el.dataset.frame];
      groups[g] = Math.min(groups[g] === undefined ? 1 : groups[g], s);
    });
    document.querySelectorAll('.rip-fit[data-fit-group]').forEach(function (el) {
      var s = groups[el.dataset.fitGroup];
      el.style.setProperty('--fit', String(s));
      report.fit[el.dataset.frame] = s;
    });
    document.querySelectorAll('[data-frame]').forEach(function (el) {
      if (el.style.height && overflows(el)) report.overflow.push(el.dataset.frame);
    });
    var sheet = document.querySelector('.page-sheet');
    if (sheet && overflows(sheet)) report.overflow.push('page-sheet');
    window.__ripReport = report;
    document.documentElement.dataset.ripReady = '1';
  }
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(run);
})();
"""


# --------------------------------------------------------------------------
# Loading and building
# --------------------------------------------------------------------------

def load_rip(pack_dir: Path, variant: Optional[str] = None) -> Dict:
    path = pack_dir / "rip.json"
    if not path.exists():
        raise FileNotFoundError(f"No rip.json in {pack_dir}")
    rip = json.loads(path.read_text(encoding="utf-8"))
    for key in ("id", "page", "frames"):
        if key not in rip:
            raise RipError(f"rip.json missing '{key}'")
    if variant:
        rip = apply_variant(rip, variant)
    return rip


def apply_variant(rip: Dict, name: str) -> Dict:
    """
    A variant re-arranges the same design for different content: it patches
    top-level frames by id and styles by name, leaving everything else alone.

        "variants": {"dense": {"description": "...",
                               "frames": {"col-left": {"y": 86, "h": 140}},
                               "styles": {"summary": {"size": 11}}}}
    """
    variants = rip.get("variants", {})
    if name not in variants:
        raise RipError(f"unknown variant '{name}' (have: {', '.join(variants) or 'none'})")
    out = copy.deepcopy(rip)
    v = variants[name]
    by_id = {f.get("id"): f for f in out["frames"]}
    for fid, patch in v.get("frames", {}).items():
        if fid not in by_id:
            raise RipError(f"variant '{name}' patches unknown frame '{fid}'")
        by_id[fid].update(patch)
    for sname, patch in v.get("styles", {}).items():
        out.setdefault("styles", {}).setdefault(sname, {}).update(patch)
    out["variant"] = name
    return out


def build_html(pack_dir: Path, data: Dict, out_path: Path, data_dir: Optional[Path] = None,
               variant: Optional[str] = None) -> str:
    rip = load_rip(pack_dir, variant)
    asset_dirs = [d for d in (data_dir, pack_dir / "assets", pack_dir) if d]
    builder = Builder(rip, data, asset_dirs, out_path.parent.resolve())
    doc = builder.document()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return doc


def build_pack(pack_dir: Path) -> Path:
    data_path = pack_dir / "default-data.json"
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}
    out = pack_dir / "template.html"
    build_html(pack_dir, data, out)
    sync_pack_json(pack_dir)
    return out


def sync_pack_json(pack_dir: Path) -> None:
    """Keep pack.json (read by the studio and compiler) in step with rip.json."""
    rip = load_rip(pack_dir)
    spec_path = pack_dir / "pack.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
    page = rip["page"]
    spec.update({
        "id": rip["id"],
        "name": rip.get("name", rip["id"]),
        "category": rip.get("category", spec.get("category", "Editorial")),
        "description": rip.get("description", spec.get("description", "")),
        "format": "rip",
    })
    spec["target"] = {"dimensions": {
        "format": page.get("format", "Custom"),
        "width_mm": page["width_mm"], "height_mm": page["height_mm"],
        "orientation": "landscape" if page["width_mm"] > page["height_mm"] else "portrait",
    }}
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rip_packs() -> List[Path]:
    return [p for p in sorted(PACKS_DIR.iterdir()) if (p / "rip.json").exists()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build and render Rip packs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Write template.html for a pack from its default data")
    b.add_argument("pack", nargs="?")
    b.add_argument("--all", action="store_true")

    r = sub.add_parser("render", help="Render a pack with your own data to PDF")
    r.add_argument("pack")
    r.add_argument("--data", required=True, help="JSON content file")
    r.add_argument("--out", required=True, help="Output PDF path")
    r.add_argument("--png", action="store_true", help="Also write a PNG preview")
    r.add_argument("--html", action="store_true", help="Keep the built HTML next to the PDF")
    r.add_argument("--variant", help="Named layout variant from rip.json")

    args = ap.parse_args(argv)

    if args.cmd == "build":
        packs = rip_packs() if args.all or not args.pack else [PACKS_DIR / args.pack]
        for p in packs:
            print(f"[OK] built {build_pack(p).relative_to(BASE_DIR)}")
        return 0

    from engine.render import Renderer

    pack_dir = PACKS_DIR / args.pack
    data_path = Path(args.data).expanduser().resolve()
    out_pdf = Path(args.out).expanduser().resolve()
    data = json.loads(data_path.read_text(encoding="utf-8"))
    html_path = out_pdf.with_suffix(".html")
    build_html(pack_dir, data, html_path, data_dir=data_path.parent, variant=args.variant)
    with Renderer() as renderer:
        res = renderer.render_file(html_path, pack_id=args.pack)
    out_pdf.write_bytes(res.pdf)
    if args.png:
        out_pdf.with_suffix(".png").write_bytes(res.png)
    if not args.html:
        html_path.unlink()
    rep = res.report or {}
    fits = ", ".join(f"{k} {v:.2f}" for k, v in rep.get("fit", {}).items() if v < 1)
    status = "OK" if res.single_sheet and not rep.get("overflow") else "WARN"
    print(f"[{status}] {out_pdf}  pages={res.pages}"
          + (f"  type scaled: {fits}" if fits else "")
          + (f"  OVERFLOW: {', '.join(rep['overflow'])}" if rep.get("overflow") else ""))
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
