"""Run the whole harvest: image in, Rip pack out."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import cv2
import numpy as np

from ..rip import PACKS_DIR, build_pack
from . import art as art_mod
from .build import Harvest, build_rip
from .layout import analyse
from .ocr import read_all, read_patch
from .sheet import find_sheet
from .typeface import Bench, match_blocks

Progress = Callable[[str], None]


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "harvest"


@dataclass
class Result:
    pack_dir: Path
    rip: Dict
    data: Dict
    score: Optional[float] = None
    history: List[Dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    seconds: float = 0.0
    frame_blocks: Dict[str, int] = field(default_factory=dict)
    type_match: float = 0.0  # how alike the chosen faces' letters are to the reference's (0-1)
    live: float = 0.0   # share of the reference's ink rebuilt as live type and shapes (not pasted images)


def harvest(image_path: Path, name: str, out_dir: Optional[Path] = None, pack_id: Optional[str] = None,
            crop: Optional[Sequence[int]] = None, renderer=None, refine_rounds: int = 3,
            progress: Optional[Progress] = None) -> Result:
    from ..render import Renderer

    t0 = time.time()
    say = progress or (lambda m: None)
    pack_id = pack_id or slug(name)
    pack_dir = Path(out_dir) if out_dir else PACKS_DIR / pack_id
    img = load_image(Path(image_path))

    say("Finding the sheet")
    sheet = find_sheet(img, crop)
    say("Finding rules and reading the text")
    rules, rule_mask = art_mod.rules(sheet.image)
    clean = art_mod.strip_rules(sheet.image, rule_mask)
    paper = art_mod.paper_colour(sheet.image)
    pans = art_mod.panels(sheet.image, paper)
    bg = art_mod.background(sheet.image, paper, pans)
    # Type on a panel is read against the panel's colour, as dark on white.
    on_panels = []
    ink_all = art_mod.ink_map(clean, bg)
    for p in pans:
        x0, y0, x1, y1 = p.box
        patch = (255 - np.clip(ink_all[y0:y1, x0:x1] * 3.5, 0, 255)).astype(np.uint8)
        on_panels += read_patch(cv2.copyMakeBorder(patch, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255),
                                x0 - 8, y0 - 8)
    lines = read_all(sheet.image, clean, extra=on_panels)
    lines += recover(clean, lines, rule_mask, bg)
    lines = [l for l in lines if l.conf >= 45]
    blocks = analyse(clean, lines)

    own = renderer is None
    r = Renderer() if own else renderer
    if own:
        r.__enter__()
    try:
        say(f"Matching type for {len(blocks)} text blocks")
        bench = Bench(r._browser)
        try:
            matches = match_blocks(bench, clean, blocks)
        finally:
            bench.close()

        notes = list(sheet.notes)
        # Verify the reading: text whose best rendering still looks unlike the
        # reference (a logotype read as letters, a row of ornaments read as
        # words) is not type we can set. Its pixels go to the art instead.
        body_px = float(np.median([b.size for b in blocks])) if blocks else 12.0
        kept, dropped = [], []
        for bi, b in enumerate(blocks):
            (kept if trusted(b, matches.get(bi), body_px) else dropped).append(bi)
        if dropped:
            notes.append(f"Kept {len(dropped)} unreadable text {'area' if len(dropped) == 1 else 'areas'} as art.")
        blocks = [blocks[i] for i in kept]
        matches = {k: matches[i] for k, i in enumerate(kept) if i in matches}
        text_lines = [r.line for b in blocks for r in b.runs]
        say("Extracting art")
        regions = art_mod.regions(sheet.image, text_lines, rule_mask, paper, pans, body_px)
        say("Looking for type set at an angle")
        from .rotated import find as find_rotated
        import os
        rotated, regions = ([], regions) if os.environ.get("RIP_NO_ROTATED") else \
            find_rotated(sheet.image, regions, bg)
        if rotated:
            notes.append(f"Read {len(rotated)} {'line' if len(rotated) == 1 else 'lines'} of type set at an angle.")
        covered = art_mod.text_mask(sheet.image.shape, text_lines) | (rule_mask > 0)
        for reg in regions:
            x0, y0, x1, y1 = reg.box
            covered[y0:y1, x0:x1] = True
        live = live_share(sheet.image, bg, text_lines, rule_mask, regions)
        x_heights = [r.ink.x_height for b in blocks for r in b.runs if r.ink and r.ink.x_height]
        if x_heights and np.median(x_heights) < 6:
            notes.append("The image is small for its type (x-height under 6 px), so some words may be misread. "
                         "A larger image reads better.")
        plate = art_mod.plate(sheet.image, covered, paper)
        if plate is not None:
            notes.append("The paper is not flat; kept it as a paper image under everything.")
        h = Harvest(sheet, blocks, matches, rules, regions, paper, notes, rotated=rotated)
        say("Writing the pack")
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
        (pack_dir / "assets").mkdir(parents=True)
        cv2.imwrite(str(pack_dir / "assets" / "reference.jpg"), sheet.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        shutil.copyfile(image_path, pack_dir / "assets" / f"source{Path(image_path).suffix.lower()}")
        if not blocks:
            notes.append("No readable type found; the sheet is kept as art.")
        asset_names = art_mod.write_assets(sheet.image, regions, pack_dir / "assets", bg)
        if plate is not None:
            cv2.imwrite(str(pack_dir / "assets" / "paper.jpg"), plate, [cv2.IMWRITE_JPEG_QUALITY, 90])
        rip, data = build_rip(h, pack_id, name, asset_names, paper_image="paper.jpg" if plate is not None else None)
        _write(pack_dir, rip, data)

        result = Result(pack_dir, rip, data, notes=notes, frame_blocks=dict(h.frame_blocks), live=live,
                        type_match=h.type_match)
        if refine_rounds:
            from .refine import refine
            say("Rendering and comparing")
            refine(result, sheet, blocks, r, rounds=refine_rounds, progress=say)
        else:
            from .refine import score_pack
            result.score = score_pack(pack_dir, r)
        result.seconds = time.time() - t0
        rip = result.rip
        rip["harvest"] = {"score": round(result.score, 1) if result.score is not None else None,
                          "live": round(result.live, 3), "type_match": round(result.type_match, 3),
                          "notes": result.notes, "history": result.history,
                          "seconds": round(result.seconds, 1)}
        _write(pack_dir, rip, result.data)
        return result
    finally:
        if own:
            r.__exit__(None, None, None)


def live_share(img, bg, text_lines, rule_mask, regions) -> float:
    """How much of the reference's ink is now live type, rules and shapes rather than pasted pixels."""
    ink = art_mod.ink_map(img, bg) > 30
    total = int(ink.sum())
    if not total:
        return 1.0
    pasted = np.zeros(ink.shape, bool)
    for r in regions:
        if r.kind in ("mark", "photo"):
            x0, y0, x1, y1 = r.box
            if r.mask is not None:
                pasted[y0:y1, x0:x1] |= r.mask
            else:
                pasted[y0:y1, x0:x1] = True
    live = ink & ~pasted
    return float(live.sum()) / total


MAX_SIDE = 3000  # px; phone photos are bigger than type needs, and memory is not free


def load_image(path: Path) -> np.ndarray:
    """Read any PNG/JPEG/WebP as BGR: transparency over white, huge images scaled down."""
    raw = np.fromfile(str(path), np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Could not read {path.name} as an image.")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        a = img[..., 3:4].astype(np.float32) / 255
        img = (img[..., :3].astype(np.float32) * a + 255 * (1 - a)).astype(np.uint8)
    if img.dtype != np.uint8:
        img = cv2.convertScaleAbs(img, alpha=255.0 / max(1, int(img.max())))
    h, w = img.shape[:2]
    if min(h, w) < 64:
        raise ValueError("The image is too small to read (under 64 px on a side).")
    if max(h, w) > MAX_SIDE:
        sc = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (round(w * sc), round(h * sc)), interpolation=cv2.INTER_AREA)
    return img


def trusted(block, match, body_px: float) -> bool:
    """
    Is this reading type we can set? A guessed logotype or a tilted letter read
    sideways looks unlike any face once rendered, or is too short to judge and
    read with little confidence; those stay as art.
    """
    conf = float(np.mean([r.conf for r in block.runs]))
    alnum = sum(c.isalnum() for c in block.text())
    if block.size < 4:
        return False
    if match is None:
        return conf >= (88 if alnum < 3 else 70)
    if alnum < 3 and conf < 88:
        return False
    if match.score < 0.5:
        return False
    if match.score < 0.62 and conf < 80:
        return False
    if os.environ.get("RIP_DEBUG_TRUST") and block.size > 2 * body_px:
        print(f"    trust? {block.text()[:24]!r} size={block.size:.0f} body={body_px:.0f} conf={conf:.0f} score={match.score:.3f}")
    if block.size > 3 * body_px and (conf < 88 or match.score < 0.66):
        return False
    # Very large lettering is usually drawn, not set: only a close match keeps it as type.
    if block.size > 5 * body_px and match.score < 0.88 and conf < 93:
        return False
    return True


def recover(img: np.ndarray, lines, rule_mask: np.ndarray, bg: np.ndarray) -> list:
    """
    Second look at ink the page readers skipped: lone figures in table cells,
    words inside a logo's outline. Each leftover patch the size of type is
    read on its own; whatever reads confidently becomes text.
    """
    from .ocr import GOOD, read_lines

    def ocr_good(t):
        return bool(GOOD.search(t))

    if not lines:
        return []
    word_h = float(np.median([w.box[3] - w.box[1] for l in lines for w in l.words]))
    ink = art_mod.ink_map(img, bg)
    covered = art_mod.text_mask(img.shape, lines) | (cv2.dilate(rule_mask, np.ones((5, 5), np.uint8)) > 0)
    comps = [c for c in art_mod.leftovers(img, ink, covered) if not art_mod.outline(c, img.shape)]
    canvas = np.zeros(img.shape[:2], np.uint8)
    for x, y, w, h, area, m in comps:
        canvas[y:y + h, x:x + w][m] = 1
    g = max(3, int(0.5 * word_h))
    grown = cv2.dilate(canvas, np.ones((max(1, g // 2), g), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(grown, 8)
    found = []
    H, W = img.shape[:2]
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (0.35 * word_h <= h <= 4.5 * word_h) or w > W * 0.8:
            continue
        pad = int(0.6 * word_h) + 2
        X0, Y0, X1, Y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
        own = (labels[Y0:Y1, X0:X1] == i) & (canvas[Y0:Y1, X0:X1] > 0)
        keep = cv2.dilate(own.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        # Read the patch as dark-on-white whatever its colours (type knocked out
        # of a red bar reads like any other).
        dist = ink[Y0:Y1, X0:X1] * keep
        crop = (255 - np.clip(dist * 3.5, 0, 255)).astype(np.uint8)
        if h > 1.7 * word_h:
            psm = 6
        elif w < 1.4 * h:
            psm = 10
        else:
            psm = 7
        try:
            got = read_lines(crop, psm=psm, raw=(psm == 10))
        except Exception:
            continue
        for l in got:
            min_conf = 60 if psm == 10 else 75
            if psm == 10:
                for wd in l.words:  # a lone figure one reads as a bar
                    if wd.text in ("|", "l", "I") and 0.5 * word_h <= h <= 1.3 * word_h:
                        wd.text = "1"
            l.words = [wd for wd in l.words if wd.conf >= min_conf and ocr_good(wd.text)]
            if not l.words:
                continue
            for wd in l.words:
                wd.box = (wd.box[0] + X0, wd.box[1] + Y0, wd.box[2] + X0, wd.box[3] + Y0)
            l.box = (min(wd.box[0] for wd in l.words), min(wd.box[1] for wd in l.words),
                     max(wd.box[2] for wd in l.words), max(wd.box[3] for wd in l.words))
            l.baseline += Y0
            found.append(l)
    return found


def _write(pack_dir: Path, rip: Dict, data: Dict) -> None:
    for name, obj in (("default-data.json", data), ("rip.json", rip)):
        tmp = pack_dir / f".{name}.tmp"
        tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(pack_dir / name)
    build_pack(pack_dir)
