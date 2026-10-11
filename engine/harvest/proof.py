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


def amend(glyphs: Glyphs, ink: np.ndarray, text: str,
          base: Optional[float] = None) -> Optional[str]:
    """The row's text with shape-overruled letters corrected, or None when the
    reader's call stands. `ink`: mask of the one row `text` was read from."""
    from .curved import _wordness

    chars = [ch for ch in text if not ch.isspace()]
    row = letter_cells(ink, base)
    if not chars or len(chars) != len(row):
        return None
    tall = float(np.percentile([c[3] for c in row], 85))
    units = [c[2] for c in row if c[3] >= 0.5 * tall]
    unit = float(np.median(units)) if units else 1.0
    company = _context_case(chars)
    strong_sw: Dict[int, str] = {}
    fair_sw: Dict[int, str] = {}
    stem_alt: Dict[int, List[str]] = {}
    for i, (ch, cell) in enumerate(zip(chars, row)):
        dotted = bool(cell[5]) if len(cell) > 5 else False
        # A shard of a mangled segmentation charts as nonsense with
        # conviction: only a letter-shaped cell may overrule the reader.
        # (A stem IS a narrow tall cell, so stems are judged on height alone.)
        if cell[3] < 0.5 * tall:
            continue
        if cell[2] < 0.3 * unit and fold(ch) not in ("i", "l", "1"):
            continue
        chart = glyphs.chart(cell[4], ANGLES, top=10)
        if not chart:
            continue
        folded: Dict[str, float] = {}
        variants: Dict[str, List[Tuple[float, str]]] = {}
        for s, _a, c in chart:
            f = fold(c)
            folded[f] = max(folded.get(f, -1.0), s)
            variants.setdefault(f, []).append((s, c))
        top_f = max(folded, key=folded.get)
        top_s = folded[top_f]
        own_f = fold(ch)
        own_s = folded.get(own_f, 0.0)
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
