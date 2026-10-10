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
    from engine.typecase import family
    # With 167 families the exact face may lose to a near twin; the kind of face must be right.
    assert family(title["font"])["category"] in ("condensed", "grotesque") and title["weight"] >= 600
    assert title.get("stretch", 100) <= 90 or family(title["font"])["category"] == "condensed"
    assert family(body["font"])["category"] in ("neo-grotesque", "grotesque", "geometric")
    # The A5 sheet snaps to A4 proportions, so sizes scale; their ratio must hold.
    assert abs(body["size"] / title["size"] - 10 / 44) < 0.03
    assert family(note["font"])["category"] in ("mono", "typewriter")


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


# ------------------------------------------------------------ lists, angles, posters

KNOWN2 = {
    "rip": 1, "id": "known2", "name": "Known 2", "page": {"width_mm": 148, "height_mm": 210, "paper": "paper", "ink": "ink"},
    "tokens": {"paper": "#ffffff", "ink": "#111111"},
    "styles": {
        "row": {"font": "Inter", "weight": 400, "size": 11, "leading": 1.2, "color": "ink"},
        "poster": {"font": "Archivo", "weight": 800, "size": 30, "leading": 1.0, "color": "ink", "case": "upper"},
        "angled": {"font": "Inter", "weight": 600, "size": 16, "leading": 1.0, "color": "ink"},
        "head": {"font": "Inter", "weight": 700, "size": 8, "tracking": 0.12, "color": "ink", "case": "upper"},
    },
    "frames": [
        {"id": "p1", "type": "text", "style": "poster", "bind": "p1", "x": 20, "y": 14, "w": 108,
         "with": {"align": "center", "wrap": "nowrap"}},
        {"id": "p2", "type": "text", "style": "poster", "bind": "p2", "x": 20, "y": 27, "w": 108,
         "with": {"align": "center", "wrap": "nowrap", "tracking": 0.32}},
        {"id": "h1", "type": "text", "style": "head", "bind": "h1", "x": 16, "y": 53},
        {"id": "h2", "type": "text", "style": "head", "bind": "h2", "x": 96, "y": 53, "w": 36, "with": {"align": "right"}},
        {"id": "rows", "type": "repeat", "bind": "rows", "x": 16, "y": 60, "gap": 4, "item": {
            "type": "row", "cols": [80, 36], "children": [
                {"type": "text", "style": "row", "bind": ".item"},
                {"type": "text", "style": "row", "bind": ".price", "with": {"align": "right"}}]}},
        {"id": "tilt", "type": "text", "style": "angled", "bind": "tilt", "x": 40, "y": 160, "w": 80,
         "rotate": -30, "with": {"wrap": "nowrap"}},
    ],
}
DATA2 = {
    "p1": "Tom of England", "p2": "Ivan Berko", "h1": "Item", "h2": "Price",
    "rows": [{"item": "Oak dining table", "price": "1,200"}, {"item": "Linen armchair", "price": "950"},
             {"item": "Walnut shelving unit", "price": "1,100"}, {"item": "Brass floor lamp", "price": "650"}],
    "tilt": "SEASON CLOSING SALE",
}


@pytest.fixture(scope="module")
def ripped2(tmp_path_factory):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer
    from engine.rip import loader_html

    work = tmp_path_factory.mktemp("known2")
    page = work / "known2.html"
    page.write_text(loader_html(KNOWN2, DATA2, work, [work]), encoding="utf-8")
    with Renderer() as r:
        (work / "known2.png").write_bytes(r.render_file(page, pdf=False).png)
        return harvest(work / "known2.png", "Known 2", out_dir=work / "pack", renderer=r, refine_rounds=1)


def test_rows_become_a_list(ripped2):
    lists = [v for v in ripped2.data.values() if isinstance(v, list)]
    assert lists, ripped2.data
    rows = lists[0]
    assert len(rows) == 4
    assert [list(r.values())[0] for r in rows][:2] == ["Oak dining table", "Linen armchair"]
    rep = next(f for f in ripped2.rip["frames"] if f.get("type") == "repeat")
    cells = [c for c in rep["item"]["children"] if c.get("type") == "text"]
    assert cells[-1]["with"].get("align") == "right"


def test_list_header_rides_on_the_repeat(ripped2):
    rep = next(f for f in ripped2.rip["frames"] if f.get("type") == "repeat")
    assert "header" in rep, rep
    cells = [c for c in rep["header"]["children"] if c.get("type") == "text"]
    titles = [ripped2.data[c["bind"].split(".")[0]][c["bind"].split(".")[1]] for c in cells]
    assert [t.upper() for t in titles] == ["ITEM", "PRICE"]
    assert cells[-1]["with"].get("align") == "right"
    loose = [ripped2.data[f["bind"]] for f in ripped2.rip["frames"]
             if f.get("type") == "text" and isinstance(ripped2.data.get(f["bind"]), str)]
    assert not any(t.upper() in ("ITEM", "PRICE") for t in loose), loose


def test_angled_type_is_read_and_rotated(ripped2):
    rot = [f for f in ripped2.rip["frames"] if f.get("rotate")]
    assert rot, "no rotated frame"
    texts = {ripped2.data[f["bind"]] for f in rot}
    assert any("CLOSING" in t for t in texts), texts
    assert all(abs(abs(f["rotate"]) - 30) < 4 for f in rot)


def test_forced_width_lines_get_their_own_tracking(ripped2):
    frames = {ripped2.data[f["bind"]].upper(): f for f in ripped2.rip["frames"]
              if f.get("type") == "text" and isinstance(ripped2.data.get(f["bind"]), str)}
    tom = next(f for t, f in frames.items() if "ENGLAND" in t)
    ivan = next(f for t, f in frames.items() if "BERKO" in t)
    assert tom is not ivan
    st = ripped2.rip["styles"]
    track = lambda f: (f.get("with") or {}).get("tracking", st[f["style"]].get("tracking", 0))  # noqa: E731
    assert track(ivan) - track(tom) > 0.15


# ------------------------------------------------------------ list headers

def _cell(text, left, right, baseline, cap=14.0):
    from engine.harvest.layout import Block, Ink, Run
    box = (left, baseline - cap, right, baseline)
    ink = Ink(baseline, None, cap, "cap", (20, 20, 20), left, right, baseline - cap, baseline)
    run = Run([Word(text, box, 95)], Line([Word(text, box, 95)], box, baseline, 0, cap, 0, 0), ink)
    return Block([run], hard=[False])


def _list_sheet(header_rows):
    """Four item/price rows at a 30 px step under whatever header cells are given."""
    blocks, style = [], {}
    for text, l, r, base, st in header_rows:
        style[len(blocks)] = st
        blocks.append(_cell(text, l, r, base))
    for i, (item, price) in enumerate([("OAK TABLE", "1,200"), ("LINEN CHAIR", "950"),
                                       ("WALNUT SHELF", "1,100"), ("BRASS LAMP", "650")]):
        base = 200 + 30 * i
        style[len(blocks)] = "row"
        blocks.append(_cell(item, 100, 100 + 12 * len(item), base))
        style[len(blocks)] = "row"
        blocks.append(_cell(price, 420 - 12 * len(price), 420, base))
    return blocks, style


def test_list_header_in_its_own_style_joins_the_list():
    from engine.harvest.tables import find_tables
    blocks, style = _list_sheet([("ITEM", 100, 150, 160, "head"), ("PRICE", 362, 420, 160, "head")])
    tables = find_tables(blocks, style)
    assert len(tables) == 1
    t = tables[0]
    assert len(t.rows) == 4
    assert [c.text if c else None for c in t.header] == ["ITEM", "PRICE"]
    assert t.header_styles == ["head", "head"]
    assert {0, 1} <= set(t.blocks)


def test_a_title_across_the_columns_is_not_a_header():
    from engine.harvest.tables import find_tables
    blocks, style = _list_sheet([("SPRING PRICE LIST", 140, 380, 160, "head")])
    t = find_tables(blocks, style)[0]
    assert t.header is None and 0 not in t.blocks


def test_a_row_far_above_the_list_is_not_a_header():
    from engine.harvest.tables import find_tables
    blocks, style = _list_sheet([("ITEM", 100, 150, 60, "head"), ("PRICE", 362, 420, 60, "head")])
    t = find_tables(blocks, style)[0]
    assert t.header is None


# ------------------------------------------------------------ mixed angles

def _angled_layer(shape, text, org, angle):
    """Hershey text drawn level from `org`, then turned `angle` degrees clockwise about `org`."""
    import cv2
    layer = np.zeros(shape, np.uint8)
    cv2.putText(layer, text, org, cv2.FONT_HERSHEY_DUPLEX, 1.1, 255, 3, cv2.LINE_AA)
    m = cv2.getRotationMatrix2D(org, -angle, 1.0)
    return cv2.warpAffine(layer, m, (shape[1], shape[0])) > 120


def test_mixed_angles_split_into_families():
    from engine.harvest.rotated import split_angles
    shape = (700, 700)
    down = _angled_layer(shape, "SALT CELLAR", (150, 110), 45) | _angled_layer(shape, "COOTIE CATCHER", (100, 140), 45)
    up = _angled_layer(shape, "ELEMENTARY", (335, 385), -45) | _angled_layer(shape, "FORTUNE TELLER", (360, 435), -45)
    mask = down | up
    fams = split_angles(mask, [45.0, -45.0])
    assert set(fams) == {45.0, -45.0}
    for ang, truth in ((45.0, down), (-45.0, up)):
        got = fams[ang]
        assert (got & truth).sum() / truth.sum() > 0.95, ang
        assert (got & ~truth).sum() / got.sum() < 0.05, ang


KNOWN3 = {
    "rip": 1, "id": "known3", "name": "Known 3", "page": {"width_mm": 148, "height_mm": 148, "paper": "paper", "ink": "ink"},
    "tokens": {"paper": "#ffffff", "ink": "#111111"},
    "styles": {"arm": {"font": "Inter", "weight": 600, "size": 15, "leading": 1.0, "color": "ink", "case": "upper"}},
    "frames": [
        {"id": "l1", "type": "text", "style": "arm", "bind": "l1", "x": 10, "y": 52, "w": 80, "rotate": 40, "with": {"wrap": "nowrap"}},
        {"id": "l2", "type": "text", "style": "arm", "bind": "l2", "x": 4, "y": 60, "w": 80, "rotate": 40, "with": {"wrap": "nowrap"}},
        {"id": "r1", "type": "text", "style": "arm", "bind": "r1", "x": 40, "y": 44, "w": 80, "rotate": -40, "with": {"wrap": "nowrap"}},
        {"id": "r2", "type": "text", "style": "arm", "bind": "r2", "x": 46, "y": 52, "w": 80, "rotate": -40, "with": {"wrap": "nowrap"}},
    ],
}
DATA3 = {"l1": "SALT CELLAR", "l2": "COOTIE CATCHER", "r1": "ELEMENTARY", "r2": "FORTUNE TELLER"}


@pytest.fixture(scope="module")
def ripped3(tmp_path_factory):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer
    from engine.rip import loader_html

    work = tmp_path_factory.mktemp("known3")
    page = work / "known3.html"
    page.write_text(loader_html(KNOWN3, DATA3, work, [work]), encoding="utf-8")
    with Renderer() as r:
        (work / "known3.png").write_bytes(r.render_file(page, pdf=False).png)
        return harvest(work / "known3.png", "Known 3", out_dir=work / "pack", renderer=r, refine_rounds=0)


def test_v_of_angled_type_reads_both_arms(ripped3):
    rot = {ripped3.data[f["bind"]]: f["rotate"] for f in ripped3.rip["frames"] if f.get("rotate")}
    for text, ang in (("SALT CELLAR", 40), ("COOTIE CATCHER", 40), ("ELEMENTARY", -40), ("FORTUNE TELLER", -40)):
        assert text in rot, rot
        assert abs(rot[text] - ang) < 4, (text, rot[text])
    # Nothing of the arms is left as level text or as art.
    level = [ripped3.data[f["bind"]] for f in ripped3.rip["frames"] if f.get("type") == "text" and not f.get("rotate")]
    assert not level, level
    # (The rendered sheet carries a hairline at its bottom edge; only art over the V counts.)
    page_h = ripped3.rip["page"]["height_mm"]
    over_v = [f for f in ripped3.rip["frames"] if f.get("type") == "image" and f["y"] + f["h"] / 2 < 0.8 * page_h]
    assert not over_v, over_v


def test_cabinet_is_complete():
    import json
    cat = json.loads((ROOT / "fonts" / "catalogue.json").read_text())
    assert len(cat["families"]) >= 150
    for fam in cat["families"]:
        for face in fam["faces"]:
            assert (ROOT / "fonts" / face["file"]).exists(), face["file"]
    css = (ROOT / "fonts" / "fonts.css").read_text()
    assert css.count("@font-face") == sum(len(f["faces"]) for f in cat["families"])
