"""
The engine's own eye for single letters.

OCR reads lines well and letters badly: alone, an N turned 90 degrees is a
perfectly confident Z, and an eroded knockout letter often reads as nothing at
all. But the engine owns a type cabinet, so it can look at a letter the way the
face matcher looks at a line: render known glyphs and compare shapes.

A Glyphs atlas holds capitals and digits from a few representative faces (a
grotesque, a condensed, a wide geometric, a serif, a mono - identity needs
shape coverage, not the right face). classify() turns a letter's mask at each
candidate angle, normalises it, and scores it against every template at once.
It answers "which character, at which turn, how surely" in microseconds,
where a single OCR call costs tens of milliseconds and lies more often.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@&"
LOWER = "abcdefghijklmnopqrstuvwxyz"
# Shape coverage, not taste: a grotesque, a condensed, a wide geometric,
# a serif and a mono between them bracket most letterforms.
FACE_WISHES = [("Inter", 600), ("Archivo Narrow", 500), ("Krona One", 400),
               ("EB Garamond", 500), ("Courier Prime", 700)]
SIDE = 40          # templates and tiles compare at SIDE x SIDE
RENDER_PX = 64     # glyphs render large, then settle down to SIDE

_ATLAS: Optional["Glyphs"] = None    # fonts never change within a process


class Glyphs:
    def __init__(self, templates: np.ndarray, chars: List[str], ars: np.ndarray):
        self.templates = templates                      # (n, SIDE, SIDE) float32, ink 0..1
        self.chars = chars                              # char per template
        self.ars = ars                                  # log aspect (h/w) per template
        self.sums = templates.reshape(len(templates), -1).sum(axis=1)

    def classify(self, mask: np.ndarray, angles: Sequence[float], top: int = 3,
                 min_sep: float = 20.0) -> List[Tuple[float, float, str]]:
        """
        The turns at which this letter looks most like a known glyph:
        [(score 0..1, angle degrees CSS-clockwise, char)], best first, angles
        kept `min_sep` apart so the list offers real alternatives.
        """
        scored: List[Tuple[float, float, str]] = []
        for a in angles:
            t, ar = _normalise(_rotate_mask(mask, a))
            if t is None:
                continue
            inter = np.minimum(self.templates, t).reshape(len(self.templates), -1).sum(axis=1)
            s = 2 * inter / np.maximum(1e-6, self.sums + t.sum())
            s = s - 0.22 * np.abs(self.ars - ar)
            j = int(np.argmax(s))
            scored.append((float(s[j]), float(a), self.chars[j]))
        scored.sort(reverse=True)
        keep: List[Tuple[float, float, str]] = []
        for sc, a, ch in scored:
            if all(_adiff(a, k[1]) > min_sep for k in keep):
                keep.append((sc, a, ch))
            if len(keep) >= top:
                break
        return keep

    def alternates(self, mask: np.ndarray, angle: float, top: int = 4
                   ) -> List[Tuple[float, str]]:
        """The best few characters for this letter at one fixed turn: [(score, char)]."""
        t, ar = _normalise(_rotate_mask(mask, angle))
        if t is None:
            return []
        inter = np.minimum(self.templates, t).reshape(len(self.templates), -1).sum(axis=1)
        s = 2 * inter / np.maximum(1e-6, self.sums + t.sum()) - 0.22 * np.abs(self.ars - ar)
        best: Dict[str, float] = {}
        for j in np.argsort(-s):
            ch = self.chars[j]
            if ch not in best:
                best[ch] = float(s[j])
            if len(best) >= top:
                break
        return sorted(((v, k) for k, v in best.items()), reverse=True)

    def chart(self, mask: np.ndarray, angles: Sequence[float], top: int = 8
              ) -> List[Tuple[float, float, str]]:
        """
        The best few characters this letter could be at any of the turns:
        [(score, angle, char)], one entry per character, best first. Where
        classify answers "what does this read as", chart answers "how well
        could it read as each thing" - the evidence a word-level referee
        needs (a C at the ring's bottom hides behind O in classify).
        """
        best: Dict[str, Tuple[float, float]] = {}
        for a in angles:
            t, ar = _normalise(_rotate_mask(mask, a))
            if t is None:
                continue
            inter = np.minimum(self.templates, t).reshape(len(self.templates), -1).sum(axis=1)
            s = 2 * inter / np.maximum(1e-6, self.sums + t.sum()) - 0.22 * np.abs(self.ars - ar)
            for j, v in enumerate(s):
                ch = self.chars[j]
                if float(v) > best.get(ch, (-1.0, 0.0))[0]:
                    best[ch] = (float(v), float(a))
        return sorted(((v, a, ch) for ch, (v, a) in best.items()), reverse=True)[:top]

    def read(self, mask: np.ndarray, angle: float) -> Tuple[float, str]:
        """The best character for this letter at one fixed turn."""
        got = self.classify(mask, [angle], top=1)
        return (got[0][0], got[0][2]) if got else (0.0, "")

    def sub(self, keep: str) -> "Glyphs":
        """A view holding only the templates whose characters are in `keep`."""
        idx = [j for j, ch in enumerate(self.chars) if ch in keep]
        return Glyphs(self.templates[idx], [self.chars[j] for j in idx], self.ars[idx])


def _adiff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _rotate_mask(mask: np.ndarray, a: float) -> np.ndarray:
    """The mask turned by `a` (cv2's sense, undoing a CSS-clockwise turn), as float ink."""
    m = mask.astype(np.float32)
    if not a:
        return m
    h, w = m.shape
    rot = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    cos, sin = abs(rot[0, 0]), abs(rot[0, 1])
    nw, nh = int(h * sin + w * cos) + 2, int(h * cos + w * sin) + 2
    rot[0, 2] += nw / 2 - w / 2
    rot[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(m, rot, (nw, nh), flags=cv2.INTER_LINEAR)


def _normalise(ink: np.ndarray) -> Tuple[Optional[np.ndarray], float]:
    """Trim to the ink, scale to SIDE x SIDE, soften; and the log aspect before scaling."""
    ys, xs = np.nonzero(ink > 0.25)
    if len(xs) < 6:
        return None, 0.0
    crop = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ar = float(np.log(crop.shape[0] / max(1, crop.shape[1])))
    t = cv2.resize(crop, (SIDE, SIDE), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(t, (3, 3), 0.8), ar


# ------------------------------------------------------------- row utilities
# Shared by every reader that faces a row of letter shapes (a stamp's
# unrolled band, a levelled rotated line): the row cut into letter cells,
# and a reader's text checked against what the cells chart as.

def cells(keep: np.ndarray, cap: float) -> List[Tuple]:
    """The strip's letters, one cell each: components, with fused pairs split
    at their ink valleys. [(x, y, w, h, mask)] in reading order."""
    nl, lab, st, cen = cv2.connectedComponentsWithStats(keep, 8)
    out = []
    for i in range(1, nl):
        x, y, w, h, area = st[i]
        if area < 12:
            continue
        mm = lab[y:y + h, x:x + w] == i
        if w <= 1.35 * cap:
            out.append((x, y, w, h, mm))
            continue
        k = max(2, int(round(w / (0.95 * cap))))
        prof = mm.sum(axis=0).astype(float)
        cuts = [0]
        for j in range(1, k):
            lo = int(w * (j - 0.25) / k)
            hi = int(w * (j + 0.25) / k)
            cuts.append(lo + int(np.argmin(prof[lo:max(lo + 1, hi)])))
        cuts.append(w)
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 3:
                continue
            piece = np.zeros_like(mm)
            piece[:, a:b] = mm[:, a:b]
            if piece.sum() >= 12:
                out.append((x + a, y, b - a, h, piece[:, a:b]))
    out.sort(key=lambda c: c[0])
    return out


def verify(glyphs, text, letter_cells) -> Tuple[float, float]:
    """How much of the reader's word the strip's shapes vouch for: the chars
    aligned to the cells in order, each checked against the cell's chart."""
    chars = [ch for ch in text.upper() if not ch.isspace()]
    letters = [c for c in letter_cells if not (c[3] < 0.5 * c[2] and c[2] < 18)]
    if not chars or not letters:
        return 0.0, 0.0
    n = min(len(chars), len(letters))
    hits, scores = 0, []
    for ch, cell in zip(chars[:n], letters[:n]):
        if not ch.isalnum() and ch not in "@&":
            hits += 1          # punctuation: the reader's call stands
            continue
        chart = glyphs.chart(cell[4], range(-24, 25, 8), top=4)
        for sc, a, c2 in chart:
            if c2 == ch and sc >= 0.58:
                hits += 1
                scores.append(100.0 * sc)
                break
    agree = hits / max(len(chars), len(letters))
    return agree, (float(np.mean(scores)) if scores else 0.0)



def atlas(browser, full: bool = False) -> Glyphs:
    """The process-wide atlas, rendered once from the cabinet.

    The default view holds capitals, digits and @& - what the angled, curved
    and stamp stages chart against (lowercase twins must not eat their chart
    slots). `full=True` adds the lowercase letters, for readers that face
    mixed-case display type (engine/harvest/proof.py)."""
    global _ATLAS
    if _ATLAS is not None:
        return _ATLAS if full else _ATLAS.sub(CHARS)
    from ..typecase import matcher_data
    from .typeface import Bench
    insts = matcher_data()["instances"]

    def pick(family: str, weight: int):
        cands = [m for m in insts if m["family"] == family and not m.get("stretch")]
        return min(cands, key=lambda m: abs(int(m["weight"]) - weight)) if cands else None

    faces = [p for p in (pick(f, w) for f, w in FACE_WISHES) if p is not None]
    bench = Bench(browser)
    try:
        S = RENDER_PX
        items = [{"text": ch, "family": f["family"], "weight": int(f["weight"]), "stretch": None,
                  "size": S, "sx": 1.0, "italic": False, "ls": 0.0,
                  "w": int(S * 2.0), "h": int(S * 1.8), "base": int(S * 1.3), "ox": int(S * 0.4)}
                 for f in faces for ch in CHARS + LOWER]
        tiles = bench.render(items)
    finally:
        bench.close()
    templates, chars, ars = [], [], []
    for it, (tile, _) in zip(items, tiles):
        t, ar = _normalise(tile)
        if t is None:
            continue
        templates.append(t)
        chars.append(it["text"])
        ars.append(ar)
    _ATLAS = Glyphs(np.stack(templates), chars, np.array(ars, np.float32))
    return _ATLAS if full else _ATLAS.sub(CHARS)
