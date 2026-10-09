"""
The render-and-verify loop.

Render the pack, compare it with the reference frame by frame, correct, and
repeat while the fidelity score improves. To see each text frame on its own
in a single render, the diagnostic pass paints every frame in its own colour
on white; antialiasing blends a colour toward white along a straight line,
so the direction of (white - pixel) says which frame a pixel belongs to.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..rip import loader_html
from .build import PT_PER_MM
from .layout import Block, ink_mask

try:  # the eval harness is importable from the repo root
    from eval.fidelity import score as fidelity_score
except ImportError:  # pragma: no cover
    fidelity_score = None


DEBUG = False


def render_rip(rip: Dict, data: Dict, pack_dir: Path, renderer, size: Tuple[int, int]) -> np.ndarray:
    page = loader_html(rip, data, pack_dir, [pack_dir / "assets", pack_dir])
    tmp = pack_dir / ".refine.html"
    tmp.write_text(page, encoding="utf-8")
    try:
        res = renderer.render_file(tmp, pack_id=rip["id"], pdf=False)
    finally:
        tmp.unlink(missing_ok=True)
    img = cv2.imdecode(np.frombuffer(res.png, np.uint8), cv2.IMREAD_COLOR)
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


def score_image(ref: np.ndarray, ren: np.ndarray) -> float:
    ok1, a = cv2.imencode(".png", ref)
    ok2, b = cv2.imencode(".png", ren)
    return float(fidelity_score(a.tobytes(), b.tobytes()).score)


def score_pack(pack_dir: Path, renderer) -> float:
    rip = json.loads((pack_dir / "rip.json").read_text())
    data = json.loads((pack_dir / "default-data.json").read_text())
    ref = cv2.imread(str(pack_dir / "assets" / "reference.jpg"))
    ren = render_rip(rip, data, pack_dir, renderer, (ref.shape[1], ref.shape[0]))
    return score_image(ref, ren)


# --------------------------------------------------------------- diagnostics

def _directions(n: int) -> np.ndarray:
    """n well-spread unit vectors in the positive octant (golden spiral over the sphere)."""
    m = 16
    while True:
        i = np.arange(m)
        z = 1 - (i + 0.5) / m
        r = np.sqrt(1 - z * z)
        phi = i * np.pi * (3 - np.sqrt(5))
        v = np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)
        v = v[(v > 0.12).all(axis=1)]
        if len(v) >= n:
            break
        m *= 2
    pick = np.linspace(0, len(v) - 1, n).round().astype(int)
    return v[pick] / np.linalg.norm(v[pick], axis=1, keepdims=True)


def diagnostic(rip: Dict, keys: Sequence[str]) -> Tuple[Dict, Dict[str, np.ndarray]]:
    dirs = _directions(len(keys))
    d = copy.deepcopy(rip)
    d["tokens"] = dict(d.get("tokens", {}), paper="#ffffff")
    colours: Dict[str, np.ndarray] = {}
    frames = []
    for f in d["frames"]:
        if f.get("type") != "text" or f.get("id") not in keys:
            continue
        v = dirs[keys.index(f["id"])]
        # Darkest colour along this direction: white - 255 * v / max(v).
        rgb = np.clip(255 - 255 * v / v.max() * 0.92, 0, 255).astype(int)
        f["with"] = dict(f.get("with", {}), color=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}", opacity=1)
        colours[f["id"]] = v[::-1]  # to BGR order
        frames.append(f)
    d["frames"] = frames
    return d, colours


def split_frames(img: np.ndarray, colours: Dict[str, np.ndarray],
                 windows: Dict[str, Tuple[int, int, int, int]]) -> Dict[str, Tuple[np.ndarray, int, int]]:
    """
    Per-frame ink masks, each the size of its window: (mask, x0, y0). A frame
    only looks inside its window (where its reference block and its current
    frame are), and only competes with frames whose windows overlap, so
    near-identical colours far apart never collide.
    """
    dark = 255.0 - img.astype(np.float32)
    mag = np.linalg.norm(dark, axis=2)
    H, W = mag.shape
    out = {}
    for k, (x0, y0, x1, y1) in windows.items():
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W, x1), min(H, y1)
        if x1 <= x0 or y1 <= y0:
            out[k] = (np.zeros((1, 1), bool), x0, y0)
            continue
        rivals = [r for r, (a, b, c, d) in windows.items() if a < x1 and c > x0 and b < y1 and d > y0]
        mat = np.stack([colours[r] for r in rivals])
        sub = dark[y0:y1, x0:x1]
        smag = mag[y0:y1, x0:x1]
        ink = smag > 40
        m = np.zeros(ink.shape, bool)
        if ink.any():
            unit = sub[ink] / smag[ink][:, None]
            cos = unit @ mat.T
            mine = rivals.index(k)
            sel = (cos.argmax(axis=1) == mine) & (cos[:, mine] > 0.97)
            ys, xs = np.nonzero(ink)
            m[ys[sel], xs[sel]] = True
        out[k] = (m, x0, y0)
    return out


def _bbox(info) -> Optional[Tuple[float, float, float, float]]:
    mask, ox, oy = info
    ys, xs = np.nonzero(mask)
    if len(xs) < 3:
        return None
    # Trim stray pixels: a hair of the extremes.
    lo, hi = (0.3, 99.7) if len(xs) > 300 else (0, 100)
    return (ox + float(np.percentile(xs, lo)), oy + float(np.percentile(ys, lo)),
            ox + float(np.percentile(xs, hi) + 1), oy + float(np.percentile(ys, hi) + 1))


def _lines(info, box, min_gap: int) -> int:
    mask, ox, oy = info
    x0, y0, x1, y1 = (int(v) for v in box)
    rows = mask[max(0, y0 - oy):max(0, y1 - oy), max(0, x0 - ox):max(0, x1 - ox)].any(axis=1)
    n, gap, inside = 0, 0, False
    for r in rows:
        if r:
            if not inside and (n == 0 or gap >= min_gap):
                n += 1
            inside, gap = True, 0
        else:
            inside = False
            gap += 1
    return n


# --------------------------------------------------------------------- loop

def refine(result, sheet, blocks: Sequence[Block], renderer, rounds: int = 3, progress=None) -> None:
    say = progress or (lambda m: None)
    pack_dir = result.pack_dir
    ref = cv2.imread(str(pack_dir / "assets" / "reference.jpg"))
    size = (ref.shape[1], ref.shape[0])
    px_mm = sheet.px_per_mm
    rip, data = result.rip, result.data

    block_of: Dict[str, Block] = {k: blocks[bi] for k, bi in result.frame_blocks.items()}
    keys = [f["id"] for f in rip["frames"] if f.get("type") == "text" and f.get("id") in block_of]

    best_score = score_image(ref, render_rip(rip, data, pack_dir, renderer, size))
    result.history.append({"round": 0, "score": round(best_score, 1)})
    say(f"First render scores {best_score:.1f}")

    for rnd in range(1, rounds + 1):
        diag, colours = diagnostic(rip, keys)
        img = render_rip(diag, data, pack_dir, renderer, size)
        windows = {}
        for k in keys:
            b = block_of[k]
            f = next(x for x in rip["frames"] if x.get("id") == k)
            pad = 1.2 * b.size
            fx0, fy0 = f["x"] * px_mm, f["y"] * px_mm
            fx1 = fx0 + f.get("w", 0) * px_mm
            fy1 = fy0 + (b.bottom - b.top) + 2 * b.size
            windows[k] = (int(min(b.left, fx0) - pad), int(min(b.top, fy0) - pad),
                          int(max(b.right, fx1) + pad), int(max(b.bottom, fy1) + pad))
        masks = split_frames(img, colours, windows)
        cand = copy.deepcopy(rip)
        fmap = {f["id"]: f for f in cand["frames"] if f.get("id")}
        size_votes: Dict[str, List[float]] = {}
        moved = 0
        for k in keys:
            b = block_of[k]
            box = _bbox(masks[k])
            if box is None:
                continue
            f = fmap[k]
            align = (f.get("with") or {}).get("align", "left")
            rl, rt, rr, rb = b.left, b.top, b.right, b.bottom
            l, t, r_, bt = box
            if align == "right":
                dx = rr - r_
            elif align == "center":
                dx = (rl + rr) / 2 - (l + r_) / 2
            else:
                dx = rl - l
            dy = rt - t
            if DEBUG:
                print(f"    {k} {data[k][:18]!r:22} dx={dx:+.1f} dy={dy:+.1f} ref={[round(v) for v in (rl, rt, rr, rb)]} ren={[round(v) for v in box]}")
            if abs(dx) > 0.6 * b.size or abs(dy) > 0.6 * b.size:
                continue  # a measurement gone wrong (a neighbour in the box), not a correction
            if abs(dx) > 0.4 or abs(dy) > 0.4:
                f["x"] = round(f["x"] + dx / px_mm, 2)
                f["y"] = round(f["y"] + dy / px_mm, 2)
                moved += 1
            # Size: compare heights of single-line frames (same text, same face).
            if len(b.runs) == 1 and (rb - rt) > 24 and (bt - t) > 4:
                size_votes.setdefault(f["style"], []).append((rb - rt) / (bt - t))
            # Width: for nowrap frames, tracking; for wrapping frames, line count.
            wth = f.get("with") or {}
            n_ref = len(b.runs)
            n_ren = _lines(masks[k], box, max(1, int(0.15 * (b.size))))
            if wth.get("wrap") != "nowrap" and n_ren != n_ref and n_ref > 1:
                f["w"] = round(f["w"] * (1.03 if n_ren > n_ref else 0.97), 2)
            elif wth.get("wrap") == "nowrap" and len(b.runs) == 1:
                n_chars = len(b.text())
                st = cand["styles"][f["style"]]
                size_px = st["size"] / PT_PER_MM * px_mm
                if n_chars > 2 and (r_ - l) > 4:
                    delta = ((rr - rl) - (r_ - l)) / (n_chars - 1) / size_px
                    if abs(delta) > 0.004:
                        cur = wth.get("tracking", st.get("tracking", 0.0))
                        f["with"] = dict(wth, tracking=round(cur + delta, 4))
        if DEBUG:
            print("    size votes", {k: [round(v, 3) for v in vs] for k, vs in size_votes.items()})
        for sname, votes in size_votes.items():
            ratio = float(np.median(votes))
            if abs(ratio - 1) > 0.025:
                st = cand["styles"][sname]
                st["size"] = round(st["size"] * ratio, 2)
        # Tidy: per-frame tracking that equals the style's goes away.
        for f in cand["frames"]:
            w = f.get("with")
            if w and "tracking" in w and abs(w["tracking"] - cand["styles"].get(f.get("style"), {}).get("tracking", 0)) < 0.003:
                del w["tracking"]
        s = score_image(ref, render_rip(cand, data, pack_dir, renderer, size))
        kind = "position, size and tracking"
        if s < best_score - 0.05:
            # Too much at once: try the moves alone.
            pos = copy.deepcopy(rip)
            pmap = {f["id"]: f for f in pos["frames"] if f.get("id")}
            for k in keys:
                pmap[k]["x"], pmap[k]["y"] = fmap[k]["x"], fmap[k]["y"]
            s2 = score_image(ref, render_rip(pos, data, pack_dir, renderer, size))
            if s2 > s:
                cand, s, kind = pos, s2, "position"
        result.history.append({"round": rnd, "score": round(s, 1), "moved": moved, "kept": kind if s >= best_score - 0.05 else None})
        say(f"Round {rnd}: {s:.1f}")
        if s >= best_score - 0.05:
            rip, best_score = cand, s
        else:
            break
    result.rip, result.score = rip, best_score
    from .pipeline import _write
    _write(pack_dir, rip, data)
