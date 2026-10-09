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
        gap = max(6, int(3.0 * (y1 - y0)))
        start, prev = xs[0], xs[0]
        for x in list(xs[1:]) + [None]:
            if x is None or x - prev > gap:
                out.append((int(start), y0, int(prev) + 1, y1))
                if x is not None:
                    start = x
            if x is not None:
                prev = x
    return out


def find(img: np.ndarray, regions: Sequence[Region], bg: np.ndarray,
         min_conf: float = 80) -> Tuple[List[RotText], List[Region]]:
    """Rotated text in the marks, and the regions with that text taken out."""
    found: List[RotText] = []
    kept: List[Region] = []
    for reg in regions:
        if reg.kind != "mark" or reg.mask is None or reg.mask.sum() < 60:
            kept.append(reg)
            continue
        x0, y0, x1, y1 = reg.box
        remaining = reg.mask.copy()
        for deg in _skew(remaining):
            got = _read_at(img, bg, reg, remaining, deg, min_conf)
            if not got:
                continue
            texts, back = got
            found.extend(texts)
            remaining = remaining & ~back
        if remaining.sum() > 0.08 * reg.mask.sum() and remaining.sum() > 40:
            reg.mask = remaining
            kept.append(reg)
    return found, kept


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
            crop = level[max(0, by0 - p):by1 + p, max(0, bx0 - p):bx1 + p]
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
                    best = (conf, flip, " ".join(w.text for w in words))
            if not best or best[0] < min_conf:
                continue
            conf, flip, text = best
            letters = [ch for ch in text if ch.isalpha()]
            caps = bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) > 0.7
            cap = h if caps else h * 0.72
            # The reading must account for the whole band, or we would set half a line
            # and throw the rest of its letters away.
            per_char = (bx1 - bx0) / max(1, len(text)) / max(1.0, cap)
            if not 0.45 <= per_char <= 1.5:
                continue
            cyl = (by0 + cap / 2) if caps else (by1 - cap / 2)
            if flip:
                cyl = (by1 - cap / 2) if caps else (by0 + cap / 2)
            cxl = (bx0 + bx1) / 2
            px, py = inv @ np.array([cxl, cyl, 1.0])
            angle = deg + (180 if flip else 0)
            angle = angle - 360 if angle > 180 else angle
            found.append(RotText(text, float(angle), x0 + px - pad, y0 + py - pad, float(cap),
                                 float(bx1 - bx0), reg.colour, conf))
            cv2.rectangle(taken, (bx0 - 2, by0 - 2), (bx1 + 2, by1 + 2), 1, -1)
        back = cv2.warpAffine(taken, inv, (gray.shape[1], gray.shape[0]), flags=cv2.INTER_NEAREST)
        back = back[pad:pad + (y1 - y0), pad:pad + (x1 - x0)] > 0
        if not found:
            return None
        return found, back & mask
