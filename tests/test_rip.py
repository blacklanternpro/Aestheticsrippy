"""Rip format: binding, repeats, variants, typesetting, fit."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.rip import Builder, apply_variant, resolve, typeset, load_rip, _MISSING  # noqa: E402

RIP = {
    "id": "t", "page": {"width_mm": 100, "height_mm": 100},
    "styles": {"body": {"font": "Inter", "size": 9}},
    "frames": [
        {"id": "name", "type": "text", "style": "body", "text": "{person.first} {person.last}", "x": 5, "y": 5},
        {"id": "list", "type": "stack", "x": 5, "y": 20, "w": 90, "h": 70, "fit": {"min": 0.8, "group": "g"},
         "children": [{"type": "repeat", "bind": "items", "item": {"type": "stack", "children": [
             {"type": "text", "style": "body", "bind": ".title"},
             {"type": "text", "style": "body", "bind": ".note"}]}}]},
    ],
    "variants": {"wide": {"frames": {"list": {"w": 95}}, "styles": {"body": {"size": 10}}}},
}
DATA = {"person": {"first": "Ada", "last": "Lovelace"},
        "items": [{"title": "One", "note": "first"}, {"title": "Two"}]}


def build(rip=RIP, data=DATA):
    return Builder(rip, data, [], ROOT).document()


def test_resolve_paths():
    assert resolve("person.first", DATA) == "Ada"
    assert resolve(".title", DATA, DATA["items"][1]) == "Two"
    assert resolve("items.0.note", DATA) == "first"
    assert resolve("nope.x", DATA) is _MISSING


def test_interpolation_and_repeat():
    doc = build()
    assert "Ada Lovelace" in doc
    assert doc.count(">One<") == 1 and doc.count(">Two<") == 1
    # missing optional field is dropped, not rendered empty
    assert doc.count(">first<") == 1


def test_fit_group_attribute():
    doc = build()
    assert 'data-fit-min="0.8"' in doc and 'data-fit-group="g"' in doc


def test_variant_patches_frames_and_styles():
    v = apply_variant(RIP, "wide")
    assert next(f for f in v["frames"] if f["id"] == "list")["w"] == 95
    assert v["styles"]["body"]["size"] == 10
    assert next(f for f in RIP["frames"] if f["id"] == "list")["w"] == 90  # original untouched


def test_typeset_binds_dashes():
    out = typeset("Licence (LF – Forklift) and work—resolving")
    assert "LF – Forklift" in out
    assert "work⁠—resolving" in out


def test_shipped_rip_packs_load_and_build():
    for pack in ("saraiva-resume", "dupont-letter"):
        pd = ROOT / "design-packs" / pack
        rip = load_rip(pd)
        data = json.loads((pd / "default-data.json").read_text())
        doc = Builder(rip, data, [pd / "assets", pd], pd).document()
        assert "page-sheet" in doc and 'data-rip="%s"' % pack in doc
        for name in rip.get("variants", {}):
            Builder(load_rip(pd, name), data, [pd / "assets", pd], pd).document()
