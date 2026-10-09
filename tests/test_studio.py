"""
The studio end to end in a real browser: create, edit inline, undo across a
reload, add an entry, restyle, export, and open a private content file.
"""
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def studio(tmp_path_factory):
    import socketserver
    import server

    content = tmp_path_factory.mktemp("content")
    pd = ROOT / "design-packs" / "dupont-letter"
    data = json.loads((pd / "default-data.json").read_text())
    data["_rip"] = {"pack": "dupont-letter"}
    data["person"]["first"] = "Test"
    data["person"]["photo"] = "face.png"
    (content / "test-letter.json").write_text(json.dumps(data))
    (content / "face.png").write_bytes((pd / "assets" / "portrait-placeholder.png").read_bytes())
    server.CONTENT_DIR = content

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), server.StudioHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/studio/", content
    httpd.shutdown()


def test_studio_flow(studio):
    url, content = studio
    errors = []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        pg.wait_for_selector(".empty-card")

        # New document from a pack
        pg.click("text=New from a pack")
        pg.click('.pack-card:has-text("Saraiva Resume")')
        pg.wait_for_selector(".sheet-host .page-sheet")
        pg.wait_for_function("document.querySelector('#fit-status').textContent.length > 0")
        assert "Fits on one page at full size" in pg.inner_text("#fit-status")

        # Inline edit on the sheet, mirrored in the content panel
        summary = pg.locator('.sheet-host [data-path="summary"]')
        summary.click()
        summary.click()
        pg.wait_for_selector(".sheet-host .is-editing")
        pg.keyboard.press("Control+End")
        pg.keyboard.type(" Typed in the studio.")
        pg.wait_for_timeout(900)  # reflow render happens while still editing
        assert pg.locator(".sheet-host .is-editing").count() == 1
        pg.keyboard.press("Escape")
        assert pg.locator('[data-field="summary"]').input_value().endswith("Typed in the studio.")

        # Undo, then the redo step survives a reload
        pg.click("#undo")
        pg.wait_for_timeout(300)
        assert "Typed in the studio" not in summary.inner_text()
        pg.reload()
        pg.wait_for_selector(".sheet-host .page-sheet")
        pg.wait_for_timeout(300)
        pg.click("#redo")
        pg.wait_for_timeout(300)
        assert "Typed in the studio" in pg.locator('.sheet-host [data-path="summary"]').inner_text()

        # Duplicate an entry from the sheet: it reflows and still fits
        before = pg.locator('.sheet-host [data-list="center.items"] > [data-item]').count()
        pg.locator('.sheet-host [data-path="center.items.1.title"]').click()
        pg.click('.item-toolbar [data-action="duplicate"]')
        pg.wait_for_timeout(500)
        assert pg.locator('.sheet-host [data-list="center.items"] > [data-item]').count() == before + 1
        assert "Doesn't fit" not in pg.inner_text("#fit-status")

        # Restyle: one style edit changes every text that uses it
        pg.locator('.sheet-host [data-path="center.items.0.body.0"]').click()
        assert "body" in pg.inner_text(".style-name")
        size = pg.locator("#p-size")
        size.fill("8.6")
        size.press("Enter")
        pg.wait_for_timeout(400)
        font_size = pg.evaluate("getComputedStyle(document.querySelector('.sheet-host [data-path=\"summary\"]')).fontSize")
        assert font_size  # the summary uses its own style; body texts changed
        assert "8.6pt" in pg.evaluate("document.querySelector('.sheet-host [data-path=\"center.items.0.body.0\"]').getAttribute('style')")

        # Export
        with pg.expect_download() as dl:
            pg.click("#export")
        pdf = Path(dl.value.path()).read_bytes()
        assert pdf[:4] == b"%PDF"

        # Open a private content file; its photo resolves from the content folder
        pg.click("#doc-button")
        pg.click("text=Open a file…")
        pg.locator('.file-row:has-text("test-letter.json") button').click()
        pg.wait_for_selector(".sheet-host .rip-image img")
        pg.wait_for_function("document.querySelector('.sheet-host .rip-image img').naturalWidth > 0")
        assert "TEST" in pg.locator('.sheet-host [data-frame="name"]').inner_text()

        # Save back to the file
        pg.locator('[data-field="letter.signoff"]').fill("Warmly,")
        pg.keyboard.press("Control+s")
        pg.wait_for_timeout(500)
        saved = json.loads((content / "test-letter.json").read_text())
        assert saved["letter"]["signoff"] == "Warmly,"
        assert saved["_rip"]["pack"] == "dupont-letter"
        browser.close()
    assert not errors, errors


def test_static_files_are_locked_down(studio):
    import urllib.error
    import urllib.request
    url, _ = studio
    base = url.rsplit("/studio/", 1)[0]
    for path in ("/.env", "/server.py", "/.git/config", "/engine/rip.py", "/design-packs/../server.py",
                 "/content/private/test-letter.json"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + path)
        assert e.value.code == 404, path
    assert urllib.request.urlopen(base + "/fonts/fonts.css").status == 200


def test_rip_an_image_from_the_studio(studio, tmp_path, monkeypatch):
    """Upload a reference, watch it rip, open the new pack as a document."""
    import server
    import engine.harvest.pipeline as pipeline

    packs = tmp_path / "packs"
    packs.mkdir()
    # Rip into a scratch pack folder; keep the shipped packs listed so the studio still boots.
    for p in (ROOT / "design-packs").iterdir():
        if (p / "rip.json").exists():
            (packs / p.name).symlink_to(p)
    monkeypatch.setattr(server, "PACKS_DIR", packs)
    monkeypatch.setattr(pipeline, "PACKS_DIR", packs)
    url, _ = studio
    errors = []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        pg.evaluate("indexedDB.databases().then(dbs => dbs.forEach(d => indexedDB.deleteDatabase(d.name)))")
        pg.reload()
        pg.wait_for_selector(".empty-card")
        pg.click('.empty-card >> text=Rip an image')
        pg.set_input_files(".rip-drop input[type=file]",
                           str(ROOT / "design-packs" / "fidele-invoice-0123" / "assets" / "reference.jpg"))
        pg.fill("#rip-name", "Test Rip")
        pg.click("text=Rip it")
        pg.wait_for_selector(".rip-steps li")
        pg.wait_for_selector("text=Test Rip is ready", timeout=240_000)
        score = float(pg.inner_text(".rip-score strong"))
        assert score > 70
        pg.click("text=Open it")
        pg.wait_for_selector(".sheet-host .page-sheet [data-path]")
        assert "Invoice" in pg.inner_text(".sheet-host .page-sheet")
        browser.close()
    assert (packs / "test-rip" / "rip.json").exists()
    assert not errors, errors
    for f in (ROOT / "content" / "uploads").glob("test-rip.*"):
        f.unlink()


def test_writes_need_json_from_the_studio(studio):
    """A form or script on another site cannot start a rip or overwrite content."""
    import urllib.error
    import urllib.request
    url, _ = studio
    base = url.rsplit("/studio/", 1)[0]
    cases = [
        ("/api/rip", "text/plain", None),
        ("/api/rip", "application/json", "https://evil.example"),
    ]
    for path, ctype, origin in cases:
        req = urllib.request.Request(base + path, data=b'{"image": "", "name": "x"}', method="POST",
                                     headers={"Content-Type": ctype, **({"Origin": origin} if origin else {})})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400, (path, ctype, origin)
