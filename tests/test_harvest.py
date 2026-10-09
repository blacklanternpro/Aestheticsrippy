"""
The harvester, checked against a sheet whose answer we know: render a Rip
pack to an image, rip the image, and compare what comes back with what went in.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("playwright.sync_api")

from engine.harvest import art, layout  # noqa: E402
from engine.harvest.build import colour_tokens  # noqa: E402
from engine.harvest.ocr import Line, Word  # noqa: E402
from engine.harvest.refine import _directions  # noqa: E402
from engine.harvest.sheet import paper_size  # noqa: E402

KNOWN = {
    "rip": 1, "id": "known", "name": "Known", "page": {"width_mm": 148, "height_mm": 210, "paper": "paper", "ink": "ink"},
    "tokens": {"paper": "#f4f1ea", "ink": "#1a1a1a", "accent": "#d0342c"},
    "styles": {
        "display": {"font": "Archivo", "weight": 800, "stretch": 75, "size": 44, "leading": 0.9, "color": "ink"},
        "body": {"font": "Inter", "weight": 400, "size": 10, "leading": 1.35, "color": "ink"},
        "tag": {"font": "Inter", "weight": 700, "size": 12, "tracking": 0.08, "color": "paper", "case": "upper"},
        "mono": {"font": "Courier Prime", "weight": 400, "size": 9, "leading": 1.3, "color": "ink"},
    },
    "frames": [
        {"id": "panel", "type": "box", "x": 12, "y": 12, "w": 46, "h": 11, "fill": "accent"},
        {"id": "tag", "type": "text", "style": "tag", "bind": "tag", "x": 15, "y": 14.5, "z": 2},
        {"id": "title", "type": "text", "style": "display", "bind": "title", "x": 12, "y": 32, "w": 124},
        {"id": "rule", "type": "rule", "x": 12, "y": 82, "w": 124, "weight": 1},
        {"id": "body", "type": "text", "style": "body", "bind": "body", "x": 12, "y": 90, "w": 84},
        {"id": "note", "type": "text", "style": "mono", "bind": "note", "x": 12, "y": 180, "w": 124},
    ],
}
DATA = {
    "tag": "Issue 04",
    "title": "Field Notes\nfrom the Coast",
    "body": ("Morning fog lifts off the harbour by nine. The ferry runs twice a day in winter, "
             "and the bakery by the pier sells out of rye before the second crossing. Bring a "
             "coat; the wind does not care what the forecast said."),
    "note": "Printed on uncoated stock, 2026.",
}


@pytest.fixture(scope="module")
def ripped(tmp_path_factory):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer
    from engine.rip import loader_html

    work = tmp_path_factory.mktemp("known")
    page = work / "known.html"
    page.write_text(loader_html(KNOWN, DATA, work, [work]), encoding="utf-8")
    with Renderer() as r:
        png = r.render_file(page, pdf=False).png
        (work / "known.png").write_bytes(png)
        res = harvest(work / "known.png", "Known", out_dir=work / "pack", renderer=r, refine_rounds=2)
    return res


def test_rip_scores_well(ripped):
    assert ripped.score >= 80, ripped.history


def test_text_comes_back(ripped):
    text = " ".join(ripped.data.values()).lower()
    for word in ("field notes", "harbour", "bakery", "forecast", "issue 04", "uncoated"):
        assert word in text, (word, text)


def test_type_is_recognised(ripped):
    rip, data = ripped.rip, ripped.data
    style_of = {f["bind"]: rip["styles"][f["style"]] for f in rip["frames"] if f.get("type") == "text"}
    by_text = {v.lower(): style_of[k] for k, v in data.items()}
    title = next(s for t, s in by_text.items() if "field notes" in t)
    body = next(s for t, s in by_text.items() if "harbour" in t)
    note = next(s for t, s in by_text.items() if "uncoated" in t)
    assert title["font"] in ("Archivo", "Archivo Black", "Oswald") and title["weight"] >= 600
    assert body["font"] in ("Inter", "Inter Tight", "Arimo")
    # The A5 sheet snaps to A4 proportions, so sizes scale; their ratio must hold.
    assert abs(body["size"] / title["size"] - 10 / 44) < 0.03
    assert note["font"] in ("Courier Prime", "Space Mono", "JetBrains Mono")


def test_art_comes_back(ripped):
    frames = ripped.rip["frames"]
    panels = [f for f in frames if f.get("type") == "box" and f.get("fill")]
    assert any(abs(int(f["fill"][1:3], 16) - 0xd0) < 30 and int(f["fill"][3:5], 16) < 90 for f in panels), panels
    assert any(f.get("type") == "rule" for f in frames)
    # The paragraph wraps as a paragraph, not as forced lines.
    body_key = next(k for k, v in ripped.data.items() if "harbour" in v)
    assert "\n" not in ripped.data[body_key]


def test_paper_sizes_snap():
    assert paper_size(1000, 1414)[0] == "A4"
    assert paper_size(1414, 1000)[0] == "A4 landscape"
    assert paper_size(1000, 1000)[0] == "Square"
    assert paper_size(1000, 1900)[0] == "Custom"


def _run(text, x0, y, w_char=6.0, h=10.0):
    words, x = [], x0
    for t in text.split():
        words.append(Word(t, (x, y - h, x + w_char * len(t), y), 95))
        x += w_char * len(t) + w_char
    line = Line(words, words[0].box[:2] + words[-1].box[2:], y, 0, h, 2, 2)
    run = layout.Run(words, line)
    run.ink = layout.Ink(y, 5.0, 7.0, "mixed", (20, 20, 20), words[0].box[0], words[-1].box[2], y - 7, y + 2)
    return run


def test_breaks_tell_wraps_from_forced_lines():
    para = layout.Block([_run("the quick brown fox jumps over", 0, 20),
                         _run("the lazy dog and keeps on running", 0, 34),
                         _run("home.", 0, 48)])
    para.align = layout.alignment(para)
    assert layout.breaks(para) == [False, False]
    address = layout.Block([_run("Name Surname", 0, 20), _run("00 Street Name,", 0, 34), _run("City", 0, 48)])
    address.align = layout.alignment(address)
    assert layout.breaks(address) == [True, True]


def test_small_type_joins_its_darker_ink():
    tokens, names = colour_tokens((250, 250, 250), [(20, 20, 20), (70, 70, 70), (40, 60, 200)],
                                  [False, True, False])
    assert names[0] == names[1] == "ink"
    assert names[2] == "accent"


def test_diagnostic_colours_are_distinct():
    d = _directions(40)
    cos = d @ d.T - np.eye(len(d)) * 2
    assert cos.max() < 0.999


def test_paper_colour_ignores_big_type():
    img = np.full((400, 300, 3), 235, np.uint8)
    img[60:340, 40:260] = 30  # a huge dark letterform in the middle
    assert art.paper_colour(img) == (235, 235, 235)
