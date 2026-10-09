"""Fast checks for the Phase 0 core: python -m pytest -q"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.fidelity import score  # noqa: E402
from engine.harvester import normalize_typographic_structures, PRIMITIVES_MARKER  # noqa: E402

REF = ROOT / "design-packs" / "minimalist-corporate-invoice" / "assets" / "reference.jpg"


def _png(img):
    return cv2.imencode(".png", img)[1].tobytes()


def test_identical_scores_100():
    ref = REF.read_bytes()
    assert score(ref, ref).score > 99.0


def test_blank_paper_scores_near_zero():
    img = cv2.imdecode(np.frombuffer(REF.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    blank = np.empty_like(img)
    blank[:] = np.median(img.reshape(-1, 3), axis=0).astype(np.uint8)
    assert score(REF.read_bytes(), _png(blank)).score < 5.0


def test_shifted_render_scores_lower_than_identical():
    img = cv2.imdecode(np.frombuffer(REF.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    shrunk = np.full_like(img, 245)
    small = cv2.resize(img, (w // 2, h // 2))
    shrunk[h // 4: h // 4 + small.shape[0], w // 4: w // 4 + small.shape[1]] = small
    assert score(REF.read_bytes(), _png(shrunk)).score < 60.0


def test_normalizer_is_generic_and_idempotent():
    html = "<html><head></head><body><main class='page-sheet'><div>3 26 16</div></main></body></html>"
    out_html, out_css = normalize_typographic_structures(html, ".page-sheet{}")
    assert "date-triptych" in out_html
    assert out_css.count(PRIMITIVES_MARKER) == 1
    again_html, again_css = normalize_typographic_structures(out_html, out_css)
    assert again_css.count(PRIMITIVES_MARKER) == 1
    assert "!important" not in again_css
