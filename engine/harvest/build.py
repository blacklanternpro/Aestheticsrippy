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
            alt = Face(f.family, w, f.stretch, f.italic)
            slack = 0.045 if m.size_px < 18 else 0.02  # small type cannot tell weights apart reliably
            if alt.key in m.scores and cur - m.scores[alt.key] <= slack and abs(w - f.weight) <= 200:
                out[bi] = alt
                break
    return out


def _harmonise_family(matches: Dict[int, Match], blocks: Sequence[Block], margin: float) -> Dict[int, Face]:
    """
    Designs use few families. Choose the set of families that explains the
    sheet best, paying a price for each family added: a second (or third)
    family must earn its place by fitting its blocks clearly better. Each block
    then takes its best face within the set. A block may still go its own way
    when nothing in the set comes close (a logotype in a face of its own).
    """
    def fam_best(m: Match, family: str) -> Tuple[float, Optional[str]]:
        best, key = -1.0, None
        for k, v in m.scores.items():
            if k.split("|")[0] == family and v > best:
                best, key = v, k
        return best, key

    if not matches:
        return {}
    weight_of = {bi: max(6, len(blocks[bi].text())) ** 0.5 * max(1.0, blocks[bi].size / 14) ** 0.5
                 for bi in matches}
    total_w = sum(weight_of.values())
    families = {k.split("|")[0] for m in matches.values() for k in m.scores}
    best_of = {f: {bi: fam_best(m, f) for bi, m in matches.items()} for f in families}

    def value(fset) -> float:
        v = 0.0
        for bi, m in matches.items():
            scores = [best_of[f][bi][0] for f in fset if best_of[f][bi][1]]
            # A block the set cannot render at all keeps its own best, discounted.
            v += weight_of[bi] * (max(scores) if scores else max(m.scores.values()) - 0.15)
        return v / total_w

    chosen_set: List[str] = []
    current = -1e9
    price = margin  # each extra family must raise the sheet's mean score by this much
    for _ in range(3):
        best_f, best_v = None, current
        for f in families - set(chosen_set):
            v = value(chosen_set + [f])
            if v > best_v + (price if chosen_set else 0):
                best_f, best_v = f, v
        if best_f is None:
            break
        chosen_set.append(best_f)
        current = best_v

    # Text of one size and colour is one family: decide per group of like blocks, not per
    # block, so measurement noise cannot set two neighbouring prices in different faces.
    groups: List[List[int]] = []
    for bi in sorted(matches, key=lambda b: blocks[b].size):
        b = blocks[bi]
        for g in groups:
            ref = blocks[g[0]]
            if abs(b.size - ref.size) <= max(0.15 * ref.size, 2.5) and _close_colour(b, ref):
                g.append(bi)
                break
        else:
            groups.append([bi])
    chosen: Dict[int, Face] = {}
    for g in groups:
        def group_value(f):
            return sum(weight_of[bi] * best_of[f][bi][0] for bi in g if best_of[f][bi][1])
        usable = [f for f in chosen_set if all(best_of[f][bi][1] for bi in g)]
        fam = max(usable, key=group_value) if usable else None
        for bi in g:
            m = matches[bi]
            top_key = max(m.scores, key=m.scores.get)
            short = sum(c.isalnum() for c in blocks[bi].text()) < 4  # a figure or two proves nothing
            if fam and (short or m.scores[top_key] - best_of[fam][bi][0] <= _margin(blocks[bi], 0.06)):
                chosen[bi] = _face(best_of[fam][bi][1])
            else:
                cands = [best_of[f][bi] for f in chosen_set if best_of[f][bi][1]]
                in_set = max(cands) if cands else (-1.0, None)
                if in_set[1] and m.scores[top_key] - in_set[0] <= _margin(blocks[bi], 0.06):
                    chosen[bi] = _face(in_set[1])
                else:
                    chosen[bi] = _face(top_key)
    return chosen


def _close_colour(a: Block, b: Block) -> bool:
    ca = np.array(a.runs[0].ink.colour, float) if a.runs[0].ink else np.zeros(3)
    cb = np.array(b.runs[0].ink.colour, float) if b.runs[0].ink else np.zeros(3)
    return float(np.linalg.norm(ca - cb)) < 70


def _face(key: str) -> Face:
    parts = key.split("|")
    fam, w, st = parts[:3]
    return Face(fam, int(w), float(st) if st else None, len(parts) > 3 and parts[3] == "i")


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
    sx: float = 1.0


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
        small = a.chars < 40
        size_tol, weight_tol = (0.16, 200) if small else (0.10, 100)
        best, dist = None, None
        for j, b in enumerate(specs):
            if j == i or target[j] != j or b.chars <= a.chars:
                continue
            if b.face.family != a.face.family or b.colour != a.colour or b.upper != a.upper:
                continue
            if abs(b.face.weight - a.face.weight) > weight_tol or abs(b.size_pt / a.size_pt - 1) > size_tol \
                    or abs(b.sx - a.sx) > 0.06:
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
    type_match: float = 0.0
    rotated: List = field(default_factory=list)


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


def _table_frame(t, n: int, styles: Dict[str, Dict], sheet: Sheet, data: Dict, labels: Dict) -> Dict:
    """A repeat of rows: each row a grid of cells (with spacers) at the measured column edges."""
    mm = sheet.mm
    k = len(t.styles)
    sizes = [styles[s]["size"] / PT_PER_MM * sheet.px_per_mm for s in t.styles]
    L = [min(row[c].left for row in t.rows) for c in range(k)]
    R = [max(row[c].right for row in t.rows) for c in range(k)]
    S, E = [], []
    for c in range(k):
        slack = 0.6 * sizes[c]
        if t.aligns[c] == "right":
            S.append(L[c] - slack)
            E.append(R[c] + 0.02 * sizes[c])
        elif t.aligns[c] == "center":
            S.append(L[c] - slack / 2)
            E.append(R[c] + slack / 2)
        else:
            S.append(L[c] - 0.04 * sizes[c])
            E.append(R[c] + slack)
    cols, children = [], []
    for c in range(k):
        if c:
            gap = S[c] - E[c - 1]
            if gap < 0:  # columns overlap: split the difference
                mid = (S[c] + E[c - 1]) / 2
                E[c - 1], S[c] = mid - 0.5, mid + 0.5
                cols[-1] = round(mm(E[c - 1] - S[c - 1]), 2)
                gap = 1.0
            cols.append(round(mm(gap), 2))
            children.append({"type": "space", "h": 0})
        cols.append(round(mm(E[c] - S[c]), 2))
        cell = {"type": "text", "style": t.styles[c], "bind": f".c{c + 1}",
                "with": {"wrap": "nowrap", "leading": round(t.step / sizes[c], 3)}}
        if t.aligns[c] != "left":
            cell["with"]["align"] = t.aligns[c]
        children.append(cell)
    # First row: put the baselines where they were.
    base = max(first_baseline(sizes[c], t.step / sizes[c], styles[t.styles[c]]["font"]) for c in range(k))
    top = t.rows[0][0].baseline - base
    key = f"list{n + 1:02d}"
    data[key] = [{f"c{c + 1}": row[c].text for c in range(k)} for row in t.rows]
    labels[key] = f"List {n + 1}"
    for c in range(k):
        labels[f"{key}.*.c{c + 1}"] = f"Column {c + 1}"
    return {"id": key, "type": "repeat", "bind": key, "x": round(mm(S[0]), 2), "y": round(mm(top), 2),
            "gap": 0, "item": {"type": "row", "cols": cols, "gap": 0, "align": "baseline", "children": children}}


def _rotated_frames(h: "Harvest", styles: Dict[str, Dict], specs, names, data, labels, tokens) -> List[Dict]:
    """
    Rotated lines take the sheet's main face, sized from their cap height and
    tracked to their measured length; lines of one size share a style.
    """
    if not h.rotated:
        return []
    from ..typecase import matcher_data
    sheet = h.sheet
    mm = sheet.mm
    # The face that sets the most text on the sheet.
    if specs:
        main = max(specs, key=lambda sp: sp.chars).face
    else:
        main = Face("Inter", 500)
    inst = next((m for m in matcher_data()["instances"] if m["family"] == main.family
                 and int(m["weight"]) == main.weight and (m.get("stretch") or None) == main.stretch), None)
    if inst is None:
        inst = next(m for m in matcher_data()["instances"] if m["family"] == main.family)
    frames, made = [], {}
    for k, rt in enumerate(h.rotated):
        size_px = rt.cap / max(0.3, inst["cap"])
        size_pt = mm(size_px) * PT_PER_MM
        sname = None
        for n, st in made.items():
            if abs(st["size"] - size_pt) <= max(0.08 * size_pt, mm(2.2) * PT_PER_MM):
                sname = n
                break
        if sname is None:
            sname = "angled" if not made else f"angled-{'bcdefghij'[(len(made) - 1) % 9]}"
            colour = min(tokens, key=lambda t: _dist_hex(tokens[t], rt.colour)) if tokens else "ink"
            made[sname] = {"font": main.family, "weight": main.weight, "size": round(size_pt, 1),
                           "leading": 1.0, "color": colour}
            if main.stretch:
                made[sname]["stretch"] = main.stretch
        st = made[sname]
        size_px = st["size"] / PT_PER_MM * sheet.px_per_mm
        adv = sum(inst["adv"].get(c, inst["adv"].get("n", 0.55)) for c in rt.text)
        n = max(2, len(rt.text))
        track = (rt.width / size_px - adv + 0.06) / (n - 1)
        track = float(np.clip(track, -0.1, 0.6))
        width = size_px * (adv + track * (n - 1)) + 0.8 * size_px
        height = size_px * 1.0
        m = metrics_of(main.family)
        base = first_baseline(size_px, 1.0, main.family)
        cap_c = base - inst["cap"] * size_px / 2
        dvec = np.array([0.0, cap_c - height / 2])
        a = np.radians(rt.angle)
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        cx, cy = np.array([rt.cx, rt.cy]) - rot @ dvec
        key = f"r{k + 1:02d}"
        data[key] = rt.text
        labels[key] = f"Angled {k + 1}"
        f = {"id": key, "type": "text", "style": sname, "bind": key,
             "x": round(mm(cx - width / 2), 2), "y": round(mm(cy - height / 2), 2), "w": round(mm(width), 2),
             "rotate": round(rt.angle, 2), "with": {"align": "center", "wrap": "nowrap", "tracking": round(track, 3)}}
        frames.append(f)
    styles.update(made)
    return frames


def _dist_hex(hexstr: str, bgr) -> float:
    r, g, b = int(hexstr[1:3], 16), int(hexstr[3:5], 16), int(hexstr[5:7], 16)
    return float(np.linalg.norm(np.array([b, g, r], float) - np.array(bgr, float)))


def metrics_of(family: str) -> Dict:
    return _metrics(family)


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
    # How closely the chosen faces match the reference's letters (the matcher's own measure).
    ws = [(len(h.blocks[bi].text()), h.matches[bi].scores.get(f.key, h.matches[bi].score)) for bi, f in faces.items()]
    h.type_match = sum(w * v for w, v in ws) / max(1, sum(w for w, _ in ws)) if ws else 0.0
    best = [(len(h.blocks[bi].text()), max(h.matches[bi].scores.values())) for bi in faces]
    h.notes.append(f"Letter match {h.type_match:.3f} with the chosen faces "
                   f"(the best face per block alone: {sum(w * v for w, v in best) / max(1, sum(w for w, _ in best)):.3f}).")
    blocks = [(bi, b) for bi, b in enumerate(h.blocks) if bi in faces]

    from .typeface import true_inks
    inks = true_inks(h.blocks)
    tokens, ink_names = colour_tokens(h.paper_bgr, [inks.get(bi, _block_colour(b)) for bi, b in blocks],
                                      [b.size < 22 for _, b in blocks])
    colour_of = {bi: ink_names[k] for k, (bi, _) in enumerate(blocks)}

    # Group blocks into styles. Display lines that differ only in tracking share a style
    # and keep their own tracking on the frame.
    block_track: Dict[int, float] = {}
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
        block_track[bi] = track
        sx = m.scale_x if face.family == m.face.family else 1.0
        # Sizes come from heights measured in whole pixels: a pixel of x-height is ~2 px of size.
        tol = max(0.07 * size_pt, mm(2.2) * PT_PER_MM)
        for si, sp in enumerate(specs):
            if (sp.face == face and abs(sp.size_pt - size_pt) <= tol
                    and (abs(sp.tracking - track) <= 0.025 or len(b.runs) == 1 and b.align != "left")
                    and sp.colour == colour_of[bi] and sp.upper == upper
                    and abs(sp.sx - sx) <= 0.04):
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
            specs.append(StyleSpec(face, size_pt, track, leading, colour_of[bi], upper, [bi], len(b.text()), sx))
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
        if sp.face.italic:
            st["italic"] = True
        if sp.upper:
            st["case"] = "upper"
        if abs(sp.sx - 1) > 0.03:
            st["scale_x"] = round(sp.sx, 3)
        if st["tracking"] == 0:
            del st["tracking"]
        styles[n] = st

    # Repeated rows become lists first; the blocks they use up are not framed again.
    from .tables import find_tables
    def same_style(x: str, y: str) -> bool:
        if x == y:
            return True
        a, b = styles[x], styles[y]
        return a["font"] == b["font"] and a["color"] == b["color"] and abs(a["size"] / b["size"] - 1) <= 0.15

    tables = find_tables(h.blocks, {bi: names[style_of[bi]] for bi, _ in blocks}, same_style)
    in_table = {bi for t in tables for bi in t.blocks}

    # Frames and data, in reading order.
    order = sorted([t for t in blocks if t[0] not in in_table],
                   key=lambda t: (round(t[1].top / max(1.0, t[1].size * 2)), t[1].left))
    frames: List[Dict] = []
    h.frame_blocks = {}
    data: Dict[str, object] = {}
    labels: Dict[str, str] = {}
    counters: Dict[str, int] = {}
    for n, t in enumerate(tables):
        frames.append(_table_frame(t, n, styles, sheet, data, labels))
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
        own_track = block_track.get(bi, 0.0)
        if abs(own_track - st.get("tracking", 0.0)) > 0.012:
            override["tracking"] = round(own_track, 3)
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
    frames += _rotated_frames(h, styles, specs, names, data, labels, tokens)
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
        "fields": {"order": [f["bind"] for f in sorted((f for f in frames if f.get("bind") in data),
                                                       key=lambda f: (round(f["y"] / 4), f["x"]))],
                   "labels": labels},
        "harvest": {"notes": h.notes},
    }
    return rip, data
