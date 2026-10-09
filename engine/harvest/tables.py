"""
Repeated rows: invoice lines, tour dates, a list of links. When three or more
rows share a rhythm, a column structure and a style per column, they are one
list, and the pack should let you add a row rather than nudge five frames.

A table is found from the runs (single lines of words) of blocks that it
uses up entirely, so nothing is left half in a list and half out of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .layout import Block, Run


@dataclass
class Table:
    rows: List[List[Run]]                 # cells left to right
    styles: List[str]                     # style per column
    aligns: List[str]                     # "left" | "right" | "center" per column
    blocks: List[int] = field(default_factory=list)   # block indices it uses up
    step: float = 0.0                     # baseline to baseline, px


def _rows(runs: Sequence[Tuple[int, Run]]) -> List[List[Tuple[int, Run]]]:
    """Group runs that share a baseline."""
    out: List[List[Tuple[int, Run]]] = []
    for bi, r in sorted(runs, key=lambda t: t[1].baseline):
        if out and abs(out[-1][0][1].baseline - r.baseline) <= 0.35 * max(r.size, out[-1][0][1].size):
            out[-1].append((bi, r))
        else:
            out.append([(bi, r)])
    return [sorted(row, key=lambda t: t[1].left) for row in out]


def _column_align(cells: Sequence[Run], tol: float) -> str:
    lefts = np.array([c.left for c in cells])
    rights = np.array([c.right for c in cells])
    centres = (lefts + rights) / 2
    spread = {"left": np.ptp(lefts), "right": np.ptp(rights), "center": np.ptp(centres)}
    best = min(spread, key=spread.get)
    return best if spread[best] <= tol else ""


def find_tables(blocks: Sequence[Block], style_of: Dict[int, str], same=None) -> List[Table]:
    """
    Rows are lines that share a baseline; a table is a run of three or more rows
    in which at least two cells line up column by column (left or right edge),
    with matching styles, at a steady rhythm. Cells elsewhere on the same
    baselines (an address column beside the item list) are not part of it.
    """
    same = same or (lambda a, b: a == b)
    runs = [(bi, r) for bi, b in enumerate(blocks) if bi in style_of for r in b.runs]
    rows = _rows(runs)

    def aligned(a: Run, b: Run, tol: float) -> bool:
        return abs(a.left - b.left) <= tol or abs(a.right - b.right) <= tol or \
            abs((a.left + a.right) / 2 - (b.left + b.right) / 2) <= tol

    tables: List[Table] = []
    taken = set()  # (row index, id(run))

    def candidate(i: int):
        chains = [[(bi, r)] for bi, r in rows[i] if (i, id(r)) not in taken]
        group = [i]
        j = i + 1
        while j < len(rows) and len(chains) >= 2:
            step = rows[j][0][1].baseline - rows[group[-1]][0][1].baseline
            nxt, missed = [], []
            for ch in chains:
                bi0, r0 = ch[-1]
                tol = 0.6 * r0.size
                hit = [(bi, r) for bi, r in rows[j] if (j, id(r)) not in taken and aligned(r0, r, tol)
                       and same(style_of[bi0], style_of[bi])] if step <= 4.5 * r0.size else []
                if len(hit) == 1:
                    nxt.append(ch + hit)
                else:
                    missed.append(ch)
            if len(nxt) < 2:
                # A row that only touches other columns (an address beside the list) is skipped;
                # one that cuts across the list's columns ends it.
                spans = [(min(r.left for _, r in ch), max(r.right for _, r in ch)) for ch in missed]
                crosses = any(r.left < hi and r.right > lo for _, r in rows[j] for lo, hi in spans)
                if crosses or step > 4.5 * chains[0][-1][1].size:
                    break
                j += 1
                continue
            if len(group) >= 2:
                first = rows[group[1]][0][1].baseline - rows[group[0]][0][1].baseline
                if abs(step - first) > 0.18 * first:
                    break
            chains = nxt
            group.append(j)
            j += 1
        if len(group) >= 3 and len(chains) >= 2:
            return group, chains
        return None

    i = 0
    while i < len(rows) - 2:
        cand = candidate(i)
        if cand is None:
            i += 1
            continue
        # A header row in its own style can start a thinner table than the rows beneath;
        # prefer the table with more columns.
        nxt = candidate(i + 1) if i + 3 < len(rows) + 1 else None
        if nxt and len(nxt[1]) > len(cand[1]):
            i += 1
            continue
        group, chains = cand
        chains.sort(key=lambda ch: ch[0][1].left)
        n = len(group)
        cells = [[chains[c][g][1] for c in range(len(chains))] for g in range(n)]
        size = float(np.median([r.size for row in cells for r in row]))
        aligns = [_column_align([row[c] for row in cells], 0.6 * size) or "left" for c in range(len(chains))]
        from collections import Counter
        sig = [Counter(style_of[bi] for bi, _ in ch).most_common(1)[0][0] for ch in chains]
        involved = {bi for ch in chains for bi, _ in ch}
        in_rows = {id(r) for ch in chains for _, r in ch}
        if all(all(id(r) in in_rows for r in blocks[bi].runs) for bi in involved):
            steps = np.diff([rows[g][0][1].baseline for g in group])
            tables.append(Table(cells, sig, aligns, sorted(involved), float(np.median(steps))))
            for g, row_i in enumerate(group):
                for ch in chains:
                    taken.add((row_i, id(ch[g][1])))
            continue  # the same rows may hold another table further across
        i += 1
    return tables
