"""
From OCR lines to typographic structure.

A *run* is a stretch of words on one baseline with no column gap inside it.
A *block* is a stack of runs that read as one text: same size and colour,
regular baseline steps, a shared edge. For each block we decide its alignment
and, between each pair of lines, whether the break was forced (an address,
a heading) or just where the text happened to wrap (a paragraph).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .ocr import Box, Line, Word

X_LETTERS = set("acemnorsuvwxz")
ASCENDERS = set("bdfhklt")
CAPS = set("ABCDEFGHIJKLMNOPRSTUVWXYZ0123456789")  # Q has a tail


@dataclass
class Ink:
    """What the pixels say about a run: baseline, heights, colour."""
    baseline: float
    x_height: Optional[float]
    tall: Optional[float]          # cap height, or caps-and-ascenders when mixed
    tall_kind: str                 # "cap", "ascender", "mixed" or ""
    colour: Tuple[int, int, int]   # BGR
    left: float                    # ink extents, sheet px
    right: float
    top: float
    bottom: float
    inverted: bool = False         # light type on a dark ground


@dataclass
class Run:
    words: List[Word]
    line: Line
    ink: Optional[Ink] = None

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def box(self) -> Box:
        return (min(w.box[0] for w in self.words), min(w.box[1] for w in self.words),
                max(w.box[2] for w in self.words), max(w.box[3] for w in self.words))

    @property
    def conf(self) -> float:
        return float(np.mean([w.conf for w in self.words]))

    @property
    def left(self) -> float:
        return self.ink.left if self.ink else self.box[0]

    @property
    def right(self) -> float:
        return self.ink.right if self.ink else self.box[2]

    @property
    def baseline(self) -> float:
        return self.ink.baseline if self.ink else self.line.baseline

    @property
    def size(self) -> float:
        """A font-size proxy in px: cap height or x-height scaled to an em-ish number."""
        if self.ink and self.ink.tall and self.ink.tall_kind == "cap":
            return self.ink.tall / 0.71
        if self.ink and self.ink.x_height:
            return self.ink.x_height / 0.52
        if self.ink and self.ink.tall:
            return self.ink.tall / 0.74
        return self.line.x_size * 0.75


@dataclass
class Block:
    runs: List[Run]
    align: str = "left"
    hard: List[bool] = field(default_factory=list)  # hard[i]: break after run i is forced
    step: Optional[float] = None                     # baseline-to-baseline, px

    @property
    def left(self) -> float:
        return min(r.left for r in self.runs)

    @property
    def right(self) -> float:
        return max(r.right for r in self.runs)

    @property
    def top(self) -> float:
        return min((r.ink.top if r.ink else r.box[1]) for r in self.runs)

    @property
    def bottom(self) -> float:
        return max((r.ink.bottom if r.ink else r.box[3]) for r in self.runs)

    @property
    def size(self) -> float:
        return float(np.median([r.size for r in self.runs]))

    def text(self) -> str:
        out = ""
        for i, r in enumerate(self.runs):
            out += r.text
            if i < len(self.runs) - 1:
                if self.hard[i]:
                    out += "\n"
                elif out.endswith("-") and len(out) > 1 and out[-2].isalpha():
                    out = out[:-1]  # a word hyphenated at the wrap
                else:
                    out += " "
        return out


# ---------------------------------------------------------------------- ink

def ink_mask(crop: np.ndarray) -> Tuple[np.ndarray, np.ndarray, bool]:
    """Ink mask for a small crop, the paper colour, and whether the ink is lighter."""
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    flat = lab.reshape(-1, 3)
    q = (flat // 12).astype(np.int32)
    keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    mode = vals[np.argmax(counts)]
    paper = flat[keys == mode].mean(axis=0)
    dist = np.linalg.norm(lab - paper, axis=2)
    d8 = np.clip(dist * 2, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = d8 > max(t, 36)
    inverted = bool(paper[0] < 110 and lab[..., 0][mask].mean() > paper[0]) if mask.any() else False
    return mask, paper, inverted


def measure(img: np.ndarray, words: Sequence[Word], text: str) -> Optional[Ink]:
    x0 = min(w.box[0] for w in words); x1 = max(w.box[2] for w in words)
    y0 = min(w.box[1] for w in words); y1 = max(w.box[3] for w in words)
    hgt = max(2.0, y1 - y0)
    px, py = 2, int(round(hgt * 0.15)) + 1
    X0, Y0 = max(0, int(x0) - px), max(0, int(y0) - py)
    X1, Y1 = min(img.shape[1], int(np.ceil(x1)) + px), min(img.shape[0], int(np.ceil(y1)) + py)
    crop = img[Y0:Y1, X0:X1]
    if crop.size == 0:
        return None
    mask, paper, inverted = ink_mask(crop)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    band0, band1 = y0 - Y0, y1 - Y0
    slack = 0.15 * hgt
    comps = [stats[i] for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] >= 2]
    # Keep glyphs inside the words' band; rules and neighbours bleed in otherwise.
    comps = [c for c in comps if c[1] >= band0 - slack and c[1] + c[3] <= band1 + slack
             and c[3] <= 1.3 * hgt]
    if not comps:
        return None
    bottoms = np.array([c[1] + c[3] for c in comps], np.float32)
    tops = np.array([c[1] for c in comps], np.float32)
    heights = bottoms - tops
    widths = np.array([c[2] for c in comps], np.float32)
    big = heights >= 0.3 * heights.max()
    # Baseline: the bottom shared by most glyph mass (descenders are the minority).
    cand = bottoms[big]
    wts = widths[big]
    best, base = -1.0, float(np.median(cand))
    for b in np.unique(np.round(cand)):
        s = wts[np.abs(cand - b) <= max(1.0, 0.04 * heights.max())].sum()
        if s > best:
            best, base = s, float(b)
    on_base = big & (np.abs(bottoms - base) <= max(1.5, 0.08 * heights.max()))
    hs = np.sort(base - tops[on_base] if on_base.any() else heights[big])

    letters = [c for c in text if c.isalnum()]
    n_x = sum(c in X_LETTERS for c in letters)
    n_tall = sum((c in CAPS) or (c in ASCENDERS) for c in letters)
    x_h = tall = None
    kind = ""
    if len(hs):
        # Split the sorted heights where the text says the x-height letters end.
        frac = n_x / max(1, n_x + n_tall)
        k = int(round(frac * len(hs)))
        if n_x and n_tall and 1 <= k < len(hs):
            x_h, tall = float(np.median(hs[:k])), float(np.median(hs[k:]))
            if tall < x_h * 1.12:  # no real step: treat as one height
                x_h, tall = None, float(np.median(hs))
        elif n_x and not n_tall:
            x_h = float(np.median(hs))
        else:
            tall = float(np.median(hs[len(hs) // 4:])) if len(hs) >= 4 else float(hs.max())
        if tall is not None:
            caps = any(c in CAPS for c in letters)
            asc = any(c in ASCENDERS for c in letters)
            kind = "mixed" if caps and asc else ("ascender" if asc else "cap")

    # Ink colour: the strongest third of ink pixels, in BGR.
    pix = crop[mask]
    if len(pix):
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)[mask]
        d = np.linalg.norm(lab - paper, axis=1)
        core = pix[d >= np.percentile(d, 85 if (x_h or tall or 99) < 12 else 66)]
        colour = tuple(int(v) for v in np.median(core, axis=0))
    else:
        colour = (0, 0, 0)
    # Extents from this run's own glyphs, not whatever else the crop caught.
    lefts = [c[0] for c in comps]
    rights = [c[0] + c[2] for c in comps]
    return Ink(baseline=Y0 + base, x_height=x_h, tall=tall, tall_kind=kind, colour=colour,
               left=float(X0 + min(lefts)), right=float(X0 + max(rights)),
               top=float(Y0 + tops.min()), bottom=float(Y0 + bottoms.max()), inverted=inverted)


# --------------------------------------------------------------------- runs

def split_runs(lines: Sequence[Line]) -> List[Run]:
    """Split OCR lines at column gaps: 'Billed To:      Payment Method:' is two runs."""
    runs: List[Run] = []
    for line in lines:
        words = sorted(line.words, key=lambda w: w.box[0])
        hs = [w.box[3] - w.box[1] for w in words]
        em = max(4.0, float(np.median(hs)))
        gaps = [b.box[0] - a.box[2] for a, b in zip(words, words[1:])]
        median = float(np.median(gaps)) if gaps else 0.3 * em
        cur = [words[0]]
        for w in words[1:]:
            gap = w.box[0] - cur[-1].box[2]
            # A column gap is wide outright, or wide against this line's own spacing
            # (a justified line spaces every gap wide, so its median gap is wide too).
            if gap > 2.5 * em or (gap > 1.25 * em and gap > 2.5 * max(min(median, 0.6 * em), 0.2 * em)):
                runs.append(Run(cur, line))
                cur = [w]
            else:
                cur.append(w)
        runs.append(Run(cur, line))
    return runs


def measure_runs(img: np.ndarray, runs: Sequence[Run]) -> None:
    for r in runs:
        r.ink = measure(img, r.words, r.text)


# ------------------------------------------------------------------- blocks

def _colour_close(a: Run, b: Run) -> bool:
    if not (a.ink and b.ink):
        return True
    ca, cb = np.array(a.ink.colour, float), np.array(b.ink.colour, float)
    return float(np.linalg.norm(ca - cb)) < 60 and a.ink.inverted == b.ink.inverted


def _edges_meet(a: Run, b: Run, tol: float) -> Optional[str]:
    if abs(a.left - b.left) <= tol:
        return "left"
    if abs(a.right - b.right) <= tol:
        return "right"
    if abs((a.left + a.right) / 2 - (b.left + b.right) / 2) <= tol:
        return "center"
    return None


def group_blocks(runs: Sequence[Run]) -> List[Block]:
    """Greedy top-down stacking of runs into blocks."""
    order = sorted(runs, key=lambda r: (r.baseline, r.left))
    blocks: List[Block] = []
    open_blocks: List[Block] = []
    for r in order:
        best, best_cost = None, None
        for b in open_blocks:
            last = b.runs[-1]
            s = max(r.size, last.size)
            if abs(r.size - last.size) > max(0.14 * s, 2.5) or not _colour_close(r, last):
                continue
            step = r.baseline - last.baseline
            if step <= 0.6 * s or step > max(1.7 * s, s + 4):  # small type: heights are +-1 px
                continue
            if b.step and abs(step - b.step) > 0.18 * b.step:
                continue
            # Horizontal relation: share an edge, or overlap well (a paragraph's ragged line).
            tol = 0.6 * s
            edge = _edges_meet(r, last, tol)
            overlap = min(r.right, b.right) - max(r.left, b.left)
            if not edge and overlap < 0.5 * min(r.right - r.left, b.right - b.left):
                continue
            if r.left > b.right or r.right < b.left:
                continue
            cost = step + (0 if edge else s)
            if best_cost is None or cost < best_cost:
                best, best_cost = b, cost
        if best is None:
            nb = Block([r])
            blocks.append(nb)
            open_blocks.append(nb)
        else:
            if best.step is None:
                best.step = r.baseline - best.runs[-1].baseline
            else:
                n = len(best.runs) - 1
                best.step = (best.step * n + (r.baseline - best.runs[-1].baseline)) / (n + 1)
            best.runs.append(r)
        # Blocks far above the current baseline can no longer grow.
        open_blocks = [b for b in open_blocks if r.baseline - b.runs[-1].baseline < 2.5 * b.size]
    for b in blocks:
        b.align = alignment(b)
        b.hard = breaks(b)
    return blocks


def alignment(b: Block) -> str:
    runs = b.runs
    s = b.size
    if len(runs) == 1:
        return "left"
    lefts = np.array([r.left for r in runs]); rights = np.array([r.right for r in runs])
    centres = (lefts + rights) / 2
    body = runs[:-1]
    spread = lambda a: float(a.max() - a.min()) if len(a) else 0.0  # noqa: E731
    tol = max(1.5, 0.12 * s)
    l, r, c = spread(lefts), spread(rights), spread(centres)
    wordy = all(len(r.words) >= 3 for r in body)
    if wordy and len(body) >= 2 and l <= tol and spread(rights[:-1]) <= tol and (rights[-1] < rights[:-1].min() - tol or
                                                                        spread(rights) <= tol):
        return "justify"
    if l <= tol:
        return "left"
    if r <= tol:
        return "right"
    if c <= tol * 1.5:
        return "center"
    return "left"


def breaks(b: Block) -> List[bool]:
    """
    hard[i] is True when line i ended early: the next line's first word would
    have fitted in the space left. That marks an address or a list, not a wrap.
    """
    runs = b.runs
    if len(runs) == 1:
        return []
    width = b.right - b.left
    if b.align in ("center", "right") or all(len(r.words) <= 3 for r in runs):
        # Set lines: centred and ranged-right type is broken by hand, as are addresses and lists.
        return [True] * (len(runs) - 1)
    out = []
    for i in range(len(runs) - 1):
        a, n = runs[i], runs[i + 1]
        first = n.words[0]
        word_w = first.box[2] - first.box[0]
        space = 0.3 * b.size
        room = width - (a.right - a.left)
        text = a.text
        if text.endswith("-") and len(text) > 1 and text[-2].isalpha():
            out.append(False)
        elif b.align == "justify" and i < len(runs) - 2:
            out.append(False)
        else:
            long_line = len(a.words) >= 4 or (a.right - a.left) >= 9 * b.size
            ends = text.rstrip()[-1:] in (":", ";") or not long_line
            out.append(ends or room > word_w + space + 0.02 * width)
    return out


def _plausible(r: Run) -> bool:
    alnum = sum(c.isalnum() for c in r.text)
    return alnum >= 2 or (alnum == 1 and r.conf >= 70)


_NATURAL = {}


def _natural_width(text: str) -> float:
    """Width of the text in a plain bold grotesque, in em: a yardstick for letterspacing."""
    if not _NATURAL:
        from ..typecase import matcher_data
        inst = next(m for m in matcher_data()["instances"] if m["family"] == "Inter" and int(m["weight"]) == 700)
        _NATURAL.update(inst["adv"])
    return sum(_NATURAL.get(c, 0.6) for c in text)


def split_forced(blocks: Sequence[Block]) -> List[Block]:
    """
    Poster lines set to one width ('TOM of ENGLAND' over a letterspaced 'IVAN BERKO')
    are spaced line by line, which one frame with one tracking cannot do. Give each
    such line its own frame, so each gets its own tracking.
    """
    out: List[Block] = []
    for b in blocks:
        if len(b.runs) < 2 or not all(b.hard) or b.align == "justify":
            out.append(b)
            continue
        widths = [r.right - r.left for r in b.runs]
        same_width = (max(widths) - min(widths)) <= 0.09 * max(widths)
        # Spacing per line, against what the letters themselves would need (an M is wider than an I).
        spacing = [w / max(1e-6, _natural_width(r.text)) for w, r in zip(widths, b.runs)]
        ratio = max(spacing) / max(1e-6, min(spacing))
        uneven = ratio > (1.12 if same_width else 1.15 if b.align in ("center", "right") else 1.3)
        if uneven:
            for r in b.runs:
                nb = Block([r], align=b.align, hard=[], step=None)
                out.append(nb)
        else:
            out.append(b)
    return out


def analyse(img: np.ndarray, lines: Sequence[Line]) -> List[Block]:
    runs = split_runs(lines)
    measure_runs(img, runs)
    runs = [r for r in runs if r.ink is not None and _plausible(r)]
    return split_forced(group_blocks(runs))
