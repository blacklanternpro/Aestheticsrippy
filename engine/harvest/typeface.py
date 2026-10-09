"""
Match the type in a reference against the type cabinet.

For a sample line of a block we render the OCR'd text in every cabinet face
(family x weight x width) at the size its measured x-height or cap height
implies, tracked to the measured width, in Chromium at the reference's own
pixel scale. Each rendering is compared with the reference crop after the
best small shift; the closest face wins. A second pass refines size and
tracking for the leaders. Blocks that share a face and size collapse into
named styles later (build.py).
"""

from __future__ import annotations

import html
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..typecase import FONTS, catalogue
from .layout import Block, Run, ink_mask

PAGE_W = 2400
BATCH_H = 9000


@dataclass(frozen=True)
class Face:
    family: str
    weight: int
    stretch: Optional[int] = None

    @property
    def key(self) -> str:
        return f"{self.family}|{self.weight}|{self.stretch or ''}"


@dataclass
class Sample:
    run: Run
    ref: np.ndarray        # float32 darkness map 0..1
    x0: int                # crop origin in sheet px
    y0: int
    base: float            # baseline y inside the crop
    left: float            # ink left inside the crop
    ink_w: float           # ink width, px
    height: float          # the measured height used for size
    kind: str              # "cap", "x", "tall"


@dataclass
class Match:
    face: Face
    size_px: float
    tracking_em: float
    score: float
    scores: Dict[str, float] = field(default_factory=dict)   # face key -> block score


def faces() -> List[Face]:
    out = []
    for fam in catalogue()["families"]:
        if not fam.get("match", True):
            continue
        for w in fam["try"]["weight"]:
            for st in fam["try"].get("stretch", [None]):
                out.append(Face(fam["family"], w, st))
    return out


def _metrics() -> Dict[str, Dict]:
    return {f["family"]: f["metrics"] for f in catalogue()["families"]}


# ------------------------------------------------------------------ samples

def _darkness(crop: np.ndarray, ink_bgr: Tuple[int, int, int]) -> np.ndarray:
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    _, paper, _ = ink_mask(crop)
    ink = cv2.cvtColor(np.uint8([[ink_bgr]]), cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]
    span = max(20.0, float(np.linalg.norm(ink - paper)))
    d = np.linalg.norm(lab - paper, axis=2) / span
    return np.clip(d, 0, 1).astype(np.float32)


def true_inks(blocks: Sequence[Block]) -> Dict[int, Tuple[int, int, int]]:
    """
    Small type never reaches its real ink colour on screen or in a photo:
    antialiasing mixes it with the paper. Borrow the colour of larger type of
    the same hue when there is some; otherwise the block's darkest pixels.
    """
    def lab(c):
        return cv2.cvtColor(np.uint8([[list(c)]]), cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]
    big = [r.ink.colour for b in blocks for r in b.runs if r.ink and r.size >= 26]
    out = {}
    for bi, b in enumerate(blocks):
        cols = [r.ink.colour for r in b.runs if r.ink]
        if not cols:
            continue
        own = tuple(int(v) for v in np.median(np.array(cols), axis=0))
        if b.size >= 26 or not big:
            out[bi] = own
            continue
        lo = lab(own)
        best = None
        for c in big:
            lc = lab(c)
            if np.hypot(lc[1] - lo[1], lc[2] - lo[2]) < 14 and lc[0] <= lo[0] + 2:
                if best is None or lc[0] < lab(best)[0]:
                    best = c
        out[bi] = tuple(int(v) for v in best) if best is not None else own
    return out


def make_sample(img: np.ndarray, run: Run, ink_bgr: Optional[Tuple[int, int, int]] = None) -> Optional[Sample]:
    ink = run.ink
    if ink is None:
        return None
    if ink.tall and ink.tall_kind == "cap":
        height, kind = ink.tall, "cap"
    elif ink.x_height:
        height, kind = ink.x_height, "x"
    elif ink.tall:
        height, kind = ink.tall, "tall"
    else:
        return None
    if height < 4:
        return None
    em = run.size
    pad_x = int(round(0.35 * em)) + 3
    x0 = max(0, int(ink.left) - pad_x)
    x1 = min(img.shape[1], int(np.ceil(ink.right)) + pad_x)
    y0 = max(0, int(ink.baseline - 1.05 * em))
    y1 = min(img.shape[0], int(np.ceil(ink.baseline + 0.32 * em)))
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    dark = _darkness(img[y0:y1, x0:x1], ink_bgr or ink.colour)
    # Only this run's own ink: blank anything outside its word boxes.
    keep = np.zeros(dark.shape, np.float32)
    g = max(2, int(0.08 * em))
    for w in run.words:
        a, b = int(w.box[0]) - x0 - g, int(np.ceil(w.box[2])) - x0 + g
        c, d = int(w.box[1]) - y0 - g, int(np.ceil(w.box[3])) - y0 + g
        keep[max(0, c):max(0, d), max(0, a):max(0, b)] = 1
    dark *= keep
    return Sample(run, dark, x0, y0, ink.baseline - y0, ink.left - x0, ink.right - ink.left, height, kind)


def nominal_size(sample: Sample, family: str, metrics: Dict[str, Dict]) -> float:
    m = metrics[family]
    if sample.kind == "cap":
        return sample.height / max(0.3, m["cap"])
    if sample.kind == "x":
        return sample.height / max(0.2, m["x"])
    return sample.height / max(0.3, m["cap"] * 1.04)


# ---------------------------------------------------------------- rendering

_JS = """
async (items) => {
  const root = document.getElementById('root');
  root.innerHTML = '';
  const specs = new Set();
  for (const it of items) specs.add(`${it.weight} ${it.stretch ? it.stretch + '% ' : ''}${it.size}px '${it.family}'`);
  await Promise.all([...specs].map((s) => document.fonts.load(s).catch(() => null)));
  const els = items.map((it) => {
    const d = document.createElement('div');
    d.style.cssText = `position:absolute; left:${it.left}px; top:${it.top}px; white-space:pre; line-height:1;` +
      `font-family:'${it.family}'; font-weight:${it.weight}; font-size:${it.size}px;` +
      (it.stretch ? `font-stretch:${it.stretch}%;` : '') + `letter-spacing:${it.ls || 0}px; color:#000;` +
      `font-kerning:normal; font-optical-sizing:auto;`;
    const b = document.createElement('span');
    b.style.cssText = 'display:inline-block; width:0; height:0; vertical-align:baseline';
    d.appendChild(b);
    d.appendChild(document.createTextNode(it.text));
    root.appendChild(d);
    return d;
  });
  await document.fonts.ready;
  return els.map((d, i) => {
    const it = items[i];
    const r = document.createRange();
    r.selectNodeContents(d.lastChild);
    let w = r.getBoundingClientRect().width;
    let ls = it.ls || 0;
    const n = [...it.text].length;
    if (it.fitWidth && n > 1) {
      // Advance width w = w0 + n * ls; aim the first n-1 gaps at the target.
      const w0 = w - n * ls;
      ls = (it.fitWidth - w0) / (n - 1);
      d.style.letterSpacing = ls + 'px';
    }
    const base = d.firstChild.getBoundingClientRect().bottom;
    d.style.top = (parseFloat(d.style.top) + (it.baseline - base)) + 'px';
    return { ls };
  });
}
"""


class Bench:
    """A Chromium page for rendering candidate lines at reference scale."""

    def __init__(self, browser):
        self.blur = 0.7  # candidate blur matching the reference's softness; set per document
        self.page = browser.new_page(device_scale_factor=1, viewport={"width": PAGE_W, "height": 1000})
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=None)
        css = (FONTS / "fonts.css").resolve().as_uri()
        self.tmp.write(f"<!doctype html><html><head><meta charset='utf-8'><link rel='stylesheet' href='{css}'>"
                       "<style>html,body{margin:0;background:#fff}#root{position:relative}</style></head>"
                       "<body><div id='root'></div></body></html>")
        self.tmp.close()
        self.page.goto(Path(self.tmp.name).as_uri())

    def close(self):
        self.page.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def render(self, items: List[Dict]) -> List[Tuple[np.ndarray, float]]:
        """items: text, family, weight, stretch, size, ls|fitWidth, w, h, baseline, ox. Returns (tile, ls)."""
        out: List[Tuple[np.ndarray, float]] = [None] * len(items)  # type: ignore
        i = 0
        while i < len(items):
            batch, y = [], 0
            while i + len(batch) < len(items):
                it = items[i + len(batch)]
                if batch and y + it["h"] > BATCH_H:
                    break
                batch.append(dict(it, top=y, left=it["ox"], baseline=y + it["base"]))
                y += it["h"] + 4
            width = max(PAGE_W, max(b["w"] for b in batch))
            self.page.set_viewport_size({"width": width, "height": max(10, y)})
            res = self.page.evaluate(_JS, [
                {k: b[k] for k in ("text", "family", "weight", "stretch", "size", "top", "left", "baseline")}
                | {"ls": b.get("ls"), "fitWidth": b.get("fitWidth")} for b in batch])
            shot = self.page.screenshot(clip={"x": 0, "y": 0, "width": width, "height": max(10, y)})
            img = cv2.imdecode(np.frombuffer(shot, np.uint8), cv2.IMREAD_GRAYSCALE)
            for j, b in enumerate(batch):
                tile = img[b["top"]:b["top"] + b["h"], 0:b["w"]]
                out[i + j] = (1.0 - tile.astype(np.float32) / 255.0, float(res[j]["ls"]))
            i += len(batch)
        return out


# ------------------------------------------------------------------ scoring



def _norm(m: np.ndarray) -> np.ndarray:
    """Scale so solid stroke cores read 1; small type never reaches full ink in either image."""
    v = m[m > 0.08]
    if not len(v):
        return m
    return np.clip(m / max(0.2, float(np.percentile(v, 92))), 0, 1)


def _compare(ref: np.ndarray, cand: np.ndarray, dx: int, dy: int, blur: float = 0.7) -> Tuple[float, int, int]:
    """Best soft-overlap score of ref against cand within +-dx, +-dy. cand is ref-sized plus margins."""
    a = cv2.GaussianBlur(ref, (0, 0), 0.5)
    b = cv2.GaussianBlur(cand, (0, 0), blur)
    if b.shape[0] < a.shape[0] or b.shape[1] < a.shape[1]:
        return 0.0, 0, 0
    res = cv2.matchTemplate(b, a, cv2.TM_SQDIFF)
    _, _, loc, _ = cv2.minMaxLoc(res)
    x, y = loc
    win = b[y:y + a.shape[0], x:x + a.shape[1]]
    inter = np.minimum(a, win).sum()
    denom = a.sum() + win.sum()
    score = 2 * inter / denom if denom > 0 else 0.0
    return float(score), x - dx, y - dy


def _ink_width(tile: np.ndarray) -> Optional[Tuple[float, float]]:
    cols = np.nonzero((tile > 0.35).any(axis=0))[0]
    if not len(cols):
        return None
    return float(cols[0]), float(cols[-1] + 1)


@dataclass
class _Try:
    sample: Sample
    face: Face
    size: float
    ls: Optional[float] = None
    score: float = 0.0
    shift: Tuple[int, int] = (0, 0)


def _items(tries: Sequence[_Try], fit: bool) -> List[Dict]:
    items = []
    for t in tries:
        s = t.sample
        dx = max(3, int(round(0.08 * t.size)))
        dy = max(2, int(round(0.04 * t.size)))
        n = len(s.run.text)
        it = {"text": s.run.text, "family": t.face.family, "weight": t.face.weight,
              "stretch": t.face.stretch, "size": round(t.size, 3),
              "w": s.ref.shape[1] + 2 * dx, "h": s.ref.shape[0] + 2 * dy,
              "base": s.base + dy, "ox": s.left + dx - 0.04 * t.size, "_dx": dx, "_dy": dy}
        if fit or t.ls is None:
            it["fitWidth"] = s.ink_w + 0.07 * t.size if n > 1 else None
        else:
            it["ls"] = t.ls
        items.append(it)
    return items


def _run(bench: Bench, tries: List[_Try], fit: bool) -> None:
    items = _items(tries, fit)
    tiles = bench.render(items)
    for t, it, (tile, ls) in zip(tries, items, tiles):
        t.ls = ls
        t.score, sx, sy = _compare(t.sample.ref, tile, it["_dx"], it["_dy"], bench.blur)
        t.shift = (sx, sy)
        # Re-aim tracking on measured ink width (bearings differ per face).
        w = _ink_width(tile)
        n = len(t.sample.run.text)
        if w and n > 1:
            t.ls = ls + (t.sample.ink_w - (w[1] - w[0])) / (n - 1)


def _penalty(t: _Try) -> float:
    if t.ls is None or t.size <= 0:
        return 0.0
    em = t.ls / t.size
    return 0.6 * max(0.0, abs(em) - 0.06) + (0.4 * max(0.0, -em - 0.03))


def match_blocks(bench: Bench, img: np.ndarray, blocks: Sequence[Block],
                 per_block: int = 2, finalists: int = 6) -> Dict[int, Match]:
    metrics = _metrics()
    all_faces = faces()
    inks = true_inks(blocks)
    samples: Dict[int, List[Sample]] = {}
    for bi, b in enumerate(blocks):
        runs = sorted(b.runs, key=lambda r: (-(r.conf >= 80), -len(r.text)))
        got = []
        for r in runs:
            s = make_sample(img, r, inks.get(bi))
            if s is not None and len(r.text) >= 2:
                got.append(s)
            if len(got) >= per_block:
                break
        if got:
            samples[bi] = got

    # How soft is the reference? Blur the candidates to match (scans and JPEGs are soft;
    # comparing soft against crisp would favour heavy weights).
    probe = sorted((s for ss in samples.values() for s in ss), key=lambda s: -s.run.conf)[:6]
    if probe:
        tries = [_Try(s, Face("Inter", w), nominal_size(s, "Inter", metrics)) for s in probe for w in (400, 700)]
        items = _items(tries, True)
        tiles = bench.render(items)
        best_sigma, best_val = 0.7, -1.0
        for sigma in (0.4, 0.7, 1.0, 1.4, 1.9):
            vals = []
            for s in probe:
                vals.append(max(_compare(t.sample.ref, tile, it["_dx"], it["_dy"], sigma)[0]
                                for t, it, (tile, _) in zip(tries, items, tiles) if t.sample is s))
            if np.mean(vals) > best_val:
                best_sigma, best_val = sigma, float(np.mean(vals))
        bench.blur = best_sigma

    # Stage 1: every face at its nominal size, tracked to width.
    stage1 = [_Try(s, f, nominal_size(s, f.family, metrics))
              for bi, ss in samples.items() for s in ss for f in all_faces]
    _run(bench, stage1, fit=True)
    owner = {id(s): bi for bi, ss in samples.items() for s in ss}
    table: Dict[int, Dict[str, List[_Try]]] = {}
    for t in stage1:
        table.setdefault(owner[id(t.sample)], {}).setdefault(t.face.key, []).append(t)

    def face_score(ts: List[_Try]) -> float:
        return float(np.mean([t.score - _penalty(t) for t in ts]))

    # Stage 2: for each block's finalists, nudge size; keep the best per sample.
    stage2: List[_Try] = []
    for bi, faces_ in table.items():
        ranked = sorted(faces_.items(), key=lambda kv: -face_score(kv[1]))[:finalists]
        for _, ts in ranked:
            for t in ts:
                for mult in (0.92, 0.96, 1.04, 1.08):
                    stage2.append(_Try(t.sample, t.face, t.size * mult))
    _run(bench, stage2, fit=True)
    for t in stage2:
        lst = table[owner[id(t.sample)]][t.face.key]
        for k, old in enumerate(lst):
            if old.sample is t.sample and (t.score - _penalty(t)) > (old.score - _penalty(old)):
                lst[k] = t

    # Final pass for the per-sample winners with corrected tracking (no refit).
    final: List[_Try] = []
    for bi, faces_ in table.items():
        ranked = sorted(faces_.items(), key=lambda kv: -face_score(kv[1]))[:3]
        for _, ts in ranked:
            final.extend(ts)
    _run(bench, final, fit=False)

    out: Dict[int, Match] = {}
    for bi, faces_ in table.items():
        scores = {k: face_score(ts) for k, ts in faces_.items()}
        best_key = max(scores, key=scores.get)
        ts = faces_[best_key]
        size = float(np.median([t.size for t in ts]))
        track = float(np.median([(t.ls or 0) / t.size for t in ts]))
        out[bi] = Match(ts[0].face, size, track, scores[best_key], scores)
    return out
