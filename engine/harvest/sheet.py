"""Find the printed sheet in a reference and give it a paper size."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

# Portrait width / height for formats worth snapping to, with a size in mm.
FORMATS = [
    ("A4", 210 / 297, (210.0, 297.0)),
    ("Letter", 8.5 / 11, (215.9, 279.4)),
    ("Square", 1.0, (210.0, 210.0)),
    ("4:5", 0.8, (200.0, 250.0)),
    ("3:4", 0.75, (210.0, 280.0)),
    ("2:3", 2 / 3, (200.0, 300.0)),
    ("A6 card", 105 / 148, (105.0, 148.0)),
]
SNAP = 0.025  # snap when the aspect is within 2.5%


@dataclass
class Sheet:
    image: np.ndarray                 # BGR, rectified sheet
    crop: Optional[List[int]]         # [x0, y0, x1, y1] in the source, when axis-aligned
    quad: Optional[List[List[float]]] = None  # source corners when it was warped
    format: str = "Custom"
    width_mm: float = 210.0
    height_mm: float = 297.0
    notes: List[str] = field(default_factory=list)

    @property
    def px_per_mm(self) -> float:
        return self.image.shape[1] / self.width_mm

    def mm(self, px: float) -> float:
        return px / self.px_per_mm


def paper_size(w_px: int, h_px: int) -> Tuple[str, float, float]:
    """Snap the sheet's aspect to a known format, else keep it at 210 mm on the short side."""
    aspect = w_px / h_px
    portrait = aspect <= 1
    a = aspect if portrait else 1 / aspect
    for name, fa, (fw, fh) in FORMATS:
        if abs(a / fa - 1) <= SNAP:
            return (name, fw, fh) if portrait else (f"{name} landscape", fh, fw)
    if portrait:
        return "Custom", 210.0, round(210.0 / aspect, 1)
    return "Custom", round(210.0 * aspect, 1), 210.0


def _order(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def find_sheet(img: np.ndarray, crop: Optional[Sequence[int]] = None) -> Sheet:
    """
    Locate the sheet. A known `crop` wins; otherwise look for a page that
    contrasts with its surround (a receipt on black, a print on a table) and
    warp it square if it was photographed at an angle.
    """
    notes: List[str] = []
    if crop:
        x0, y0, x1, y1 = (int(v) for v in crop)
        sheet_img, used_crop, quad = img[y0:y1, x0:x1].copy(), [x0, y0, x1, y1], None
        notes.append("Sheet crop given.")
    else:
        sheet_img, used_crop, quad = _detect(img, notes)
    name, w_mm, h_mm = paper_size(sheet_img.shape[1], sheet_img.shape[0])
    notes.append(f"Paper: {name}, {w_mm:g} x {h_mm:g} mm.")
    # Snapping changed the proportions slightly: make the pixels agree, so one
    # px-per-mm holds in both directions.
    want_h = int(round(sheet_img.shape[1] * h_mm / w_mm))
    if want_h != sheet_img.shape[0]:
        sheet_img = cv2.resize(sheet_img, (sheet_img.shape[1], want_h), interpolation=cv2.INTER_CUBIC)
        used_crop = None
    return Sheet(sheet_img, used_crop, quad, name, w_mm, h_mm, notes)


def _detect(img: np.ndarray, notes: List[str]):
    h, w = img.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    band = max(3, min(h, w) // 100)
    border = np.concatenate([lab[:band].reshape(-1, 3), lab[-band:].reshape(-1, 3),
                             lab[:, :band].reshape(-1, 3), lab[:, -band:].reshape(-1, 3)])
    surround = np.median(border, axis=0)
    # The surround must be uniform for this to mean anything.
    spread = np.median(np.linalg.norm(border - surround, axis=1))
    dist = np.linalg.norm(lab - surround, axis=2)
    interior = dist[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    if spread > 12 or np.median(interior) < 25:
        notes.append("No contrasting surround; the whole image is the sheet.")
        return img.copy(), [0, 0, w, h], None

    mask = (dist > 25).astype(np.uint8) * 255
    k = max(5, min(h, w) // 60)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img.copy(), [0, 0, w, h], None
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 0.15 * w * h or area > 0.985 * w * h:
        notes.append("No clear sheet edge; the whole image is the sheet.")
        return img.copy(), [0, 0, w, h], None

    hull = cv2.convexHull(c)
    approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
    x, y, cw, ch = cv2.boundingRect(hull)
    if len(approx) == 4:
        q = _order(approx.reshape(4, 2).astype(np.float32))
        angles = []
        for a, b in ((q[0], q[1]), (q[3], q[2])):
            angles.append(np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])))
        skew = max(abs(a) for a in angles)
        rect_fill = area / float(cw * ch)
        if skew > 0.6 or rect_fill < 0.97:
            wt = int(round(max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))))
            ht = int(round(max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))))
            m = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [wt, 0], [wt, ht], [0, ht]]))
            warped = cv2.warpPerspective(img, m, (wt, ht), flags=cv2.INTER_CUBIC)
            notes.append(f"Sheet found and squared up ({skew:.1f} deg skew).")
            return warped, None, q.tolist()
    # Trim a hair so the surround's anti-aliased edge stays out.
    t = max(1, min(cw, ch) // 300)
    notes.append("Sheet found against its surround.")
    return img[y + t:y + ch - t, x + t:x + cw - t].copy(), [x + t, y + t, x + cw - t, y + ch - t], None
