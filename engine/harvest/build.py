"""
Assemble a Rip pack from the harvest: tokens, styles, frames, data, fields.

The aim is a pack a person would have written: a handful of named styles,
not one per line; colours as tokens; text in data, bound by key; frames in
millimetres where the reference put the ink.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..typecase import catalogue
from .art import Region, Rule
from .layout import Block
from .sheet import Sheet
from .typeface import Face, Match

PT_PER_MM = 72 / 25.4


def hexcolour(bgr: Sequence[int]) -> str:
    b, g, r = (int(v) for v in bgr[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _lab(bgr) -> np.ndarray:
    return cv2.cvtColor(np.uint8([[list(bgr)]]), cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0] * [100 / 255, 1, 1]


# ------------------------------------------------------------------- faces

def harmonise(matches: Dict[int, Match], blocks: Sequence[Block], margin: float = 0.02) -> Dict[int, Face]:
    chosen = _harmonise_family(matches, blocks, margin)
    return _harmonise_weights(matches, chosen)


def _margin(block: Block, base: float) -> float:
    """Small or short type carries little evidence: be readier to follow the document's family."""
    px = block.size
    short = sum(c.isalpha() for c in block.text()) < 8
    return base + (0.05 if px < 16 else 0.03 if px < 28 else 0.0) + (0.03 if short else 0.0)


def _harmonise_weights(matches: Dict[int, Match], chosen: Dict[int, Face]) -> Dict[int, Face]:
    """Within a family, settle on few weights: move a block to a weight already in use when nearly as good."""
    by_family: Dict[str, Dict[int, float]] = {}
    for bi, f in chosen.items():
        by_family.setdefault(f.family, {})
        by_family[f.family][f.weight] = by_family[f.family].get(f.weight, 0) + 1
    out = dict(chosen)
    for bi, f in chosen.items():
        m = matches[bi]
        counts = by_family[f.family]
        cur = m.scores.get(f.key, -1)
        for w, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            if w == f.weight or n <= counts[f.weight]:
                continue
            alt = Face(f.family, w, f.stretch)
            if alt.key in m.scores and cur - m.scores[alt.key] <= 0.02 and abs(w - f.weight) <= 200:
                out[bi] = alt
                break
    return out


def _harmonise_family(matches: Dict[int, Match], blocks: Sequence[Block], margin: float) -> Dict[int, Face]:
    """
    Designs use one or two families. Pick the family that explains the most
    text, then let a block keep a different family only when it is clearly
    better there (display type usually is the exception).
    """
    def fam_best(m: Match, family: str) -> Tuple[float, Optional[str]]:
        best, key = -1.0, None
        for k, v in m.scores.items():
            if k.split("|")[0] == family and v > best:
                best, key = v, k
        return best, key

    weight_of = {bi: max(1, len(blocks[bi].text())) for bi in matches}
    families = {k.split("|")[0] for m in matches.values() for k in m.scores}
    total = {f: sum(weight_of[bi] * max(0.0, fam_best(m, f)[0]) for bi, m in matches.items()) for f in families}
    primary = max(total, key=total.get) if total else None

    chosen: Dict[int, Face] = {}
    secondary: Dict[str, float] = {}
    for bi, m in matches.items():
        top_key = max(m.scores, key=m.scores.get)
        p_score, p_key = fam_best(m, primary) if primary else (-1, None)
        if p_key and m.scores[top_key] - p_score <= _margin(blocks[bi], margin):
            chosen[bi] = _face(p_key)
        else:
            chosen[bi] = _face(top_key)
            secondary[top_key.split("|")[0]] = secondary.get(top_key.split("|")[0], 0) + weight_of[bi]
    # Collapse several "exception" families into the strongest one where close.
    if len(secondary) > 1:
        second = max(secondary, key=secondary.get)
        for bi, face in list(chosen.items()):
            if face.family not in (primary, second):
                s_score, s_key = fam_best(matches[bi], second)
                if s_key and matches[bi].scores[_key(face)] - s_score <= _margin(blocks[bi], margin):
                    chosen[bi] = _face(s_key)
    return chosen


def _face(key: str) -> Face:
    fam, w, st = key.split("|")
    return Face(fam, int(w), int(st) if st else None)


def _key(face: Face) -> str:
    return face.key


# ------------------------------------------------------------------ colours

def _neutral_exists(clusters, order) -> bool:
    for i in order:
        lab = _lab(np.median(np.array(clusters[i]["members"]), axis=0))
        if float(np.hypot(lab[1] - 128, lab[2] - 128)) <= 25:
            return True
    return False


def colour_tokens(paper_bgr, inks: Sequence[Tuple[int, int, int]],
                  small: Optional[Sequence[bool]] = None) -> Tuple[Dict[str, str], List[str]]:
    """
    Cluster ink colours; name them ink, ink-2... (or accent when saturated).
    Small type never shows its true ink (antialiasing lightens it), so it joins
    a nearby cluster more readily. Large type is clustered first.
    """
    small = list(small) if small is not None else [False] * len(inks)
    clusters: List[Dict] = []
    assign: List[int] = [0] * len(inks)
    order = sorted(range(len(inks)), key=lambda i: (small[i], _lab(inks[i])[0]))
    for idx in order:
        c = inks[idx]
        lab = _lab(c)
        thresh = 30 if small[idx] else 14
        for i, cl in enumerate(clusters):
            if np.linalg.norm(cl["lab"] - lab) < thresh:
                if not small[idx]:
                    cl["members"].append(c)
                cl["n"] += 1
                assign[idx] = i
                break
        else:
            clusters.append({"lab": lab, "members": [c], "n": 1})
            assign[idx] = len(clusters) - 1
    order = sorted(range(len(clusters)), key=lambda i: -clusters[i]["n"])
    names: Dict[int, str] = {}
    tokens: Dict[str, str] = {"paper": hexcolour(paper_bgr)}
    n_accent = n_ink = 0
    for i in order:
        med = np.median(np.array(clusters[i]["members"]), axis=0)
        lab = _lab(med)
        chroma = float(np.hypot(lab[1] - 128, lab[2] - 128))
        if chroma > 25 and (n_ink or _neutral_exists(clusters, order)):
            n_accent += 1
            name = "accent" if n_accent == 1 else f"accent-{n_accent}"
        else:
            n_ink += 1
            name = "ink" if n_ink == 1 else f"ink-{n_ink}"
        names[i] = name
        tokens[name] = hexcolour(med)
    if "ink" not in tokens:
        tokens["ink"] = tokens.get("accent", "#111111")
    return tokens, [names[a] for a in assign]


# ------------------------------------------------------------------- styles

@dataclass
class StyleSpec:
    face: Face
    size_pt: float
    tracking: float
    leading: Optional[float]
    colour: str
    upper: bool
    members: List[int] = field(default_factory=list)
    chars: int = 0


def _round(v: float, step: float) -> float:
    return round(round(v / step) * step, 4)


ROLE_NAMES = ["display", "title", "heading", "subheading", "lead"]
SMALL_NAMES = ["small", "caption", "fine", "micro"]


def _consolidate(specs: List[StyleSpec], style_of: Dict[int, int]) -> Tuple[List[StyleSpec], Dict[int, int]]:
    """
    A style used for a word or two, close to a bigger style of the same family,
    is measurement noise rather than design: fold it in.
    """
    order = sorted(range(len(specs)), key=lambda i: specs[i].chars)
    target = {i: i for i in range(len(specs))}
    for i in order:
        a = specs[i]
        if a.chars >= 40:
            continue
        best, dist = None, None
        for j, b in enumerate(specs):
            if j == i or target[j] != j or b.chars <= a.chars:
                continue
            if b.face.family != a.face.family or b.colour != a.colour or b.upper != a.upper:
                continue
            if abs(b.face.weight - a.face.weight) > 200 or abs(b.size_pt / a.size_pt - 1) > 0.16:
                continue
            d = abs(np.log(b.size_pt / a.size_pt)) + abs(b.face.weight - a.face.weight) / 1000
            if dist is None or d < dist:
                best, dist = j, d
        if best is not None:
            target[i] = best
            specs[best].chars += a.chars
            specs[best].members += a.members
    keep = [i for i in range(len(specs)) if target[i] == i]
    index = {old: new for new, old in enumerate(keep)}

    def root(i):
        while target[i] != i:
            i = target[i]
        return i
    return [specs[i] for i in keep], {bi: index[root(si)] for bi, si in style_of.items()}


def name_styles(specs: List[StyleSpec]) -> List[str]:
    """body = the style with the most text; bigger ones get display roles, smaller ones small roles."""
    if not specs:
        return []
    body = max(range(len(specs)), key=lambda i: specs[i].chars)
    names = [""] * len(specs)
    names[body] = "body"
    big = sorted([i for i in range(len(specs)) if specs[i].size_pt > specs[body].size_pt * 1.05],
                 key=lambda i: -specs[i].size_pt)
    small = sorted([i for i in range(len(specs)) if specs[i].size_pt < specs[body].size_pt * 0.95],
                   key=lambda i: -specs[i].size_pt)
    same = [i for i in range(len(specs)) if not names[i] and i not in big and i not in small]
    for k, i in enumerate(big):
        names[i] = ROLE_NAMES[k] if k < len(ROLE_NAMES) else f"heading-{'bcdefghij'[(k - len(ROLE_NAMES)) % 9]}"
    for k, i in enumerate(small):
        names[i] = SMALL_NAMES[k] if k < len(SMALL_NAMES) else f"small-{'bcdefghij'[(k - len(SMALL_NAMES)) % 9]}"
    for k, i in enumerate(same):
        f = specs[i]
        bits = ["body"]
        if f.face.weight >= specs[body].face.weight + 150:
            bits.append("strong")
        elif f.face.weight <= specs[body].face.weight - 150:
            bits.append("light")
        if f.upper and not specs[body].upper:
            bits.append("caps")
        if f.colour != specs[body].colour:
            bits.append(f.colour)
        if f.face.family != specs[body].face.family:
            bits.append(re.sub(r"\W+", "-", f.face.family.lower()))
        names[i] = "-".join(bits) if len(bits) > 1 else f"body-{'bcdefghij'[k % 9]}"
    # Unique.
    seen: Dict[str, int] = {}
    for i, n in enumerate(names):
        if n in seen:
            seen[n] += 1
            names[i] = f"{n}-{'abcdefghij'[(seen[n] - 1) % 10]}"
        else:
            seen[n] = 1
    return names


# --------------------------------------------------------------------- pack

@dataclass
class Harvest:
    sheet: Sheet
    blocks: List[Block]
    matches: Dict[int, Match]
    rules: List[Rule]
    regions: List[Region]
    paper_bgr: Tuple[int, int, int]
    notes: List[str] = field(default_factory=list)
    frame_blocks: Dict[str, int] = field(default_factory=dict)


def _metrics(family: str) -> Dict:
    for f in catalogue()["families"]:
        if f["family"] == family:
            return f["metrics"]
    raise KeyError(family)


def _block_colour(b: Block):
    cols = np.array([r.ink.colour for r in b.runs if r.ink])
    return tuple(int(v) for v in np.median(cols, axis=0))


def _borrow_matches(h: "Harvest") -> None:
    """Blocks too short to match on their own (a lone '1') take the face of the nearest-sized block."""
    matched = [bi for bi in h.matches]
    if not matched:
        return
    for bi, b in enumerate(h.blocks):
        if bi in h.matches or not b.runs or b.runs[0].ink is None:
            continue
        near = min(matched, key=lambda k: abs(np.log(h.blocks[k].size / max(1e-3, b.size)))
                   + 0.3 * (abs(h.blocks[k].top - b.top) / max(1.0, h.sheet.image.shape[0])))
        m = h.matches[near]
        h.matches[bi] = Match(m.face, m.size_px * b.size / h.blocks[near].size, m.tracking_em, m.score,
                              dict(m.scores))


def first_baseline(size_px: float, leading: float, family: str) -> float:
    """Distance from a text frame's top to its first baseline, in px (CSS line box model)."""
    m = _metrics(family)
    content = (m["ascent"] + m["descent"]) * size_px
    return (leading * size_px - content) / 2 + m["ascent"] * size_px


def build_rip(h: Harvest, pack_id: str, name: str, asset_names: Dict[int, str],
              paper_image: Optional[str] = None) -> Tuple[Dict, Dict]:
    sheet = h.sheet
    mm = sheet.mm
    _borrow_matches(h)
    faces = harmonise(h.matches, h.blocks)
    blocks = [(bi, b) for bi, b in enumerate(h.blocks) if bi in faces]

    tokens, ink_names = colour_tokens(h.paper_bgr, [_block_colour(b) for _, b in blocks],
                                      [b.size < 22 for _, b in blocks])
    colour_of = {bi: ink_names[k] for k, (bi, _) in enumerate(blocks)}

    # Group blocks into styles.
    specs: List[StyleSpec] = []
    style_of: Dict[int, int] = {}
    for bi, b in blocks:
        m = h.matches[bi]
        face = faces[bi]
        # The match's size was solved for the winning face; rescale to the chosen face's metrics.
        size_px = m.size_px
        if face.family != m.face.family:
            a, c = _metrics(m.face.family), _metrics(face.family)
            ratio = (a["cap"] / c["cap"]) if (b.runs[0].ink.tall_kind == "cap") else (a["x"] / max(0.2, c["x"]))
            size_px *= ratio
        size_pt = mm(size_px) * PT_PER_MM
        leading = (b.step / size_px) if b.step else None
        letters = [c for c in b.text() if c.isalpha()]
        upper = bool(letters) and all(c.isupper() for c in letters) and len(letters) >= 2
        track = m.tracking_em if face.family == m.face.family else 0.0
        # Sizes come from heights measured in whole pixels: a pixel of x-height is ~2 px of size.
        tol = max(0.07 * size_pt, mm(2.2) * PT_PER_MM)
        for si, sp in enumerate(specs):
            if (sp.face == face and abs(sp.size_pt - size_pt) <= tol
                    and abs(sp.tracking - track) <= 0.025 and sp.colour == colour_of[bi] and sp.upper == upper):
                n = sp.chars
                c = len(b.text())
                sp.size_pt = (sp.size_pt * n + size_pt * c) / (n + c)
                sp.tracking = (sp.tracking * n + track * c) / (n + c)
                if leading:
                    sp.leading = leading if sp.leading is None else (sp.leading + leading) / 2
                sp.members.append(bi)
                sp.chars += len(b.text())
                style_of[bi] = si
                break
        else:
            specs.append(StyleSpec(face, size_pt, track, leading, colour_of[bi], upper, [bi], len(b.text())))
            style_of[bi] = len(specs) - 1

    specs, style_of = _consolidate(specs, style_of)
    names = name_styles(specs)
    styles: Dict[str, Dict] = {}
    for sp, n in zip(specs, names):
        st = {"font": sp.face.family, "size": _round(sp.size_pt, 0.1), "weight": sp.face.weight,
              "leading": _round(sp.leading if sp.leading else 1.2, 0.01),
              "tracking": _round(sp.tracking, 0.005), "color": sp.colour}
        if sp.face.stretch:
            st["stretch"] = sp.face.stretch
        if sp.upper:
            st["case"] = "upper"
        if st["tracking"] == 0:
            del st["tracking"]
        styles[n] = st

    # Frames and data, in reading order.
    order = sorted(blocks, key=lambda t: (round(t[1].top / max(1.0, t[1].size * 2)), t[1].left))
    frames: List[Dict] = []
    h.frame_blocks = {}
    data: Dict[str, str] = {}
    labels: Dict[str, str] = {}
    counters: Dict[str, int] = {}
    for k, (bi, b) in enumerate(order):
        sname = names[style_of[bi]]
        st = styles[sname]
        size_px = st["size"] / PT_PER_MM * sheet.px_per_mm
        lead = st["leading"]
        key = f"t{k + 1:02d}"
        text = b.text()
        data[key] = text
        h.frame_blocks[key] = bi
        counters[sname] = counters.get(sname, 0) + 1
        labels[key] = f"{sname.replace('-', ' ').capitalize()} {counters[sname]}"
        eff_lead = lead
        if b.step and abs(b.step / size_px - lead) > 0.03 * lead:
            eff_lead = round(b.step / size_px, 3)
        top_px = b.runs[0].baseline - first_baseline(size_px, eff_lead, st["font"])
        hard_only = all(b.hard) if b.hard else True
        widths = [r.right - r.left for r in b.runs]
        if b.align == "justify" or not hard_only:
            limits = []
            for i, hard in enumerate(b.hard):
                if not hard:
                    nxt = b.runs[i + 1].words[0]
                    limits.append(widths[i] + 0.3 * size_px + (nxt.box[2] - nxt.box[0]))
            wmax = max(widths)
            w_px = wmax + (0.6 if b.align == "justify" else min(0.5 * (min(limits) - wmax), 0.5 * size_px)
                           if limits and min(limits) > wmax else 0.6)
        else:
            w_px = max(widths) + 0.6 * size_px
        if b.align == "right":
            x_px = b.right - w_px + 0.02 * size_px
        elif b.align == "center":
            x_px = (b.left + b.right) / 2 - w_px / 2
        else:
            x_px = b.left - 0.04 * size_px
        f = {"id": key, "type": "text", "style": sname, "bind": key,
             "x": round(mm(x_px), 2), "y": round(mm(top_px), 2), "w": round(mm(w_px), 2)}
        override = {}
        if b.align in ("right", "center", "justify"):
            override["align"] = b.align
        if hard_only:
            override["wrap"] = "nowrap"
        if eff_lead != lead:
            override["leading"] = eff_lead
        if b.align == "justify" and any(r.text.endswith("-") for r in b.runs[:-1]):
            override["hyphenate"] = True
        if override:
            f["with"] = override
        frames.append(f)

    # Art under the text: panels, photos, marks, then rules.
    art_frames: List[Dict] = []
    for i, reg in enumerate(h.regions):
        x0, y0, x1, y1 = reg.box
        base = {"id": f"art{i + 1:02d}", "x": round(mm(x0), 2), "y": round(mm(y0), 2),
                "w": round(mm(x1 - x0), 2), "h": round(mm(y1 - y0), 2), "z": 0}
        if reg.kind == "panel":
            art_frames.append({**base, "type": "box", "fill": hexcolour(reg.colour)})
        elif reg.kind == "outline":
            art_frames.append({**base, "type": "box", "stroke": hexcolour(reg.colour),
                               "stroke_weight": round(max(0.25, mm(2) * PT_PER_MM), 2),
                               **({"radius": reg.radius} if reg.radius else {})})
        elif i in asset_names:
            art_frames.append({**base, "type": "image", "src": asset_names[i], "fit": "fill"})
    for j, r in enumerate(h.rules):
        weight_pt = round(max(0.25, mm(r.thickness) * PT_PER_MM), 2)
        col = hexcolour(r.colour)
        if r.vertical:
            art_frames.append({"id": f"rule{j + 1:02d}", "type": "box", "x": round(mm(r.x0 - r.thickness / 2), 2),
                               "y": round(mm(r.y0), 2), "w": round(mm(r.thickness), 2),
                               "h": round(mm(r.y1 - r.y0), 2), "fill": col, "z": 0})
        else:
            art_frames.append({"id": f"rule{j + 1:02d}", "type": "rule", "x": round(mm(r.x0), 2),
                               "y": round(mm(r.y0 - r.thickness / 2), 2), "w": round(mm(r.x1 - r.x0), 2),
                               "weight": weight_pt, "color": col, "z": 0})
    for f in frames:
        f["z"] = 2
    if paper_image:
        art_frames.insert(0, {"id": "paper", "type": "image", "src": paper_image, "x": 0, "y": 0,
                              "w": sheet.width_mm, "h": sheet.height_mm, "fit": "fill", "z": 0})

    rip = {
        "rip": 1, "id": pack_id, "name": name, "category": "Harvested",
        "description": f"Ripped from a reference by the harvester. {len(styles)} type styles, "
                       f"{len(frames)} text frames, {len(art_frames)} art frames.",
        "reference": {"image": "assets/reference.jpg"},
        "page": {"width_mm": sheet.width_mm, "height_mm": sheet.height_mm, "format": sheet.format,
                 "paper": "paper", "ink": "ink"},
        "tokens": tokens,
        "styles": styles,
        "frames": art_frames + frames,
        "fields": {"order": list(data), "labels": labels},
        "harvest": {"notes": h.notes},
    }
    return rip, data
