"""
Aestheticsrippy - measuring the print finish.

Over-inked, blurred and photocopied type carries the look of the press on top
of the letterform. Read clean, ink gain passes for a heavier weight (strokes
swollen, counters part-filled) and the matcher obliges with a Bold - or, when
the swelling is severe, dodges to a condensed face at negative tracking that
was never in the design. This pass re-fits each size-group against the
reference with the finish applied to the CANDIDATE tiles in cv2, mirroring
the renderer's own chain: grayscale dilation for gain, extra Gaussian for
softness, and a steep re-threshold for the hard-edged xerox look - no
re-render, solving face, weight, true size and finish jointly in one bench
batch. The candidates cover the lighter weights of the group's own family AND
of its clean runners-up, so a swollen mono can out-explain the condensed
dodge that beat it clean. Weights are discrete and gain fills the gaps
between them, so among near-equal fits the lighter weight + least finish
wins.

A finish is only recorded when the finished fit truly explains the ink
(BEST_FLOOR) and beats every clean candidate by a clear margin: a true Bold
is matched perfectly by the Bold face, and a dilated Regular cannot beat it
(bold designs change proportions, not just stroke width), so clean sheets
pass through untouched. Residuals on the winning fit name the rest of the
look: contour length beyond the fit's becomes `rough` (the photocopy's eroded
edge), and a winning re-thresholded fit keeps `threshold`.

Everything is written back onto the Match - face, size, score and the
`finish` dict - before the trust filter runs, so type whose clean match
looked hopeless stays live once the finish explains it.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from dataclasses import replace as _replace

from .layout import Block
from .typeface import (Bench, Face, Match, Sample, _compare, _face, _items,
                       _samples, _Try, instance_size, instances, shortlist)

# Em-relative ladders. Gain is the dilation radius; blur is the extra sigma on
# top of the document's scan softness (bench.blur), so a clean sheet fits at 0.
GAIN_EM = (0.0, 0.012, 0.02, 0.03, 0.045, 0.065)
BLUR_EM = (0.0, 0.01, 0.02, 0.035)
SIZE_MULTS = (1.0, 0.94, 0.88)   # dilation re-inflates a smaller true size
MARGIN = 0.02                    # the finish must beat every clean candidate by this
TIE = 0.008                      # fits this close are "equal"; prefer lighter/less
BEST_FLOOR = 0.86                # the finished fit must actually explain the ink
RAGGED_FLOOR = 0.80              # ...a positively-identified photocopy a little less so
GAIN_CAP = 0.055                 # beyond this the "gain" is a wrong weight in disguise
TRY_CEIL = 0.90                  # groups explained this well clean are left alone


def _disk(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _harden(tile: np.ndarray) -> np.ndarray:
    """The xerox re-threshold: mid-tones snap to ink or paper."""
    return np.clip((tile - 0.45) * 6.0, 0.0, 1.0)


def _weight_ladder(face: Face, insts: Dict[str, Dict], per: int = 3) -> List[Face]:
    """The face's own weight and its nearest lighter siblings (gain only adds ink)."""
    ws = sorted({_face(k).weight for k in insts
                 if _face(k).family == face.family and (_face(k).stretch or 100) == (face.stretch or 100)
                 and _face(k).weight <= face.weight}, reverse=True)
    return [Face(face.family, w, face.stretch, face.italic) for w in ws[:per]]


def _stroke(ref: np.ndarray) -> Optional[float]:
    """Mean stroke width of the reference ink, px (twice the ridge distance)."""
    ink = (ref > 0.45).astype(np.uint8)
    if int(ink.sum()) < 30:
        return None
    dt = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    return 2.0 * float(dt[ink > 0].mean())


def _degained(s: Sample, r: float) -> Optional[Sample]:
    """The sample as it would measure with r px of ink gain peeled off."""
    t = _stroke(s.ref)
    if not t or t <= 2 * r + 0.5:
        return None
    return _replace(s, height=max(4.0, s.height - 2 * r), ink_w=max(2.0, s.ink_w - 2 * r),
                    mass=s.mass * max(0.15, (t - 2 * r) / t))


def _candidates(m: Match, picks: Sequence[Sample], insts: Dict[str, Dict],
                families: int = 3, cap: int = 12) -> List[Face]:
    """Lighter weights of the group's own family, of its clean runners-up, and
    of the faces the features point at once a hypothetical gain is peeled off:
    severe gain pushes the clean shortlist to families that were never there."""
    best: Dict[Tuple[str, Optional[int], bool], Tuple[float, Face]] = {}
    for k, v in m.scores.items():
        f = _face(k)
        key = (f.family, f.stretch, f.italic)
        if key not in best or v > best[key][0]:
            best[key] = (v, f)
    own = (m.face.family, m.face.stretch, m.face.italic)
    ranked = sorted(best, key=lambda k: (k != own, -best[k][0]))[:families]
    faces: List[Face] = []
    for key in ranked:
        faces.extend(_weight_ladder(best[key][1], insts, per=4 if key == own else 2))
    for r_em in (0.025, 0.05):
        adj = [d for s in picks if (d := _degained(s, r_em * m.size_px)) is not None]
        if adj:
            for f in shortlist(adj, insts, k=3, per_family=1):
                faces.extend(_weight_ladder(f, insts, per=2))
    seen, out = set(), []
    for f in faces:
        if f.key not in seen:
            seen.add(f.key)
            out.append(f)
    return out[:cap]


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


def _residuals(ref: np.ndarray, fit: np.ndarray) -> Tuple[float, float]:
    """(raggedness, midtone fraction) of ref against the aligned winning fit.

    Raggedness: how much longer the reference's ink contour runs than the
    fit's at matched area - eroded photocopy edges wander. Midtone fraction:
    how much of the reference's edge band sits between ink and paper - a
    re-thresholded copy has almost none."""
    if fit.shape[0] < ref.shape[0] or fit.shape[1] < ref.shape[1]:
        return 1.0, 1.0
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
    debug = bool(os.environ.get("RIP_DEBUG_FINISH"))
    insts = instances()
    samples = _samples(img, blocks)
    found = 0
    for group in _groups(blocks, matches):
        m0 = matches[group[0]]
        chars = sum(sum(c.isalnum() for c in blocks[bi].text()) for bi in group)
        need = 4 if m0.size_px >= 28 else 8   # a display word is its own print run
        if chars < need or m0.score >= TRY_CEIL or m0.size_px < 14:
            if debug and chars >= 4 and m0.size_px >= 14:
                print(f"    finish- {blocks[group[0]].text()[:24]!r} size={m0.size_px:.0f} "
                      f"{m0.face.key} score={m0.score:.3f} chars={chars} (left alone)")
            continue
        picks = [s for bi in group if bi in samples for s in samples[bi]][:3]
        if not picks:
            continue
        faces = _candidates(m0, picks, insts)

        def base(s: Sample, f: Face) -> float:
            inst = insts.get(f.upright.key)
            return instance_size(s, inst) if inst else s.height / 0.7

        # One bench batch: every sample at every candidate face and true size.
        tries = [_Try(s, f, base(s, f) * mult)
                 for s in picks for f in faces for mult in SIZE_MULTS]
        items = _items(tries, fit=True)
        tiles = bench.render(items)

        # The grid, scored per (face, mult, gain, blur, threshold) as the mean
        # over samples - the finish chain applied to the tiles in cv2.
        size = m0.size_px
        gains = sorted({int(round(e * size)) for e in GAIN_EM})
        blurs = sorted({round(e * size, 2) for e in BLUR_EM})
        grid: Dict[Tuple, List[float]] = {}
        fits: Dict[Tuple, Tuple[np.ndarray, np.ndarray]] = {}
        for t, it, (tile, _) in zip(tries, items, tiles):
            mu = round(t.size / base(t.sample, t.face), 3)
            for r in gains:
                fat = cv2.dilate(tile, _disk(r)) if r > 0 else tile
                for sg in blurs:
                    soft = cv2.GaussianBlur(fat, (0, 0), sg) if sg > 0 else fat
                    for thr in (0, 1):
                        cand = _harden(soft) if thr else soft
                        sc, _, _ = _compare(t.sample.ref, cand, it["_dx"], it["_dy"], bench.blur)
                        key = (t.face.key, mu, r, sg, thr)
                        grid.setdefault(key, []).append(sc)
                        if t.sample is picks[0]:
                            fits[key] = (t.sample.ref, cand)
        score = {k: float(np.mean(v)) for k, v in grid.items()}
        clean = max(v for (fk, mu, r, sg, thr), v in score.items() if r == 0 and sg == 0 and thr == 0)
        best = max(score.values())
        # Among near-equal fits: the lightest weight, then the least finish.
        fk, mu, r, sg, thr = min((k for k, v in score.items() if v >= best - TIE),
                                 key=lambda k: (_face(k[0]).weight, k[2], k[3], k[4], -k[1]))
        size_win = float(np.median([base(s, _face(fk)) for s in picks])) * mu
        gain_em = r / max(1.0, size_win)
        rag, mid = _residuals(*fits[(fk, mu, r, sg, thr)])
        # A reference with almost no mid-tones on its edges positively looks
        # re-thresholded; its unmodelled raggedness suppresses every score, so
        # the bar drops a little - but only for a winning thresholded fit.
        hard = mid < 0.45
        floor = RAGGED_FLOOR if (thr and hard) else BEST_FLOOR
        margin = 0.012 if (thr and hard) else MARGIN
        if debug:
            print(f"    finish? {blocks[group[0]].text()[:24]!r} size={size:.0f} {m0.face.key} "
                  f"clean={clean:.3f} best={best:.3f} {fk} r={r} sg={sg} thr={thr} mu={mu} "
                  f"rag={rag:.2f} mid={mid:.2f}")
        # The finished fit must truly explain the ink: dilation nudging a bad
        # face up a little is a wrong weight, not a finish.
        if r <= 0 and not thr:
            continue
        if best < clean + margin or best < floor or gain_em > GAIN_CAP:
            continue

        face = _face(fk)
        fin: Dict[str, object] = {}
        if gain_em > 0:
            fin["gain"] = round(gain_em, 4)
        if sg > 0:
            fin["blur"] = round(sg / max(1.0, size_win), 4)
        if thr:
            fin["threshold"] = 0.5
        if rag >= 1.15:
            fin["rough"] = {"freq": 8, "scale": round(min(0.08, max(0.02, 0.04 * (rag - 1) / 0.15)), 3),
                            "seed": 7}
        if not fin:
            continue
        owner = {}
        for bi in group:
            for s in samples.get(bi, []):
                owner[id(s)] = bi
        for bi in group:
            m = matches[bi]
            own = [base(s, face) * mu for s in picks if owner.get(id(s)) == bi]
            m.face = face
            m.size_px = float(np.mean(own)) if own else size_win
            m.score = best
            m.scores[face.key] = best
            m.finish = dict(fin)
            if face.family != m0.face.family:
                m.tracking_em = 0.0   # the dodge's tracking belonged to the dodge
        found += 1
        say(f"Print finish on {len(group)} block(s) at {size:.0f}px: {face.key}, "
            f"{fin}, clean fit was {clean:.3f} -> {best:.3f}")
    return found
