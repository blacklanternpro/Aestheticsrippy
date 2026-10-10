"""
Type set along a curve: text round a circle, along a wave, letters strung
along the strokes of a big letterform.

The page and angle readers only see straight lines, so curved type ends up in
the art. In each mark, find letter-sized pieces (dark letters, or light
letters cut out of a dark shape) and string them into chains: each piece
linked to its neighbours, a chain being the longest run through them. A
smooth curve through a chain's centres is its path. Two ways to read it:

  along   the band either side of the path is unrolled into a straight
          strip (letters turned with the curve read level);
  upright each letter is lifted out as it stands and set side by side
          (letters that stay upright while the path turns).

Each is read both ways round; a confident reading that accounts for the
chain's pieces becomes a path text, and its letters are taken out of the art.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .art import Region, ink_map
from .ocr import GOOD, read_lines


@dataclass
class PathText:
    text: str
    points: np.ndarray            # (n, 2) sheet px, in reading order: the baseline, or the
    #                               letters' centre line when `pitch` is set
    cap: float                    # cap height (or estimate), px
    colour: Tuple[int, int, int]  # BGR
    conf: float
    pitch: Optional[float] = None  # px between letter centres for spaced-out lettering
    upright: bool = False
    offset: float = 0.0           # px along `points` to the first letter (its left edge, or
    #                               its centre when pitched)
    length: float = 0.0           # px from the first letter's start to the last letter's end
    light: bool = False           # light letters cut out of a dark shape
    pieces: List[np.ndarray] = field(default_factory=list)   # sheet masks per letter (for the art)
    box: Tuple[int, int, int, int] = (0, 0, 0, 0)            # region box the pieces are in


# ------------------------------------------------------------------ pieces

@dataclass
class _Piece:
    mask: np.ndarray       # bool over the piece's own box
    x: int                 # box origin, sheet px
    y: int
    centre: np.ndarray     # (x, y) sheet px
    size: float            # larger side of the box
    src: Tuple[str, int]   # ("mark", region index) or ("level", block index)


def _pieces(polar: np.ndarray, ox: int, oy: int, src: Tuple[str, int], min_area: int = 12,
            max_size: Optional[float] = None) -> List[_Piece]:
    n, lab, st, cen = cv2.connectedComponentsWithStats(polar.astype(np.uint8), 8)
    out = []
    H, W = polar.shape
    cap = max_size if max_size is not None else 0.5 * max(H, W)
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < min_area or max(w, h) < 5 or max(w, h) > cap:
            continue
        out.append(_Piece(lab[y:y + h, x:x + w] == i, ox + int(x), oy + int(y),
                          cen[i].astype(np.float64) + [ox, oy], float(max(w, h)), src))
    return out


def _holes(ink: np.ndarray) -> np.ndarray:
    """Paper enclosed by ink: light letters cut out of a dark shape."""
    inv = (~ink).astype(np.uint8)
    h, w = inv.shape
    pad = cv2.copyMakeBorder(inv, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=1)
    seed = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(pad, seed, (0, 0), 0)
    return pad[1:-1, 1:-1] > 0


# ------------------------------------------------------------------ chains

def _chains(pieces: Sequence[_Piece], min_len: int = 4) -> List[List[int]]:
    """
    Pieces of like size linked to near neighbours; per linked group, the
    longest path through its spanning tree is the chain (side pieces, a dot or
    an accent, join the chain piece they sit nearest).
    """
    n = len(pieces)
    if n < min_len:
        return []
    c = np.array([p.centre for p in pieces])
    s = np.array([p.size for p in pieces])
    d = np.hypot(c[:, None, 0] - c[None, :, 0], c[:, None, 1] - c[None, :, 1])
    ratio = np.maximum(s[:, None], s[None, :]) / np.maximum(1e-6, np.minimum(s[:, None], s[None, :]))
    reach = 2.6 * (s[:, None] + s[None, :]) / 2
    ok = (d <= reach) & (ratio <= 2.2)
    np.fill_diagonal(ok, False)
    # Kruskal over the allowed edges.
    parent = list(range(n))

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    adj: List[List[int]] = [[] for _ in range(n)]
    for i, j in sorted(zip(*np.nonzero(np.triu(ok))), key=lambda e: d[e[0], e[1]]):
        ri, rj = root(i), root(j)
        if ri != rj:
            parent[ri] = rj
            adj[i].append(j)
            adj[j].append(i)

    def far(start, allowed):
        dist = {start: 0.0}
        prev = {start: None}
        stack = [start]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v in allowed and v not in dist:
                    dist[v] = dist[u] + d[u, v]
                    prev[v] = u
                    stack.append(v)
        end = max(dist, key=dist.get)
        return end, prev

    groups = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < min_len:
            continue
        allowed = set(members)
        a, _ = far(members[0], allowed)
        b, prev = far(a, allowed)
        path = [b]
        while prev[path[-1]] is not None:
            path.append(prev[path[-1]])
        if len(path) >= min_len:
            out.append(path)
    return out


# ------------------------------------------------------------------ curves

def _smooth(pts: np.ndarray, rounds: int = 2) -> np.ndarray:
    """Moving-average smoothing that keeps the ends."""
    p = pts.astype(np.float64).copy()
    for _ in range(rounds):
        if len(p) < 3:
            break
        q = p.copy()
        q[1:-1] = (p[:-2] + p[1:-1] + p[2:]) / 3
        p = q
    return p


def _resample(pts: np.ndarray, step: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """Points every `step` px along a polyline, and the arc length at each input point."""
    seg = np.hypot(*np.diff(pts, axis=0).T)
    at = np.r_[0, np.cumsum(seg)]
    total = at[-1]
    if total <= 0:
        return pts.copy(), at
    s = np.arange(0, total + 1e-6, step)
    x = np.interp(s, at, pts[:, 0])
    y = np.interp(s, at, pts[:, 1])
    return np.stack([x, y], 1), at


def _extend(path: np.ndarray, by: float) -> np.ndarray:
    """The path lengthened at both ends along its end directions."""
    def tip(a, b):
        v = a - b
        n = np.hypot(*v)
        return a + v / n * by if n > 0 else a
    k = min(len(path) - 1, max(1, int(by)))
    return np.vstack([tip(path[0], path[k]), path, tip(path[-1], path[-1 - k])])


def _normals(path: np.ndarray) -> np.ndarray:
    t = np.gradient(path, axis=0)
    t /= np.maximum(1e-9, np.hypot(*t.T))[:, None]
    return np.stack([-t[:, 1], t[:, 0]], 1)     # the tangent turned clockwise (y down): "below" the path


def _unroll(img: np.ndarray, path: np.ndarray, half: float) -> np.ndarray:
    """The band either side of `path` as a straight strip: row 0 on the upper side."""
    nrm = _normals(path)
    rows = np.arange(-half, half + 1e-6, 1.0)
    mx = (path[None, :, 0] + rows[:, None] * nrm[None, :, 0]).astype(np.float32)
    my = (path[None, :, 1] + rows[:, None] * nrm[None, :, 1]).astype(np.float32)
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderValue=255)


# ------------------------------------------------------------------ reading

def _read(strip: np.ndarray) -> Optional[Tuple[float, str, list]]:
    pad = 10
    s = cv2.copyMakeBorder(strip, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    try:
        lines = read_lines(cv2.cvtColor(s, cv2.COLOR_GRAY2BGR), psm=7)
    except Exception:
        return None
    words = [w for l in lines for w in l.words if GOOD.search(w.text)]
    if not words:
        return None
    conf = float(np.mean([w.conf for w in words]))
    return conf, " ".join(w.text for w in words), words


def _letters(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def find(img: np.ndarray, regions: Sequence[Region], bg: np.ndarray,
         min_conf: float = 75) -> Tuple[List[PathText], List[Region]]:
    """Curved text in the marks, and the regions with it taken out (or painted over)."""
    found: List[PathText] = []
    kept: List[Region] = []
    for reg in regions:
        if reg.kind != "mark" or reg.mask is None or reg.mask.sum() < 60:
            kept.append(reg)
            continue
        x0, y0, x1, y1 = reg.box
        dist = ink_map(img[y0:y1, x0:x1], bg[y0:y1, x0:x1])
        inside = dist[reg.mask]
        if not inside.size:
            kept.append(reg)
            continue
        ink = (dist > 0.5 * float(np.median(inside))) & reg.mask
        taken = np.zeros(reg.mask.shape, bool)       # dark letters read: out of the mark
        filled = np.zeros(reg.mask.shape, bool)      # light letters read: painted over
        for light, polar in ((False, ink), (True, _holes(cv2.morphologyEx(
                ink.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0))):
            pieces = _pieces(polar)
            for chain in _chains(pieces):
                got = _read_chain(img, reg, pieces, chain, light)
                if got is None or got.conf < min_conf:
                    continue
                found.append(got)
                for k in chain:
                    m = cv2.dilate(pieces[k].mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                    (filled if light else taken)[...] |= m
        if filled.any():
            reg.fill = filled if getattr(reg, "fill", None) is None else (reg.fill | filled)
        remaining = reg.mask & ~taken
        if remaining.sum() > 40 or filled.any():
            reg.mask = remaining
            kept.append(reg)
    return found, kept


def _read_chain(img, reg: Region, pieces: Sequence[_Piece], chain: List[int], light: bool) -> Optional[PathText]:
    x0, y0, x1, y1 = reg.box
    sel = [pieces[k] for k in chain]
    size = float(np.median([p.size for p in sel]))
    # The letters alone, dark on white: nothing else in the mark can confuse the reader.
    only = np.zeros(reg.mask.shape, bool)
    for p in sel:
        only |= p.mask
    gray = (255 - 255 * only.astype(np.uint8))
    gray = cv2.GaussianBlur(gray, (3, 3), 0.6)
    centres = np.array([p.centre for p in sel])
    line = _smooth(centres)
    dense, _ = _resample(line)
    if len(dense) < 4:
        return None
    spacing = float(np.median(np.hypot(*np.diff(centres, axis=0).T)))
    best = None
    # Along: the band unrolled straight, read either way round.
    path = _extend(dense, 0.9 * size)
    strip = _unroll(gray, path, 0.75 * size)
    for flip in (False, True):
        s = cv2.rotate(strip, cv2.ROTATE_180) if flip else strip
        r = _read(s)
        if r and (best is None or r[0] > best[0]):
            best = (r[0], r[1], "along", flip, r[2], s.shape[1])
    # Upright: each letter lifted out as it stands, set side by side in chain order.
    gap = int(round(0.35 * size))
    tiles = []
    for p in sel:
        ys, xs = np.nonzero(p.mask)
        t = 255 - 255 * p.mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8)
        tiles.append(t)
    hmax = max(t.shape[0] for t in tiles)
    row = []
    for t in tiles:
        top = (hmax - t.shape[0]) // 2
        row.append(cv2.copyMakeBorder(t, top, hmax - t.shape[0] - top, 0, gap, cv2.BORDER_CONSTANT, value=255))
    joined = np.hstack(row)
    for rev in (False, True):
        s = np.hstack(row[::-1]) if rev else joined
        r = _read(s)
        if r and (best is None or r[0] > best[0] + 3):
            best = (r[0], r[1], "upright", rev, r[2], s.shape[1])
    if best is None:
        return None
    conf, text, mode, flip, words, _ = best
    n = len(chain)
    if _letters(text) < 3 or abs(_letters(text) - n) > max(1, int(0.25 * n)):
        return None   # the reading must account for the chain's letters, no more, no less
    letters = [ch for ch in text if ch.isalpha()]
    caps = bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) > 0.7
    order = np.arange(n)[::-1] if flip else np.arange(n)
    pts = centres[order] + np.array([x0, y0], float)
    line = _smooth(pts)
    colour = tuple(int(v) for v in np.median(img[y0:y1, x0:x1][only], axis=0))
    upright = mode == "upright"
    # Heights across the path: each letter's extent along the local normal.
    nrm = _normals(_resample(line)[0])
    dense_line = _resample(line)[0]
    heights = []
    for k, idx in enumerate(order):
        p = sel[idx]
        ys, xs = np.nonzero(p.mask)
        j = int(np.argmin(np.hypot(*(dense_line - (p.centre + [x0, y0])).T)))
        if upright:
            heights.append(float(ys.max() - ys.min() + 1))
        else:
            proj = (xs + x0 - dense_line[j, 0]) * nrm[j, 0] + (ys + y0 - dense_line[j, 1]) * nrm[j, 1]
            heights.append(float(np.ptp(proj) + 1))
    h_med = float(np.median(heights))
    cap = h_med if caps else 0.72 * h_med
    spaced = spacing > 1.3 * size or upright
    out = PathText(text, line, cap, colour, conf, upright=upright, light=light,
                   pieces=[sel[i].mask for i in order], box=reg.box)
    if spaced:
        arc = np.r_[0, np.cumsum(np.hypot(*np.diff(line, axis=0).T))]
        out.pitch = float(arc[-1] / max(1, n - 1))
        out.offset = 0.0
        out.length = float(arc[-1])
        return out
    # Tight text on the curve: the baseline lies half a cap below the centre line.
    base_dense = dense_line + nrm * (h_med / 2)
    lead = 0.9 * size
    ext = _extend(base_dense, lead)
    first = sel[order[0]]
    ys, xs = np.nonzero(first.mask)
    t0 = dense_line[min(len(dense_line) - 1, 3)] - dense_line[0]
    t0 /= max(1e-9, np.hypot(*t0))
    half_w = float(np.ptp((xs + x0) * t0[0] + (ys + y0) * t0[1])) / 2
    out.points = ext
    out.offset = max(0.0, lead - half_w)
    last = sel[order[-1]]
    ys2, xs2 = np.nonzero(last.mask)
    t1 = dense_line[-1] - dense_line[max(0, len(dense_line) - 4)]
    t1 /= max(1e-9, np.hypot(*t1))
    half_w2 = float(np.ptp((xs2 + x0) * t1[0] + (ys2 + y0) * t1[1])) / 2
    arc = float(np.sum(np.hypot(*np.diff(dense_line, axis=0).T)))
    out.length = arc + half_w + half_w2
    return out
