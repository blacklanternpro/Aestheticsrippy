"""
Aestheticsrippy - proofreading degraded display type.

OCR earns its keep on body text and loses it on big degraded type: over-inked
or photocopied display comes back as 'Unicago', 'MB/20', 'AA-Ceiis' - mostly
right, poisoned by a letter or two whose shape the engine can actually check.
The glyph atlas (with its lowercase extension) looks at each letter cell of
the row and overrules the reader only where the shape evidence is strong, or
where it is fair and the correction makes the word more of a word.

The correction happens before type matching, so everything downstream - the
face bench, the print-finish fit, the trust filter, the rendered text -
works from the proofread reading.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .letters import Glyphs, cells

# Upper and lower case are the same drawing at different sizes: the atlas
# cannot tell them apart, so the cell's height against the row's tall letters
# decides. (Letters with distinct forms carry their case in their shape.)
TWINS = set("cosuvwxz")
# Bare vertical stems are interchangeable to the eye; the word's own company
# decides which one was meant.
STEMS = ("l", "I", "1")

ANGLES = (-6.0, 0.0, 6.0)      # level rows may lean a touch
STRONG, STRONG_MARGIN = 0.62, 0.10
FAIR, FAIR_MARGIN = 0.58, 0.05
PUNCT_OVERRULE = 0.70          # a claimed '/' or '-' must chart clearly as something


def fold(ch: str) -> str:
    """Case-folded identity: the thing the atlas can actually vouch for."""
    return ch.lower() if ch.isalpha() else ch


def _valley_split(cell: Tuple, unit: float) -> List[Tuple]:
    """A cell holding several fused letters, cut at its ink valleys."""
    x, y, w, h, m = cell
    k = max(2, int(round(w / unit)))
    prof = m.sum(axis=0).astype(float)
    cuts = [0]
    for j in range(1, k):
        lo = int(w * (j - 0.3) / k)
        hi = int(w * (j + 0.3) / k)
        cuts.append(lo + int(np.argmin(prof[lo:max(lo + 1, hi)])))
    cuts.append(w)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 3:
            continue
        piece = m[:, a:b]
        ys, xs = np.nonzero(piece)
        if len(xs) < 12:
            continue
        out.append((x + a + int(xs.min()), y + int(ys.min()),
                    int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1),
                    piece[ys.min():ys.max() + 1, xs.min():xs.max() + 1]))
    return out or [cell]


def letter_cells(ink: np.ndarray, base: Optional[float] = None) -> List[Tuple]:
    """The row's letters, one cell each: ink off the row's own baseline band
    dropped, fused runs cut at valleys by the MEDIAN letter width (a cap-high
    unit under-cuts lowercase), and an 'i'-dot folded into its letter.

    `ink`: uint8/bool mask of one level row; `base`: its baseline y, if known.
    Returns [(x, y, w, h, mask)] in reading order."""
    keep = (ink > 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(keep, 8)
    comps = [tuple(st[i][:4]) + (i,) for i in range(1, n) if st[i][4] >= 12]
    if not comps:
        return []
    cap = float(np.percentile([c[3] for c in comps], 85))
    if base is not None:
        # Another row caught in the crop (a sub-line under big display type)
        # lives off this row's baseline band; its ink is not ours to read.
        lo, hi = base - 1.4 * cap, base + 0.04 * cap
        for x, y, w, h, i in comps:
            if not (y < hi and y + h > lo):
                keep[lab == i] = 0
        ys = np.nonzero(keep.any(axis=1))[0]
        if not len(ys):
            return []
    out = cells(keep, cap)
    letters = [c for c in out if c[3] >= 0.5 * cap]
    if not letters:
        return [c + (False,) for c in out]
    unit = float(np.median([c[2] for c in letters]))
    # Fused pairs survive cells() when the row is lowercase (its unit is the
    # cap height; a lowercase pair is narrower than that): re-cut by width.
    out = [p for c in out for p in (_valley_split(c, unit) if c[2] > 1.6 * unit and c[3] >= 0.5 * cap else [c])]
    # Fold a dot into its letter (i, j): without this the dot is a cell of its
    # own and the row no longer aligns with the reader's characters. Dots are
    # mapped to hosts first, in one pass, so order in the row cannot matter.
    dots = [a for a, (x, y, w, h, _m) in enumerate(out)
            if h < 0.4 * cap and w < 0.8 * unit
            and (base is None or y + h < base - 0.55 * cap)]
    host_of: Dict[int, int] = {}
    for a in dots:
        x, y, w, h, _m = out[a]
        hosts = [(b, cb) for b, cb in enumerate(out) if b != a and b not in dots
                 and cb[3] >= 0.5 * cap
                 and min(x + w, cb[0] + cb[2]) - max(x, cb[0]) > 0.4 * w]
        if hosts:
            b, _cb = max(hosts, key=lambda t: min(x + w, t[1][0] + t[1][2]) - max(x, t[1][0]))
            host_of[a] = b
    merged: List[Tuple] = []
    for b, cb in enumerate(out):
        if b in host_of:
            continue
        mine = [a for a, h in host_of.items() if h == b]
        if not mine:
            merged.append(cb + (False,))
            continue
        pieces = [out[a] for a in mine] + [cb]
        x2 = min(p[0] for p in pieces); y2 = min(p[1] for p in pieces)
        x3 = max(p[0] + p[2] for p in pieces); y3 = max(p[1] + p[3] for p in pieces)
        mm = np.zeros((y3 - y2, x3 - x2), bool)
        for x, y, w, h, m in pieces:
            mm[y - y2:y - y2 + h, x - x2:x - x2 + w] |= m.astype(bool)
        # Only a mark sitting ABOVE the letter's body is an i-dot; a degraded
        # speck beside a stem merges for alignment but proves nothing.
        dotted = any(out[a][1] + out[a][3] <= cb[1] + 0.25 * cb[3] for a in mine)
        merged.append((x2, y2, x3 - x2, y3 - y2, mm, dotted))
    merged.sort(key=lambda c: c[0])
    return merged


def _context_case(chars: Sequence[str]) -> str:
    """What company the word keeps: 'lower', 'upper' or 'digit'."""
    lo = sum(c.isalpha() and c.islower() for c in chars)
    up = sum(c.isalpha() and c.isupper() for c in chars)
    dg = sum(c.isdigit() for c in chars)
    return max((("lower", lo), ("upper", up), ("digit", dg)), key=lambda t: t[1])[0]


def _spell(fold_ch: str, variants: List[Tuple[float, str]], h: float, tall: float,
           company: str, dotted: bool = False) -> str:
    """The actual character for a folded identity the atlas chose."""
    if fold_ch in ("i", "l", "1"):
        return "i" if dotted else {"lower": "l", "upper": "I", "digit": "1"}[company]
    if fold_ch.isalpha():
        if fold_ch in TWINS:
            return fold_ch.upper() if h >= 0.82 * tall else fold_ch
        for _s, c in variants:
            if fold(c) == fold_ch:
                return c
    return fold_ch


def _chart_folds(glyphs: Glyphs, mask: np.ndarray):
    """One chart per cell, kept whole: ([(score, angle, char)], {fold: best})."""
    chart = glyphs.chart(mask, ANGLES, top=60)
    folded: Dict[str, float] = {}
    for s, _a, c in chart:
        f = fold(c)
        folded[f] = max(folded.get(f, -1.0), s)
    return chart, folded


def _join(a: Tuple, b: Tuple) -> Tuple:
    """Two cells as one (a letter the print snapped in half)."""
    x2, y2 = min(a[0], b[0]), min(a[1], b[1])
    x3 = max(a[0] + a[2], b[0] + b[2]); y3 = max(a[1] + a[3], b[1] + b[3])
    mm = np.zeros((y3 - y2, x3 - x2), bool)
    for x, y, w, h, m, *rest in (a, b):
        mm[y - y2:y - y2 + h, x - x2:x - x2 + w] |= m.astype(bool)
    dotted = any(len(c) > 5 and c[5] for c in (a, b))
    return (x2, y2, x3 - x2, y3 - y2, mm, dotted)


def _align(glyphs: Glyphs, chars: List[str], row: List[Tuple], tall: float,
           unit: float) -> Optional[List[Optional[Tuple]]]:
    """Each character's cell, aligned by dynamic programming: a speck of
    spatter is stepped over, a letter the print broke is rejoined, and a pair
    the ink fused is matched to its one cell (and left unamended there).
    Returns per-char (cell, chart) - None where no clean cell owns the char -
    or None when even the best alignment reads badly."""
    n, m = len(chars), len(row)
    if n == 0 or m == 0 or abs(n - m) > max(3, n // 3):
        return None
    charts = [_chart_folds(glyphs, c[4]) for c in row]
    joined: Dict[int, Tuple] = {}

    def tiny(j: int) -> bool:
        return row[j][3] < 0.45 * tall

    def match(i: int, j: int) -> float:
        ch = chars[i]
        if not ch.isalnum():
            return 0.2 if tiny(j) else 0.55
        if tiny(j):
            return 0.8
        return 1.0 - charts[j][1].get(fold(ch), 0.0)

    def split(i: int, j: int) -> float:
        a, b = row[j], row[j + 1]
        gap = b[0] - (a[0] + a[2])
        if gap > 0.4 * unit or a[2] + b[2] > 1.8 * unit or not chars[i].isalnum():
            return 9.0
        if j not in joined:
            joined[j] = _join(a, b)
        _c, folds = _chart_folds(glyphs, joined[j][4])
        return 1.0 - folds.get(fold(chars[i]), 0.0) + 0.12

    BIG = 1e9
    D = np.full((n + 1, m + 1), BIG)
    OP = np.zeros((n + 1, m + 1), np.int8)
    D[0][0] = 0.0
    skip_char = 0.7
    for j in range(1, m + 1):
        D[0][j] = D[0][j - 1] + (0.22 if tiny(j - 1) else 0.6)
        OP[0][j] = 3
    for i in range(1, n + 1):
        D[i][0] = D[i - 1][0] + skip_char
        OP[i][0] = 4
        for j in range(1, m + 1):
            best, op = D[i - 1][j - 1] + match(i - 1, j - 1), 1
            if j >= 2:
                v = D[i - 1][j - 2] + split(i - 1, j - 2)
                if v < best:
                    best, op = v, 2
            v = D[i][j - 1] + (0.22 if tiny(j - 1) else 0.6)
            if v < best:
                best, op = v, 3
            v = D[i - 1][j] + skip_char
            if v < best:
                best, op = v, 4
            if i >= 2:
                v = D[i - 2][j - 1] + (0.45 if row[j - 1][2] > 1.25 * unit else 0.75)
                if v < best:
                    best, op = v, 5
            D[i][j] = best
            OP[i][j] = op
    if D[n][m] / max(1, n) > 0.55:
        return None   # even the best alignment reads badly: not our row to fix
    out: List[Optional[Tuple]] = [None] * n
    i, j = n, m
    while i > 0 or j > 0:
        op = OP[i][j]
        if op == 1:
            out[i - 1] = (row[j - 1], charts[j - 1])
            i, j = i - 1, j - 1
        elif op == 2:
            cell = joined[j - 2]
            out[i - 1] = (cell, _chart_folds(glyphs, cell[4]))
            i, j = i - 1, j - 2
        elif op == 3:
            j -= 1
        elif op == 4:
            i -= 1
        elif op == 5:
            i, j = i - 2, j - 1   # fused pair: both chars stand as read
        else:
            break
    return out


_ADV: Optional[Dict[str, float]] = None


def _advances() -> Dict[str, float]:
    """Per-character advance widths from the cabinet (a neutral grotesque):
    the real proportions of a C against an i, for the elastic grid."""
    global _ADV
    if _ADV is None:
        from ..typecase import matcher_data
        insts = matcher_data()["instances"]
        pick = min((m for m in insts if m["family"] == "Inter" and not m.get("stretch")),
                   key=lambda m: abs(int(m["weight"]) - 600), default=None)
        _ADV = dict(pick["adv"]) if pick else {}
    return _ADV


def _blob_cells(ink: np.ndarray, chars: List[str], base: Optional[float]) -> Optional[List[Tuple]]:
    """A row fused into one lump of ink, recut into the reader's own letters
    at the ink valleys. The reader's characters set an elastic grid - an 'i'
    earns half a slot, an 'm' one and a half, even when the letter itself was
    misread, since width class survives most misreadings (U for C, n for h).
    Returns [(x, y, w, h, mask, False)] or None."""
    n = len(chars)
    keep = (ink > 0).astype(np.uint8)
    if base is not None:
        nl, lab, st, _ = cv2.connectedComponentsWithStats(keep, 8)
        comps = [tuple(st[i][:4]) + (i,) for i in range(1, nl) if st[i][4] >= 12]
        if comps:
            cap = float(np.percentile([c[3] for c in comps], 85))
            lo, hi = base - 1.4 * cap, base + 0.04 * cap
            for x, y, w, h, i in comps:
                if not (y < hi and y + h > lo):
                    keep[lab == i] = 0
    ys, xs = np.nonzero(keep)
    if len(xs) < 50 or n < 2:
        return None
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    span = x1 - x0
    slot = span / n
    prof = cv2.GaussianBlur(keep[:, x0:x1].sum(axis=0).astype(np.float32).reshape(1, -1),
                            (0, 0), max(0.8, 0.08 * slot)).ravel()
    adv = _advances()
    units = [adv.get(c, adv.get(c.swapcase(), 0.55)) for c in chars]
    edges = np.cumsum([0.0] + units) / sum(units) * span
    cuts: List[int] = []
    for j in range(1, n):
        half = 0.3 * min(units[j - 1], units[j]) / np.mean(units) * slot + 1
        lo2 = max(1, int(edges[j] - half))
        hi2 = min(span - 1, int(edges[j] + half))
        cuts.append(lo2 + int(np.argmin(prof[lo2:max(lo2 + 1, hi2)])))
    if sorted(set(cuts)) != sorted(cuts):
        return None
    bounds = [0] + cuts + [span]
    out: List[Tuple] = []
    for a, b in zip(bounds, bounds[1:]):
        piece = keep[:, x0 + a:x0 + b]
        pys, pxs = np.nonzero(piece)
        if len(pxs) < 12:
            return None
        out.append((x0 + a + int(pxs.min()), int(pys.min()),
                    int(pxs.max() - pxs.min() + 1), int(pys.max() - pys.min() + 1),
                    piece[pys.min():pys.max() + 1, pxs.min():pxs.max() + 1].astype(bool),
                    False))
    return out


def _blob_read(glyphs: Glyphs, ink: np.ndarray, text: str, chars: List[str],
               base: Optional[float]) -> Optional[str]:
    """Read a fused row as a WORD: recut by the reader's count, then pick the
    spelling that the shapes and the language ear agree on jointly. In a blob
    every cell is noisy (neighbours bleed in), so no single cell may overrule
    the reader alone - only a whole word that reads better may."""
    from itertools import product

    from .curved import _wordness

    row = _blob_cells(ink, chars, base)
    if row is None:
        return None
    tall = float(np.percentile([c[3] for c in row], 85))
    if tall < 40:
        return None   # too few pixels per letter: blob reading would be guessing
    company = _context_case(chars)
    cands: List[List[Tuple[str, float, List[Tuple[float, str]]]]] = []
    for ch, cell in zip(chars, row):
        chart, folds = _chart_folds(glyphs, cell[4].astype(np.float32))
        own_f = fold(ch)
        own_s = folds.get(own_f, 0.0)
        opts = [(own_f, own_s)]
        if ch.isalnum() and folds:
            top_s = max(folds.values())
            opts += [(f, s) for f, s in sorted(folds.items(), key=lambda kv: -kv[1])[:8]
                     if s >= top_s - 0.10 and f != own_f
                     and f.isalpha() == ch.isalpha() and f.isdigit() == ch.isdigit()]
        variants: Dict[str, List[Tuple[float, str]]] = {}
        for s, _a, c in chart:
            variants.setdefault(fold(c), []).append((s, c))
        cands.append([(f, s, sorted(variants.get(f, []), reverse=True)) for f, s in opts[:6]])
    loose = [c for c in cands if len(c) > 1]
    if len(loose) > 9:
        return None   # too uncertain everywhere: this is not reading, it is guessing

    def spell(pick) -> str:
        out = []
        for (f, _s, vs), cell, ch in zip(pick, row, chars):
            if f == fold(ch):
                out.append(ch)
            else:
                out.append(_spell(f, vs or [(0.0, f)], cell[3], tall, company))
        it = iter(out)
        return "".join(c if c.isspace() else next(it) for c in text)

    def total(pick) -> float:
        swaps = sum(f != fold(ch) for (f, _s, _v), ch in zip(pick, chars))
        return float(np.mean([s for _f, s, _v in pick])) + 0.5 * _wordness(spell(pick)) \
            - 0.025 * swaps

    own_pick = tuple(c[0] for c in cands)
    best_pick, best_v = own_pick, total(own_pick)
    for combo in product(*cands):
        v = total(combo)
        if v > best_v:
            best_pick, best_v = combo, v
    got = spell(best_pick)
    if got == text or best_v < total(own_pick) + 0.18:
        return None
    if float(np.mean([s for _f, s, _v in best_pick])) < 0.60:
        return None   # the pieces do not genuinely read as these letters
    return got


def amend(glyphs: Glyphs, ink: np.ndarray, text: str,
          base: Optional[float] = None) -> Optional[str]:
    """The row's text with shape-overruled letters corrected, or None when the
    reader's call stands. `ink`: mask of the one row `text` was read from."""
    from .curved import _wordness

    chars = [ch for ch in text if not ch.isspace()]
    row = letter_cells(ink, base)
    if not chars or not row:
        return None
    tall = float(np.percentile([c[3] for c in row], 85))
    units = [c[2] for c in row if c[3] >= 0.5 * tall]
    unit = float(np.median(units)) if units else 1.0
    aligned = _align(glyphs, chars, row, tall, unit)
    # A word fused into a lump defeats alignment outright, or "survives" it
    # only by fusing most characters into unexaminable cells. Either way the
    # reader DID count the letters: recut the blob into that many pieces and
    # read it as a WORD, since single fused cells are too noisy to trust.
    if aligned is None or sum(a is not None for a in aligned) < 0.6 * len(chars):
        got = _blob_read(glyphs, ink, text, chars, base)
        if got is not None or aligned is None:
            return got
    company = _context_case(chars)
    strong_sw: Dict[int, str] = {}
    fair_sw: Dict[int, str] = {}
    stem_alt: Dict[int, List[str]] = {}
    agree, judged = 0, 0
    for i, ch in enumerate(chars):
        if aligned[i] is None:
            continue
        cell, (chart, folded0) = aligned[i]
        dotted = bool(cell[5]) if len(cell) > 5 else False
        # A shard of a mangled segmentation charts as nonsense with
        # conviction: only a letter-shaped cell may overrule the reader.
        # (A stem IS a narrow tall cell, so stems are judged on height alone.)
        if cell[3] < 0.5 * tall:
            continue
        if cell[2] < 0.3 * unit and fold(ch) not in ("i", "l", "1"):
            continue
        if not chart:
            continue
        folded: Dict[str, float] = dict(folded0)
        variants: Dict[str, List[Tuple[float, str]]] = {}
        for s, _a, c in chart:
            variants.setdefault(fold(c), []).append((s, c))
        top_f = max(folded, key=folded.get)
        top_s = folded[top_f]
        own_f = fold(ch)
        own_s = folded.get(own_f, 0.0)
        if ch.isalnum():
            judged += 1
            if own_s >= 0.55:
                agree += 1
        # Bare stems: i, l, I and 1 are the same drawing to the atlas, and the
        # dot above a stem may be toner spatter as easily as an i's tittle.
        # Offer the structural spellings and let the word's ear pick below.
        if own_f in ("i", "l", "1") and top_f in {"i", "l", "1", own_f}:
            if top_s >= FAIR:
                alts = [{"lower": "l", "upper": "I", "digit": "1"}[company]]
                if dotted:
                    alts.append("i")
                alts = [c for c in dict.fromkeys(alts) if fold(c) != own_f]
                if alts:
                    stem_alt[i] = alts
            continue
        if top_f == own_f:
            continue
        got = _spell(top_f, sorted(variants[top_f], reverse=True), cell[3], tall, company,
                     dotted)
        if ch.isalnum():
            if top_s >= STRONG and top_s - own_s >= STRONG_MARGIN:
                strong_sw[i] = got
            elif top_s >= FAIR and top_s - own_s >= FAIR_MARGIN:
                fair_sw[i] = got
        else:
            # A dot or comma scale-normalises into a blob that charts as a
            # round letter: only a mark the SIZE of a letter can be overruled.
            if top_s >= PUNCT_OVERRULE and cell[3] >= 0.55 * tall:
                strong_sw[i] = got
    if not strong_sw and not fair_sw and not stem_alt:
        return None
    # Proofreading fixes a letter or two in a reading that is broadly RIGHT.
    # When the cells disagree with most of the text, the row is mis-cut or
    # mis-read wholesale, and swapping letters inside it only makes new noise.
    if judged and agree / judged < 0.65:
        return None
    budget = max(2, judged // 4)
    if len(strong_sw) + len(fair_sw) > budget:
        return None

    def spelled(swaps: Dict[int, str]) -> str:
        fixed = list(chars)
        for i, c in swaps.items():
            fixed[i] = c
        it = iter(fixed)
        return "".join(ch if ch.isspace() else next(it) for ch in text)

    adopted = dict(strong_sw)
    if fair_sw:
        trial = {**adopted, **fair_sw}
        if _wordness(spelled(trial)) > _wordness(spelled(adopted)) + 0.2:
            adopted = trial
    if stem_alt:
        from itertools import product
        keys = list(stem_alt)[:4]
        best, best_w = adopted, _wordness(spelled(adopted))
        floor_w = best_w
        for combo in product(*[[None] + stem_alt[k] for k in keys]):
            trial = {**adopted, **{k: c for k, c in zip(keys, combo) if c is not None}}
            w = _wordness(spelled(trial))
            if w > best_w:
                best, best_w = trial, w
        if best_w > floor_w + 0.2:
            adopted = best
    base = spelled(adopted)
    if base == text:
        return None
    if not strong_sw and _wordness(base) <= _wordness(text) + 0.2:
        return None   # soft evidence alone must also make the word more of a word
    if _wordness(base) < _wordness(text) - 0.2:
        return None   # even strong shape evidence should not UNmake a word
    return base


def amend_blocks(img: np.ndarray, blocks: Sequence, glyphs: Glyphs,
                 say=lambda m: None) -> int:
    """Proofread the degraded display rows in place. Returns rows changed."""
    from .typeface import make_sample, true_inks

    import os
    debug = bool(os.environ.get("RIP_DEBUG_PROOF"))
    inks = true_inks(blocks)
    changed = 0
    for bi, b in enumerate(blocks):
        conf = float(np.mean([r.conf for r in b.runs]))
        # Display rows only - and no confidence gate: tesseract reports 91+
        # on misreads of degraded display type ('Unicago' at 91, 'Chicago' at
        # 96 on the same sheet). The shape evidence gates inside amend().
        if b.size < 24:
            continue
        for run in b.runs:
            # A short row has no word around the letter to protect it.
            if sum(c.isalnum() for c in run.text) < 6:
                continue
            s = make_sample(img, run, inks.get(bi))
            if s is None:
                if debug:
                    print(f"    proof! {run.text[:24]!r} no sample")
                continue
            new = amend(glyphs, (s.ref > 0.45).astype(np.uint8), run.text, base=s.base)
            if debug:
                row = letter_cells((s.ref > 0.45).astype(np.uint8), s.base)
                print(f"    proof? {run.text[:24]!r} size={b.size:.0f} conf={conf:.0f} "
                      f"cells={len(row)} chars={len([c for c in run.text if not c.isspace()])} -> {new!r}")
                dump = os.environ.get("RIP_DEBUG_PROOF_DUMP")
                if dump:
                    import pickle
                    safe = "".join(c if c.isalnum() else "_" for c in run.text[:16])
                    with open(f"{dump}/row-{safe}.pkl", "wb") as f:
                        pickle.dump({"ref": s.ref, "text": run.text, "base": s.base,
                                     "size": b.size}, f)
                    vis = cv2.cvtColor((255 * (1 - s.ref)).astype(np.uint8), cv2.COLOR_GRAY2BGR)
                    for x, y, w, h, _m in row:
                        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 1)
                    cv2.imwrite(f"{dump}/row-{safe}.png", vis)
            if new is None:
                continue
            old = run.text
            pos = 0
            for w in run.words:
                n = len(w.text)
                w.text = new[pos:pos + n]
                w.conf = max(w.conf, 75.0)   # the shapes now vouch for it
                pos += n + 1                 # the joining space
            changed += 1
            say(f"Proofread {old!r} -> {run.text!r}")
    return changed
