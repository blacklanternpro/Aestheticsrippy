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
