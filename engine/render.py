"""
Aestheticsrippy - headless renderer.

One place that turns a Design Pack into pixels and a PDF, on any OS, using
Playwright's bundled Chromium. The compiler, the eval harness and (later)
the harvester's verify loop all go through here so they see identical output.

    with Renderer() as r:
        result = r.render_pack("design-packs/studio-neue", pdf=True)
        result.png      # bytes, the .page-sheet at `scale` device pixels per CSS px
        result.pages    # PDF page count
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import sync_playwright, Browser, Playwright

MM_PER_CSS_PX = 25.4 / 96.0

_SHEET_PROBE = """() => {
  const s = document.querySelector('.page-sheet');
  if (!s) return null;
  const r = s.getBoundingClientRect();
  return {
    widthPx: r.width, heightPx: r.height,
    scrollHeight: s.scrollHeight, clientHeight: s.clientHeight,
    scrollWidth: s.scrollWidth, clientWidth: s.clientWidth,
  };
}"""


@dataclass
class RenderResult:
    pack_id: str
    png: bytes
    pdf: Optional[bytes]
    pages: Optional[int]
    width_mm: float
    height_mm: float
    overflow: bool
    errors: List[str] = field(default_factory=list)

    @property
    def single_sheet(self) -> bool:
        return self.pages == 1 and not self.overflow


def count_pdf_pages(pdf: bytes) -> int:
    """Count page objects without a PDF dependency (Chromium writes plain objects)."""
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf))


class Renderer:
    """Holds one Chromium instance; reuse it across many renders."""

    def __init__(self, scale: float = 2.0, timeout_ms: int = 30_000):
        self.scale = scale
        self.timeout_ms = timeout_ms
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    def __enter__(self) -> "Renderer":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def render_pack(self, pack_dir: Path | str, pdf: bool = True) -> RenderResult:
        pack_dir = Path(pack_dir).resolve()
        template = pack_dir / "template.html"
        if not template.exists():
            raise FileNotFoundError(f"No template.html in {pack_dir}")
        return self.render_file(template, pack_id=pack_dir.name, pdf=pdf)

    def render_file(self, html_path: Path, pack_id: str = "", pdf: bool = True) -> RenderResult:
        assert self._browser, "Use Renderer as a context manager"
        page = self._browser.new_page(device_scale_factor=self.scale)
        errors: List[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url}"))
        try:
            page.goto(Path(html_path).resolve().as_uri(), wait_until="networkidle",
                      timeout=self.timeout_ms)
            page.evaluate("document.fonts.ready.then(() => true)")

            probe = page.evaluate(_SHEET_PROBE)
            if probe:
                sheet = page.locator(".page-sheet").first
                png = sheet.screenshot(animations="disabled")
                width_mm = probe["widthPx"] * MM_PER_CSS_PX
                height_mm = probe["heightPx"] * MM_PER_CSS_PX
                overflow = (probe["scrollHeight"] > probe["clientHeight"] + 2
                            or probe["scrollWidth"] > probe["clientWidth"] + 2)
            else:
                errors.append("no .page-sheet element; captured full page")
                png = page.screenshot(full_page=True, animations="disabled")
                width_mm = height_mm = 0.0
                overflow = False

            pdf_bytes = pages = None
            if pdf:
                pdf_bytes = page.pdf(prefer_css_page_size=True, print_background=True)
                pages = count_pdf_pages(pdf_bytes)

            return RenderResult(
                pack_id=pack_id or Path(html_path).parent.name,
                png=png, pdf=pdf_bytes, pages=pages,
                width_mm=round(width_mm, 2), height_mm=round(height_mm, 2),
                overflow=overflow, errors=errors,
            )
        finally:
            page.close()
