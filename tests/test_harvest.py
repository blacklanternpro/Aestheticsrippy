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
    # Absolute size holds where the cabinet owns the face (the title's face is
    # substituted, which moves nominal points while the pixels match). The
    # rasterizer quantises x-height to whole pixels - ~3% of a 10pt body on
    # this sheet - so the bound prices that floor in and catches gross drift.
    assert abs(body["size"] * 148 / ripped.rip["page"]["width_mm"] / 10 - 1) < 0.05, body
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
    # The titles were set spaced (0.12 em); the spacing survives whatever face they land in.
    st = ripped2.rip["styles"]
    track = [c["with"].get("tracking", st[c["style"]].get("tracking", 0)) for c in cells]
    assert all(t > 0.06 for t in track), track
    loose = [ripped2.data[f["bind"]] for f in ripped2.rip["frames"]
             if f.get("type") == "text" and isinstance(ripped2.data.get(f["bind"]), str)]
    assert not any(t.upper() in ("ITEM", "PRICE") for t in loose), loose


def test_angled_type_is_read_and_rotated(ripped2):
    rot = [f for f in ripped2.rip["frames"] if f.get("rotate")]
    assert rot, "no rotated frame"
    texts = {ripped2.data[f["bind"]] for f in rot}
    assert any("CLOSING" in t for t in texts), texts
    assert all(abs(abs(f["rotate"]) - 30) < 4 for f in rot)


def test_angled_line_set_in_the_sheet_family_stays_in_it(ripped2):
    # Angled lines are benched now; a line the design set in its own text
    # family must not be dragged to a lookalike.
    st = ripped2.rip["styles"]
    rot = [f for f in ripped2.rip["frames"] if f.get("rotate")]
    assert all(st[f["style"]]["font"] == "Inter" for f in rot), [st[f["style"]] for f in rot]


def _rot(text, cap, colour=(90, 90, 220)):
    from engine.harvest.rotated import RotText
    return RotText(text, 90.0, 0.0, 0.0, cap, 10.0 * cap, colour, 90.0)


def test_angled_sets_pool_their_bench_scores():
    from engine.harvest.pipeline import pool_rotated_faces
    rot = [_rot("PANGPANG", 34), _rot("MEDGES", 36), _rot("GPANG", 33),
           _rot("NOTE", 12, colour=(20, 20, 20))]
    scores = {
        0: {"Epilogue|500|": 0.84, "Archivo Narrow|500|": 0.83},     # one row alone picks Epilogue
        1: {"Archivo Narrow|500|": 0.83, "Epilogue|500|": 0.79},
        2: {"Archivo Narrow|500|": 0.85, "Inter Tight|500|": 0.80},  # never shortlisted Epilogue
        3: {"Inter|400|": 0.9},
    }
    out = {tuple(s): win for s, win, _ in pool_rotated_faces(rot, scores, set())}
    assert out[(0, 1, 2)] == "Archivo Narrow|500|"     # the set wins on the pool
    assert out[(3,)] is None      # another colour and size: its own set, and one line alone is no consensus


def test_angled_sets_without_consensus_keep_the_main_face():
    # Small 45-degree labels: every row crowns a different lookalike, and the
    # pool's winner is far below what each row thought of its own pick.
    from engine.harvest.pipeline import pool_rotated_faces
    rot = [_rot("GD4 LLC", 15), _rot("ELEMENTARY", 16), _rot("SALT CELLAR", 16)]
    scores = {0: {"Epilogue|900|": 0.84, "Archivo Narrow|700|": 0.77},
              1: {"Archivo|900|75.0": 0.86, "Archivo Narrow|700|": 0.78},
              2: {"IBM Plex Sans|700|100.0": 0.86, "Archivo Narrow|700|": 0.76}}
    assert pool_rotated_faces(rot, scores, set())[0][1] is None


def test_angled_sets_prefer_the_sheet_family_only_when_nearly_as_good():
    from engine.harvest.pipeline import pool_rotated_faces
    rot = [_rot("PANGPANG", 34), _rot("MEDGES", 35)]
    near = {0: {"Archivo Narrow|500|": 0.820, "Epilogue|500|": 0.815},
            1: {"Archivo Narrow|500|": 0.820, "Epilogue|500|": 0.815}}
    far = {0: {"Archivo Narrow|500|": 0.820, "Epilogue|500|": 0.80},
           1: {"Archivo Narrow|500|": 0.820, "Epilogue|500|": 0.80}}
    assert pool_rotated_faces(rot, near, {"Epilogue"})[0][1] == "Epilogue|500|"
    assert pool_rotated_faces(rot, far, {"Epilogue"})[0][1] == "Archivo Narrow|500|"


def test_a_matched_angled_set_shares_one_size():
    # The two MEDGES rows measure 36-37 px, the PANGPANG rows 32-34: round
    # letters overshoot the cap line. Benched as one set they share the
    # median cap, so the taller word does not mint an 'angled-b'.
    from engine.harvest.build import Harvest, _rotated_frames
    from engine.harvest.sheet import Sheet
    from engine.harvest.typeface import Face
    sheet = Sheet(np.full((1350, 1080, 3), 255, np.uint8), None, width_mm=200.0, height_mm=250.0)
    rot = [_rot("PANGPANG", 33), _rot("MEDGES ALE", 37), _rot("MEDGES", 36.5), _rot("GPANG", 34)]
    for r in rot:
        r.face = Face("Archivo Narrow", 500)
        r.set_cap = 35.0
    lone = _rot("SPINE", 33)        # no set: keeps its own measured cap
    h = Harvest(sheet, [], {}, [], [], (255, 255, 255), [], rotated=rot + [lone])
    styles, data, labels = {}, {}, {}
    frames = _rotated_frames(h, styles, [], {}, data, labels, {"accent": "#e1999a"})
    assert {f["style"] for f in frames[:4]} == {"angled"}, [f["style"] for f in frames]
    assert styles["angled"]["font"] == "Archivo Narrow"
    lone_st = styles[frames[4]["style"]]
    assert lone_st["font"] != "Archivo Narrow" or lone_st["size"] < styles["angled"]["size"]


def test_forced_width_lines_get_their_own_tracking(ripped2):
    frames = {ripped2.data[f["bind"]].upper(): f for f in ripped2.rip["frames"]
              if f.get("type") == "text" and isinstance(ripped2.data.get(f["bind"]), str)}
    tom = next(f for t, f in frames.items() if "ENGLAND" in t)
    ivan = next(f for t, f in frames.items() if "BERKO" in t)
    assert tom is not ivan
    st = ripped2.rip["styles"]
    track = lambda f: (f.get("with") or {}).get("tracking", st[f["style"]].get("tracking", 0))  # noqa: E731
    assert track(ivan) - track(tom) > 0.15


# ------------------------------------------------------------ faces

def _matched(text, size, scores, baseline=100.0):
    """A block of `text` at cap-height-based `size` px with matcher scores {family: score}."""
    from engine.harvest.typeface import Face, Match
    blk = _cell(text, 50, 50 + 7 * len(text), baseline, cap=size * 0.71)
    keys = {f"{fam}|400|": v for fam, v in scores.items()}
    best = max(keys, key=keys.get)
    m = Match(Face(best.split("|")[0], 400), size, 0.0, keys[best], keys)
    return blk, m


def test_figures_follow_the_family_the_words_prove():
    """
    Body text proves its face on long lines; prices a pixel taller (a separate size
    group) score noisily and lean to another face. They carry no evidence and must
    not drag a second family onto the sheet.
    """
    from engine.harvest.build import harmonise
    sheet = [("Luxury Sofa Set with matching cushions", 13.0, {"Grotesk": 0.84, "Narrow": 0.77}),
             ("King Size Bed Frame in solid oak wood", 13.0, {"Grotesk": 0.83, "Narrow": 0.78}),
             ("Terms and conditions apply to every order", 13.5, {"Grotesk": 0.86, "Narrow": 0.76}),
             ("$1,300", 15.5, {"Grotesk": 0.72, "Narrow": 0.79}),
             ("$950", 15.5, {"Grotesk": 0.73, "Narrow": 0.80}),
             ("$650", 15.5, {"Grotesk": 0.74, "Narrow": 0.79}),
             ("$5,720", 15.5, {"Grotesk": 0.69, "Narrow": 0.75})]
    blocks, matches = [], {}
    for i, (t, s, sc) in enumerate(sheet):
        b, m = _matched(t, s, sc, baseline=100 + 30 * i)
        blocks.append(b)
        matches[i] = m
    faces = harmonise(matches, blocks)
    assert {f.family for f in faces.values()} == {"Grotesk"}, {i: f.family for i, f in faces.items()}


def test_noise_alone_does_not_buy_a_second_family():
    """
    Two near-identical faces whose scores trade places block by block: taking the
    better of the two per block gains on noise alone. One size of text is one face.
    """
    from engine.harvest.build import harmonise
    words = ["Luxury Sofa Set", "Dining Table Set", "King Size Bed Frame", "Wardrobe Cabinet",
             "Office Desk and Chair", "Account Name Claudia", "Payment Method Card", "New York City Office"]
    blocks, matches = [], {}
    # Two size groups (measurement noise on small type splits one size): each leans a hair
    # to a different face, with the scores trading places block by block on top.
    for i, t in enumerate(words + words):
        size, lean = (13.0, 0.01) if i < len(words) else (17.0, -0.01)
        d = 0.04 if i % 2 else -0.04
        b, m = _matched(t, size, {"Grotesk": 0.80 + lean + d, "Narrow": 0.80 - lean - d}, baseline=100 + 30 * i)
        blocks.append(b)
        matches[i] = m
    faces = harmonise(matches, blocks)
    assert len({f.family for f in faces.values()}) == 1, {i: f.family for i, f in faces.items()}


def test_one_big_display_line_keeps_its_own_face():
    """A single large headline that clearly fits another face keeps it, among much body text."""
    from engine.harvest.build import harmonise
    words = ["Luxury Sofa Set", "Dining Table Set", "King Size Bed Frame", "Wardrobe Cabinet",
             "Office Desk and Chair", "Account Name Claudia", "Payment Method Card", "New York City Office",
             "Terms and conditions apply", "Payment is due within days", "Thank you for your order"]
    blocks, matches = [], {}
    for i, t in enumerate(words * 4):
        b, m = _matched(t, 13.0, {"Grotesk": 0.82, "Display": 0.76}, baseline=200 + 25 * i)
        blocks.append(b)
        matches[len(matches)] = m
    b, m = _matched("Invoice.", 98.0, {"Grotesk": 0.859, "Display": 0.927}, baseline=150)
    blocks.append(b)
    matches[len(matches)] = m
    faces = harmonise(matches, blocks)
    assert faces[len(blocks) - 1].family == "Display"
    assert {faces[i].family for i in range(len(blocks) - 1)} == {"Grotesk"}


def test_a_real_second_family_still_earns_its_place():
    """Long headings that clearly fit another face keep it."""
    from engine.harvest.build import harmonise
    sheet = [("Luxury Sofa Set with matching cushions", 13.0, {"Grotesk": 0.84, "Serif": 0.60}),
             ("King Size Bed Frame in solid oak wood", 13.0, {"Grotesk": 0.83, "Serif": 0.61}),
             ("The Spring Collection Catalogue", 40.0, {"Grotesk": 0.62, "Serif": 0.90}),
             ("Handmade Furniture Since Nineteen Ten", 40.0, {"Grotesk": 0.63, "Serif": 0.89})]
    blocks, matches = [], {}
    for i, (t, s, sc) in enumerate(sheet):
        b, m = _matched(t, s, sc, baseline=100 + 60 * i)
        blocks.append(b)
        matches[i] = m
    faces = harmonise(matches, blocks)
    assert [faces[i].family for i in range(4)] == ["Grotesk", "Grotesk", "Serif", "Serif"]


# ------------------------------------------------------------ weights on small type

KNOWN5 = {
    "rip": 1, "id": "known5", "name": "Known 5", "page": {"width_mm": 148, "height_mm": 148, "paper": "paper", "ink": "ink"},
    "tokens": {"paper": "#ffffff", "ink": "#111111"},
    "styles": {"label": {"font": "Inter", "weight": 700, "size": 6.5, "leading": 1.3, "color": "ink"},
               "value": {"font": "Inter", "weight": 400, "size": 6.5, "leading": 1.3, "color": "ink"}},
    "frames": [
        {"id": "l1", "type": "text", "style": "label", "bind": "l1", "x": 12, "y": 14},
        {"id": "v1", "type": "text", "style": "value", "bind": "v1", "x": 12, "y": 19, "w": 50},
        {"id": "l2", "type": "text", "style": "label", "bind": "l2", "x": 70, "y": 14},
        {"id": "v2", "type": "text", "style": "value", "bind": "v2", "x": 70, "y": 19, "w": 60},
        {"id": "l3", "type": "text", "style": "label", "bind": "l3", "x": 12, "y": 50},
        {"id": "v3", "type": "text", "style": "value", "bind": "v3", "x": 12, "y": 55, "w": 120},
        {"id": "l4", "type": "text", "style": "label", "bind": "l4", "x": 12, "y": 90},
        {"id": "v4", "type": "text", "style": "value", "bind": "v4", "x": 12, "y": 95, "w": 120},
    ],
}
DATA5 = {"l1": "Billed To:", "v1": "Hannah Morales\nNew York City",
         "l2": "Payment Method:", "v2": "Account No: 123-456-7890\nAccount Name: Claudia Alves",
         "l3": "Terms and Conditions:",
         "v3": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.\nUt posuere velit eu massa placerat fermentum.",
         "l4": "Payment is due within 14 days",
         "v4": "Thank you for choosing our furniture for your home.\nWe hope it serves you for many years."}


@pytest.fixture(scope="module")
def ripped5(tmp_path_factory):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer
    from engine.rip import loader_html

    work = tmp_path_factory.mktemp("known5")
    page = work / "known5.html"
    page.write_text(loader_html(KNOWN5, DATA5, work, [work]), encoding="utf-8")
    with Renderer() as r:
        (work / "known5.png").write_bytes(r.render_file(page, pdf=False).png)
        return harvest(work / "known5.png", "Known 5", out_dir=work / "pack", renderer=r, refine_rounds=0)


def test_bold_labels_stay_bold_on_small_type(ripped5):
    st = ripped5.rip["styles"]
    got = [(ripped5.data[f["bind"]], st[f["style"]]["weight"]) for f in ripped5.rip["frames"] if f.get("type") == "text"]

    def weight_of(text):
        hits = [w for t, w in got if t.startswith(text[:14])]
        assert hits, (text, got)
        return hits[0]
    weight = {t: weight_of(t) for t in [DATA5[k].split("\n")[0] for k in ("l1", "l2", "l3", "l4", "v1", "v2", "v3", "v4")]}
    labels = [DATA5[k] for k in ("l1", "l2", "l3", "l4")]
    values = [DATA5[k].split("\n")[0] for k in ("v1", "v2", "v3", "v4")]
    assert all(weight[t] >= 600 for t in labels), {t: weight[t] for t in labels}
    assert all(weight[t] <= 500 for t in values), {t: weight[t] for t in values}


# ------------------------------------------------------------ print finish

KNOWN6 = {
    "rip": 1, "id": "known6", "name": "Known 6", "page": {"width_mm": 148, "height_mm": 105, "paper": "paper", "ink": "ink"},
    "tokens": {"paper": "#ffffff", "ink": "#111111"},
    "styles": {
        # The letterform is Regular; the design's character is the press: heavy
        # ink gain and a soft edge. Read clean, this look passes for a Bold.
        "display": {"font": "Inter", "weight": 400, "size": 23, "leading": 1.15, "color": "ink", "case": "upper",
                    "finish": {"gain": 0.035, "blur": 0.02}},
        "body": {"font": "Inter", "weight": 400, "size": 9, "leading": 1.4, "color": "ink"},
    },
    "frames": [
        {"id": "h1", "type": "text", "style": "display", "bind": "h1", "x": 12, "y": 14},
        {"id": "h2", "type": "text", "style": "display", "bind": "h2", "x": 12, "y": 26},
        {"id": "p1", "type": "text", "style": "body", "bind": "p1", "x": 12, "y": 52, "w": 120},
    ],
}
DATA6 = {"h1": "OVERPRINT SEASON", "h2": "HEAVY INK DEPARTMENT",
         "p1": ("The proofs came back from the press darker than the comp, strokes swollen "
                "and corners gone round. Nobody minded. The smith reckoned the sheet finally "
                "looked like it had been made by a machine with opinions of its own.")}


@pytest.fixture(scope="module")
def ripped6(tmp_path_factory):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer
    from engine.rip import loader_html

    work = tmp_path_factory.mktemp("known6")
    page = work / "known6.html"
    page.write_text(loader_html(KNOWN6, DATA6, work, [work]), encoding="utf-8")
    with Renderer() as r:
        (work / "known6.png").write_bytes(r.render_file(page, pdf=False).png)
        return harvest(work / "known6.png", "Known 6", out_dir=work / "pack", renderer=r, refine_rounds=0)


def _style_of(res, text):
    for f in res.rip["frames"]:
        if f.get("type") == "text" and str(res.data.get(f.get("bind", ""), "")).startswith(text[:12]):
            return res.rip["styles"][f["style"]]
    raise AssertionError((text, [str(res.data.get(f.get("bind", "")))[:30] for f in res.rip["frames"] if f.get("type") == "text"]))


def test_overinked_type_stays_live_and_regular(ripped6):
    # The headline must come back as live type at the weight underneath the
    # ink, with the gain measured as a finish - not as a Bold, not as art.
    st = _style_of(ripped6, DATA6["h1"])
    assert st["weight"] < 500, st
    fin = st.get("finish")
    assert fin, st
    assert 0.015 <= fin["gain"] <= 0.06, fin


def test_clean_type_earns_no_finish(ripped6):
    st = _style_of(ripped6, DATA6["p1"])
    assert "finish" not in st, st


# ------------------------------------------------------------ curved text

def _circle(cx, cy, r, a0=180, a1=540, step=6):
    import math
    return [[round(cx + r * math.cos(math.radians(a)), 2), round(cy + r * math.sin(math.radians(a)), 2)]
            for a in range(a0, a1 + 1, step)]


KNOWN4 = {
    "rip": 1, "id": "known4", "name": "Known 4", "page": {"width_mm": 148, "height_mm": 148, "paper": "paper", "ink": "ink"},
    "tokens": {"paper": "#ffffff", "ink": "#111111"},
    "styles": {"arc": {"font": "Inter", "weight": 700, "size": 16, "tracking": 0.12, "color": "ink", "case": "upper"},
               "big": {"font": "Inter", "weight": 700, "size": 20, "color": "ink", "case": "upper"}},
    "frames": [
        {"id": "ring", "type": "path", "style": "arc", "bind": "ring", "x": 10, "y": 8, "w": 60, "h": 60,
         "points": _circle(30, 30, 24, 180, 470)},
        {"id": "wave", "type": "path", "style": "arc", "bind": "wave", "x": 20, "y": 85, "w": 100, "h": 50,
         "points": [[round(5 + 90 * t / 60, 2), round(25 + 16 * __import__("math").sin(t / 60 * 6.2832), 2)]
                    for t in range(61)], "offset": 4},
        {"id": "stem", "type": "path", "style": "big", "bind": "stem", "x": 120, "y": 10, "w": 14, "h": 80,
         "points": [[7, 0], [7, 80]], "offset": 6, "pitch": 15, "upright": True},
    ],
}
DATA4 = {"ring": "Last Saturday Dance", "wave": "Fortune Teller", "stem": "Party"}


@pytest.fixture(scope="module")
def ripped4(tmp_path_factory):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer
    from engine.rip import loader_html

    work = tmp_path_factory.mktemp("known4")
    page = work / "known4.html"
    page.write_text(loader_html(KNOWN4, DATA4, work, [work]), encoding="utf-8")
    with Renderer() as r:
        (work / "known4.png").write_bytes(r.render_file(page, pdf=False).png)
        return harvest(work / "known4.png", "Known 4", out_dir=work / "pack", renderer=r, refine_rounds=0)


def test_curved_text_is_read_onto_paths(ripped4):
    paths = {ripped4.data[f["bind"]].upper(): f for f in ripped4.rip["frames"] if f.get("type") == "path"}
    assert set(paths) >= {"LAST SATURDAY DANCE", "FORTUNE TELLER", "PARTY"}, paths.keys()
    stem = paths["PARTY"]
    assert stem.get("upright") and stem.get("pitch"), stem
    # Spaced 15 mm apart on the page (scaled with any paper-size snap).
    scale = ripped4.rip["page"]["width_mm"] / KNOWN4["page"]["width_mm"]
    assert abs(stem["pitch"] / (15 * scale) - 1) < 0.08, stem["pitch"]
    assert not paths["LAST SATURDAY DANCE"].get("pitch")
    # The letters are not also left behind as art or level text.
    page_h = ripped4.rip["page"]["height_mm"]
    art = [f for f in ripped4.rip["frames"] if f.get("type") == "image" and f["y"] + f["h"] / 2 < 0.9 * page_h]
    assert not art, art
    level = [ripped4.data[f["bind"]] for f in ripped4.rip["frames"] if f.get("type") == "text"]
    assert not level, level


# ------------------------------------------------------------ ransom lettering

RANSOM_JITTER = {"FORTUNE": [25, -18, 30, -27, 12, -30, 20], "LAST": [-25, 20, -30, 18]}


def _ransom_page() -> str:
    """Letters strung with hand-placed jitter: along an arc, and down a stem."""
    import math
    spans = []
    for i, (ch, j) in enumerate(zip("FORTUNE", RANSOM_JITTER["FORTUNE"])):
        t = i / 6.0
        x, y = 60 + 360 * t, 240 - 170 * math.sin(t * math.pi)
        tang = math.degrees(math.atan2(-170 * math.pi / 6 * math.cos(t * math.pi), 60))
        spans.append(f'<span style="position:absolute;left:{x}px;top:{y}px;'
                     f'transform:rotate({tang + j:.0f}deg)">{ch}</span>')
    for i, (ch, j) in enumerate(zip("LAST", RANSOM_JITTER["LAST"])):
        spans.append(f'<span style="position:absolute;left:560px;top:{60 + 90 * i}px;'
                     f'transform:rotate({90 + j}deg)">{ch}</span>')
    font = (ROOT / "fonts" / "Inter-var.woff2").resolve()
    return ("<!doctype html><meta charset=\"utf-8\"><style>"
            f"@font-face {{ font-family:'Inter'; src: url('file://{font}'); }}"
            "body { background:#fff; margin:0; width:700px; height:700px; position:relative;"
            " font-family:Inter; font-weight:700; font-size:44px; color:#111; }"
            "</style>" + "".join(spans))


def _vee_page() -> str:
    """Crisp angled words, stacked so their initial letters align into a
    perpendicular column - the geometry that fools neighbour counts, where
    each letter's own shape must name its family."""
    rows = []
    for k, word in enumerate(("EXPEDITE", "ELEGANT", "EASTWARD")):
        x, y = 390 + k * 34, 310 + k * 34
        rows.append(f'<div style="position:absolute;left:{x}px;top:{y}px;'
                    f'transform:rotate(-45deg);transform-origin:left top;'
                    f'letter-spacing:0.30em">{word}</div>')
    for k, word in enumerate(("SATURDAY", "SIDEWAYS", "SOLSTICE")):
        x, y = 310 - k * 34, 310 + k * 34
        rows.append(f'<div style="position:absolute;left:{x}px;top:{y}px;'
                    f'transform:rotate(45deg);transform-origin:right top;'
                    f'text-align:right;width:0;white-space:nowrap;direction:rtl;'
                    f'letter-spacing:0.30em">{word}</div>')
    font = (ROOT / "fonts" / "Inter-var.woff2").resolve()
    para = ('<div style="position:absolute;left:60px;top:580px;width:560px;'
            'font-weight:400;font-size:15px;letter-spacing:0">'
            'The six words above are set on two opposing diagonals, spaced far '
            'enough apart that every letter prints alone. A body paragraph sits '
            'below them so the sheet has an ordinary text size of its own, as '
            'any real specimen would.</div>')
    return ("<!doctype html><meta charset=\"utf-8\"><style>"
            f"@font-face {{ font-family:'Inter'; src: url('file://{font}'); }}"
            "body { background:#fff; margin:0; width:700px; height:700px; position:relative;"
            " font-family:Inter; font-weight:700; font-size:26px; color:#151515; }"
            "</style>" + "".join(rows) + para)


def test_shattered_angled_marks_regroup_for_reading(tmp_path):
    # One region per letter, by construction: no per-region read can touch a
    # single letter, so neighbouring letter marks must regroup into lines.
    import cv2
    import numpy as np
    from engine.harvest import art as A, rotated as R
    from engine.harvest.sheet import find_sheet
    from engine.render import Renderer

    page = tmp_path / "vee.html"
    page.write_text(_vee_page(), encoding="utf-8")
    with Renderer() as r:
        (tmp_path / "vee.png").write_bytes(r.render_file(page, pdf=False).png)
    img = cv2.imread(str(tmp_path / "vee.png"))
    sheet = find_sheet(img)
    paper = A.paper_colour(sheet.image)
    bg = A.background(sheet.image, paper, [])
    ink = (A.ink_map(sheet.image, bg) > 30).astype(np.uint8)
    ink[int(0.70 * ink.shape[0]):] = 0          # the body paragraph is not the subject
    n, lab, st, cen = cv2.connectedComponentsWithStats(ink, 8)
    regions = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < 40:
            continue
        regions.append(A.Region("mark", (int(x), int(y), int(x + w), int(y + h)), (20, 20, 20),
                                mask=lab[y:y + h, x:x + w] == i))
    assert len(regions) >= 30, len(regions)     # genuinely shattered
    found, kept, absorbed = R.find(sheet.image, regions, bg)
    texts = " ".join(t.text for t in found).upper()
    hits = sum(w in texts for w in ("EXPEDITE", "ELEGANT", "EASTWARD", "SATURDAY", "SIDEWAYS", "SOLSTICE"))
    assert hits >= 4, (hits, sorted(t.text for t in found))


def test_stacked_angled_words_keep_their_letters(tmp_path):
    # Spaced angled lettering shatters into one mark per letter, which no
    # per-region read can touch: neighbouring letter marks regroup for
    # reading. Crisp separate letters also starve the family split of
    # word-runs; the glyph atlas names each letter's family, and correct
    # rows the reader doubts are vouched for letter by letter.
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer

    page = tmp_path / "vee.html"
    page.write_text(_vee_page(), encoding="utf-8")
    with Renderer() as r:
        (tmp_path / "vee.png").write_bytes(r.render_file(page, pdf=False).png)
        res = harvest(tmp_path / "vee.png", "Vee", out_dir=tmp_path / "pack",
                      renderer=r, refine_rounds=0)
    texts = " ".join(str(v) for v in res.data.values()).upper()
    hits = sum(w in texts for w in ("EXPEDITE", "ELEGANT", "EASTWARD", "SATURDAY", "SIDEWAYS", "SOLSTICE"))
    assert hits >= 5, (hits, res.data)


RING_JITTER = [8, -14, 10, -6, 12]


def _ring_page(word: str) -> str:
    """Light letters knocked out of a dark band round a counter, clockwise from
    the top, each turned with the ring give or take a hand's jitter."""
    import math
    spans = []
    n = len(word)
    for i, (ch, j) in enumerate(zip(word, RING_JITTER)):
        th = -90 + 360 * i / n                     # degrees, screen-clockwise from the top
        x = 350 + 165 * math.cos(math.radians(th))
        y = 350 + 165 * math.sin(math.radians(th))
        spans.append(f'<span style="position:absolute;left:{x - 22:.0f}px;top:{y - 30:.0f}px;'
                     f'width:44px;text-align:center;line-height:60px;'
                     f'transform:rotate({th + 90 + j:.0f}deg)">{ch}</span>')
    font = (ROOT / "fonts" / "Inter-var.woff2").resolve()
    return ("<!doctype html><meta charset=\"utf-8\"><style>"
            f"@font-face {{ font-family:'Inter'; src: url('file://{font}'); }}"
            "body { background:#fff; margin:0; width:700px; height:700px; position:relative;"
            " font-family:Inter; font-weight:700; font-size:52px; color:#fff; }"
            ".ring { position:absolute; left:120px; top:120px; width:460px; height:460px;"
            " border-radius:50%; border:115px solid #151515; box-sizing:border-box; }"
            "</style><div class=\"ring\"></div>" + "".join(spans))


def test_ring_lettering_reads_round_its_counter(tmp_path):
    # Letters cut out round a counter chain in whatever order the tree breaks
    # the loop; the ring is found from geometry, read clockwise from the top.
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer

    page = tmp_path / "ring.html"
    page.write_text(_ring_page("NIGHT"), encoding="utf-8")
    with Renderer() as r:
        (tmp_path / "ring.png").write_bytes(r.render_file(page, pdf=False).png)
        res = harvest(tmp_path / "ring.png", "Ring", out_dir=tmp_path / "pack",
                      renderer=r, refine_rounds=0)
    paths = [res.data[f["bind"]] for f in res.rip["frames"] if f.get("type") == "path"]
    assert "NIGHT" in paths, paths


def test_wordness_hears_words_not_digit_dodges():
    from engine.harvest.curved import _lexical, _wordness
    assert _wordness("LAST") > _wordness("IAST") > _wordness("1AST") - 1   # sanity of order
    assert _wordness("LAST") > _wordness("1AST")
    assert _wordness("DANCE") > _wordness("DANGE")
    assert _wordness("SATURDAY") > _wordness("YADRUTAS")
    assert _lexical("DANCE") and _lexical("LAST SATURDAY")
    assert not _lexical("D4ZOE") and not _lexical("ADENO")


# ------------------------------------------------ proofreading display type

def test_collinear_slivers_read_as_one_ribbon():
    # Edge-running text gets chopped into overlapping art fragments by the
    # level readers' stray claims; collinear slim marks must be read as ONE
    # ribbon or every fragment yields its own partial.
    from engine.harvest.art import Region
    from engine.harvest.rotated import _ribbons

    def reg(x0, y0, x1, y1):
        m = np.ones((y1 - y0, x1 - x0), bool)
        return Region("mark", (x0, y0, x1, y1), (0, 0, 0), mask=m)

    a, b, c = reg(767, 0, 811, 59), reg(767, 21, 811, 160), reg(766, 240, 812, 400)
    photo = Region("photo", (760, 500, 812, 700), (0, 0, 0),
                   mask=np.ones((200, 52), bool))
    wide = reg(100, 0, 700, 60)   # not slim: a banner, not a ribbon
    out = _ribbons([(a, None), (b, None), (c, None), (photo, None), (wide, None)])
    merged = [r for r, mem in out if mem is not None]
    singles = [r for r, mem in out if mem is None]
    assert len(merged) == 1 and len(singles) == 2, [(r.box, mem is None) for r, mem in out]
    r, mem = [(r, mem) for r, mem in out if mem is not None][0]
    assert r.box == (766, 0, 812, 400)
    assert len(mem) == 3
    assert r.mask.shape == (400, 46)


def test_a_vertical_column_is_one_direction_not_two():
    # Projection skew scans -89..90 and peaks at BOTH ends for a near-vertical
    # line: 90 and -89 are the same direction 1 degree apart, but the dedup
    # compared raw degrees (179 apart) and shipped both. split_angles then
    # deals the column's letters between the twins like a coin flip, and every
    # family read yields Swiss cheese ('MED E A' here, 'GESA' there).
    import cv2
    from engine.harvest.rotated import _adiff, _skew
    img = np.zeros((60, 420), np.uint8)
    for i, w in enumerate(["MEDGES", "ALE", "PANGPANG"]):
        cv2.putText(img, w, (10 + i * 140, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 255, 2)
    col = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE) > 0
    out = _skew(col)
    assert out, "the column's direction was found at all"
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            assert _adiff(a, b) > 10, f"one direction reported twice: {out}"


def test_the_sheet_lexicon_completes_edge_partials(tmp_path):
    # Brand text running along the sheet's edge reads as partials ('IGPANG'),
    # while the SAME word sits perfectly read in the body. A lexicon word
    # that explains the band's letter cells decisively better stands in -
    # but a band the DESIGN truly crops keeps its honest partial.
    import cv2
    from engine.harvest.letters import atlas, cells
    from engine.harvest.rotated import lexicon_pick
    from engine.render import Renderer
    with Renderer() as r:
        full_row = _word_row(tmp_path, r, "PANGPANG", px=48)
        glyphs = atlas(r._browser)
    ink = full_row.astype(np.uint8)
    ys, xs = np.nonzero(ink)
    h = int(ys.max() - ys.min() + 1)
    row_cells = cells(ink, 0.9 * h)
    lex = {"PANGPANG", "MEDGES", "FESTAURANG"}
    assert lexicon_pick(glyphs, "IGPANG", row_cells, lex) == "PANGPANG"
    # correct reads and honest crops stand
    assert lexicon_pick(glyphs, "PANGPANG", row_cells, lex) is None
    cropped = ink[:, int(xs.min() + (xs.max() - xs.min()) * 0.3):]
    crop_cells = cells(cropped, 0.9 * h)
    assert lexicon_pick(glyphs, "GPANG", crop_cells, lex) is None


def test_a_ghost_word_is_read_with_no_ocr_anchor(tmp_path):
    # A big display word OCR never turned into a text block: read it cold
    # from its ink alone - cells, segmentation options, and the ear - and
    # refuse to hallucinate one out of a scribble.
    import cv2
    from engine.harvest.letters import atlas
    from engine.harvest.proof import ghost_word
    from engine.render import Renderer
    with Renderer() as r:
        ink = _word_row(tmp_path, r, "Garden", px=64)
        full = atlas(r._browser, full=True)
    soft = cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8))
    got = ghost_word(soft, full)
    assert got is not None and got[0] == "Garden", got
    # a scribble is not a word
    noise = np.zeros_like(soft)
    cv2.ellipse(noise, (300, 70), (250, 50), 10, 0, 360, 1, 12)
    cv2.line(noise, (60, 100), (520, 40), 1, 9)
    assert ghost_word(noise, full) is None


def test_the_ghost_keeps_the_overprint_as_art(tmp_path):
    # The office-card shape: a grey display word with a red logotype struck
    # through it. The word comes back live from its own colour layer, and the
    # red ink - and ONLY the red ink - stays behind as art.
    import cv2
    from engine.harvest.art import Region
    from engine.harvest.ghost import find as find_ghosts
    from engine.harvest.letters import atlas
    from engine.render import Renderer
    with Renderer() as r:
        ink = _word_row(tmp_path, r, "Garden", px=64)
        full = atlas(r._browser, full=True)
    h, w = ink.shape
    band = np.full((h, w, 3), 245, np.uint8)
    band[ink > 0] = (40, 40, 40)
    red = np.zeros((h, w), np.uint8)
    cv2.ellipse(red, (w // 2, h // 2), (int(w * 0.3), int(h * 0.25)), -8, 0, 360, 1, 10)
    band[red > 0] = (30, 30, 200)   # BGR red, struck through the word
    ys, xs = np.nonzero((ink > 0) | (red > 0))
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    mask = ((ink > 0) | (red > 0))[box[1]:box[3], box[0]:box[2]]
    reg = Region("mark", box, (40, 40, 40), mask=mask)
    bg = np.full_like(band, 245)
    ghosts, regions = find_ghosts(band, [reg], bg, full, body_px=12.0)
    assert len(ghosts) == 1 and ghosts[0].text == "Garden", [g.text for g in ghosts]
    # the region that remains is the red ink, not the word
    assert len(regions) == 1
    rm = regions[0].mask
    red_in_box = red[box[1]:box[3], box[0]:box[2]] > 0
    word_in_box = ink[box[1]:box[3], box[0]:box[2]] > 0
    assert (rm & red_in_box).sum() > 0.6 * red_in_box.sum()
    assert (rm & word_in_box & ~red_in_box).sum() < 0.2 * word_in_box.sum()


def test_a_soft_ghost_takes_its_fringe_and_spares_the_overprint():
    # The office card proper: the display word is SOFT (airbrushed), so colour
    # k-means splits it into a dark core and a light fringe, and the overprint
    # multiplies into dark maroon that clusters WITH the core. Subtracting the
    # raw layer then (a) leaves a letter-shaped fringe shell as art and (b)
    # carves the maroon out of the logotype the region is keeping. The claim
    # must go by COLOUR: neutral ink near the word leaves with the ghost,
    # ink leaning a rival's hue stays, however the clusters fell.
    import cv2
    from engine.harvest.ghost import _claim
    h, w = 120, 420
    core = np.zeros((h, w), bool)
    for i in range(6):                       # six fat letter-ish stems
        core[30:90, 30 + i * 62:62 + i * 62] = True
    soft = cv2.GaussianBlur(core.astype(np.float32), (0, 0), 4.0)
    soft = soft / soft.max()
    word = soft > 0.08
    fringe = word & ~core
    crop = np.full((h, w, 3), 245, np.uint8)
    g = (245 - soft * 205).astype(np.uint8)
    for c in range(3):
        crop[:, :, c] = g
    red8 = np.zeros((h, w), np.uint8)
    cv2.ellipse(red8, (w // 2, 60), (170, 34), -8, 0, 360, 1, 12)
    red = red8 > 0
    crop[red] = (crop[red].astype(np.int32) * np.array([28, 28, 180]) // 245).astype(np.uint8)
    mask = word | red
    # the k-means accident: the "layer" holds the dark core AND the maroon
    # overlap, but not the fringe - exactly the office split
    layer = (core | (red & word)) & mask
    taken = _claim(crop, mask, layer, cap=60.0, rivals=[(28, 28, 180)])
    clear_fringe = fringe & ~red    # fringe under the overprint stays with it
    assert (taken & clear_fringe).sum() > 0.8 * clear_fringe.sum(), \
        f"fringe left behind: took {(taken & clear_fringe).sum()} of {clear_fringe.sum()}"
    assert (taken & red & ~word).sum() < 0.05 * (red & ~word).sum(), \
        "the ghost claimed the overprint's own ink"
    overlap = red & word
    assert (taken & overlap).sum() < 0.2 * overlap.sum(), \
        f"the overprint was carved: took {(taken & overlap).sum()} of {overlap.sum()}"
    # a one-colour region (no rival ink): the whole neighbourhood is the word's
    plain = np.full((h, w, 3), 245, np.uint8)
    for c in range(3):
        plain[:, :, c] = g
    t2 = _claim(plain, word, core & word, cap=60.0, rivals=[])
    assert (t2 & fringe).sum() > 0.8 * fringe.sum()


def test_stacked_junk_blocks_are_lendable_to_the_angled_reader():
    # The repro's corner: the head of an edge-running column reads level as a
    # stack of two-letter nonsense ('SA' over 'Lu') - a TWO-RUN block, so the
    # single-run loose gate misses it, and one word per run, so the stray-word
    # gate misses it too. A block made entirely of tiny junk words is lendable
    # whole, however the words are stacked; real text is not.
    from engine.harvest.layout import Block, Run
    from engine.harvest.ocr import Line, Word
    from engine.harvest.pipeline import _junk_block

    def block(rows):
        runs = []
        for words in rows:
            ws = [Word(t, (10, 10, 30, 30), 70.0) for t in words]
            runs.append(Run(ws, Line(ws, (10, 10, 30, 30), 30.0, 0.0, 20.0, 8.0, 4.0)))
        return Block(runs, hard=[True] * len(runs))

    assert _junk_block(block([["SA"], ["Lu"]]))          # the corner junk
    assert _junk_block(block([["22"]]))                  # the old single-run gate
    assert _junk_block(block([["w"]]))
    assert not _junk_block(block([["Pale", "Ale"]]))     # real words stay
    assert not _junk_block(block([["MB720"]]))           # one real token
    assert not _junk_block(block([["It", "is", "so", "on", "we", "go"]]))  # too much total ink


def test_twin_artwork_vouches_for_the_better_reading(tmp_path):
    # The same design printed twice on a sheet, read two ways: the inks are
    # near-identical artwork, so the reading that is more of a word stands
    # for both. Different words are NOT twins and vouch for nothing.
    import cv2
    from engine.harvest.proof import referee, twin_score
    from engine.render import Renderer
    with Renderer() as r:
        a = _word_row(tmp_path, r, "Chicago").astype(np.float32)
        b = _word_row(tmp_path, r, "Wireless").astype(np.float32)
    fat = cv2.dilate(a.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
    assert twin_score(a, fat) >= 0.72, twin_score(a, fat)
    assert twin_score(a, b) < 0.72, twin_score(a, b)

    class W:
        def __init__(self, t, c):
            self.text, self.conf = t, c

    class R:
        def __init__(self, t, c):
            self.words = [W(p, c) for p in t.split(" ")]

        @property
        def text(self):
            return " ".join(w.text for w in self.words)

    class S:
        def __init__(self, ref):
            self.ref = ref

    good, bad, other = R("Chicago", 96), R("Unicago", 91), R("Wireless", 90)
    n = referee([(bad, S(fat), 56.0), (good, S(a), 56.0), (other, S(b), 56.0)])
    assert n == 1 and bad.text == "Chicago", (n, bad.text)
    assert other.text == "Wireless"

def _word_row(tmp_path, r, word, px=56, weight=700):
    """One word rendered with the local Inter, returned as a bool ink mask."""
    import cv2
    font = (ROOT / "fonts" / "Inter-var.woff2").resolve()
    page = tmp_path / f"row-{''.join(c for c in word if c.isalnum())}.html"
    page.write_text(
        "<!doctype html><meta charset=\"utf-8\"><style>"
        f"@font-face {{ font-family:'Inter'; src: url('file://{font}'); }}"
        "body { background:#fff; margin:0; width:700px; height:160px; }"
        f"div {{ font-family:Inter; font-weight:{weight}; font-size:{px}px;"
        " color:#111; margin:30px 0 0 30px }"
        f"</style><div>{word}</div>", encoding="utf-8")
    png = r.render_file(page, pdf=False).png
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    return img < 128


def test_the_atlas_keeps_its_uppercase_eye(tmp_path):
    # The angled, curved and stamp stages chart against capitals; lowercase
    # twins must not eat their chart slots.
    from engine.harvest.letters import atlas
    from engine.render import Renderer
    with Renderer() as r:
        glyphs = atlas(r._browser)
        full = atlas(r._browser, full=True)
    assert not any(c.islower() for c in glyphs.chars)
    assert any(c.islower() for c in full.chars)


def test_the_atlas_reads_lowercase(tmp_path):
    from engine.harvest.letters import atlas
    from engine.harvest.proof import fold, letter_cells
    from engine.render import Renderer
    with Renderer() as r:
        ink = _word_row(tmp_path, r, "Chicago")
        full = atlas(r._browser, full=True)
    cells_ = letter_cells(ink.astype(np.uint8))
    assert len(cells_) == 7, len(cells_)
    got = []
    for c in cells_:
        chart = full.chart(c[4], (-6, 0, 6), top=3)
        got.append(fold(chart[0][2]) if chart else "?")
    hits = sum(a == b for a, b in zip(got, "chicago"))
    assert hits >= 5, (got, hits)


def test_degraded_display_reads_are_amended(tmp_path):
    # Over-inked print misreads at the OCR ('Unicago', 'MB/20'): the atlas
    # looks at each letter cell and overrules only on strong shape evidence.
    import cv2
    from engine.harvest.letters import atlas
    from engine.harvest.proof import amend
    from engine.render import Renderer
    with Renderer() as r:
        chicago = _word_row(tmp_path, r, "Chicago")
        item = _word_row(tmp_path, r, "MB720")
        full = atlas(r._browser, full=True)
    k = np.ones((3, 3), np.uint8)
    fat = cv2.dilate(chicago.astype(np.uint8), k)
    assert amend(full, fat, "Unicago") == "Chicago"
    assert amend(full, cv2.dilate(item.astype(np.uint8), k), "MB/20") == "MB720"


def test_amend_aligns_through_spatter_and_breaks(tmp_path):
    # A photocopy adds toner specks and snaps thin strokes, so the row's
    # cells stop lining up 1:1 with the reader's characters. The alignment
    # must step over the spatter and rejoin the broken letter, and still
    # correct the misread underneath.
    import cv2
    from engine.harvest.letters import atlas
    from engine.harvest.proof import amend
    from engine.render import Renderer
    with Renderer() as r:
        ink = _word_row(tmp_path, r, "AA-Cells")
        full = atlas(r._browser, full=True)
    fat = cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero(fat)
    # a toner speck between the words, clear of every letter
    fat[ys.min() + 2:ys.min() + 8, xs.max() + 12:xs.max() + 17] = 1
    assert amend(full, fat, "AA-Ceiis") == "AA-Cells"
    # snap the first 'l' in half: one character, two cells
    broken = fat.copy()
    cols = np.nonzero(broken.any(axis=0))[0]
    # find the first stem after 'Ce': cut a 2px horizontal slice mid-letter
    from engine.harvest.proof import letter_cells
    cs = letter_cells(fat)
    tallest = max(c[3] for c in cs)
    stem = [c for c in cs if c[2] < 0.4 * tallest and c[3] > 0.8 * tallest][0]
    y_mid = stem[1] + stem[3] // 2
    broken[y_mid:y_mid + 2, stem[0]:stem[0] + stem[2]] = 0
    assert amend(full, broken.astype(np.uint8), "AA-Ceiis") == "AA-Cells"


def test_a_fused_blob_is_recut_by_the_readers_count(tmp_path):
    # Ink gain so severe the word is one connected component: no cell cutting
    # survives it, but the reader DID count the letters - recut the blob into
    # that many pieces at the ink valleys and chart each one.
    import cv2
    from engine.harvest.letters import atlas
    from engine.harvest.proof import amend
    from engine.render import Renderer
    with Renderer() as r:
        ink = _word_row(tmp_path, r, "Chicago")
        full = atlas(r._browser, full=True)
    blob = cv2.dilate(ink.astype(np.uint8), np.ones((11, 11), np.uint8))
    n = cv2.connectedComponentsWithStats(blob, 8)[0] - 1
    assert n <= 2, n   # the premise: the letters have truly fused
    assert amend(full, blob, "Unicago") == "Chicago"
    # and a fused word the reader got RIGHT is left alone
    assert amend(full, blob, "Chicago") is None


def test_sound_reads_are_left_alone(tmp_path):
    from engine.harvest.letters import atlas
    from engine.harvest.proof import amend
    from engine.render import Renderer
    with Renderer() as r:
        ink = _word_row(tmp_path, r, "Chicago")
        full = atlas(r._browser, full=True)
    assert amend(full, ink.astype(np.uint8), "Chicago") is None


def _stamp_page() -> str:
    """A rubber stamp: ring text round a lined globe, crossing a rule."""
    import math
    cx, cy, rm, rt = 350, 380, 90, 128
    spans = []
    word = "RIPPED@HAND.FUN"
    n = len(word)
    for i, ch in enumerate(word):
        th = -120 + 270 * i / n                  # 270-degree arc leaves the ring's own gap
        x = cx + rt * math.cos(math.radians(th))
        y = cy + rt * math.sin(math.radians(th))
        spans.append(f'<span style="position:absolute;left:{x - 20:.0f}px;top:{y - 26:.0f}px;'
                     f'width:40px;text-align:center;line-height:52px;'
                     f'transform:rotate({th + 90:.0f}deg)">{ch}</span>')
    font = (ROOT / "fonts" / "Inter-var.woff2").resolve()
    rings = "".join(f'<div style="position:absolute;left:{cx - rx}px;top:{cy - rm}px;width:{2 * rx}px;'
                    f'height:{2 * rm}px;border:3px solid #222;border-radius:50%"></div>'
                    for rx in (rm, int(0.62 * rm), int(0.3 * rm)))
    bands = "".join(f'<div style="position:absolute;left:{cx - rm}px;top:{cy - ry}px;width:{2 * rm}px;'
                    f'height:{2 * ry}px;border:3px solid #222;border-radius:50%"></div>'
                    for ry in (int(0.55 * rm),))
    rule = f'<div style="position:absolute;left:40px;top:{cy - 40}px;width:620px;height:4px;background:#222"></div>'
    return ("<!doctype html><meta charset=\"utf-8\"><style>"
            f"@font-face {{ font-family:'Inter'; src: url('file://{font}'); }}"
            "body { background:#fff; margin:0; width:700px; height:700px; position:relative;"
            " font-family:Inter; font-weight:700; font-size:40px; color:#1a1a1a; }"
            "</style>" + rings + bands + rule + "".join(spans))


def test_stamp_ring_reads_through_its_own_art(tmp_path):
    # Ring text woven through a stamp's line art and a crossing rule: found by
    # the motif, unrolled about the fitted circle, read as an ordinary row.
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer

    page = tmp_path / "stamp.html"
    page.write_text(_stamp_page(), encoding="utf-8")
    with Renderer() as r:
        (tmp_path / "stamp.png").write_bytes(r.render_file(page, pdf=False).png)
        res = harvest(tmp_path / "stamp.png", "Stamp", out_dir=tmp_path / "pack",
                      renderer=r, refine_rounds=0)
    paths = [res.data[f["bind"]] for f in res.rip["frames"] if f.get("type") == "path"]
    joined = " ".join(paths).upper()
    assert "RIPPED" in joined and "HAND" in joined, paths


def test_ransom_lettering_reads_with_per_letter_angles(tmp_path):
    from engine.harvest.pipeline import harvest
    from engine.render import Renderer

    page = tmp_path / "ransom.html"
    page.write_text(_ransom_page(), encoding="utf-8")
    with Renderer() as r:
        (tmp_path / "ransom.png").write_bytes(r.render_file(page, pdf=False).png)
        res = harvest(tmp_path / "ransom.png", "Ransom", out_dir=tmp_path / "pack",
                      renderer=r, refine_rounds=0)
    paths = {res.data[f["bind"]]: f for f in res.rip["frames"] if f.get("type") == "path"}
    assert set(paths) >= {"FORTUNE", "LAST"}, paths.keys()
    for text, f in paths.items():
        if text not in RANSOM_JITTER:
            continue
        assert f.get("pitch"), f
        if f.get("angles") is None:
            # Read without per-letter angles: the letters then turn with the path,
            # which is within the jitter of the truth - but only if they turn.
            assert not f.get("upright"), f
            continue
        assert len(f["angles"]) == len(text)
        # Each recovered turn lands near the letter's true one (symmetric letters
        # may settle half a turn away; the row read cannot tell those apart).
        import math as m
        for k, ch in enumerate(text):
            true = (90 if text == "LAST" else m.degrees(m.atan2(
                -170 * m.pi / 6 * m.cos(k / 6 * m.pi), 60))) + RANSOM_JITTER[text][k]
            d = abs(f["angles"][k] - true) % 360
            d = min(d, 360 - d)
            assert d < 35 or abs(d - 180) < 35, (ch, f["angles"][k], round(true))


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


def test_a_header_in_the_rows_own_style_is_found_by_its_figures():
    from engine.harvest.tables import find_tables
    blocks, style = _list_sheet([("ITEM", 100, 150, 170, "row"), ("PRICE", 362, 420, 170, "row")])
    tables = find_tables(blocks, style)
    assert len(tables) == 1
    t = tables[0]
    assert len(t.rows) == 4, [r[0].text for r in t.rows]
    assert [c.text for c in t.header] == ["ITEM", "PRICE"]


def test_summary_rows_end_the_list_instead_of_shrinking_it():
    """Item / qty / price rows, then subtotal rows using only the outer columns."""
    from engine.harvest.tables import find_tables
    blocks, style = [], {}

    def add(text, l, r, base):
        style[len(blocks)] = "row"
        blocks.append(_cell(text, l, r, base))
    for i, item in enumerate(["OAK TABLE", "LINEN CHAIR", "WALNUT SHELF", "BRASS LAMP"]):
        add(item, 100, 100 + 12 * len(item), 200 + 30 * i)
        add("1", 300, 310, 200 + 30 * i)
        add("$950", 372, 420, 200 + 30 * i)
    for i, label in enumerate(["SUBTOTAL", "TAX", "TOTAL"]):
        add(label, 100, 100 + 12 * len(label), 320 + 30 * i)
        add("$950", 372, 420, 320 + 30 * i)
    tables = sorted(find_tables(blocks, style), key=lambda t: t.rows[0][0].baseline)
    assert len(tables[0].styles) == 3, [len(t.styles) for t in tables]
    assert len(tables[0].rows) == 4


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
    # Set at 15 pt with no tracking (the page may snap to a larger paper size: scale with it).
    scale = ripped3.rip["page"]["width_mm"] / KNOWN3["page"]["width_mm"]
    for f in ripped3.rip["frames"]:
        if f.get("rotate"):
            size = ripped3.rip["styles"][f["style"]]["size"]
            assert abs(size / (15 * scale) - 1) < 0.03, size
            assert abs(f["with"].get("tracking", 0)) < 0.03, f["with"]
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
