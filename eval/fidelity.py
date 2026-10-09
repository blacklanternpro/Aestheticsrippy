"""
Aestheticsrippy - fidelity metrics.

Scores how closely a rendered sheet matches its reference image, on a 0-100
scale, and explains *why* through four sub-scores:

  layout     Where the ink sits. Correlation of coarse ink-density maps, so
             "everything shrank toward the centre" is punished hard while a
             one-pixel nudge is not.
  structure  Edge-level similarity (SSIM on edge maps at two blur scales):
             rules, letter shapes, borders, rhythm.
  tone       Paper and ink colour: perceptual distance between weighted
             palettes in CIELAB.
  aspect     Whether the sheet has the reference's proportions at all.

The reference is first cropped to the printed sheet when it was photographed
on a contrasting background (a receipt on black, a poster in a frame).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Tuple

import cv2
import numpy as np

GRID_W = 480          # comparison width in px; height follows the reference aspect
DENSITY_CELLS = 24    # ink-density grid across the short side

WEIGHTS = {"layout": 0.40, "structure": 0.30, "tone": 0.20, "aspect": 0.10}


@dataclass
class Fidelity:
    score: float        # 0 = no better than blank paper in the right colour, 100 = identical
    raw: float          # weighted sub-scores before that calibration
    layout: float
    structure: float
    tone: float
    aspect: float
    ref_aspect: float
    render_aspect: float
    cropped: bool

    def as_dict(self) -> Dict:
        out = {}
        for k, v in asdict(self).items():
            if isinstance(v, (bool, np.bool_)):
                out[k] = bool(v)
            elif isinstance(v, (float, np.floating)):
                out[k] = round(float(v), 3 if k.endswith("aspect") and k != "aspect" else 1)
            else:
                out[k] = v
        return out


# --------------------------------------------------------------------------
# Loading and registration
# --------------------------------------------------------------------------

def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    return img


def crop_to_sheet(img: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    If the reference shows the sheet against a clearly different surround
    (dark table, black frame), crop to the sheet. Otherwise return it as-is.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    border = np.concatenate([gray[:4].ravel(), gray[-4:].ravel(),
                             gray[:, :4].ravel(), gray[:, -4:].ravel()])
    interior = gray[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    if abs(float(np.median(border)) - float(np.median(interior))) < 60:
        return img, False  # no contrasting surround

    surround_dark = np.median(border) < np.median(interior)
    flag = cv2.THRESH_BINARY if surround_dark else cv2.THRESH_BINARY_INV
    _, mask = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, flag + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img, False
    x, y, cw, ch = cv2.boundingRect(max(contours, key=cv2.contourArea))
    if cw * ch < 0.25 * w * h or cw * ch > 0.98 * w * h:
        return img, False
    return img[y:y + ch, x:x + cw], True


def _resize(img: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def _ink_mask(gray: np.ndarray) -> np.ndarray:
    """Ink = pixels meaningfully darker or lighter than the dominant paper tone."""
    paper = float(np.median(gray))
    diff = np.abs(gray.astype(np.float32) - paper)
    thresh = max(40.0, float(np.percentile(diff, 50)) + 25.0)
    return (diff > thresh).astype(np.float32)


def _density(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    short = min(h, w)
    cell = max(4, short // DENSITY_CELLS)
    gh, gw = max(1, h // cell), max(1, w // cell)
    grid = cv2.resize(mask, (gw, gh), interpolation=cv2.INTER_AREA)
    # Soften by about one cell so a near-miss earns partial credit.
    return cv2.GaussianBlur(grid, (0, 0), 0.8)


def layout_score(ref_gray: np.ndarray, ren_gray: np.ndarray) -> float:
    a = _density(_ink_mask(ref_gray)).ravel()
    b = _density(_ink_mask(ren_gray)).ravel()
    if a.std() < 1e-6 or b.std() < 1e-6:
        return 0.0
    corr = float(np.corrcoef(a, b)[0, 1])
    # Penalise a big difference in total ink coverage even if the shape correlates.
    coverage = 1.0 - min(1.0, abs(a.mean() - b.mean()) / max(a.mean(), b.mean(), 1e-6))
    return max(0.0, corr) * 100.0 * (0.75 + 0.25 * coverage)


def _ssim(x: np.ndarray, y: np.ndarray) -> float:
    x = x.astype(np.float64)
    y = y.astype(np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda z: cv2.GaussianBlur(z, (11, 11), 1.5)  # noqa: E731
    mx, my = blur(x), blur(y)
    sxx = blur(x * x) - mx * mx
    syy = blur(y * y) - my * my
    sxy = blur(x * y) - mx * my
    ssim_map = ((2 * mx * my + c1) * (2 * sxy + c2)) / ((mx * mx + my * my + c1) * (sxx + syy + c2))
    return float(ssim_map.mean())


def structure_score(ref_gray: np.ndarray, ren_gray: np.ndarray) -> float:
    scores = []
    for k in (3, 9):
        ea = cv2.Canny(cv2.GaussianBlur(ref_gray, (k, k), 0), 50, 150)
        eb = cv2.Canny(cv2.GaussianBlur(ren_gray, (k, k), 0), 50, 150)
        # Thicken edges so near-misses count partially.
        ea = cv2.GaussianBlur(ea, (0, 0), 3)
        eb = cv2.GaussianBlur(eb, (0, 0), 3)
        scores.append(_ssim(ea, eb))
    return max(0.0, float(np.mean(scores))) * 100.0


def _palette(img: np.ndarray, k: int = 4) -> Tuple[np.ndarray, np.ndarray]:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    rng = np.random.default_rng(0)
    sample = lab[rng.choice(len(lab), size=min(6000, len(lab)), replace=False)]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(0)
    _, labels, centers = cv2.kmeans(sample, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    weights = np.bincount(labels.ravel(), minlength=k).astype(np.float64)
    return centers, weights / weights.sum()


def tone_score(ref: np.ndarray, ren: np.ndarray) -> float:
    ca, wa = _palette(ref)
    cb, wb = _palette(ren)
    # OpenCV 8-bit Lab: L in 0..255, so rescale to approximate Delta E units.
    scale = np.array([100 / 255, 1.0, 1.0])
    d = np.linalg.norm((ca[:, None, :] - cb[None, :, :]) * scale, axis=2)
    # Symmetric weighted nearest-colour distance.
    dist = 0.5 * ((wa * d.min(axis=1)).sum() + (wb * d.min(axis=0)).sum())
    return float(max(0.0, 100.0 - 2.0 * dist))  # dE 50 -> 0


def aspect_score(ref_aspect: float, ren_aspect: float) -> float:
    err = abs(np.log(ren_aspect / ref_aspect))
    return float(max(0.0, 100.0 * (1.0 - err / 0.35)))  # ~30% off -> 0


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def prepare(ref_bytes: bytes, render_bytes: bytes):
    ref_full = decode(ref_bytes)
    ref, cropped = crop_to_sheet(ref_full)
    ren = decode(render_bytes)
    rh, rw = ref.shape[:2]
    size = (GRID_W, max(1, round(GRID_W * rh / rw)))
    return ref, ren, cropped, _resize(ref, size), _resize(ren, size)


def _parts(ref_s: np.ndarray, ren_s: np.ndarray, ref_aspect: float, ren_aspect: float) -> Dict[str, float]:
    ref_g = cv2.cvtColor(ref_s, cv2.COLOR_BGR2GRAY)
    ren_g = cv2.cvtColor(ren_s, cv2.COLOR_BGR2GRAY)
    return {
        "layout": layout_score(ref_g, ren_g),
        "structure": structure_score(ref_g, ren_g),
        "tone": tone_score(ref_s, ren_s),
        "aspect": aspect_score(ref_aspect, ren_aspect),
    }


def _weighted(parts: Dict[str, float]) -> float:
    return sum(WEIGHTS[k] * v for k, v in parts.items())


def score(ref_bytes: bytes, render_bytes: bytes) -> Fidelity:
    ref, ren, cropped, ref_s, ren_s = prepare(ref_bytes, render_bytes)
    ref_aspect = ref.shape[1] / ref.shape[0]
    ren_aspect = ren.shape[1] / ren.shape[0]

    parts = _parts(ref_s, ren_s, ref_aspect, ren_aspect)
    raw = _weighted(parts)

    # Calibrate against the cheapest possible answer: an empty sheet in the
    # reference's paper colour at the right proportions. Matching tone and
    # aspect alone should not score well.
    paper = np.median(ref_s.reshape(-1, 3), axis=0).astype(np.uint8)
    blank = np.empty_like(ref_s)
    blank[:] = paper
    floor = _weighted(_parts(ref_s, blank, ref_aspect, ref_aspect))
    calibrated = max(0.0, (raw - floor) / max(1e-6, 100.0 - floor)) * 100.0

    return Fidelity(score=calibrated, raw=raw, ref_aspect=ref_aspect, render_aspect=ren_aspect,
                    cropped=cropped, **parts)


def diff_image(ref_bytes: bytes, render_bytes: bytes, height: int = 720) -> np.ndarray:
    """
    Reference | render | ink overlay. In the overlay, red is ink the reference
    has and the render lacks; blue is ink the render added; dark is agreement.
    """
    _, _, _, ref_s, ren_s = prepare(ref_bytes, render_bytes)
    a = _ink_mask(cv2.cvtColor(ref_s, cv2.COLOR_BGR2GRAY)) > 0
    b = _ink_mask(cv2.cvtColor(ren_s, cv2.COLOR_BGR2GRAY)) > 0
    overlay = np.full(ref_s.shape, 245, np.uint8)
    overlay[a & b] = (40, 40, 40)
    overlay[a & ~b] = (60, 60, 230)    # BGR red: missing
    overlay[~a & b] = (230, 140, 40)   # BGR blue: extra
    scale = height / ref_s.shape[0]
    tiles = [cv2.resize(t, (round(t.shape[1] * scale), height), interpolation=cv2.INTER_AREA)
             for t in (ref_s, ren_s, overlay)]
    gap = np.full((height, 12, 3), 255, np.uint8)
    return np.hstack([tiles[0], gap, tiles[1], gap, tiles[2]])
