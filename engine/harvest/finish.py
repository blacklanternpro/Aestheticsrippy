"""
Aestheticsrippy - measuring the print finish.

Over-inked, blurred and photocopied type carries the look of the press on top
of the letterform. Read clean, ink gain passes for a heavier weight (strokes
swollen, counters part-filled) and the matcher obliges with a Bold that was
never in the design. This pass re-fits each size-group's face against the
reference with the finish applied to the CANDIDATE tiles in cv2 - grayscale
dilation for gain, extra Gaussian for softness - with no re-render, solving
face, weight, size, gain and blur jointly. Weights are discrete and gain fills
the gaps between them, so among fits that explain the ink equally the lighter
weight + gain wins.

A finish is only recorded when it beats the best CLEAN fit of any weight by a
clear margin: a true Bold is matched perfectly by the Bold face, and a dilated
Regular cannot beat it (bold designs change proportions, not just stroke
width), so clean sheets pass through untouched. Residuals on the winning fit
then name the rest of the look: edge raggedness beyond what gain + blur draw
becomes `rough` (the photocopy's eroded contour), and hard, mid-tone-free
edges on a ragged letter become `threshold` (the re-thresholded xerox look).

Everything is written back onto the Match - face, size, score and the
`finish` dict - before the trust filter runs, so type whose clean match
looked hopeless stays live once the finish explains it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .layout import Block
from .typeface import (Bench, Face, Match, _compare, _face, _items, _samples,
                       _Try, instances)

# Em-relative ladders. Gain is the dilation radius; blur is the extra sigma on
# top of the document's scan softness (bench.blur), so a clean sheet fits at 0.
GAIN_EM = (0.0, 0.012, 0.02, 0.03, 0.045, 0.065)
BLUR_EM = (0.0, 0.01, 0.02, 0.035)
SIZE_MULTS = (1.0, 0.94, 0.88)   # dilation re-inflates a smaller true size
MARGIN = 0.02                    # the finish must beat every clean weight by this
TIE = 0.008                      # fits this close are "equal"; prefer lighter/less
CLEAN_FLOOR = 0.78               # the letterform underneath must already be nearly right
BEST_FLOOR = 0.86                # and the finished fit must actually explain the ink
GAIN_CAP = 0.055                 # beyond this the "gain" is a wrong weight in disguise


def _disk(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _finished(tile: np.ndarray, r: int, sigma: float) -> np.ndarray:
    out = cv2.dilate(tile, _disk(r)) if r > 0 else tile
    if sigma > 0:
        out = cv2.GaussianBlur(out, (0, 0), sigma)
    return out


def _weight_ladder(face: Face, insts: Dict[str, Dict], per: int = 4) -> List[Face]:
    """The face's own weight and its nearest lighter siblings (gain only adds ink)."""
    ws = sorted({_face(k).weight for k in insts
                 if _face(k).family == face.family and (_face(k).stretch or 100) == (face.stretch or 100)
                 and _face(k).weight <= face.weight}, reverse=True)
    return [Face(face.family, w, face.stretch, face.italic) for w in ws[:per]]


def _groups(blocks: Sequence[Block], matches: Dict[int, Match]) -> List[List[int]]:
    """Size-groups: blocks sharing a face and a size (within 12%) are one print run."""
    groups: List[List[int]] = []
    for bi in sorted(matches, key=lambda i: -blocks[i].size):
        m = matches[bi]
        for g in groups:
            o = matches[g[0]]
            if (m.face.key == o.face.key
                    and abs(m.size_px - o.size_px) <= 0.12 * max(m.size_px, o.size_px)):
                g.append(bi)
                break
        else:
            groups.append([bi])
    return groups


def _residuals(ref: np.ndarray, fit: np.ndarray, dx: int, dy: int) -> Tuple[float, float]:
    """(raggedness, midtone fraction) of ref against the aligned winning fit.

    Raggedness: how much longer the reference's ink contour runs than the
    fit's at matched area - eroded photocopy edges wander. Midtone fraction:
    how much of the reference's edge band sits between ink and paper - a
    re-thresholded copy has almost none."""
    res = cv2.matchTemplate(fit, ref, cv2.TM_SQDIFF)
    _, _, (x, y), _ = cv2.minMaxLoc(res)
    win = fit[y:y + ref.shape[0], x:x + ref.shape[1]]
    rb = (ref > 0.5 * max(0.2, float(ref.max()))).astype(np.uint8)
    fb = (win > 0.5 * max(0.2, float(win.max()))).astype(np.uint8)
    per = [sum(cv2.arcLength(c, True) for c in
               cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0]) for b in (rb, fb)]
    rag = per[0] / max(1.0, per[1])
    band = (cv2.dilate(rb, _disk(1)) > 0) & (cv2.erode(rb, _disk(1)) == 0)
    mid = float(np.mean((ref[band] > 0.25) & (ref[band] < 0.75))) if band.any() else 1.0
    return float(rag), mid


def measure(bench: Bench, img: np.ndarray, blocks: Sequence[Block],
            matches: Dict[int, Match], say=lambda m: None) -> int:
    """Fit a print finish per size-group; update matches in place. Returns
    how many groups came out finished."""
    insts = instances()
    samples = _samples(img, blocks)
    found = 0
    for group in _groups(blocks, matches):
        m0 = matches[group[0]]
        chars = sum(sum(c.isalnum() for c in blocks[bi].text()) for bi in group)
        if chars < 8 or not (0.74 <= m0.score < 0.90) or m0.size_px < 14:
            continue
        ladder = _weight_ladder(m0.face, insts)
        picks = [s for bi in group if bi in samples for s in samples[bi]][:3]
        if not picks:
            continue

        # One bench batch: every sample at every candidate weight and true size.
        tries = [_Try(s, f, m0.size_px * (s.height / max(1.0, picks[0].height)) * mult)
                 for s in picks for f in ladder for mult in SIZE_MULTS]
        items = _items(tries, fit=True)
        tiles = bench.render(items)

        # The grid, scored per (weight, mult, gain, blur) as the mean over samples.
        size = m0.size_px
        gains = sorted({int(round(e * size)) for e in GAIN_EM})
        blurs = sorted({round(e * size, 2) for e in BLUR_EM})
        grid: Dict[Tuple[int, float, int, float], List[float]] = {}
        fits: Dict[Tuple[int, float, int, float], Tuple] = {}
        for t, it, (tile, _) in zip(tries, items, tiles):
            for r in gains:
                fat = _finished(tile, r, 0.0)
                for sg in blurs:
                    cand = cv2.GaussianBlur(fat, (0, 0), sg) if sg > 0 else fat
                    sc, _, _ = _compare(t.sample.ref, cand, it["_dx"], it["_dy"], bench.blur)
                    key = (t.face.weight, round(t.size / (m0.size_px * (t.sample.height / max(1.0, picks[0].height))), 3), r, sg)
                    grid.setdefault(key, []).append(sc)
                    if t.sample is picks[0]:
                        fits[key] = (t.sample.ref, cand, it["_dx"], it["_dy"])
        score = {k: float(np.mean(v)) for k, v in grid.items()}
        clean = max(v for (w, mu, r, sg), v in score.items() if r == 0 and sg == 0)
        best = max(score.values())
        # Among near-equal fits: the lightest weight, then the least finish.
        w, mu, r, sg = min((k for k, v in score.items() if v >= best - TIE),
                           key=lambda k: (k[0], k[2], k[3], -k[1]))
        gain_em = r / (size * mu)
        # A finish is the press on a face we already believe in. A bad face
        # helped a little by dilation is a wrong weight, not a finish.
        if r <= 0 or best < clean + MARGIN or clean < CLEAN_FLOOR or best < BEST_FLOOR \
                or gain_em > GAIN_CAP:
            continue

        fin: Dict[str, object] = {"gain": round(gain_em, 4)}
        if sg > 0:
            fin["blur"] = round(sg / (size * mu), 4)
        rag, mid = _residuals(*fits[(w, mu, r, sg)])
        if rag >= 1.15:
            fin["rough"] = {"freq": 8, "scale": round(min(0.08, max(0.02, 0.04 * (rag - 1) / 0.15)), 3), "seed": 7}
            if mid < 0.30:
                fin["threshold"] = 0.5
        for bi in group:
            m = matches[bi]
            m.face = Face(m.face.family, w, m.face.stretch, m.face.italic)
            m.size_px *= mu
            m.score = best
            m.scores[m.face.key] = best
            m.finish = dict(fin)
        found += 1
        say(f"Print finish on {len(group)} block(s) at {size:.0f}px: weight {w}, "
            f"gain {fin['gain']}, clean fit was {clean:.3f} -> {best:.3f}")
    return found
