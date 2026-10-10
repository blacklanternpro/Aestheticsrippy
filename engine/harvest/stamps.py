"""
Rubber-stamp rings: text set round a circle, woven through the stamp's own
art (a globe's rim and meridians, a crest, crossing rules), often clipped by
the sheet's edge.

The letters never come free by connected components - they touch the lines -
so no piecing is attempted in sheet space. Instead the stamp is found by its
motif (a compact, hole-dense blob of line art), the text ring is found as the
circle whose annulus the letter-sized ink fills thickly, and the annulus is
unrolled: in polar space the ring becomes an ordinary line of upright type,
the crossing furniture becomes clutter clinging to the strip's edges, and the
line readers do the rest. Reading from the raw ink, the unroll also reaches
letters a bloated OCR word box swallowed.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .art import ink_map
from .curved import PathText, _lexical, _wordness
from .ocr import read_lines

CAP_FALLBACK = 14.0


def find(img: np.ndarray, regions, bg: np.ndarray, rules: Optional[np.ndarray] = None,
         glyphs=None, lines: Sequence = ()) -> Tuple[List[PathText], List]:
    """
    Ring text on rubber stamps: (readings, regions). Letter pixels are cut
    from the regions that held them, and orphaned stamp ink (art a text box
    swallowed) is folded back into the stamp's own region.
    """
    H, W = img.shape[:2]
    ink = ink_map(img, bg).astype(np.float32)
    rul = (cv2.dilate(rules, np.ones((3, 3), np.uint8)) > 0) if rules is not None \
        else np.zeros((H, W), bool)
    raw = ink.copy()
    raw[rul] = 0.0

    canvas = np.zeros((H, W), np.uint8)
    for reg in regions:
        if reg.mask is None or reg.kind not in ("mark", "photo"):
            continue
        x0, y0, x1, y1 = reg.box
        canvas[y0:y1, x0:x1] |= reg.mask.astype(np.uint8)
    nl, lab, st, cen = cv2.connectedComponentsWithStats(canvas, 8)

    found: List[PathText] = []
    for mi in _motifs(nl, lab, st):
        mcx, mcy = cen[mi]
        mr = 0.5 * max(st[mi][2], st[mi][3])
        cap, letters = _letter_members(nl, st, cen, mi, mcx, mcy, mr, lab)
        if letters.sum() < 6 * cap:
            continue
        got = None
        for ring in _ring_search(letters, mcx, mcy, mr, cap, W, H):
            cx, cy, rt = _polish(raw, *ring, cap, W, H)
            for drt, dcap in ((0.0, 1.0), (-0.5, 1.0), (0.5, 1.0), (0.0, 1.2)):
                # the fit lands within half a cap of the truth; a short ladder
                # of hypotheses costs little and forgives the residual
                got = _read_ring(img, raw, cx, cy, rt + drt * cap, cap * dcap, W, H, glyphs)
                if got is not None:
                    break
            if got is not None:
                break
        if got is None:
            continue
        text, conf, strip_keep, tcol, rs, comps, (cx, cy, rt) = got
        pt = _emit(img, text, conf, cx, cy, tcol, rs, comps, strip_keep)
        if pt is None:
            continue
        _claim(regions, raw, lines, cx, cy, rt, cap, strip_keep, tcol, rs, mi, lab, st)
        found.append(pt)
    return found, regions


# ------------------------------------------------------------------ locating

def _motifs(nl, lab, st) -> List[int]:
    """Compact, holey blobs: a stamp's central art encloses paper (meridian
    quads, crest counters, ring gaps), where bars and borders enclose none."""
    out = []
    for i in range(1, nl):
        x, y, w, h, area = st[i]
        if area < 250 or max(w, h) < 25 or max(w, h) / max(1, min(w, h)) > 2.0:
            continue
        mm = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        cont, hier = cv2.findContours(mm, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is None:
            continue
        floor = max(9.0, 0.0015 * area)
        holes = sum(1 for c, hh in zip(cont, hier[0]) if hh[3] >= 0 and cv2.contourArea(c) >= floor)
        if holes >= 4:
            out.append(i)
    return out


def _letter_members(nl, st, cen, mi, mcx, mcy, mr, lab):
    """Letter-sized components around the motif, and their median size.
    Letter size scales with the stamp: a ring letter runs a modest fraction
    of the motif's radius, whatever the sheet's resolution."""
    caps = []
    idx = []
    for i in range(1, nl):
        x, y, w, h, area = st[i]
        if i == mi or area < 15:
            continue
        if np.hypot(cen[i][0] - mcx, cen[i][1] - mcy) > 2.6 * mr:
            continue
        if max(5.0, 0.08 * mr) <= max(w, h) <= 1.1 * mr:
            caps.append(float(max(w, h)))
        idx.append(i)
    cap = float(np.median(caps)) if caps else CAP_FALLBACK
    letters = np.zeros(lab.shape, np.uint8)
    for i in idx:
        x, y, w, h, area = st[i]
        if max(w, h) <= 2.2 * cap:
            letters[lab == i] = 1
    return cap, letters


def _ring_search(letters, mcx, mcy, mr, cap, W, H):
    """
    The circle whose annulus the letter ink fills thickly: a grid of centres
    about the motif, radii out to where a ring could sit. A bin of the ring
    counts only when its ink spans most of a cap height radially - the rule
    that tells the text ring from the motif's own rim.
    """
    py, px = np.nonzero(letters)
    if len(px) < 40:
        return []
    P = np.c_[px, py].astype(np.float64)
    NB = 72
    ranked = []
    step = max(2.0, mr / 12.0)
    reach = 0.62 * mr
    rstep = max(1.0, cap / 10.0)
    offs = np.arange(-reach, reach + 1e-6, step)
    rts = np.arange(1.1 * mr, 3.0 * mr, rstep)
    win = 0.6 * cap
    for dx in offs:
        for dy in offs:
            c = (mcx + dx, mcy + dy)
            d0 = P[:, 0] - c[0]
            d1 = P[:, 1] - c[1]
            rr = np.hypot(d0, d1)
            bins = ((np.arctan2(d1, d0) + np.pi) / (2 * np.pi) * NB).astype(int) % NB
            # occupancy of (angle bin, radius row): thickness tests become
            # row spans instead of per-bin percentile loops
            ri = np.round(rr).astype(int)
            rmax = int(rts[-1] + win) + 2
            keep_pts = ri < rmax
            M = np.zeros((NB, rmax), bool)
            M[bins[keep_pts], ri[keep_pts]] = True
            tb = (np.arange(NB) + 0.5) / NB * 2 * np.pi - np.pi
            for rt in rts:
                lo, hi = int(rt - win), int(rt + win) + 1
                Wn = M[:, max(0, lo):hi]
                anyb = Wn.any(axis=1)
                if not anyb.any():
                    continue
                first = np.argmax(Wn, axis=1)
                last = Wn.shape[1] - 1 - np.argmax(Wn[:, ::-1], axis=1)
                good = int((anyb & (last - first >= 0.45 * cap)).sum())
                ox = c[0] + rt * np.cos(tb)
                oy = c[1] + rt * np.sin(tb)
                ons = int(((ox >= 0) & (ox < W) & (oy >= 0) & (oy < H)).sum())
                score = (good / max(1, ons)) * min(1.0, good / 20)
                if good >= 10 and score >= 0.18:
                    ranked.append((score, float(c[0]), float(c[1]), float(rt)))
    ranked.sort(reverse=True)
    out = []
    for sc, x, y, rr2 in ranked:
        if all(np.hypot(x - o[0], y - o[1]) > 0.4 * cap or abs(rr2 - o[2]) > 0.4 * cap
               for o in out):
            out.append((x, y, rr2))
        if len(out) >= 3:
            break
    return out


def _polish(raw, cx, cy, rt, cap, W, H):
    """
    The circle trued up on the raw ink: each column of a generous band casts
    a vote with its cap-tall ink runs, and a bounded robust fit of
    r(theta) = r + ex cos(theta) + ey sin(theta) absorbs the residual centre
    error. The bounds keep neighbouring straight text from stealing the fit.
    """
    strip, tcol, rs = _unwarp(raw, cx, cy, rt - 1.2 * cap, rt + 2.0 * cap, W, H)
    if strip is None:
        return cx, cy, rt
    sb = strip > 30
    T, R = [], []
    for j in range(sb.shape[1]):
        col = sb[:, j].astype(np.int8)
        d = np.diff(col)
        starts = list(np.nonzero(d == 1)[0] + 1) + ([0] if col[0] else [])
        for s in sorted(starts):
            e = s
            while e < len(col) and col[e]:
                e += 1
            if 0.5 * cap <= e - s <= 1.6 * cap:
                T.append(float(np.interp(j, np.arange(len(tcol)), tcol)))
                R.append(float(np.interp(0.5 * (s + e), np.arange(len(rs)), rs)))
    if len(T) < 12:
        return cx, cy, rt
    T = np.array(T)
    R = np.array(R)
    rng = np.random.default_rng(0)
    best = None
    for _ in range(2500):
        s = rng.choice(len(T), 3, replace=False)
        Am = np.c_[np.ones(3), np.cos(T[s]), np.sin(T[s])]
        try:
            r2, ex, ey = np.linalg.solve(Am, R[s])
        except np.linalg.LinAlgError:
            continue
        if abs(ex) > 0.5 * cap or abs(ey) > 0.5 * cap or not (rt - 0.5 * cap <= r2 <= rt + 0.8 * cap):
            continue
        res = np.abs(R - (r2 + ex * np.cos(T) + ey * np.sin(T)))
        nin = int((res < 2.2).sum())
        if best is None or nin > best[0]:
            best = (nin, res < 2.2)
    if best is None or best[0] < 8:
        return cx, cy, rt
    inl = best[1]
    Am = np.c_[np.ones(int(inl.sum())), np.cos(T[inl]), np.sin(T[inl])]
    sol, *_ = np.linalg.lstsq(Am, R[inl], rcond=None)
    r2, ex, ey = (float(v) for v in sol)
    if abs(ex) > 0.5 * cap or abs(ey) > 0.5 * cap or not (rt - 0.5 * cap <= r2 <= rt + 0.8 * cap):
        return cx, cy, rt
    return cx + ex, cy + ey, r2


# ------------------------------------------------------------------ reading

def _unwarp(src, cx, cy, r0, r1, W, H, ss: int = 1):
    """The annulus unrolled: rows from outer to inner radius, columns sweeping
    the on-sheet angles clockwise (the reading direction for crown text).
    `ss` supersamples both axes: binarising 11px letters and upscaling after
    throws away the greys that OCR and the atlas read by."""
    if r1 - r0 < 6:
        return None, None, None
    rmid = 0.5 * (r0 + r1)
    n = 1440
    th = np.linspace(-np.pi, np.pi, n, endpoint=False)
    onx = cx + rmid * np.cos(th)
    ony = cy + rmid * np.sin(th)
    on = (onx >= 0) & (onx < W) & (ony >= 0) & (ony < H)
    if on.all():
        ts = th
    else:
        off = np.nonzero(~on)[0]
        if len(off) == n:
            return None, None, None
        runs = np.split(off, np.nonzero(np.diff(off) > 1)[0] + 1)
        if off[0] == 0 and off[-1] == n - 1 and len(runs) > 1:
            runs[0] = np.concatenate([runs[-1], runs[0]])
            runs.pop()
        gap = max(runs, key=len)
        start = (gap[-1] + 1) % n
        order = (np.arange(n) + start) % n
        ts = np.unwrap(th[order])[on[order]]
    if len(ts) < 30:
        return None, None, None
    nrow = max(8, int(round((r1 - r0) * ss)))
    rs = np.linspace(r1, r0, nrow)
    ncol = max(60, int((ts[-1] - ts[0]) * rmid * ss))
    tcol = np.linspace(ts[0], ts[-1], ncol)
    mapx = (cx + rs[:, None] * np.cos(tcol)[None, :]).astype(np.float32)
    mapy = (cy + rs[:, None] * np.sin(tcol)[None, :]).astype(np.float32)
    flags = cv2.INTER_CUBIC if ss > 1 else cv2.INTER_LINEAR
    return cv2.remap(src, mapx, mapy, flags, borderValue=0), tcol, rs


SS = 3    # unroll supersampling


def ts_full(tcol) -> bool:
    return tcol is not None and (tcol[-1] - tcol[0]) >= 2 * np.pi * 0.98


def _read_ring(img, raw, cx, cy, rt, cap, W, H, glyphs=None, refit=True):
    """
    Unroll the text band, sweep the furniture off the strip's edges, and
    hand the row to the line reader. The reader supplies the text; where its
    confidence collapses (an @ in a worn stamp), the atlas verifies the
    reading letter by letter against the strip's own shapes. When the read
    fails but letters stood in the band, their feet re-true the circle - the
    baseline they share is the best measurement of it - and one more pass
    reads from the corrected band.
    """
    strip, tcol, rs = _unwarp(raw, cx, cy, rt - 0.8 * cap, rt + 1.5 * cap, W, H, ss=SS)
    if strip is None:
        return None
    nr = len(rs)
    capS = cap * SS
    sb = (strip > 30).astype(np.uint8)
    nl, lab, st, cen = cv2.connectedComponentsWithStats(sb, 8)
    keep = np.zeros_like(sb)
    comps = []
    for i in range(1, nl):
        x, y, w, h, area = st[i]
        if area < 8 * SS * SS:
            continue
        if y <= SS and y + h < 0.55 * nr:
            continue              # clings to the outer edge, never reaches the letters
        if y + h >= nr - SS and y > 0.78 * nr:
            continue              # pokes in from under the letters' feet
        if h > 1.9 * capS or w > 3.0 * capS:
            continue              # furniture crossing the band whole
        keep[lab == i] = 1
        comps.append((x, y, w, h, area))
    if keep.sum() < 4 * capS * SS:
        return None
    if ts_full(tcol):
        # A full ring has no sheet edge to cut it: start the row at the
        # text's own widest gap, or the reader starts mid-word.
        empty = (keep.sum(axis=0) == 0).astype(np.uint8)
        n = len(empty)
        two = np.r_[empty, empty]
        best_len, best_at, run = 0, 0, 0
        for j in range(len(two)):
            run = run + 1 if two[j] else 0
            if run > best_len and j - run + 1 < n:
                best_len, best_at = run, j - run + 1
        if best_len > 2:
            k = (best_at + best_len) % n     # first column after the gap
            strip = np.concatenate([strip[:, k:], strip[:, :k]], axis=1)
            keep = np.concatenate([keep[:, k:], keep[:, :k]], axis=1)
            tcol = np.concatenate([tcol[k:], tcol[:k] + 2 * np.pi])
    gs = 255 - np.clip(strip * 2.5, 0, 255).astype(np.uint8)
    gs[keep == 0] = 255
    pad = 40
    big = cv2.copyMakeBorder(gs, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    got = read_lines(cv2.cvtColor(big, cv2.COLOR_GRAY2BGR), psm=7, raw=True)
    words = [w for l in got for w in l.words if w.text.strip()]
    if not words:
        return None
    words.sort(key=lambda w: w.box[0])
    cells = _cells(keep, capS) if glyphs is not None else []
    picked = []
    for w in words:
        t = w.text.strip()
        c = float(w.conf)
        if glyphs is not None and c < 72:
            span = [cl for cl in cells if w.box[0] - pad - 2 <= cl[0] + cl[2] and cl[0] <= w.box[2] - pad + 2]
            agree, score = _verify(glyphs, t, span)
            if agree >= 0.6:
                c = score
            else:
                t2, c2 = _assemble(glyphs, span, capS)
                if t2 and c2 >= 74:
                    t, c = t2, c2
        picked.append((t, c))
    while picked and not any(ch.isalnum() for ch in picked[-1][0]):
        picked.pop()               # a clipped letter at the sheet's edge reads as a dash
    if not picked:
        return None
    t, c = picked[-1]
    while t and not (t[-1].isalnum() or t[-1] in ".!?"):
        t = t[:-1]                 # junk the sheet edge made of a half letter
    picked[-1] = (t, c)
    text = " ".join(t for t, c in picked).strip()
    conf = float(np.mean([c for t, c in picked]))
    letters = sum(ch.isalnum() for ch in text)
    cols = np.nonzero(keep.any(axis=0))[0]
    span = float(np.interp(cols[-1], np.arange(len(tcol)), tcol)
                 - np.interp(cols[0], np.arange(len(tcol)), tcol)) if len(cols) else 0.0
    gate = 70 if (_lexical(text) or _wordness(text) > 0.5) else 76
    # A stamp's ring says something and wraps far around: a short scrap of
    # bold digits on a circle of counters is a ledger row, not a stamp.
    if letters < 6 or span < np.radians(110) or conf < gate:
        if not refit:
            return None
        feet = [(float(np.interp(x + 0.5 * w, np.arange(len(tcol)), tcol)),
                 float(np.interp(y + h, np.arange(len(rs)), rs)))
                for x, y, w, h, a in comps if 0.5 * cap * SS <= h <= 1.6 * cap * SS]
        if len(feet) < 5:
            return None
        T = np.array([f[0] for f in feet])
        R = np.array([f[1] for f in feet])
        Am = np.c_[np.ones(len(T)), np.cos(T), np.sin(T)]
        sol, *_ = np.linalg.lstsq(Am, R, rcond=None)
        rf, ex, ey = (float(v) for v in sol)
        if abs(ex) > 0.9 * cap or abs(ey) > 0.9 * cap:
            return None
        if np.hypot(ex, ey) < 0.8 and abs(rf + 0.5 * cap - rt) < 0.8:
            return None     # nothing to correct: the reading simply failed
        return _read_ring(img, raw, cx + ex, cy + ey, rf + 0.5 * cap, cap, W, H,
                          glyphs, refit=False)
    return text, conf, keep, tcol, rs, comps, (cx, cy, rt)


def _cells(keep, capS):
    """The strip's letters, one cell each: components, with fused pairs split
    at their ink valleys. [(x, y, w, h, mask)] in reading order."""
    nl, lab, st, cen = cv2.connectedComponentsWithStats(keep, 8)
    out = []
    for i in range(1, nl):
        x, y, w, h, area = st[i]
        if area < 12:
            continue
        mm = lab[y:y + h, x:x + w] == i
        if w <= 1.35 * capS:
            out.append((x, y, w, h, mm))
            continue
        k = max(2, int(round(w / (0.95 * capS))))
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


def _verify(glyphs, text, cells):
    """How much of the reader's word the strip's shapes vouch for: the chars
    aligned to the cells in order, each checked against the cell's chart."""
    chars = [ch for ch in text.upper() if not ch.isspace()]
    letters = [c for c in cells if not (c[3] < 0.5 * c[2] and c[2] < 18)]
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


def _assemble(glyphs, cells, capS):
    """A reading straight from the atlas when the reader offers nothing
    usable: each cell's best upright character, dots and spaces by size."""
    chars, scores, xs = [], [], []
    for x, y, w, h, mm in cells:
        if h < 0.5 * capS and w < 0.6 * capS:
            chars.append(".")
            xs.append(x)
            continue
        got = glyphs.classify(mm, range(-24, 25, 8), top=1)
        if not got:
            continue
        sc, a, ch = got[0]
        if xs:
            adv = np.diff(xs)
            if len(adv) and x - xs[-1] > 1.7 * float(np.median(adv)):
                chars.append(" ")
        chars.append(ch)
        scores.append(100.0 * sc)
        xs.append(x)
    if not scores:
        return None, 0.0
    return "".join(chars), float(np.mean(scores))


# ------------------------------------------------------------------ emitting

def _emit(img, text, conf, cx, cy, tcol, rs, comps, keep) -> Optional[PathText]:
    """A PathText whose baseline is the arc under the letters' feet."""
    if not comps:
        return None
    ss = max(1, int(round(len(rs) / max(1.0, rs[0] - rs[-1]))))
    feet_row = float(np.median([y + h for x, y, w, h, a in comps]))
    r_base = float(np.interp(feet_row, np.arange(len(rs)), rs))
    caps_px = float(np.median([h for x, y, w, h, a in comps if h >= 5])) / ss
    cols = np.nonzero(keep.any(axis=0))[0]
    j0, j1 = int(cols[0]), int(cols[-1])
    t0 = float(np.interp(j0, np.arange(len(tcol)), tcol))
    t1 = float(np.interp(j1, np.arange(len(tcol)), tcol))
    pad = 3.0 / max(1.0, r_base)
    th = np.linspace(t0 - pad, t1 + pad, max(8, int((t1 - t0 + 2 * pad) * r_base / 4)))
    pts = np.c_[cx + r_base * np.cos(th), cy + r_base * np.sin(th)]
    ys, xs = np.nonzero(keep)
    # letter colour from the sheet, through the warp
    sx = (cx + np.interp(ys, np.arange(len(rs)), rs) * np.cos(np.interp(xs, np.arange(len(tcol)), tcol))).astype(int)
    sy = (cy + np.interp(ys, np.arange(len(rs)), rs) * np.sin(np.interp(xs, np.arange(len(tcol)), tcol))).astype(int)
    ok = (sx >= 0) & (sx < img.shape[1]) & (sy >= 0) & (sy < img.shape[0])
    colour = tuple(int(v) for v in np.median(img[sy[ok], sx[ok]], axis=0)) if ok.any() else (0, 0, 0)
    row = (255 - 255 * keep).astype(np.uint8)
    if ss > 1:
        row = cv2.resize(row, (max(1, row.shape[1] // ss), max(1, row.shape[0] // ss)),
                         interpolation=cv2.INTER_AREA)
    out = PathText(text, pts, caps_px, colour, conf, upright=False, light=False, row=row)
    out.offset = 3.0
    out.length = float((t1 - t0) * r_base)
    return out


def _claim(regions, raw, lines, cx, cy, rt, cap, keep, tcol, rs, mi, lab, st):
    """
    The letters leave the art: their pixels (mapped back from the strip) are
    cut from every region that held them. Orphaned stamp ink in the band -
    swallowed by a text box, so in no region at all - is folded into the
    stamp's own region so the art renders whole.
    """
    H, W = lab.shape
    ys, xs = np.nonzero(keep)
    sx = (cx + np.interp(ys, np.arange(len(rs)), rs) * np.cos(np.interp(xs, np.arange(len(tcol)), tcol)))
    sy = (cy + np.interp(ys, np.arange(len(rs)), rs) * np.sin(np.interp(xs, np.arange(len(tcol)), tcol)))
    letter = np.zeros((H, W), np.uint8)
    pxi = np.clip(np.round(sx).astype(int), 0, W - 1)
    pyi = np.clip(np.round(sy).astype(int), 0, H - 1)
    letter[pyi, pxi] = 1
    letter = cv2.dilate(letter, np.ones((3, 3), np.uint8))   # warp rounding leaves pinholes
    lb = letter > 0
    for reg in regions:
        if reg.mask is None:
            continue
        x0, y0, x1, y1 = reg.box
        reg.mask &= ~lb[y0:y1, x0:x1]
    # fold orphaned band ink into the stamp's region
    host = None
    for reg in regions:
        if reg.mask is None:
            continue
        x0, y0, x1, y1 = reg.box
        if x0 <= st[mi][0] < x1 and y0 <= st[mi][1] < y1:
            host = reg
            break
    if host is None:
        return
    from .art import debloat, text_mask
    tm = text_mask((H, W), debloat(list(lines))) if len(lines) else np.zeros((H, W), bool)
    yy, xx = np.mgrid[0:H, 0:W]
    band = np.hypot(xx - cx, yy - cy) <= rt + 1.3 * cap
    orphan = (raw > 30) & band & ~lb & ~tm
    x0, y0, x1, y1 = host.box
    inside = np.zeros((H, W), bool)
    inside[y0:y1, x0:x1] = host.mask
    orphan &= ~inside
    ny, nx = np.nonzero(orphan)
    if len(ny) == 0:
        return
    nx0, ny0 = min(x0, int(nx.min())), min(y0, int(ny.min()))
    nx1, ny1 = max(x1, int(nx.max()) + 1), max(y1, int(ny.max()) + 1)
    m = np.zeros((ny1 - ny0, nx1 - nx0), bool)
    m[y0 - ny0:y1 - ny0, x0 - nx0:x1 - nx0] = host.mask
    m[ny - ny0, nx - nx0] = True
    host.box = (nx0, ny0, nx1, ny1)
    host.mask = m
