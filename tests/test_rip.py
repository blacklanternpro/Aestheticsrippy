"""Rip packs end to end: the Python loader drives the shared JS renderer."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.rip import RipError, build_html, find_assets, load_rip, render_pdf  # noqa: E402


def test_renderer_unit_tests_pass():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    out = subprocess.run([node, "--test", *map(str, (ROOT / "studio" / "tests").glob("*.test.js"))],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]


def test_asset_map_finds_named_files(tmp_path):
    (tmp_path / "me.jpg").write_bytes(b"x")
    data = {"person": {"photo": "me.jpg", "name": "Not a file"}, "list": ["me.jpg"]}
    assets = find_assets(data, [tmp_path], tmp_path / "out")
    assert assets == {"me.jpg": "../me.jpg"}


def test_unknown_variant_is_refused(tmp_path):
    pack = ROOT / "design-packs" / "saraiva-resume"
    with pytest.raises(RipError):
        build_html(pack, {}, tmp_path / "x.html", variant="nope")


@pytest.mark.parametrize("pack", ["saraiva-resume", "dupont-letter"])
def test_pack_renders_one_clean_page(pack):
    pd = ROOT / "design-packs" / pack
    data = json.loads((pd / "default-data.json").read_text())
    res = render_pdf(pack, data)
    assert res.pages == 1
    assert not res.errors, res.errors
    assert res.report and not res.report["overflow"]
    assert all(v == 1 for v in res.report["fit"].values())  # reference content fits at full size
    for variant in load_rip(pd).get("variants", {}):
        assert render_pdf(pack, data, variant=variant).pages == 1
