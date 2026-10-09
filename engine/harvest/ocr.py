"""Words and lines from tesseract's hOCR, in sheet pixels."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

Box = Tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class Word:
    text: str
    box: Box
    conf: float


@dataclass
class Line:
    words: List[Word]
    box: Box
    baseline: float          # y of the baseline at the line's left edge, sheet px
    slope: float             # baseline slope (dy/dx)
    x_size: float            # tesseract's text-size estimate, px
    ascenders: float
    descenders: float
    block: str = ""
    par: str = ""
    angle: int = 0           # 0, or 90/270 for text read after rotating the sheet

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def conf(self) -> float:
        return float(np.mean([w.conf for w in self.words])) if self.words else 0.0


def _title(attr: str) -> Dict[str, List[str]]:
    out = {}
    for part in attr.split(";"):
        bits = part.strip().split()
        if bits:
            out[bits[0]] = bits[1:]
    return out


class _HOCR(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines: List[Dict] = []
        self.stack: List[Tuple[str, Optional[Dict]]] = []
        self.block = self.par = ""
        self.word: Optional[Dict] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        info = None
        if cls == "ocr_carea":
            self.block = a.get("id", "")
        elif cls == "ocr_par":
            self.par = a.get("id", "")
        elif cls in ("ocr_line", "ocr_caption", "ocr_textfloat", "ocr_header"):
            info = {"title": _title(a.get("title", "")), "words": [], "block": self.block, "par": self.par}
            self.lines.append(info)
        elif cls == "ocrx_word":
            self.word = {"title": _title(a.get("title", "")), "text": ""}
            info = self.word
        self.stack.append((tag, info))

    def handle_endtag(self, tag):
        while self.stack:
            t, info = self.stack.pop()
            if info is not None and info is self.word:
                if self.lines:
                    self.lines[-1]["words"].append(self.word)
                self.word = None
            if t == tag:
                break

    def handle_data(self, data):
        if self.word is not None:
            self.word["text"] += data


def tesseract(gray: np.ndarray, psm: int = 3) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.png"
        cv2.imwrite(str(src), gray)
        out = Path(tmp) / "out"
        subprocess.run(["tesseract", str(src), str(out), "--psm", str(psm), "-l", "eng",
                        "-c", "preserve_interword_spaces=1", "hocr"],
                       check=True, capture_output=True)
        return (Path(tmp) / "out.hocr").read_text(encoding="utf-8")


def _read_scale(img: np.ndarray) -> float:
    """Tesseract reads best with letters around 20-40 px tall; scale small images up."""
    long_side = max(img.shape[:2])
    return float(np.clip(2600 / long_side, 1.0, 6.0))


GOOD = re.compile(r"[A-Za-z0-9€$£%&@]")


def _keep(word: Word, line_conf: float) -> bool:
    t = word.text
    if not GOOD.search(t):
        return False
    if word.conf >= 55:
        return True
    letters = sum(c.isalnum() for c in t)
    return word.conf >= 30 and letters >= 3 and letters / len(t) >= 0.7 and line_conf >= 55


def read_lines(img: np.ndarray, psm: int = 3, angle: int = 0, raw: bool = False) -> List[Line]:
    """OCR the (already rectified) sheet. Coordinates come back in sheet pixels."""
    s = _read_scale(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    big = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1 else gray
    parser = _HOCR()
    parser.feed(tesseract(big, psm))
    lines: List[Line] = []
    for found in parser.lines:
        t = found["title"]
        if "bbox" not in t:
            continue
        x0, y0, x1, y1 = (float(v) / s for v in t["bbox"])
        words = []
        for w in found["words"]:
            text = w["text"].strip()
            if not text or "bbox" not in w["title"]:
                continue
            wb = tuple(float(v) / s for v in w["title"]["bbox"])
            conf = float(w["title"].get("x_wconf", ["0"])[0])
            words.append(Word(text, wb, conf))
        if not words:
            continue
        line_conf = float(np.mean([w.conf for w in words]))
        if not raw:
            words = [w for w in words if _keep(w, line_conf)]
        if not words:
            continue
        slope, off = (float(v) for v in t.get("baseline", ["0", "0"]))
        # hOCR baseline: y = slope * (x - x0) + off, measured from the bbox bottom.
        baseline = y1 + off / s
        lines.append(Line(
            words=words,
            box=(min(w.box[0] for w in words), min(w.box[1] for w in words),
                 max(w.box[2] for w in words), max(w.box[3] for w in words)),
            baseline=baseline, slope=slope,
            x_size=float(t.get("x_size", ["0"])[0]) / s,
            ascenders=float(t.get("x_ascenders", ["0"])[0]) / s,
            descenders=float(t.get("x_descenders", ["0"])[0]) / s,
            block=found["block"], par=found["par"], angle=angle,
        ))
    return lines


def _overlap(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter / small if small > 0 else 0.0


def read_all(img: np.ndarray, clean: Optional[np.ndarray] = None, extra: Optional[List[Line]] = None) -> List[Line]:
    """
    Several readings, merged. Page segmentation (psm 3) reads paragraphs well
    but drops isolated words in tables and posters; sparse mode (psm 11) finds
    those; a copy with the rules painted out helps inside tables but can upset
    display type. Lines are taken best first (confidence x length) and later
    readings only add words nothing better has claimed.
    """
    passes = [read_lines(img, psm=3)]
    if clean is not None:
        passes.append(read_lines(clean, psm=3))
    passes.append(read_lines(clean if clean is not None else img, psm=11))
    cands = [l for p in passes for l in p] + list(extra or [])
    cands.sort(key=lambda l: -(l.conf * len(l.text.replace(" ", ""))))
    taken: List[Box] = []
    out: List[Line] = []
    for line in cands:
        new = [w for w in line.words if all(_overlap(w.box, b) < 0.3 for b in taken)]
        if not new:
            continue
        if len(new) < len(line.words):
            new = [w for w in new if w.conf >= 70]
            if not new:
                continue
            line.words = new
            line.box = (min(w.box[0] for w in new), min(w.box[1] for w in new),
                        max(w.box[2] for w in new), max(w.box[3] for w in new))
        out.append(line)
        taken.extend(w.box for w in new)
    out.sort(key=lambda l: (l.box[1], l.box[0]))
    return out


def read_patch(gray: np.ndarray, x0: int, y0: int, psm: int = 6) -> List[Line]:
    """Read a dark-on-white patch cut from the sheet at (x0, y0); boxes come back in sheet pixels."""
    out = read_lines(gray, psm=psm)
    for l in out:
        for w in l.words:
            w.box = (w.box[0] + x0, w.box[1] + y0, w.box[2] + x0, w.box[3] + y0)
        l.box = (l.box[0] + x0, l.box[1] + y0, l.box[2] + x0, l.box[3] + y0)
        l.baseline += y0
    return out
