"""
Type set at an angle: diagonal labels, sideways spines, tilted stamps.

The page readers only see horizontal lines, so rotated type ends up in the
art. For each mark, find its main direction from the spread of its ink, turn
it level (both ways round), read it, and keep a confident reading as rotated
text frames. Whatever the reading covers is taken out of the mark.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .art import Region, ink_map
from .ocr import GOOD, read_lines


@dataclass
class RotText:
    text: str
    angle: float          # degrees, clockwise (CSS rotate)
    cx: float             # sheet px: centre of the line's cap band
    cy: float
    cap: float            # cap height (or x-height-based estimate), px
    width: float          # ink width along the line, px
    colour: Tuple[int, int, int]
    conf: float


def _direction(points: np.ndarray) -> Optional[float]:
    """Main direction of a point cloud, degrees in (-90, 90], or None if it is round."""
    pts = points.astype(np.float64)
    pts -= pts.mean(axis=0)
    cov = np.cov(pts.T)
    vals, vecs = np.linalg.eigh(cov)
    if vals[1] < 2.5 * max(vals[0], 1e-6):
        return None
    vx, vy = vecs[:, 1]
    a = float(np.degrees(np.arctan2(vy, vx)))
    if a <= -90:
        a += 180
    if a > 90:
        a -= 180
    return a


def _rotate(img: np.ndarray, angle: float, fill: int = 255):
    """Rotate so a line at `angle` (clockwise) becomes level; returns image and the 2x3 matrix."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos) + 2, int(h * cos + w * sin) + 2
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    out = cv2.warpAffine(img, m, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=fill)
    return out, m


def _skew(mask: np.ndarray, min_angle: float = 6) -> List[float]:
    """
    The angle (away from level) at which the mark's ink falls into the sharpest
    rows: skew detection by projection. Level type the page readers already
    passed over is ignored, so a tilted block beside it still gets found.
    """
    ys, xs = np.nonzero(mask)
    if len(xs) < 40:
        return []
    if len(xs) > 6000:
        pick = np.random.default_rng(0).choice(len(xs), 6000, replace=False)
        ys, xs = ys[pick], xs[pick]

    def sharp(deg: float) -> float:
        t = np.radians(deg)
        proj = -xs * np.sin(t) + ys * np.cos(t)
        h = np.bincount((proj - proj.min()).astype(int))
        return float((h.astype(np.float64) ** 2).sum()) / len(xs)

    scores = {deg: sharp(deg) for deg in range(-89, 91)}
    floor = float(np.median(list(scores.values())))
    # Local peaks away from level, strongest first: one mark can hold blocks at several angles.
    peaks = []
    for d, v in scores.items():
        if abs(d) < min_angle or v < floor * 1.35:
            continue
        if v >= scores.get(d - 1, 0) and v >= scores.get(d + 1, 0):
            peaks.append((v, d))
    out: List[float] = []
    for v, d in sorted(peaks, reverse=True):
        if all(abs(d - o) > 10 for o in out):
            out.append(float(d))
        if len(out) >= 3:
            break
    return out


def _piece_angles(mask: np.ndarray, min_angle: float = 6) -> List[float]:
    """
    Angles the mark's long pieces (words whose letters run together) agree on.
    Projection sharpness is ruled by the biggest family of lines, so a second,
    smaller family (one arm of a V) can hide under its floor; the pieces still
    point its way.
    """
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    pieces = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 20:
            continue
        ys, xs = np.nonzero(lab == i)
        q = np.stack([xs, ys], 1).astype(np.float64)
        q -= q.mean(axis=0)
        _, vecs = np.linalg.eigh(np.cov(q.T))
        major, minor = vecs[:, 1], vecs[:, 0]
        length, width = float(np.ptp(q @ major)), float(np.ptp(q @ minor))
        a = (float(np.degrees(np.arctan2(major[1], major[0]))) + 90) % 180 - 90
        pieces.append((a, length, width))
    if not pieces:
        return []
    h = float(np.median([w for _, _, w in pieces]))
    long = [(a, l) for a, l, w in pieces if l > 3 * w and l > 2.5 * h]
    total = sum(l for _, l in long)
    out: List[float] = []
    for a, _ in sorted(long, key=lambda t: -t[1]):
        near = [(b, l) for b, l in long if _adiff(a, b) <= 4]
        share = sum(l for _, l in near)
        if len(near) < 2 or share < 0.15 * total or abs(a) < min_angle:
            continue
        mean = float(np.average([b for b, _ in near], weights=[l for _, l in near]))
        if all(_adiff(mean, o) > 10 for o in out):
            out.append(float(round(mean)))
    return out


def _neighbour_angles(ink: np.ndarray, min_angle: float = 6) -> List[float]:
    """
    Angles from letters' nearest neighbours (a docstrum): within a word the next
    letter lies along the baseline, closer than the next line, so the directions
    to near neighbours pile up at each family's angle however small the family.
    Only pairs of like-sized pieces closer than a letter's height vote, which
    keeps line-to-line pairs (the perpendicular) out.
    """
    n, lab, st, cen = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    ok = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 6]
    if len(ok) < 6:
        return []
    if len(ok) > 2500:   # a texture, not lettering: sample it rather than pair every speck
        ok = list(np.random.default_rng(0).choice(ok, 2500, replace=False))
    size = np.array([max(st[i, 2], st[i, 3]) for i in ok], float)
    h = float(np.median(size))
    pts = cen[ok]
    votes = []
    for j in range(len(ok)):
        d = np.hypot(*(pts - pts[j]).T)
        d[j] = np.inf
        like = (size > 0.5 * size[j]) & (size < 2.0 * size[j])
        cand = np.where(like & (d < 1.1 * h))[0]
        for k in cand[np.argsort(d[cand])][:2]:
            dx, dy = pts[k] - pts[j]
            votes.append((float(np.degrees(np.arctan2(dy, dx))) + 90) % 180 - 90)
    if len(votes) < 6:
        return []
    hist = np.zeros(180)
    for v in votes:
        hist[int(round(v)) % 180] += 1
    smooth = np.convolve(np.r_[hist[-3:], hist, hist[:3]], np.ones(5) / 5, mode="same")[3:-3]
    out: List[float] = []
    floor = max(3.0, 0.12 * len(votes) / 5)
    for d in np.argsort(-smooth):
        a = (d + 90) % 180 - 90
        if smooth[d] < floor:
            break
        if abs(a) < min_angle or smooth[d] < smooth[(d - 1) % 180] or smooth[d] < smooth[(d + 1) % 180]:
            continue
        if all(_adiff(a, o) > 10 for o in out):
            out.append(float(a))
        if len(out) >= 3:
            break
    return out


def _angles(mask: np.ndarray, ink: Optional[np.ndarray] = None) -> List[float]:
    """
    The mark's line angles: projection peaks, plus any family the pieces agree
    on. Pieces come from the ink itself when given (the mark's mask is grown and
    fuses stacked lines into one blob).
    """
    out = _skew(mask)
    pieces = mask if ink is None else ink & mask
    for a in _piece_angles(pieces) + _neighbour_angles(pieces):
        if all(_adiff(a, o) > 10 for o in out):
            out.append(a)
    return out


def _adiff(a: float, b: float) -> float:
    """Distance between two line directions, degrees (directions repeat every 180)."""
    d = abs(a - b) % 180
    return min(d, 180 - d)


def split_angles(ink: np.ndarray, angles: Sequence[float], tol: float = 12) -> dict:
    """
    Share a mark's ink out among the angles its lines run at, so each family can
    be levelled and read without the other's ink crossing its rows (the arms of
    a V, a starburst of labels). Returns {angle: mask}.

    Words and long pieces vote by their own direction. A single letter's shape
    says little about its baseline, so it goes where a thin strip through it
    finds the most ink already placed: along its line the strip runs through
    neighbouring letters; across, it falls into the leading. Pieces running
    clearly at none of the angles (level type, a rule) are left out.
    """
    out = {float(a): np.zeros(ink.shape, bool) for a in angles}
    if not len(angles):
        return out
    n, lab, st, cen = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    if n <= 1:
        return out
    shapes = {}
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 4:
            continue
        ys, xs = np.nonzero(lab == i)
        q = np.stack([xs, ys], 1).astype(np.float64)
        q -= q.mean(axis=0)
        if len(q) < 3:
            continue
        _, vecs = np.linalg.eigh(np.cov(q.T))
        major, minor = vecs[:, 1], vecs[:, 0]
        a = (float(np.degrees(np.arctan2(major[1], major[0]))) + 90) % 180 - 90
        shapes[i] = (a, float(np.ptp(q @ major)), float(np.ptp(q @ minor)))
    if not shapes:
        return out
    # The scale of a letter (or of a line, where letters run together): the narrow
    # side of the pieces. A lone I or l is long and thin but short in absolute
    # terms, so it only votes by its direction when it is long beside this.
    h = max(4.0, float(np.median([w for _, _, w in shapes.values()])))

    pick = {}
    for i, (a, length, width) in shapes.items():
        best = min(angles, key=lambda t: _adiff(t, a))
        # Long pieces (a word whose letters run together) know their baseline.
        if length > 1.8 * width and length > 1.5 * h:
            if _adiff(best, a) < tol:
                pick[i] = float(best)
            elif min(_adiff(t, a) for t in angles) > 20:
                pick[i] = None          # runs its own way: not one of these lines
    sure = {float(t): np.isin(lab, [i for i, p in pick.items() if p == t]) for t in angles}
    pts = {t: np.stack(np.nonzero(m)[::-1], 1).astype(np.float64) for t, m in sure.items()}
    if not all(len(p) for p in pts.values()):
        everything = np.stack(np.nonzero(ink)[::-1], 1).astype(np.float64)
        pts = {t: everything for t in pts}
    for i in shapes:
        if i in pick:
            continue
        c = cen[i]
        score = {}
        for t, p in pts.items():
            if not len(p):
                score[t] = 0
                continue
            r = np.radians(t)
            q = p - c
            along = np.abs(q @ np.array([np.cos(r), np.sin(r)]))
            across = np.abs(q @ np.array([-np.sin(r), np.cos(r)]))
            score[t] = int(((along < 2.5 * h) & (across < 0.25 * h)).sum())
        if max(score.values()) > 0:
            pick[i] = max(score, key=score.get)
    # Whatever is still unplaced (dots, specks) follows its nearest placed neighbour.
    placed = [i for i, p in pick.items() if p is not None]
    for i in range(1, n):
        if i in pick or not placed:
            continue
        j = min(placed, key=lambda k: float(np.hypot(*(cen[i] - cen[k]))))
        pick[i] = pick[j]
    for t in out:
        ids = [i for i, p in pick.items() if p == t]
        if ids:
            out[t] = np.isin(lab, ids)
    return out


def _families(reg_mask: np.ndarray, ink: np.ndarray, angles: Sequence[float]) -> dict:
    """split_angles on the ink, then every pixel of the region mask goes with its nearest ink."""
    fams = split_angles(ink & reg_mask, angles)
    if len(fams) < 2:
        return fams
    keys = list(fams)
    dist = np.stack([cv2.distanceTransform((~fams[k]).astype(np.uint8), cv2.DIST_L2, 3) if fams[k].any()
                     else np.full(reg_mask.shape, 1e9, np.float32) for k in keys])
    near = dist.argmin(axis=0)
    far = dist.min(axis=0) > 6
    return {k: reg_mask & (near == n) & ~far | fams[k] for n, k in enumerate(keys)}


def _bands(level_mask: np.ndarray, min_h: int = 4) -> List[Tuple[int, int, int, int]]:
    """Text lines in a levelled mask: row bands, each cut at wide gaps into phrases."""
    rows = level_mask.sum(axis=1)
    on = rows > max(1, 0.04 * rows.max())
    out, y = [], 0
    H = len(rows)
    while y < H:
        if not on[y]:
            y += 1
            continue
        y0 = y
        while y < H and (on[y] or (y + 1 < H and on[y + 1])):
            y += 1
        y1 = y
        if y1 - y0 < min_h:
            continue
        cols = level_mask[y0:y1].any(axis=0)
        xs = np.nonzero(cols)[0]
        if not len(xs):
            continue
        # Lines can share a baseline across a wide gap (the arms of a V): cut there.
        # Word spaces are well under a line height.
        gap = max(6, int(1.6 * (y1 - y0)))
        start, prev = xs[0], xs[0]
        for x in list(xs[1:]) + [None]:
            if x is None or x - prev > gap:
                out.append((int(start), y0, int(prev) + 1, y1))
                if x is not None:
                    start = x
            if x is not None:
                prev = x
    return out


def _grow(img, bg, reg: Region, boxes) -> List[np.ndarray]:
    """
    Take the ink of level readings in `boxes` into the mark (box and mask grow
    to hold them). Returns, per box, its ink as a mask over the grown box.
    """
    x0, y0, x1, y1 = reg.box
    H, W = img.shape[:2]
    # The art lost each reading's box plus a margin (art.text_mask): lend both back.
    g = [0.2 * (b[3] - b[1]) + 1 for b in boxes]
    bs = [(max(0, int(b[0] - e)), max(0, int(b[1] - e)), min(W, int(np.ceil(b[2] + e))), min(H, int(np.ceil(b[3] + e))))
          for b, e in zip(boxes, g)]
    nx0, ny0 = min([x0] + [b[0] for b in bs]), min([y0] + [b[1] for b in bs])
    nx1, ny1 = max([x1] + [b[2] for b in bs]), max([y1] + [b[3] for b in bs])
    mask = np.zeros((ny1 - ny0, nx1 - nx0), bool)
    mask[y0 - ny0:y1 - ny0, x0 - nx0:x1 - nx0] = reg.mask
    dist = ink_map(img[ny0:ny1, nx0:nx1], bg[ny0:ny1, nx0:nx1])
    inside = dist[mask]
    level = 0.5 * float(np.median(inside)) if inside.size else 40.0
    out = []
    for bx0, by0, bx1, by1 in bs:
        m = np.zeros(mask.shape, bool)
        m[by0 - ny0:by1 - ny0, bx0 - nx0:bx1 - nx0] = dist[by0 - ny0:by1 - ny0, bx0 - nx0:bx1 - nx0] > level
        mask |= m
        out.append(m)
    reg.box, reg.mask = (nx0, ny0, nx1, ny1), mask
    return out


def _real_families(img, bg, reg: Region, angles: Sequence[float]) -> dict:
    """
    The mark's ink shared out by angle, keeping only families that are lines in
    their own right: a fair share of the ink whose own skew comes back at the
    family's angle. A stray skew peak on a single tilted line (letter strokes
    lining up) fails this, as its letters still line up at the line's own angle.
    Returns {} unless at least two families are real.
    """
    x0, y0, x1, y1 = reg.box
    dist = ink_map(img[y0:y1, x0:x1], bg[y0:y1, x0:x1])
    inside = dist[reg.mask]
    if not inside.size:
        return {}
    ink = dist > 0.5 * float(np.median(inside))
    fams = _families(reg.mask, ink, angles)
    total = max(1, int(reg.mask.sum()))
    real = {}
    for a, m in fams.items():
        if m.sum() < 0.12 * total:
            continue
        own = _skew(m & ink)
        if own and _adiff(own[0], a) <= 4:
            real[a] = m
    return real if len(real) > 1 else {}


def _near(box, reg_box, gap: float) -> bool:
    x0, y0, x1, y1 = reg_box
    return box[0] < x1 + gap and box[2] > x0 - gap and box[1] < y1 + gap and box[3] > y0 - gap


def find(img: np.ndarray, regions: Sequence[Region], bg: np.ndarray, min_conf: float = 80,
         loose: Sequence[Tuple[int, Tuple[float, float, float, float]]] = ()
         ) -> Tuple[List[RotText], List[Region], List[int]]:
    """
    Rotated text in the marks, the regions with that text taken out, and which
    of the `loose` level readings (id, box) turned out to be part of it.

    `loose` are short level readings, a letter or two: the page readers often
    take the first letters of a tilted word for a level one, which leaves the
    rest of the word too short to read. They are lent to any angled mark they
    touch; those an angled reading covers are reported back so the level
    reading can be dropped.
    """
    found: List[RotText] = []
    kept: List[Region] = []
    absorbed: List[int] = []
    for reg in regions:
        if reg.kind != "mark" or reg.mask is None or reg.mask.sum() < 60:
            kept.append(reg)
            continue
        # The mark's own angles, found before any level ink is lent to it.
        x0, y0, x1, y1 = reg.box
        dist = ink_map(img[y0:y1, x0:x1], bg[y0:y1, x0:x1])
        inside = dist[reg.mask]
        angles = _angles(reg.mask, dist > 0.5 * float(np.median(inside)) if inside.size else None)
        lent: List[Tuple[int, np.ndarray]] = []
        orig_box, orig_mask = reg.box, reg.mask
        if loose and angles:
            gap = 0.5 * float(np.median([b[3] - b[1] for _, b in loose]))
            near = [(i, b) for i, b in loose if i not in absorbed and _near(b, reg.box, gap)]
            if near:
                lent = list(zip([i for i, _ in near], _grow(img, bg, reg, [b for _, b in near])))
        x0, y0, x1, y1 = reg.box
        remaining = reg.mask.copy()

        def read(deg, mask):
            nonlocal remaining
            got = _read_at(img, bg, reg, mask, deg, min_conf) if mask.sum() >= 40 else None
            if got:
                found.extend(got[0])
                remaining = remaining & ~got[1]

        # Lines at several angles sharing one mark (the arms of a V): share the
        # ink out by angle and read each family on its own first, so the other
        # family's ink no longer crosses its rows.
        if len(angles) > 1:
            for deg, fam in _real_families(img, bg, reg, angles).items():
                read(deg, remaining & fam)
        # Then each angle against whatever is left: the whole mark when it holds
        # one family of lines, and anything the families missed.
        for deg in angles:
            read(deg, remaining)
        took = False
        for i, m in lent:
            n = int(m.sum())
            if n and (m & ~remaining).sum() > 0.6 * n:
                absorbed.append(i)        # an angled line took it: the level reading goes
                took = True
            else:
                remaining &= ~m           # stays level text: give its ink back
        if lent and not took:
            # Nothing borrowed was used: the mark goes back to exactly what it was,
            # less whatever its own lines gave up.
            gx0, gy0 = reg.box[0], reg.box[1]
            ox0, oy0, ox1, oy1 = orig_box
            remaining = remaining[oy0 - gy0:oy1 - gy0, ox0 - gx0:ox1 - gx0] & orig_mask
            reg.box, reg.mask = orig_box, orig_mask
        remaining = _leftover(reg.mask, remaining)
        if remaining.sum() > 40:
            reg.mask = remaining
            kept.append(reg)
    return found, kept, absorbed


def _leftover(mask: np.ndarray, remaining: np.ndarray) -> np.ndarray:
    """
    What is left of a mark once its lines are read. Fringe hugging the read
    letters goes; pieces standing apart (a short word the reader would not
    trust, an ornament) stay as art rather than vanish from the sheet.
    """
    if remaining.sum() == mask.sum():
        return remaining
    near_read = cv2.dilate((mask & ~remaining).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(remaining.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA]
        if area < 12:
            continue
        piece = lab == i
        keep[i] = (piece & near_read).sum() < 0.5 * area
    return keep[lab]


def _snap_ends(band: np.ndarray, x0: float, x1: float, h: float) -> Tuple[float, float]:
    """
    A line's ends on its own ink: the reader's word boxes run a little loose.
    Columns join across gaps narrower than a word space, so a neighbouring
    group on the same baseline is not swallowed.
    """
    cols = np.nonzero(band.sum(axis=0) >= 1)[0]
    if not len(cols):
        return x0, x1
    gap = max(2.0, 0.45 * h)
    segs, start, prev = [], cols[0], cols[0]
    for c in list(cols[1:]) + [None]:
        if c is None or c - prev > gap:
            segs.append((start, prev + 1))
            if c is not None:
                start = c
        if c is not None:
            prev = c
    mine = [(a, b) for a, b in segs if b > x0 and a < x1]
    if not mine:
        return x0, x1
    a, b = float(min(s[0] for s in mine)), float(max(s[1] for s in mine))
    # Only tighten or nudge: a snap that moves an end by more than a letter is a wrong join.
    if abs(a - x0) > h or abs(b - x1) > h:
        return x0, x1
    return a, b


def _read_at(img, bg, reg, mask, deg, min_conf):
    """Read the lines of `mask` at angle `deg`; returns (texts, mask of what was read) or None."""
    found = []
    if True:
        x0, y0, x1, y1 = reg.box
        dist = ink_map(img[y0:y1, x0:x1], bg[y0:y1, x0:x1])
        keep = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        pad = 12
        gray = (255 - np.clip(dist * keep * 3.5, 0, 255)).astype(np.uint8)
        gray = cv2.copyMakeBorder(gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
        level, m = _rotate(gray, deg)
        inv = cv2.invertAffineTransform(m)
        lmask = level < 150
        taken = np.zeros(level.shape, np.uint8)
        for bx0, by0, bx1, by1 in _bands(lmask):
            h = by1 - by0
            p = max(4, h // 2)
            top = max(0, by0 - p)
            crop = level[top:by1 + p, max(0, bx0 - p):bx1 + p].copy()
            # Keep the margin but not the neighbouring lines' tops and tails in it:
            # a single-line reader gives up on a crop with slivers of other lines.
            crop[:max(0, by0 - 1 - top)] = 255
            crop[by1 + 1 - top:] = 255
            left = max(0, bx0 - p)
            cw = crop.shape[1]
            best = None
            for flip in (False, True):
                c = cv2.rotate(crop, cv2.ROTATE_180) if flip else crop
                try:
                    lines = read_lines(cv2.cvtColor(c, cv2.COLOR_GRAY2BGR), psm=7)
                except Exception:
                    continue
                words = [w for l in lines for w in l.words if GOOD.search(w.text)]
                letters = sum(ch.isalnum() for w in words for ch in w.text)
                if letters < 4:
                    continue
                conf = float(np.mean([w.conf for w in words]))
                if best is None or conf > best[0]:
                    best = (conf, flip, sorted(words, key=lambda w: w.box[0]))
            if not best or best[0] < min_conf:
                continue
            _, flip, words = best
            ch_ = crop.shape[0]
            # One band can hold several lines (the arms of a V, or two staggered
            # blocks whose baselines nearly meet): a gap much wider than a space,
            # or a jump in the baseline, starts a new line.
            word_h = float(np.median([w.box[3] - w.box[1] for w in words]))
            groups = [[words[0]]]
            for w in words[1:]:
                prev = groups[-1][-1]
                if w.box[0] - prev.box[2] > 0.9 * word_h or abs(w.box[3] - prev.box[3]) > 0.25 * word_h:
                    groups.append([w])
                else:
                    groups[-1].append(w)
            for g in groups:
                gtext = " ".join(w.text for w in g)
                gconf = float(np.mean([w.conf for w in g]))
                if sum(ch.isalnum() for ch in gtext) < 3 or gconf < min_conf:
                    continue
                letters = [ch for ch in gtext if ch.isalpha()]
                caps = bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) > 0.7
                # Place and size the line by what was read, not by the band: a
                # reading that missed part of the band must not be stretched over it.
                gx0, gx1 = min(w.box[0] for w in g), max(w.box[2] for w in g)
                gy0, gy1 = min(w.box[1] for w in g), max(w.box[3] for w in g)
                if flip:
                    gx0, gx1, gy0, gy1 = cw - gx1, cw - gx0, ch_ - gy1, ch_ - gy0
                lx0, lx1, ly0, ly1 = left + gx0, left + gx1, top + gy0, top + gy1
                lx0, lx1 = _snap_ends(lmask[by0:by1], lx0, lx1, word_h)
                # The reader's word boxes say which ink is this line, but their heights
                # wander (some run down to the crop's edge): measure height from the ink.
                sub = lmask[by0:by1, max(0, int(lx0)):int(np.ceil(lx1))]
                # Rows count when they hold a real share of the line's ink: levelling smears
                # a fringe row onto the top and bottom, which would make the type too big.
                rs = sub.sum(axis=1) if sub.size else np.zeros(0)
                rows = np.nonzero(rs >= max(2, 0.2 * rs.max()))[0] if rs.size else []
                if len(rows):
                    ly0, ly1 = by0 + rows[0], by0 + rows[-1] + 1
                gh = ly1 - ly0
                if caps and len(rows):
                    # Caps: the median column top and bottom sit on the cap line and baseline;
                    # the outer rows include round letters' overshoot, a few percent too tall.
                    cols = np.nonzero(sub.any(axis=0))[0]
                    if len(cols) >= 8:
                        tops = np.argmax(sub[:, cols], axis=0)
                        bots = sub.shape[0] - 1 - np.argmax(sub[::-1, cols], axis=0)
                        mt, mb = float(np.median(tops)), float(np.median(bots))
                        gh = max(2.0, mb - mt + 1)
                        # Place by the same band: an outer row may be a neighbour's stray ink.
                        ly0, ly1 = by0 + mt, by0 + mb + 1
                cap = gh if caps else gh * 0.72
                per_char = (lx1 - lx0) / max(1, len(gtext)) / max(1.0, cap)
                if not 0.45 <= per_char <= 1.5:
                    continue
                cyl = (ly0 + cap / 2) if caps else (ly1 - cap / 2)
                if flip and not caps:
                    cyl = ly0 + cap / 2
                px, py = inv @ np.array([(lx0 + lx1) / 2, cyl, 1.0])
                angle = deg + (180 if flip else 0)
                angle = angle - 360 if angle > 180 else angle
                found.append(RotText(gtext, float(angle), x0 + px - pad, y0 + py - pad, float(cap),
                                     float(lx1 - lx0), reg.colour, gconf))
                cv2.rectangle(taken, (int(lx0) - 2, int(ly0) - 2), (int(np.ceil(lx1)) + 2, int(np.ceil(ly1)) + 2), 1, -1)
        back = cv2.warpAffine(taken, inv, (gray.shape[1], gray.shape[0]), flags=cv2.INTER_NEAREST)
        back = back[pad:pad + (y1 - y0), pad:pad + (x1 - x0)] > 0
        if not found:
            return None
        return found, back & mask
