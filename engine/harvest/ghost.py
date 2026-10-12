"""
Aestheticsrippy - ghost words: display type OCR never saw at all.

The office-card shape: a big, soft display word with a logotype overprinted
across it. Tesseract never makes a text block of it, so the whole band falls
through to the art and the design's centrepiece ships as pixels. But the band
usually carries two inks - the word in one colour, the overprint in another -
and once the colours are separated, the word's own layer is a clean row the
glyph atlas can read cold (engine/harvest/proof.ghost_word).

A ghost that reads convincingly becomes a straight-baseline PathText (the
curved pathway: it gets its own bench-matched face downstream, and build sets
it as live type), and ONLY its own colour layer leaves the region - the
overprint keeps its pixels and stays art, to composite back over the live
word. Scribbles, logos and ornaments read as nothing and stay art whole.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .art import Region
from .curved import PathText
from .letters import Glyphs
from .proof import ghost_word

MIN_LAYER = 0.18     # a colour layer below this share of the region's ink is noise
MIN_CONF = 70.0


def fit_sizes(ghosts: Sequence[PathText]) -> None:
    """After face matching: a ghost's width was MEASURED, so a matched face
    that sets wider than the ink shrinks to fit - on a display word a width
    error screams louder than a few percent of height."""
    from ..typecase import matcher_data
    insts = matcher_data()["instances"]
    for pt in ghosts:
        if pt.face is None or not pt.size_px or pt.length <= 0:
            continue
        inst = next((m for m in insts if m["family"] == pt.face.family
                     and int(m["weight"]) == pt.face.weight
                     and (m.get("stretch") or None) == pt.face.stretch), None)
        if inst is None:
            continue
        adv = sum(inst["adv"].get(c, inst["adv"].get("n", 0.55)) for c in pt.text)
        if adv <= 0:
            continue
        cap = 0.96 * pt.length / adv   # margin: browser advances run a hair
        if pt.size_px > cap:           # wider than the cabinet's tables
            pt.size_px = cap


def _layers(crop: np.ndarray, mask: np.ndarray) -> List[np.ndarray]:
    """The region's ink split by colour (Lab k-means): the word's own ink and
    the overprint's. A one-colour region comes back whole."""
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2Lab).astype(np.float32)
    px = lab[mask]
    if len(px) < 200:
        return [mask]
    spread = float(np.mean(np.std(px, axis=0)[1:]))   # chroma spread
    out = [mask]
    if spread > 6.0:
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 0.5)
        _r, labels, _c = cv2.kmeans(px, 2, None, crit, 3, cv2.KMEANS_PP_CENTERS)
        full = np.zeros(mask.shape, np.int32) - 1
        full[mask] = labels.ravel()
        for k in range(2):
            m = full == k
            if m.sum() >= MIN_LAYER * mask.sum():
                # shed the other colour's bleed at the seams
                m2 = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN,
                                      np.ones((3, 3), np.uint8)).astype(bool)
                if m2.sum() >= 0.5 * m.sum():
                    out.append(m2)
    return out


def find(img: np.ndarray, regions: Sequence[Region], bg: np.ndarray, glyphs: Glyphs,
         body_px: float = 12.0) -> Tuple[List[PathText], List[Region]]:
    """Read ghost words out of big art regions; return them as straight
    PathText lines and the regions with the claimed ink removed."""
    import os
    debug = bool(os.environ.get("RIP_DEBUG_GHOST"))
    ghosts: List[PathText] = []
    kept: List[Region] = []
    for reg in regions:
        x0, y0, x1, y1 = reg.box
        h, w = y1 - y0, x1 - x0
        if reg.kind not in ("mark", "photo") or reg.mask is None \
                or h < 3 * body_px or w < 1.2 * h or reg.mask.sum() < 400:
            if debug and h >= 2 * body_px and w >= h:
                print(f"    ghost- {reg.kind} {w}x{h} mask={'yes' if reg.mask is not None else 'no'} (left alone)")
            kept.append(reg)
            continue
        crop = img[y0:y1, x0:x1]
        taken = np.zeros(reg.mask.shape, bool)
        for li, layer in enumerate(_layers(crop, reg.mask.astype(bool))):
            got = ghost_word(layer.astype(np.uint8), glyphs)
            if debug:
                print(f"    ghost? {reg.kind} {w}x{h} layer{li} px={int(layer.sum())} -> "
                      f"{got[0] if got else None}")
            if got is None:
                continue
            text, shape, pieces = got
            bases = [p[1] + p[3] for p in pieces]
            caps = [p[3] for p in pieces]
            base = float(np.median(bases))
            cap = float(np.percentile(caps, 85))
            lx0 = min(p[0] for p in pieces)
            lx1 = max(p[0] + p[2] for p in pieces)
            colour = tuple(int(v) for v in np.median(crop[layer], axis=0))
            # The matcher must see the ink's real softness - a hard mask of a
            # soft fat word reads as ultra-heavy and matches the wrong face.
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            grown = cv2.dilate(layer.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            row = np.full(layer.shape, 255, np.uint8)
            row[grown] = gray[grown]
            # The press on the ghost: edge softness measured from the ink's
            # own mid-tones becomes a blur finish, so a soft display word
            # renders soft instead of razor-cut.
            fin = None
            sub = gray.astype(np.float32)
            paper_g = float(np.median(sub[~grown])) if (~grown).any() else 255.0
            ink_g = float(np.percentile(sub[layer], 10))
            if paper_g - ink_g > 40:
                d = np.clip((paper_g - sub) / (paper_g - ink_g), 0, 1)
                mid = int(((d > 0.25) & (d < 0.75) & grown).sum())
                per = sum(cv2.arcLength(c, True) for c in cv2.findContours(
                    layer.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0])
                sigma = mid / max(1.0, 2.0 * per)
                blur_em = sigma / max(1.0, cap / 0.72)
                if blur_em >= 0.004:
                    fin = {"blur": round(min(blur_em, 0.05), 4)}
            ghosts.append(PathText(
                text=text,
                points=np.array([[x0 + lx0 - 2, y0 + base], [x0 + lx1 + 2, y0 + base]], np.float64),
                cap=cap, colour=colour, conf=MIN_CONF + 25 * (shape - 0.65) / 0.35,
                row=row, length=float(lx1 - lx0), finish=fin))
            taken |= cv2.dilate(layer.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        if not taken.any():
            kept.append(reg)
            continue
        rest = reg.mask & ~taken
        if rest.sum() >= 60:
            ys, xs = np.nonzero(rest)
            reg.mask = rest
            reg.notes.append("a ghost word was read out of this mark")
            kept.append(reg)
    return ghosts, kept
