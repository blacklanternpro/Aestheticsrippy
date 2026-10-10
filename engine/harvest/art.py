"""
Everything on the sheet that is not live text.

    rules(img)          long thin horizontal and vertical lines, as Rip rules
    strip_rules(img)    the sheet with those lines painted out (for OCR)
    regions(img, text)  what is left once text and rules are masked: panels,
                        photos and marks, ready to become frames
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class Rule:
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float      # px
    colour: Tuple[int, int, int]
    vertical: bool = False


@dataclass
class Region:
    kind: str             # "panel", "photo", "mark", "outline"
    box: Tuple[int, int, int, int]
    colour: Tuple[int, int, int] = (0, 0, 0)
    mask: Optional[np.ndarray] = None   # bool mask over the box
    radius: Optional[str] = None        # "ellipse" for round outlines
    notes: List[str] = field(default_factory=list)
    fill: Optional[np.ndarray] = None   # bool over the box: pixels to paint over with the
    #                                     mark's own colour (light letters read out of it)


def paper_colour(img: np.ndarray) -> Tuple[int, int, int]:
    """
    The paper: the commonest colour around the edges of the sheet (big type can
    outnumber the paper in the middle of a poster), coarsely binned so a
    gentle gradient or grain still counts as one colour.
    """
    h, w = img.shape[:2]
    b = max(2, int(0.06 * min(h, w)))
    band = np.concatenate([img[:b].reshape(-1, 3), img[-b:].reshape(-1, 3),
                           img[:, :b].reshape(-1, 3), img[:, -b:].reshape(-1, 3)])
    q = (band // 16).astype(np.int32)
    keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    mode = vals[np.argmax(counts)]
    return tuple(int(v) for v in np.median(band[keys == mode], axis=0))


def plate(img: np.ndarray, covered: np.ndarray, paper) -> Optional[np.ndarray]:
    """
    The bare paper: everything covered (text, rules, art) painted out and
    smoothed. Returned only when the paper is not flat (a gradient, a tint,
    a photographed sheet's light falloff), so flat sheets stay a colour token.
    """
    h, w = img.shape[:2]
    sc = 360 / max(h, w)
    small = cv2.resize(img, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA)
    m = cv2.resize(covered.astype(np.uint8) * 255, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    bare = cv2.inpaint(small, m, 5, cv2.INPAINT_TELEA)
    bare = cv2.GaussianBlur(bare, (0, 0), 6)
    lab = _lab_img(bare)
    flat = _lab_img(np.uint8([[paper]]))[0, 0]
    dev = np.linalg.norm(lab - flat, axis=2)
    if np.percentile(dev, 90) < 6:
        return None
    return cv2.resize(bare, (w, h), interpolation=cv2.INTER_CUBIC)


def _line_masks(gray: np.ndarray, dark: bool) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = gray.shape
    k = max(3, int(round(min(h, w) / 160)) | 1)
    se = cv2.getStructuringElement(cv2.MORPH_RECT, (k * 2 + 1, k * 2 + 1))
    hat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT if dark else cv2.MORPH_TOPHAT, se)
    _, thin = cv2.threshold(hat, 40, 255, cv2.THRESH_BINARY)
    lh = max(20, w // 14)
    lv = max(20, h // 14)
    horiz = cv2.morphologyEx(thin, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (lh, 1)))
    vert = cv2.morphologyEx(thin, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, lv)))
    return horiz, vert, thin


def rules(img: np.ndarray) -> Tuple[List[Rule], np.ndarray]:
    """Long thin lines (darker or lighter than their surround) and their pixel mask."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    found: List[Rule] = []
    full = np.zeros(gray.shape, np.uint8)
    for dark in (True, False):
        horiz, vert, thin = _line_masks(gray, dark)
        for mask, vertical in ((horiz, False), (vert, True)):
            n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            for i in range(1, n):
                x, y, cw, ch, area = stats[i]
                length, thick = (ch, cw) if vertical else (cw, ch)
                if thick > max(6, length / 12):
                    continue
                # Light lines on dark ground: only long ones (gaps between big letters are not rules).
                if not dark and length < (h if vertical else w) / 4:
                    continue
                comp = labels == i
                if not _isolated(thin, x, y, cw, ch, vertical):
                    continue
                full[comp] = 255
                colour = tuple(int(v) for v in np.median(img[comp], axis=0))
                t = area / max(1, length)
                if vertical:
                    cx = x + cw / 2
                    found.append(Rule(cx, y, cx, y + ch, t, colour, True))
                else:
                    cy = y + ch / 2
                    found.append(Rule(x, cy, x + cw, cy, t, colour, False))
    return _merge(found), full


def _isolated(thin: np.ndarray, x: int, y: int, cw: int, ch: int, vertical: bool) -> bool:
    """A rule has clear space on both sides; a row of letters has ink above its baseline."""
    h, w = thin.shape
    if vertical:
        t = cw
        a = thin[y:y + ch, max(0, x - 2 * t - 3):max(0, x - 1)]
        b = thin[y:y + ch, min(w, x + cw + 1):min(w, x + cw + 2 * t + 3)]
    else:
        t = ch
        a = thin[max(0, y - 2 * t - 3):max(0, y - 1), x:x + cw]
        b = thin[min(h, y + ch + 1):min(h, y + ch + 2 * t + 3), x:x + cw]
    dens = [float((z > 0).mean()) if z.size else 0.0 for z in (a, b)]
    return max(dens) < 0.3 and min(dens) < 0.15


def _merge(rs: List[Rule]) -> List[Rule]:
    """Join collinear pieces split by text or noise."""
    out: List[Rule] = []
    for r in sorted(rs, key=lambda r: (r.vertical, r.y0 if not r.vertical else r.x0, r.x0, r.y0)):
        if out:
            p = out[-1]
            if p.vertical == r.vertical:
                if not r.vertical and abs(p.y0 - r.y0) <= 2 and r.x0 - p.x1 <= 6:
                    p.x1 = max(p.x1, r.x1)
                    p.thickness = max(p.thickness, r.thickness)
                    continue
                if r.vertical and abs(p.x0 - r.x0) <= 2 and r.y0 - p.y1 <= 6:
                    p.y1 = max(p.y1, r.y1)
                    p.thickness = max(p.thickness, r.thickness)
                    continue
        out.append(r)
    return out


def strip_rules(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if not mask.any():
        return img.copy()
    m = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    return cv2.inpaint(img, m, 3, cv2.INPAINT_TELEA)


# ------------------------------------------------------------------ regions

def _lab_img(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)


def panels(img: np.ndarray, paper) -> List[Region]:
    """
    Large flat areas of a colour other than the paper: bars, blocks, bands.
    Close the non-paper mask (fills type knocked out of a bar), open it with a
    wide kernel (removes type and rules), and keep big, solid, flat shapes.
    A shape counts as a panel if it carries knocked-out type or is large.
    """
    h, w = img.shape[:2]
    sc = min(1.0, 800 / max(h, w))
    small = cv2.resize(img, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    lab = _lab_img(small)
    paper_lab = _lab_img(np.uint8([[paper]]))[0, 0]
    off = (np.linalg.norm(lab - paper_lab, axis=2) > 30).astype(np.uint8)
    kc = max(3, int(0.012 * min(sh, sw)))
    ko = max(7, int(0.03 * min(sh, sw)))
    closed = cv2.morphologyEx(off, cv2.MORPH_CLOSE, np.ones((kc, kc), np.uint8))
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((ko, ko), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(opened, 8)
    out: List[Region] = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if area < 0.005 * sh * sw:
            continue
        comp = (labels[y:y + ch, x:x + cw] == i)
        if area / float(cw * ch) < 0.85:
            continue
        # Straight, unbroken edges: a bar or block, not a cluster of bold letters.
        o = off[y:y + ch, x:x + cw]
        d = max(1, int(0.004 * min(sh, sw)) + 1)
        edges = [o[min(d, ch - 1), :], o[max(0, ch - 1 - d), :], o[:, min(d, cw - 1)], o[:, max(0, cw - 1 - d)]]
        if min(float(e.mean()) for e in edges) < 0.85:
            continue
        inside = off[y:y + ch, x:x + cw][comp]
        holes = 1.0 - inside.mean()
        if holes < 0.04 and area < 0.04 * sh * sw:
            continue  # a heavy stroke of display type, not a panel
        reg_lab = lab[y:y + ch, x:x + cw][comp]
        reg_lab = reg_lab[inside > 0]
        centre = np.median(reg_lab, axis=0)
        close = np.linalg.norm(reg_lab - centre, axis=1) < 20
        if close.mean() < 0.6:
            continue  # textured: a photo, not a panel
        reg_bgr = small[y:y + ch, x:x + cw][comp][inside > 0]
        colour = tuple(int(v) for v in np.median(reg_bgr[close], axis=0))
        X0, Y0 = int(x / sc), int(y / sc)
        X1, Y1 = int(round((x + cw) / sc)), int(round((y + ch) / sc))
        X0, Y0, X1, Y1 = _snap_edges(img, (X0, Y0, X1, Y1), colour)
        out.append(Region("panel", (X0, Y0, X1, Y1), colour))
    return out


def _snap_edges(img, box, colour):
    """Grow or shrink a panel's box to where its colour actually stops."""
    x0, y0, x1, y1 = box
    h, w = img.shape[:2]
    lab = _lab_img(img)
    target = _lab_img(np.uint8([[colour]]))[0, 0]
    inside = np.linalg.norm(lab - target, axis=2) < 22

    def frac_col(x):
        return inside[y0:y1, x].mean() if 0 <= x < w else 0

    def frac_row(y):
        return inside[y, x0:x1].mean() if 0 <= y < h else 0

    for _ in range(12):
        changed = False
        if x0 > 0 and frac_col(x0 - 1) > 0.5:
            x0 -= 1; changed = True
        elif frac_col(x0) < 0.5 and x0 < x1 - 2:
            x0 += 1; changed = True
        if x1 < w and frac_col(x1) > 0.5:
            x1 += 1; changed = True
        elif frac_col(x1 - 1) < 0.5 and x1 > x0 + 2:
            x1 -= 1; changed = True
        if y0 > 0 and frac_row(y0 - 1) > 0.5:
            y0 -= 1; changed = True
        elif frac_row(y0) < 0.5 and y0 < y1 - 2:
            y0 += 1; changed = True
        if y1 < h and frac_row(y1) > 0.5:
            y1 += 1; changed = True
        elif frac_row(y1 - 1) < 0.5 and y1 > y0 + 2:
            y1 -= 1; changed = True
        if not changed:
            break
    return x0, y0, x1, y1


def background(img: np.ndarray, paper, pans: Sequence[Region]) -> np.ndarray:
    bg = np.empty_like(img)
    bg[:] = paper
    for p in pans:
        x0, y0, x1, y1 = p.box
        bg[y0:y1, x0:x1] = p.colour
    return bg


def ink_map(img: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """Distance from the expected background, in Lab units."""
    return np.linalg.norm(_lab_img(img) - _lab_img(bg), axis=2)


def text_mask(shape, lines, grow: float = 0.18) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    for l in lines:
        for w in l.words:
            x0, y0, x1, y1 = w.box
            g = grow * (y1 - y0)
            cv2.rectangle(m, (int(x0 - g), int(y0 - g)), (int(np.ceil(x1 + g)), int(np.ceil(y1 + g))), 255, -1)
    return m > 0


def leftovers(img: np.ndarray, ink: np.ndarray, covered: np.ndarray, thresh: float = 30) -> List[Tuple]:
    """Connected components of ink nothing else explains: (stats, mask-in-box)."""
    mask = ((ink > thresh) & ~covered).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 12:
            continue
        out.append((x, y, w, h, area, labels[y:y + h, x:x + w] == i))
    return out


def outline(comp, img_shape) -> Optional[Tuple[str, float]]:
    """Is this component a thin closed outline (ellipse or rectangle)? Returns (shape, stroke px)."""
    x, y, w, h, area, m = comp
    if w < 20 or h < 12 or area / float(w * h) > 0.3:
        return None
    m8 = m.astype(np.uint8)
    contours, hier = cv2.findContours(m8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return None
    holes = [c for c, hh in zip(contours, hier[0]) if hh[3] >= 0]
    if not holes or max(cv2.contourArea(c) for c in holes) < 0.45 * w * h:
        return None
    stroke = area / max(1.0, cv2.arcLength(max(contours, key=cv2.contourArea), True))
    test = np.zeros_like(m8)
    cv2.ellipse(test, ((w / 2, h / 2), (w - stroke, h - stroke), 0), 1, max(1, int(round(stroke))))
    inter = (test & m8).sum()
    if inter / max(1, m8.sum()) > 0.6:
        return "ellipse", stroke
    return "rect", stroke


def classify(img: np.ndarray, bg: np.ndarray, box, mask: np.ndarray) -> str:
    x0, y0, x1, y1 = box
    region = img[y0:y1, x0:x1]
    fill = mask.mean()
    L = _lab_img(region)[..., 0][mask]
    if fill > 0.55 and L.std() > 22 and (x1 - x0) * (y1 - y0) > 2500:
        return "photo"
    return "mark"


def regions(img: np.ndarray, lines, rule_mask: np.ndarray, paper, pans: Optional[Sequence[Region]] = None,
            body_px: float = 12.0) -> List[Region]:
    """Everything left over once text, rules and panels are accounted for."""
    pans = list(pans if pans is not None else panels(img, paper))
    bg = background(img, paper, pans)
    ink = ink_map(img, bg)
    covered = text_mask(img.shape, lines) | (cv2.dilate(rule_mask, np.ones((5, 5), np.uint8)) > 0)
    for p in pans:  # panel edges are antialiased, not art
        x0, y0, x1, y1 = p.box
        edge = np.zeros(img.shape[:2], np.uint8)
        cv2.rectangle(edge, (x0, y0), (x1 - 1, y1 - 1), 1, 3)
        covered |= edge > 0
    comps = leftovers(img, ink, covered)
    out: List[Region] = list(pans)
    rest = []
    for c in comps:
        o = outline(c, img.shape)
        if o:
            x, y, w, h, area, m = c
            colour = tuple(int(v) for v in np.median(img[y:y + h, x:x + w][m], axis=0))
            r = Region("outline", (x, y, x + w, y + h), colour, radius="ellipse" if o[0] == "ellipse" else None)
            r.notes.append(f"stroke {o[1]:.1f}px")
            out.append(r)
        else:
            rest.append(c)
    # Group what is left into marks: nearby pieces belong together.
    g = max(3, int(0.6 * body_px))
    canvas = np.zeros(img.shape[:2], np.uint8)
    for x, y, w, h, area, m in rest:
        canvas[y:y + h, x:x + w][m] = 1
    grown = cv2.dilate(canvas, np.ones((g, g), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(grown, 8)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        m = (labels[y:y + h, x:x + w] == i) & (canvas[y:y + h, x:x + w] > 0)
        if m.sum() < 30 or max(w, h) < 6:
            continue
        box = (int(x), int(y), int(x + w), int(y + h))
        kind = classify(img, bg, box, m)
        colour = tuple(int(v) for v in np.median(img[y:y + h, x:x + w][m], axis=0))
        out.append(Region(kind, box, colour, mask=m))
    return out


def write_assets(img: np.ndarray, regs: Sequence[Region], out_dir, bg: Optional[np.ndarray] = None) -> dict:
    """Photos as JPEG crops; marks as PNG with alpha from their distance to the background."""
    from pathlib import Path

    out_dir = Path(out_dir)
    names = {}
    for i, r in enumerate(regs):
        x0, y0, x1, y1 = r.box
        crop = img[y0:y1, x0:x1]
        if r.kind == "photo":
            name = f"photo-{i + 1:02d}.jpg"
            cv2.imwrite(str(out_dir / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            names[i] = name
        elif r.kind == "mark":
            name = f"mark-{i + 1:02d}.png"
            back = bg[y0:y1, x0:x1] if bg is not None else np.full_like(crop, 255)
            if r.fill is not None and r.mask is not None:
                # Letters read out of this mark (holes, or a tint on the shape): paint
                # them with the shape's own colour, and the type renders on top.
                body = r.mask & ~cv2.dilate(r.fill.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
                paint = crop[body if body.any() else r.mask]
                crop = crop.copy()
                crop[r.fill] = np.median(paint, axis=0).astype(crop.dtype)
                r.mask = r.mask | r.fill
            d = ink_map(crop, back)
            alpha = np.clip((d - 8) / 60.0, 0, 1)
            if r.mask is not None:
                keep = cv2.dilate(r.mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                alpha = alpha * keep
            # Un-mix the colour from the background where the mark is partly transparent.
            a = np.maximum(alpha, 1e-3)[..., None]
            col = np.clip((crop.astype(np.float32) - (1 - a) * back.astype(np.float32)) / a, 0, 255)
            rgba = np.dstack([col.astype(np.uint8), (alpha * 255).astype(np.uint8)])
            cv2.imwrite(str(out_dir / name), rgba)
            names[i] = name
    return names
