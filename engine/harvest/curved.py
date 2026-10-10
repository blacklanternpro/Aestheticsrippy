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

import time
from dataclasses import dataclass
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
    angles: Optional[List[float]] = None   # per-letter rotation, degrees CW, for ransom lettering
    stops: Optional[List[float]] = None    # per-character distance along `points`, px (pitched only)
    row: Optional[np.ndarray] = None       # the righted letters as read (gray, dark on white), for face matching
    face: Optional[object] = None          # typeface.Face matched on `row`
    size_px: Optional[float] = None        # font size matched on `row`, sheet px
    offset: float = 0.0           # px along `points` to the first letter (its left edge, or
    #                               its centre when pitched)
    length: float = 0.0           # px from the first letter's start to the last letter's end
    light: bool = False           # letters painted over in the art (holes, or a tint on a shape)


# ------------------------------------------------------------------ pieces

@dataclass
class _Piece:
    mask: np.ndarray       # bool over the piece's own box
    x: int                 # box origin, sheet px
    y: int
    centre: np.ndarray     # (x, y) sheet px
    size: float            # larger side of the box
    src: Tuple[str, int]   # ("mark", region index) or ("level", block index)
    group: Tuple = ()      # enclosed letters chain within their enclosing shape only
    t: float = 0.0         # position along the enclosing shape's spine, px


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


def _spine(mask: np.ndarray) -> Optional[np.ndarray]:
    """
    The long way through a shape: the geodesic between its two farthest pixels,
    walked inside the shape (an S's spine follows the S, fold and all).
    Returns (n, 2) x,y points in the mask's own pixels, or None.
    """
    from collections import deque
    h, w = mask.shape
    k = max(1, int(max(h, w) / 160))
    small = mask[::k, ::k]
    ys, xs = np.nonzero(small)
    if len(ys) < 4:
        return None
    H, W = small.shape

    def bfs(start, track=False):
        dist = np.full((H, W), -1, np.int32)
        par = {}
        q = deque([start])
        dist[start] = 0
        last = start
        while q:
            y, x = q.popleft()
            last = (y, x)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and small[ny, nx] and dist[ny, nx] < 0:
                        dist[ny, nx] = dist[y, x] + 1
                        if track:
                            par[(ny, nx)] = (y, x)
                        q.append((ny, nx))
        return last, par

    a, _ = bfs((int(ys[0]), int(xs[0])))
    b, par = bfs(a, True)
    path = [b]
    while path[-1] != a:
        path.append(par[path[-1]])
    return np.array([[px * k, py * k] for py, px in path], float)


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
    reach = 4.5 * (s[:, None] + s[None, :]) / 2
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


def _runs(sel: List[_Piece]) -> List[List[_Piece]]:
    """
    A dark chain split into runs of one text each: a jump much longer than the
    chain's own rhythm, or a long jump with a sharp turn, is a boundary (the
    arc of one word chaining into the stem of the next). Spaced-out lettering
    splits harder - at any gap clearly over its rhythm with whole words both
    sides - since its words are separate texts, while a tight chain's word
    gaps belong inside its one line.
    """
    if len(sel) < 2:
        return [sel]
    c = np.array([p.centre for p in sel])
    d = np.hypot(*np.diff(c, axis=0).T)
    med = float(np.median(d))
    size = float(np.median([p.size for p in sel]))
    spaced = med > 1.3 * size
    out, start = [], 0
    for i in range(1, len(sel)):
        long_jump = d[i - 1] > 2.0 * med
        if spaced and not long_jump:
            long_jump = d[i - 1] > 1.45 * med and i - start >= 4 and len(sel) - i >= 4
        turn = False
        if 0 < i < len(sel) - 1:
            a = c[i] - c[i - 1]
            b = c[i + 1] - c[i]
            na, nb = np.hypot(*a), np.hypot(*b)
            if na > 0 and nb > 0:
                turn = float(np.degrees(np.arccos(np.clip(a @ b / (na * nb), -1, 1)))) > 70
        if long_jump or (d[i - 1] > 1.4 * med and turn):
            out.append(sel[start:i])
            start = i
    out.append(sel[start:])
    return [r for r in out if r]


def _right(tile: np.ndarray, a: float) -> np.ndarray:
    """The tile rotated by `a` degrees (cv2's sense, which undoes a CSS-clockwise turn)."""
    h, w = tile.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos) + 2, int(h * cos + w * sin) + 2
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(tile, m, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=255)


def _char_conf(tile: np.ndarray) -> Optional[Tuple[float, str]]:
    pad = 8
    t = cv2.copyMakeBorder(tile, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    try:
        lines = read_lines(cv2.cvtColor(t, cv2.COLOR_GRAY2BGR), psm=10, raw=True)
    except Exception:
        return None
    ws = [w for l in lines for w in l.words if w.text.strip()]
    if not ws:
        return None
    w = max(ws, key=lambda w: w.conf)
    return float(w.conf), w.text


_WORDS: Optional[frozenset] = None


def _words() -> frozenset:
    """Common English words (top-20k by frequency, vendored): the whole-word
    ear that settles what bigrams cannot - DANCE and DANGE share every pair."""
    global _WORDS
    if _WORDS is None:
        import gzip
        import os
        path = os.path.join(os.path.dirname(__file__), "data", "words-en.txt.gz")
        _WORDS = frozenset(gzip.decompress(open(path, "rb").read()).decode().split())
    return _WORDS


def _lexical(text: str) -> bool:
    """Every run of three or more letters is a common word, and there is one."""
    toks = "".join(c if c.isalnum() else " " for c in text.upper()).split()
    long = [t for t in toks if len(t) >= 3]
    return bool(long) and all(t.isalpha() and t in _words() for t in long)


_BIGRAMS = {b: w for bs, w in (
    ("TH HE IN ER AN RE ON AT EN ND TI ES OR TE OF ED IS IT AL AR ST TO NT NG SE HA AS OU IO LE VE CO ME DE HI RI RO IC NE EA RA CE", 1.0),
    ("LI CH LL BE MA SI OM UR CA EL TA LA NS DI FO HO PE EC PR NO CT US AC OT IL TR LY NC ET UT SS SO RS UN LO WA GE IE WH EE WI EM AD OL RT", 0.6),
    ("PO WE NA UL NI TS MO QU BI RU PA SH OW KE PU CK DO AP PL AY GH AI SA SU DU UE UA UP DA GO BY MY GA AB BO FA", 0.3),
) for b in bs.split()}


def _wordness(text: str) -> float:
    """
    A rough ear for language: common-bigram share, enough to tell "SATURDAY"
    from "YADRUTAS" when the reader cannot. Only ever used comparatively.
    Digits count as pair members - neutral among themselves (a year, a price),
    costly inside a word ("1AST" must never outscore "LAST" by shedding the
    pairs its digit broke).
    """
    chars = [c for c in text.upper() if c.isalnum()]
    if len(chars) < 2:
        return 0.0
    tot = 0.0
    for a, b in zip(chars, chars[1:]):
        if a.isdigit() and b.isdigit():
            pass
        elif a.isdigit() or b.isdigit():
            tot -= 0.6
        else:
            tot += _BIGRAMS.get(a + b, -0.4)
    base = tot / (len(chars) - 1)
    # Whole words get the final say ("DANCE" and "DANGE" share every pair).
    # A token is a word only when it is all letters: a digit does not split
    # a run into bonus-earning fragments ("D4ZOE" contains no "ZOE").
    toks = "".join(c if c.isalnum() else " " for c in text.upper()).split()
    alpha = sum(c.isalpha() for c in text.upper())
    hits = sum(len(t) for t in toks if t.isalpha() and len(t) >= 3 and t in _words())
    return base + (0.6 * hits / alpha if alpha else 0.0)


class _OutOfTime(Exception):
    """The sheet's time for reading curves ran out mid-sweep."""


def _window(anchor: float) -> List[float]:
    """Candidate turns for a letter: about the path tangent, its half-turn, and upright."""
    out: List[float] = []
    for base, half in ((anchor, 40), (anchor + 180, 40), (0.0, 24)):
        for d in range(-half, half + 1, 8):
            a = (base + d + 180) % 360 - 180
            if all(abs(a - o) > 3 for o in out):
                out.append(a)
    return out


def _ransom_candidates(sel: Sequence[_Piece], anchors: Sequence[float],
                       deadline: Optional[float] = None,
                       glyphs=None) -> List[List[Tuple[float, float, str]]]:
    """
    Candidate rotations per letter (degrees, CSS-clockwise), best first, with
    the character each one reads as. In the designs this serves, a letter is
    turned roughly with the path, or stands roughly upright, give or take
    hand-placed jitter - so the sweep anchors on the local tangent, its
    half-turn and upright, not on every possible angle, which also starves
    the classic traps (an N turned 90 reads as a perfectly fine Z).
    The glyph atlas does this in microseconds; OCR is the fallback oracle.
    """
    out = []
    for p, anchor in zip(sel, anchors):
        cached = getattr(p, "cands", None)
        if cached is not None and cached[0] == round(anchor):
            out.append(cached[1])
            continue
        keep: List[Tuple[float, float, str]] = []    # (angle, own conf, char)
        if glyphs is not None:
            # The atlas is cheap enough to try every turn: hand-placed letters
            # wander much further from the path than any window would allow.
            for sc, a, ch in glyphs.classify(p.mask, range(-180, 180, 10)):
                keep.append((a, 100.0 * sc, ch))
        else:
            tile = 255 - 255 * p.mask.astype(np.uint8)
            bases = [anchor]
            for b in (anchor + 180, 0.0):   # the path walked the other way; or upright letters
                if all(_cdiff(b, o) > 20 for o in bases):
                    bases.append(b)
            scored = []
            for off in (0, 15, -15, 30, -30):
                for base in bases:
                    if deadline is not None and time.monotonic() > deadline:
                        raise _OutOfTime
                    a = (base + off + 180) % 360 - 180
                    r = _char_conf(_right(tile, a))
                    if r:
                        scored.append((r[0], float(a), r[1]))
            scored.sort(reverse=True)
            for conf, a, ch in scored:
                if conf < max(55.0, scored[0][0] - 25):
                    break
                if all(_cdiff(a, o) > 20 for o, _, _ in keep):
                    keep.append((a, conf, ch))
                if len(keep) >= 2:
                    break
        keep = keep or [(float(anchor), 0.0, "")]
        p.cands = (round(anchor), keep)
        out.append(keep)
    return out


def _cdiff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _ring_spin(sel: Sequence[_Piece], anchors: Sequence[float], deadline, glyphs
               ) -> List[Tuple[List[_Piece], List[float]]]:
    """
    Letters cut out around a counter form a closed ring, and the chain's cut
    falls wherever the tree happened to break the loop ("ADEON" for a ring
    spelling DANCE). When the two ends sit one letter-gap apart, offer the
    few cuts whose letters best speak language - every rotation, both ways,
    judged cheaply from the atlas candidates - for the row read to referee.
    """
    pts = np.array([p.centre for p in sel], dtype=float)
    n = len(sel)
    if n < 4:
        return []
    # A ring is a matter of geometry, not of the chain's order: the tree may
    # zig-zag across the counter (A-D-E-N-C round a D). Letters sitting on an
    # ellipse about their centroid - even radii once each axis is scaled to
    # its spread, no wide empty arc - are put in clockwise order and become
    # the cycle; their anchors follow the ring's tangent.
    ctr = pts.mean(axis=0)
    sd = np.maximum(pts.std(axis=0), 1e-6)
    q = (pts - ctr) / sd
    rad = np.hypot(q[:, 0], q[:, 1])
    th = np.arctan2(q[:, 1], q[:, 0])
    srt = np.sort(th)
    wide = float(np.max(np.diff(np.concatenate([srt, [srt[0] + 2 * np.pi]]))))
    if float(rad.std() / max(1e-6, rad.mean())) < 0.2 and wide < np.radians(130):
        polar = [int(i) for i in np.argsort(th)]
        sel = [sel[i] for i in polar]
        pts = pts[polar]
        anchors = [float(np.degrees(t)) + 90.0 for t in th[polar]]
    else:
        gaps = [float(np.hypot(*(pts[i + 1] - pts[i]))) for i in range(n - 1)]
        if float(np.hypot(*(pts[0] - pts[-1]))) > 1.7 * float(np.median(gaps)):
            return []
    try:
        cands = _ransom_candidates(sel, anchors, deadline, glyphs)
    except _OutOfTime:
        return []

    def score(order):
        front = {}
        for _, cf, ch in cands[order[0]]:
            front[ch] = max(front.get(ch, -1e9), 0.03 * cf)
        for i in order[1:]:
            nxt = {}
            for _, cf, ch in cands[i]:
                v = max(v0 + _BIGRAMS.get(p0 + ch, -0.4) for p0, v0 in front.items()) + 0.03 * cf
                if v > nxt.get(ch, -1e9):
                    nxt[ch] = v
            front = nxt
        return max(front.values())

    # Ring lettering follows the clock: it reads clockwise, starting near the
    # top (clock faces, seals, coin edges - and DANCE round the D). Geometry
    # gets a voice beside language, or every rotation of the same letters
    # sounds alike ("ONADE" and "DANCE" share a cycle).
    ang = [float(np.arctan2(p[1] - ctr[1], p[0] - ctr[0])) for p in pts]

    def prior(order):
        steps = [(ang[order[k + 1]] - ang[order[k]] + np.pi) % (2 * np.pi) - np.pi
                 for k in range(len(order) - 1)]
        clockwise = 0.6 if sum(steps) > 0 else 0.0       # y runs down: positive is clockwise
        top = 0.6 * max(0.0, float(np.cos(ang[order[0]] + np.pi / 2)))
        return clockwise + top

    ranked = []
    for flip in (False, True):
        idx = list(range(n))[::-1] if flip else list(range(n))
        for r in range(n):
            order = idx[r:] + idx[:r]
            ranked.append((score(order) + prior(order), prior(order), order, flip))
    ranked.sort(key=lambda t: -t[0])
    out = []
    for _, pr, order, flip in ranked[:3]:
        turn = 180.0 if flip else 0.0
        out.append(([sel[i] for i in order], [anchors[i] + turn for i in order], pr))
    return out


def _ransom_read(sel: Sequence[_Piece], size: float, anchors: Sequence[float],
                 deadline: Optional[float] = None,
                 glyphs=None) -> Optional[Tuple[float, str, List[float], List[np.ndarray], np.ndarray]]:
    """
    Right each letter and read the row, letting the row read choose between
    each letter's candidate turns (greedy, a few passes). Returns
    (conf, text, angles, righted tiles) of the best row.
    """
    try:
        cands = _ransom_candidates(sel, anchors, deadline, glyphs)
    except _OutOfTime:
        return None
    gap = max(2, int(round(0.35 * size)))

    def assemble(choice, angles=None):
        tiles = []
        for i, p in enumerate(sel):
            a = angles[i] if angles is not None else cands[i][choice[i]][0]
            t = _right(255 - 255 * p.mask.astype(np.uint8), a)
            on = np.nonzero((t < 128).any(axis=1))[0]
            if len(on):
                t = t[on[0]:on[-1] + 1]      # trim rotation padding to the ink
            tiles.append(t)
        hmax = max(t.shape[0] for t in tiles)
        # Letters share a baseline (caps sit on the line); soften the hard masks
        # a little, as print would, before the reader sees them.
        row = [cv2.copyMakeBorder(t, hmax - t.shape[0], 0, 0, gap, cv2.BORDER_CONSTANT, value=255)
               for t in tiles]
        return tiles, cv2.GaussianBlur(np.hstack(row), (3, 3), 0.7)

    def value(r, choice):
        if not r:
            return -1e9, None
        miss = abs(_letters(r[1]) - len(sel))
        bonus = (18.0 if miss == 0 else 12.0) if miss <= max(1, int(0.25 * len(sel))) else 0.0
        # Honest turns: the chosen angle must also be one the letter itself reads
        # well at, or the row ascent beats a two-word chain into confident nonsense.
        # And language gets a word: between readings the OCR likes equally well,
        # the one that sounds like words wins ("LAST" over "LYST").
        own = float(np.mean([cands[i][choice[i]][1] for i in range(len(sel))]))
        return r[0] + bonus + 0.4 * own + 8.0 * _wordness(r[1]), r

    choice = [0] * len(sel)
    tiles, row = assemble(choice)
    best_v, best_r = value(_read(row), choice)
    best_row = row
    budget = 2 * len(sel)
    for i in range(len(sel)):
        for alt in range(1, len(cands[i])):
            if budget <= 0 or (deadline is not None and time.monotonic() > deadline):
                break
            trial = list(choice)
            trial[i] = alt
            t2, row2 = assemble(trial)
            v, r = value(_read(row2), trial)
            budget -= 1
            if v > best_v:
                best_v, best_r, choice, tiles, best_row = v, r, trial, t2, row2
    if best_r is None:
        return None
    conf, text = best_r[0], best_r[1]
    if glyphs is not None:
        kept = [c for c in text if c.isalnum()]
        if len(kept) == len(sel):
            # The row reader chose the characters; now the atlas gets a say,
            # letter by letter, with language refereeing. A shape the atlas
            # knows surely (an eroded S the row read as N) beats a row-context
            # guess, but never against the ear ("U8" never beats "UR").
            chars = [c.upper() for c in kept]
            final = [cands[i][choice[i]][0] for i in range(len(sel))]
            changed = False
            for i, p in enumerate(sel):
                # Every character the shape could be, each at its own best
                # turn (a C at the ring's bottom hides behind O in classify's
                # angle-separated shortlist; chart lets it speak).
                ch_chart = getattr(p, "chart", None)
                if ch_chart is None:
                    ch_chart = p.chart = glyphs.chart(p.mask, range(-180, 180, 10))
                props = {ch: (100.0 * sc, a) for sc, a, ch in ch_chart if ch}
                # The letter standing there has two witnesses: the atlas (if
                # it charted it) and the row reader, who saw it in context
                # with all its print detail. It keeps the better word.
                cur_sc = max(props.get(chars[i], (0.0, 0.0))[0], conf - 15.0)
                best_gain, best_ch = 0.0, None
                for ch, (sc, a) in props.items():
                    if ch == chars[i] or sc < 70.0:
                        continue
                    sub = chars[:i] + [ch] + chars[i + 1:]
                    gain = (8.0 * (_wordness("".join(sub)) - _wordness("".join(chars)))
                            + 0.25 * (sc - cur_sc))
                    if gain > best_gain:
                        best_gain, best_ch = gain, ch
                if best_ch is not None:
                    chars[i] = best_ch
                    final[i] = props[best_ch][1]
                    changed = True
            # Spaces come from the gaps, not the reader: letters spread evenly
            # are one word however the row image smudged them together.
            cs = np.array([p.centre for p in sel])
            gaps = np.hypot(*np.diff(cs, axis=0).T)
            med = float(np.median(gaps)) if len(gaps) else 0.0
            text = chars[0]
            for k in range(1, len(chars)):
                if med and gaps[k - 1] > 1.6 * med:
                    text += " "
                text += chars[k]
            if changed:
                tiles, best_row = assemble(choice, final)
            angles = [_tighten(p, a) for p, a in zip(sel, final)]
            return conf, text, angles, tiles, best_row
    angles = [_tighten(p, cands[i][choice[i]][0]) for i, p in enumerate(sel)]
    return conf, text, angles, tiles, best_row


def _glyph_fallback(sel: Sequence[_Piece], anchors: Sequence[float], glyphs, size: float
                    ) -> Optional[Tuple[float, str, List[float], List[np.ndarray], np.ndarray]]:
    """
    A reading straight from the atlas, for lettering OCR cannot confirm even
    righted (eroded knockouts). Both directions are read; the one that sounds
    like language wins. Held to a higher bar than a confirmed reading.
    """
    def reading(seq, anchs):
        got = [glyphs.classify(p.mask, range(-180, 180, 10), top=1) for p, a in zip(seq, anchs)]
        if any(not g for g in got):
            return None
        scores = [g[0][0] for g in got]
        angles = [g[0][1] for g in got]
        chars = [g[0][2] for g in got]
        c = np.array([p.centre for p in seq])
        gaps = np.hypot(*np.diff(c, axis=0).T)
        med = float(np.median(gaps)) if len(gaps) else 0.0
        text = chars[0]
        for k in range(1, len(chars)):
            if med and gaps[k - 1] > 1.6 * med:
                text += " "
            text += chars[k]
        return float(np.mean(scores)) * 100.0, text, angles

    fwd = reading(sel, anchors)
    bwd = reading(list(sel)[::-1], [a + 180 for a in reversed(anchors)])
    if fwd is None and bwd is None:
        return None
    pick_bwd = bwd is not None and (fwd is None or _wordness(bwd[1]) > _wordness(fwd[1]) + 0.05)
    conf, text, angles = (bwd if pick_bwd else fwd)
    seq = list(sel)[::-1] if pick_bwd else list(sel)
    if conf < 84 or len({c for c in text if c.isalnum()}) < 3:
        return None
    tiles = []
    for p, a in zip(seq, angles):
        t = _right(255 - 255 * p.mask.astype(np.uint8), a)
        on = np.nonzero((t < 128).any(axis=1))[0]
        tiles.append(t[on[0]:on[-1] + 1] if len(on) else t)
    gap = max(2, int(round(0.35 * size)))
    hmax = max(t.shape[0] for t in tiles)
    row = np.hstack([cv2.copyMakeBorder(t, hmax - t.shape[0], 0, 0, gap, cv2.BORDER_CONSTANT, value=255)
                     for t in tiles])
    return conf - 2.0, text, angles, tiles, cv2.GaussianBlur(row, (3, 3), 0.7), seq


def _tighten(p: _Piece, a: float, span: int = 12) -> float:
    """
    Fine-tune a letter's turn: within +-span degrees, the true turn is where the
    righted letter's ink box is tightest (straight-stroked letters square up).
    Round letters give a flat curve and barely move; a change needs a clear win.
    """
    ys, xs = np.nonzero(p.mask)
    if len(xs) < 12:
        return a
    q = np.stack([xs, ys], 1).astype(np.float64)
    q -= q.mean(axis=0)

    def area(deg):
        t = np.radians(deg)          # undo a CSS-clockwise turn of `deg`
        c, s_ = np.cos(t), np.sin(t)
        x = q[:, 0] * c + q[:, 1] * s_
        y = -q[:, 0] * s_ + q[:, 1] * c
        return float(np.ptp(x) * np.ptp(y))

    base = area(a)
    best_a, best_v = a, base
    for d in range(-span, span + 1):
        v = area(a + d)
        if v < best_v:
            best_a, best_v = a + d, v
    return best_a if best_v < 0.97 * base else a


def _varied(sel: Sequence[_Piece], min_diff: float = 0.12) -> bool:
    """
    Do these pieces look like different letters? Rows of ticks, dots and other
    repeating marks chain beautifully but are all one shape; text is varied.
    Compares the pieces' shapes, each scaled to a small square (and in both
    orientations, so a tick turned with its path still matches its neighbour).
    """
    if len(sel) < 3:
        return True
    tiles = []
    for p in sel:
        t = cv2.resize(p.mask.astype(np.float32), (16, 16), interpolation=cv2.INTER_AREA)
        tiles.append(t)
    diffs = []
    for i in range(len(tiles)):
        for j in range(i + 1, min(len(tiles), i + 4)):
            a, b = tiles[i], tiles[j]
            diffs.append(min(float(np.abs(a - b).mean()), float(np.abs(a - b.T).mean())))
    return float(np.median(diffs)) >= min_diff


def _geometry(centres: np.ndarray, size: float) -> Tuple[bool, bool, float]:
    """Is this chain of letter centres curved, or spaced out? Returns (curved, spaced, spacing)."""
    spacing = float(np.median(np.hypot(*np.diff(centres, axis=0).T)))
    dense, _ = _resample(_smooth(centres))
    chord = float(np.hypot(*(dense[-1] - dense[0])))
    arc = float(np.sum(np.hypot(*np.diff(dense, axis=0).T)))
    if chord > 1e-6:
        v = (dense[-1] - dense[0]) / chord
        d = dense - dense[0]
        dev = float(np.abs(d[:, 0] * v[1] - d[:, 1] * v[0]).max())
    else:
        dev = arc
    curved = dev > max(0.35 * size, 0.04 * arc) or arc > 1.12 * max(1e-6, chord)
    return curved, spacing > 1.3 * size, spacing


def find(img: np.ndarray, regions: Sequence[Region], bg: np.ndarray, min_conf: float = 80,
         loose: Sequence[Tuple[int, Tuple[float, float, float, float]]] = (),
         time_budget: float = 30.0, glyphs=None) -> Tuple[List[PathText], List[Region], List[int]]:
    """
    Curved text in the marks, the regions with it taken out (or marked to be
    painted over), and which of the `loose` level readings (id, box) its chains
    absorbed. `loose` are one-or-two-letter level readings: letters spaced
    along a path often read level one by one, and belong to the path instead.

    Letter pieces come three ways: dark ink in a mark; paper holes enclosed by
    ink (light letters cut out of a shape); and ink inside a mark whose colour
    stands apart from the mark's own (a tint: orange letters on a green
    letterform). Holes and tints are painted over rather than cut out, so the
    carrying shape survives as art and the type renders on top.
    """
    H, W = img.shape[:2]
    cap = 0.22 * max(H, W)
    pieces: List[_Piece] = []
    marks = [(ri, reg) for ri, reg in enumerate(regions)
             if reg.kind == "mark" and reg.mask is not None and reg.mask.sum() >= 60]
    for ri, reg in enumerate(regions):
        # A "photo" that is really flat ink with paper cut out (a textured
        # letterform full of knockouts misreads as photographic): its ink
        # levels sit at two poles with hardly anything between. Adopt it as
        # a mark so its holes get read like any other lettering.
        if reg.kind == "photo" and reg.mask is not None and reg.mask.sum() >= 500:
            x0, y0, x1, y1 = reg.box
            inside = ink_map(img[y0:y1, x0:x1], bg[y0:y1, x0:x1])[reg.mask].astype(np.float32)
            tot = float(inside.var())
            if tot <= 0:
                continue
            u8 = np.clip(255 * inside / max(1e-6, float(inside.max())), 0, 255).astype(np.uint8)
            t, _ = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            lo, hi = inside[u8 <= t], inside[u8 > t]
            if len(lo) and len(hi):
                w = len(lo) / len(inside)
                if w * (1 - w) * (lo.mean() - hi.mean()) ** 2 / tot >= 0.85:
                    marks.append((ri, reg))
    for ri, reg in marks:
        x0, y0, x1, y1 = reg.box
        dist = ink_map(img[y0:y1, x0:x1], bg[y0:y1, x0:x1])
        inside = dist[reg.mask]
        if not inside.size:
            continue
        ink = (dist > 0.5 * float(np.median(inside))) & reg.mask
        pieces += _pieces(ink, x0, y0, ("mark", ri), max_size=cap)
        closed = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
        _, complab = cv2.connectedComponents(closed.astype(np.uint8), 8)

        spines: dict = {}

        def grouped(ps):
            # Letters knocked out of (or set into) a shape belong to that shape:
            # chains never run from one shape to a neighbouring one. The shape is
            # whichever ink component surrounds the piece the most.
            for p in ps:
                h, w = p.mask.shape
                lx, ly = p.x - x0, p.y - y0
                g = max(2, int(0.2 * p.size))
                sy0, sy1 = max(0, ly - g), min(complab.shape[0], ly + h + g)
                sx0, sx1 = max(0, lx - g), min(complab.shape[1], lx + w + g)
                around = complab[sy0:sy1, sx0:sx1]
                ring = cv2.dilate(np.pad(p.mask, ((ly - sy0, sy1 - ly - h), (lx - sx0, sx1 - lx - w))).astype(np.uint8),
                                  np.ones((2 * g + 1, 2 * g + 1), np.uint8)) > 0
                vals = around[ring & (around > 0)]
                comp = int(np.bincount(vals).argmax()) if vals.size else -1
                p.group = (ri, comp)
                # Position along the shape's spine orders the letters (a chain across
                # an S's fold would zig-zag; the spine walks the long way round).
                if comp not in spines:
                    spines[comp] = _spine(complab == comp) if comp >= 0 else None
                sp = spines[comp]
                if sp is not None:
                    c = p.centre - [x0, y0]
                    p.t = float(np.argmin(np.hypot(sp[:, 0] - c[0], sp[:, 1] - c[1])))
            return ps

        holes = _holes(closed)
        pieces += grouped(_pieces(holes, x0, y0, ("hole", ri), max_size=cap))
        if holes.any():
            # Inset letters: ink inside the shape, parted from it by a thin paper
            # outline (the ring shows up as a hole). Cutting the ink at the rings
            # frees them as pieces of their own; only pieces hugging a ring count.
            ring = cv2.dilate(holes.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            for p in _pieces(ink & ~ring, x0, y0, ("inset", ri), max_size=cap):
                h, w = p.mask.shape
                lx, ly = p.x - x0, p.y - y0
                pad = cv2.dilate(p.mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
                rx0, ry0 = max(0, lx - 0), max(0, ly - 0)
                if (pad & ring[ry0:ry0 + h, rx0:rx0 + w]).any():
                    pieces += grouped([p])
        # A tint: ink whose colour stands apart from the mark's dominant colour.
        if ink.sum() > 400:
            lab = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2LAB).astype(np.float32)
            dom = np.median(lab[ink], axis=0)
            tint = (np.linalg.norm(lab - dom, axis=2) > 45) & ink
            pieces += grouped(_pieces(tint, x0, y0, ("tint", ri), max_size=cap))
    for bi, box in loose:
        g = int(0.2 * (box[3] - box[1]) + 1)
        bx0, by0 = max(0, int(box[0]) - g), max(0, int(box[1]) - g)
        bx1, by1 = min(W, int(np.ceil(box[2])) + g), min(H, int(np.ceil(box[3])) + g)
        if bx1 - bx0 < 3 or by1 - by0 < 3:
            continue
        dist = ink_map(img[by0:by1, bx0:bx1], bg[by0:by1, bx0:bx1])
        ink = dist > max(40.0, 0.5 * float(dist.max()))
        pieces += _pieces(ink, bx0, by0, ("level", bi), max_size=1.5 * max(bx1 - bx0, by1 - by0))
    if len(pieces) > 800:   # texture, not lettering: keep the most letter-like sizes
        med = float(np.median([p.size for p in pieces]))
        pieces = sorted(pieces, key=lambda p: abs(np.log(p.size / med)))[:800]

    found: List[PathText] = []
    absorbed: List[int] = []
    taken = {}      # region index -> mask of dark letters read (cut out of the mark)
    filled = {}     # region index -> mask of hole/tint letters read (painted over)
    fills_core = {}  # region index -> the letters themselves (always painted)
    # Chains never mix polarities: dark letters (and level readings, which are dark)
    # chain together; holes and tints each chain apart, or a letter's own counter
    # would join the chain between its neighbours.
    dark = [p for p in pieces if p.src[0] in ("mark", "level")]
    sels: List[List[_Piece]] = []
    paths = [[dark[k] for k in ch] for ch in _chains(dark)]
    on_path = {id(p) for path in paths for p in path}
    # A chain's longest path drops branch pieces (a letter on a short spur):
    # give each one back to the path that passes right by it, before the path
    # is cut into runs, so a returned letter counts toward its own word.
    spares = [p for p in dark if id(p) not in on_path]
    for path in paths:
        c = np.array([p.centre for p in path])
        med = float(np.median(np.hypot(*np.diff(c, axis=0).T))) if len(path) > 1 else 0.0
        path_med = float(np.median([p.size for p in path]))
        for p in spares:
            if id(p) in on_path or not 0.45 * path_med <= p.size <= 2.2 * path_med:
                continue
            seg = np.hypot(*(c - p.centre).T)
            j = int(np.argmin(seg))
            if seg[j] < 1.6 * med:
                before = j > 0 and np.hypot(*(c[j - 1] - p.centre)) < (
                    np.hypot(*(c[j + 1] - p.centre)) if j + 1 < len(path) else np.inf)
                path.insert(j if before else j + 1, p)
                c = np.array([q.centre for q in path])
                on_path.add(id(p))
    for path in paths:
        for run in _runs(path):
            if len(run) >= 4:
                sels.append(run)
    enclosed: dict = {}
    for p in pieces:
        if p.src[0] in ("hole", "tint", "inset"):
            enclosed.setdefault((p.src[0], p.group), []).append(p)
    for ps in enclosed.values():
        # One shape's letters are one chain, ordered along the shape's spine;
        # size outliers (a stray counter beside real letters) stay out.
        med = float(np.median([p.size for p in ps]))
        ps = sorted((p for p in ps if 0.45 * med <= p.size <= 2.2 * med), key=lambda p: p.t)
        if len(ps) >= 4:
            sels.append(ps)
    # Most promising first: dark lettering and knock-outs (holes, insets) before
    # tints (colour fragments are the noisiest source), longer chains first. A
    # sheet gets a fixed time to read curves in, so noise cannot run up the bill.
    rank = {"mark": 0, "level": 0, "hole": 1, "inset": 1, "tint": 2}
    queue = sorted(sels, key=lambda sl: (min(rank[p.src[0]] for p in sl), -len(sl)))
    ransom_budget = [6]   # per-letter sweeps are slow; a sheet gets so many ransom tries
    deadline = time.monotonic() + time_budget
    while queue:
        if time.monotonic() > deadline:
            break
        sel = queue.pop(0)
        size = float(np.median([p.size for p in sel]))
        centres = np.array([p.centre for p in sel])
        curved, spaced, spacing = _geometry(centres, size)
        if not (curved or spaced):
            continue    # a straight, tight chain is the line readers' business, not ours
        if not _varied(sel):
            continue    # a row of identical marks (ticks, dots): a pattern, not text
        got = _read_chain(img, sel, spacing, min_conf, ransom_budget, deadline, glyphs)
        if (got is None or got.conf < min_conf) and len(sel) >= 8:
            # Two texts can share a chain (one word's arc running into the next
            # word's stem): split at the longest internal gap and try each side.
            d = np.hypot(*np.diff(centres, axis=0).T)
            j = int(np.argmax(d))
            if d[j] > 1.3 * float(np.median(d)) and j + 1 >= 4 and len(sel) - j - 1 >= 4:
                queue += [sel[:j + 1], sel[j + 1:]]
            continue
        if got is None or got.conf < min_conf:
            continue
        found.append(got)
        for p in sel:
            kind, idx = p.src
            if kind == "level":
                if idx not in absorbed:
                    absorbed.append(idx)
                continue
            store = taken if kind == "mark" else filled    # holes, tints and insets are painted over
            acc = store.setdefault(idx, np.zeros(regions[idx].mask.shape, bool))
            rx0, ry0 = regions[idx].box[0], regions[idx].box[1]
            h, w = p.mask.shape
            if store is filled:
                # Printed knock-outs carry a fringe (misregistration, ink spread): paint
                # a margin of about a stroke round the letter. It is painted with the
                # shape's own colour and kept inside the shape below, so it is harmless.
                g = max(2, int(round(0.28 * p.size)))
                m = cv2.dilate(np.pad(p.mask, g).astype(np.uint8), np.ones((2 * g + 1, 2 * g + 1), np.uint8)) > 0
                ys, xs = p.y - ry0 - g, p.x - rx0 - g
                H2, W2 = acc.shape
                cy0, cx0 = max(0, ys), max(0, xs)
                cy1, cx1 = min(H2, ys + m.shape[0]), min(W2, xs + m.shape[1])
                acc[cy0:cy1, cx0:cx1] |= m[cy0 - ys:cy1 - ys, cx0 - xs:cx1 - xs]
                fills_core.setdefault(idx, np.zeros(regions[idx].mask.shape, bool))[
                    p.y - ry0:p.y - ry0 + h, p.x - rx0:p.x - rx0 + w] |= p.mask
            else:
                acc[p.y - ry0:p.y - ry0 + h, p.x - rx0:p.x - rx0 + w] |= p.mask

    kept: List[Region] = []
    for ri, reg in enumerate(regions):
        if ri in taken:
            cut = cv2.dilate(taken[ri].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            reg.mask = reg.mask & ~cut
        if ri in filled:
            # The margin stays inside the shape (the letter itself is paper, so is kept).
            shape = cv2.morphologyEx(reg.mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
            pad = (filled[ri] & (shape | reg.mask)) | fills_core[ri]
            reg.fill = pad if getattr(reg, "fill", None) is None else (reg.fill | pad)
        if reg.kind == "mark" and reg.mask is not None and reg.mask.sum() <= 40 \
                and getattr(reg, "fill", None) is None:
            continue    # nothing left of it
        kept.append(reg)
    return found, kept, absorbed


def _mend(sel: Sequence[_Piece]) -> List[_Piece]:
    """
    Fragments rejoined to their letter: an eroded knockout can print as a
    letter plus a crumb (the tail of an S cut off by ink spread), and the crumb
    then counts as a letter of its own. A piece much smaller than the chain's
    letters whose box all but touches a neighbour's is folded into it. Thin
    letters (I, 1) are spared: they are as tall as the rest.
    """
    sel = list(sel)
    if len(sel) < 4:
        return sel
    while True:
        area = float(np.median([p.mask.sum() for p in sel]))
        size = float(np.median([p.size for p in sel]))
        crumbs = [i for i, p in enumerate(sel)
                  if p.mask.sum() < 0.35 * area and p.size < 0.65 * size]
        if not crumbs:
            return sel
        i = crumbs[0]
        c = sel[i]

        def gap(o):
            dx = max(o.x - (c.x + c.mask.shape[1]), c.x - (o.x + o.mask.shape[1]), 0)
            dy = max(o.y - (c.y + c.mask.shape[0]), c.y - (o.y + o.mask.shape[0]), 0)
            return float(np.hypot(dx, dy))

        near = [j for j in (i - 1, i + 1) if 0 <= j < len(sel)]
        if not near:
            return sel
        j = min(near, key=lambda k: gap(sel[k]))
        if gap(sel[j]) > 0.15 * size:
            return sel     # a crumb on its own: leave the gates to judge it
        o = sel[j]
        x0, y0 = min(c.x, o.x), min(c.y, o.y)
        x1 = max(c.x + c.mask.shape[1], o.x + o.mask.shape[1])
        y1 = max(c.y + c.mask.shape[0], o.y + o.mask.shape[0])
        m = np.zeros((y1 - y0, x1 - x0), bool)
        for q in (c, o):
            m[q.y - y0:q.y - y0 + q.mask.shape[0], q.x - x0:q.x - x0 + q.mask.shape[1]] |= q.mask
        ac, ao = float(c.mask.sum()), float(o.mask.sum())
        cen = (c.centre * ac + o.centre * ao) / (ac + ao)
        sel[j] = _Piece(m, x0, y0, cen, float(max(m.shape)), o.src, o.group, o.t)
        del sel[i]
        if len(sel) < 4:
            return sel


def _read_chain(img, sel: Sequence[_Piece], spacing: float, min_conf: float,
                ransom_budget: Optional[List[int]] = None, deadline: Optional[float] = None,
                glyphs=None) -> Optional[PathText]:
    sel = _mend(sel)
    # Read left to right, or top to bottom: the chain's own order is arbitrary.
    ends = sel[-1].centre - sel[0].centre
    if (abs(ends[0]) >= abs(ends[1]) and ends[0] < 0) or (abs(ends[1]) > abs(ends[0]) and ends[1] < 0):
        sel = list(sel)[::-1]
    size = float(np.median([p.size for p in sel]))
    pad = int(1.5 * size) + 2
    bx0 = min(p.x for p in sel) - pad
    by0 = min(p.y for p in sel) - pad
    bx1 = max(p.x + p.mask.shape[1] for p in sel) + pad
    by1 = max(p.y + p.mask.shape[0] for p in sel) + pad
    # The letters alone, dark on white: nothing else on the sheet can confuse the reader.
    canvas = np.full((by1 - by0, bx1 - bx0), 255, np.uint8)
    for p in sel:
        h, w = p.mask.shape
        patch = canvas[p.y - by0:p.y - by0 + h, p.x - bx0:p.x - bx0 + w]
        patch[p.mask] = 0
    canvas = cv2.GaussianBlur(canvas, (3, 3), 0.6)
    centres = np.array([p.centre for p in sel]) - [bx0, by0]
    line = _smooth(centres)
    dense, _ = _resample(line)
    if len(dense) < 4:
        return None
    best = None
    best_img = None

    def consider(r, mode, flip, bonus=0, img=None):
        nonlocal best, best_img
        if r and (best is None or r[0] > best[0] + bonus):
            best = (r[0], r[1], mode, flip)
            best_img = img

    # Along: the band either side of the path unrolled straight. The canonical
    # direction decides; the reversed read is only a rescue when it fails, since
    # the reader is happy to read nonsense backwards with full confidence.
    # Extend past both end letters, then resample so every strip column is 1 px of arc.
    path = _resample(_extend(dense, 1.1 * size))[0]
    strip = _unroll(canvas, path, 0.8 * size)
    consider(_read(strip), "along", False, img=strip)
    if best is None or best[0] < min_conf:
        flipped = cv2.rotate(strip, cv2.ROTATE_180)
        consider(_read(flipped), "along", True, img=flipped)
    # Upright: each letter lifted out as it stands, set side by side in chain
    # order - but only when the letters really do stand upright: a sideways row
    # can scrape past the gates and then render unrotated. Three letters probed
    # at no turn decide.
    # One probe serves both remaining modes: three letters read alone, as they
    # stand and turned to the path (either way round). Letters that read standing
    # are upright lettering; letters that read only turned may be ransom
    # lettering; letters that read neither way are not letters, and stop here.
    anchors = []
    for p in sel:
        c = p.centre - [bx0, by0]
        j = int(np.argmin(np.hypot(*(dense - c).T)))
        j0, j1 = max(0, j - 3), min(len(dense) - 1, j + 3)
        d = dense[j1] - dense[j0]
        anchors.append(float(np.degrees(np.arctan2(d[1], d[0]))) if np.hypot(*d) > 0 else 0.0)
    stand_conf = turned_conf = turn_gain = 0.0
    if best is None or best[0] < 92:
        sv, tv = [], []
        for k in sorted({0, len(sel) // 2, len(sel) - 1}):
            if glyphs is not None:
                sv.append(100.0 * max((sc for sc, _, _ in glyphs.classify(
                    sel[k].mask, [-16, -8, 0, 8, 16], top=1)), default=0.0))
                tv.append(max(sv[-1], 100.0 * max((sc for sc, _, _ in glyphs.classify(
                    sel[k].mask, range(-180, 180, 10), top=1)), default=0.0)))
            else:
                def lettered(r):
                    # A confident "_" or ">" is no letter: only alphanumeric readings count.
                    return r[0] if r and any(ch.isalnum() for ch in r[1]) else 0.0

                tile = 255 - 255 * sel[k].mask.astype(np.uint8)
                sv.append(lettered(_char_conf(tile)))
                tv.append(max(sv[-1], max((lettered(_char_conf(_right(tile, a)))
                                           for a in (anchors[k], anchors[k] + 180)), default=0.0))
                          if sv[-1] < 70 else sv[-1])
        stand_conf, turned_conf = float(np.mean(sv)), float(np.mean(tv))
        turn_gain = max(t - v for t, v in zip(tv, sv))
    stands = stand_conf >= (80 if glyphs is not None else 68)
    if stands and (best is None or best[0] < 92):
        gap = max(2, int(round(0.35 * size)))
        tiles = [255 - 255 * p.mask.astype(np.uint8) for p in sel]
        hmax = max(t.shape[0] for t in tiles)
        row = []
        for t in tiles:
            top = (hmax - t.shape[0]) // 2
            row.append(cv2.copyMakeBorder(t, top, hmax - t.shape[0] - top, 0, gap,
                                          cv2.BORDER_CONSTANT, value=255))
        # Upright letters look the same read either way, and the reader is happy to
        # read nonsense backwards with confidence: top-down / left-right is the rule.
        upright_row = np.hstack(row)
        consider(_read(upright_row), "upright", False, 3, img=upright_row)
    # Ransom lettering: each letter at an angle of its own. Right each letter by
    # the turn it reads best at, then read the righted row; the row read is the
    # arbiter, so one letter righted wrong does not decide anything.
    angs = righted = None
    may_ransom = ransom_budget is None or ransom_budget[0] > 0
    if may_ransom and (best is None or best[0] < 88) and 4 <= len(sel) <= 12:
        # The probe gates the full per-letter sweep: ticks, dots and texture must
        # not pay for it. The local path direction anchors each letter's turn.
        # Ransom lettering has letters that read turned far better than standing
        # (others may stand: an upright T, a symmetric S). A chain zig-zagging
        # across two lines of ordinary text passes every other test, but its
        # letters all read standing, so turning gains nothing and it stops here.
        letterish = (turned_conf >= 80 and turn_gain >= 4) if glyphs is not None \
            else (turned_conf >= 62 and turn_gain >= 25)
        if letterish and ransom_budget is not None:
            ransom_budget[0] -= 1
        n = len(sel)

        def good(r):
            # Confident, accounts for the chain's letters, and is not one stroke
            # over and over ("IIIII"): a partial or junk reading must not block
            # the rescues just by being loud. A reading that spells real words
            # is its own evidence, and may be a little less loud.
            return (r is not None
                    and r[0] >= (min_conf - 6 if _lexical(r[1]) else min_conf)
                    and abs(_letters(r[1]) - n) <= max(1, int(0.25 * n))
                    and (n < 5 or len(set(c for c in r[1] if c.isalnum())) > 2))

        got = None
        rings = _ring_spin(sel, anchors, deadline, glyphs) if letterish and glyphs is not None else []
        ring_key = None
        for sel2, anch2, pr in rings:
            # A ring's cuts all hold the same letters, and the row reader's
            # confidence across cuts is mostly noise. Real words come first
            # (DANCE over a louder ANGED); then the reading, the ear for
            # language and the ring's own geometry (clockwise, from the top).
            if deadline is not None and time.monotonic() > deadline:
                break
            r2 = _ransom_read(sel2, size, anch2, deadline, glyphs)
            if r2 is None or not good(r2) or _letters(r2[1]) != len(sel2):
                continue
            key = (_lexical(r2[1]), r2[0] + 8.0 * _wordness(r2[1]) + 5.0 * pr)
            if ring_key is None or key > ring_key:
                ring_key, got, sel, anchors = key, r2, sel2, anch2
        if got is None:
            got = _ransom_read(sel, size, anchors, deadline, glyphs) if letterish else None
        if letterish and not ring_key and (not good(got) or (glyphs is not None and not _lexical(got[1]))):
            # The chain may read the other way (text running up a stroke). The
            # reader is happy to read nonsense backwards with confidence
            # ("YADFUTAS"), so the reversal is a rescue, never a competitor on
            # confidence alone - but language may call it: a reading that
            # spells words, or sounds clearly more like them, takes the turn.
            rev = _ransom_read(sel[::-1], size, [a + 180 for a in reversed(anchors)], deadline, glyphs)
            if rev is not None:
                if not good(got):
                    take = good(rev) or got is None or rev[0] > got[0]
                else:
                    take = good(rev) and (_lexical(rev[1])
                                          or _wordness(rev[1]) > _wordness(got[1]) + 0.3)
                if take:
                    got = rev
                    sel = list(sel)[::-1]
        if letterish and glyphs is not None and not good(got):
            # The last resort: read straight from the atlas, with language as the
            # judge of direction. Eroded knockouts land here, where OCR reads nothing.
            fb = _glyph_fallback(sel, anchors, glyphs, size)
            if fb is not None and good(fb[:5]):
                got = fb[:5]
                sel = fb[5]
        if not good(got):
            got = None
        # A loud reading that cannot account for the chain's letters (the
        # whole band read as one "4") is no reading: it must not outbid a
        # ransom reading that accounts for every letter.
        if got and (best is None or got[0] > best[0] + 3
                    or abs(_letters(best[1]) - len(sel)) > max(1, int(0.25 * len(sel)))):
            best = (got[0], got[1], "ransom", False)
            angs, righted, best_img = got[2], got[3], got[4]
    if best is None:
        return None
    conf, text, mode, flip = best
    n = len(sel)
    if _letters(text) < 4 or abs(_letters(text) - n) > max(1, int(0.25 * n)):
        return None   # the reading must account for the chain's letters, no more, no less
    letters = [ch for ch in text if ch.isalpha()]
    caps = bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) > 0.7
    order = list(range(n))[::-1] if flip else list(range(n))
    sel = [sel[i] for i in order]
    pts = np.array([p.centre for p in sel])
    line = _smooth(pts)
    dense_line, _ = _resample(line)
    nrm = _normals(dense_line)
    upright = mode in ("upright", "ransom")
    colour_px = []
    heights = []
    for p in sel:
        ys, xs = np.nonzero(p.mask)
        colour_px.append(img[p.y + ys, p.x + xs])
        if upright:
            heights.append(float(ys.max() - ys.min() + 1))
        else:
            j = int(np.argmin(np.hypot(*(dense_line - p.centre).T)))
            proj = (xs + p.x - dense_line[j, 0]) * nrm[j, 0] + (ys + p.y - dense_line[j, 1]) * nrm[j, 1]
            heights.append(float(np.ptp(proj) + 1))
    if mode == "ransom" and righted is not None:
        # Heights from the righted letters: a tilted letter's upright box lies.
        heights = []
        for t in righted:
            rows_on = np.nonzero((t < 128).any(axis=1))[0]
            heights.append(float(rows_on[-1] - rows_on[0] + 1) if len(rows_on) else 1.0)
    h_med = float(np.median(heights))
    cap = h_med if caps else 0.72 * h_med
    colour = tuple(int(v) for v in np.median(np.vstack(colour_px), axis=0))
    light = any(p.src[0] in ("hole", "tint", "inset") for p in sel)
    out = PathText(text, line, cap, colour, conf, upright=upright, light=light, row=best_img)
    arc = float(np.sum(np.hypot(*np.diff(dense_line, axis=0).T)))
    if spacing > 1.3 * size or upright:
        # Spaced-out lettering: a slot per character of the reading. The path runs
        # through the letters' own centres (corners and all, no smoothing) and,
        # when the reading accounts for every piece, each letter gets its measured
        # distance along it, so uneven spacing round a corner lands true.
        raw = np.array([p.centre for p in sel], float)
        steps = np.hypot(*np.diff(raw, axis=0).T)
        at = np.r_[0.0, np.cumsum(steps)]
        out.pitch = float(at[-1] / max(1, len(text.rstrip()) - 1))
        out.length = float(at[-1])
        chars = text.rstrip()
        if sum(not c.isspace() for c in chars) == len(sel):
            out.points = raw
            stops, k = [], 0
            for i, c in enumerate(chars):
                if c.isspace():
                    stops.append(None)
                else:
                    stops.append(float(at[k]))
                    k += 1
            for i, v in enumerate(stops):      # a space sits halfway between its neighbours
                if v is None:
                    prev = next((stops[j] for j in range(i - 1, -1, -1) if stops[j] is not None), 0.0)
                    nxt = next((stops[j] for j in range(i + 1, len(stops)) if stops[j] is not None), prev)
                    stops[i] = (prev + nxt) / 2
            out.stops = stops
            out.pitch = float(np.median(steps)) if len(steps) else out.pitch
        if mode == "ransom":
            chars = [c for c in text if not c.isspace()]
            if angs is not None and len(chars) == len(sel):
                it = iter(angs)
                out.angles = [0.0 if c.isspace() else round(float(next(it)), 1) for c in text.rstrip()]
            else:
                # No per-letter angles to carry: letters turned with the path is the
                # closest render (the sweep anchored on the tangent), not upright.
                out.upright = False
        return out
    # Tight text on the curve: the baseline lies half a height below the centre line.
    lead = 0.9 * size
    out.points = _extend(dense_line + nrm * (h_med / 2), lead)

    def half_width(p, a, b):
        t = b - a
        t /= max(1e-9, np.hypot(*t))
        ys, xs = np.nonzero(p.mask)
        return float(np.ptp((xs + p.x) * t[0] + (ys + p.y) * t[1])) / 2
    half0 = half_width(sel[0], dense_line[0], dense_line[min(len(dense_line) - 1, 3)])
    half1 = half_width(sel[-1], dense_line[max(0, len(dense_line) - 4)], dense_line[-1])
    out.offset = max(0.0, lead - half0)
    out.length = arc + half0 + half1
    return out
