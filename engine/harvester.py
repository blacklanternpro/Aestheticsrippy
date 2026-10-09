"""
Aesthetic Compiler - Boutique Vision Harvester (Phase 2)
Deconstructs graphic scans and photos into publication-grade, print-locked Design Packs.
Performs multimodal visual decomposition, dynamic archetype classification,
and bespoke semantic HTML/CSS synthesis.
"""

import os
import sys
import json
import base64
import re
import urllib.request
import urllib.error
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from PIL import Image
import io

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from engine.boutique_glyphs import generate_glyph_lockup

import time

# Available models in order of priority (including flash-lite with generous quota)
GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.1-pro-preview"
]

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Fallback: check known local .env locations if no env key
if not DEFAULT_API_KEY:
    potential_envs = [
        BASE_DIR / ".env",
        Path("C:/Users/edtli/dell-estate-flow/.env"),
        Path("C:/Users/edtli/r1i-sales-intel/.env")
    ]
    for env_path in potential_envs:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY=") or line.startswith("VITE_GEMINI_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                DEFAULT_API_KEY = val
                                break
            except Exception:
                pass
        if DEFAULT_API_KEY:
            break

def build_harvest_prompt(aspect: float, auto_format: str, w_mm: int, h_mm: int) -> str:
    orientation = "landscape" if w_mm > h_mm else "portrait"
    return f"""You are the world's premier boutique graphic designer, typographic deconstructor, and publication-grade CSS engineer.
Analyze this graphic design reference image and reverse-engineer its visual DNA into a faithful, publication-grade digital reproduction in HTML/CSS.
Do NOT output a generic web page or generic template. Replicate the EXACT visual layout, typography, proportions, containment, and graphic rhythm of this scan.

IMAGE GEOMETRY METRICS (STRICT ENFORCEMENT):
- Physical Aspect Ratio: {aspect:.2f}
- Target Print Format: {auto_format} ({w_mm}mm wide × {h_mm}mm high).
- Your generated CSS @page and .page-sheet MUST be exactly {w_mm}mm × {h_mm}mm.

CRITICAL ARCHITECTURAL & DESIGN DECONSTRUCTION RULES:

1. **MACRO-REGION & MULTI-ZONE SPATIAL MAPPING**:
   - Deconstruct the artboard into its authentic macro-regions before writing HTML:
     * Examples: Top calendar grid (e.g. 2 columns: January on left, February on right, occupying ~55% of vertical space).
     * Bottom region: If there is an inset sticker/brick on the bottom-left and an open artwork/graphic zone on the bottom-right, use a two-column or multi-column flex/grid layout (e.g. `<div class="bottom-section"><div class="breakout-brick visual-object ac-movable">...</div><div class="artwork-zone visual-object ac-movable">...</div></div>`).
     * NEVER force inset content into a full-width page footer! If an element is a distinct card, brick, or badge, it must stay in its exact spatial quadrant!

2. **COLORED BREAKOUT BRICKS / STICKERS / INSET CARDS (STRICT CONTAINMENT)**:
   - If the scan contains a distinct colored rectangular block, card, or sticker (e.g. a hot pink brick, neon yellow badge, black card, industrial stamp):
     * It is a self-contained card container (`<div class="breakout-brick visual-object ac-movable">`).
     * Preserve its exact background color (e.g. `#ff007f` / `#ff00a0`), border (e.g. `border: 2px solid #000;`), and relative width/height (e.g. `width: 44%; min-height: 260px;`).
     * **ALL text, headlines, logos, dividers, QR codes, addresses, and fine print visually sitting inside that colored shape MUST be nested INSIDE that container!**
     * Sub-divide inside the card cleanly: top headers with underlines, middle logos/lettering, horizontal divider lines, internal 2-column micro-grids (e.g. QR code + ticket text on left, logo + address on right), and micro-copyright at the bottom.
     * NEVER spill these details out into the parent page or dump them into a generic footer!

3. **TYPOGRAPHIC PHYSICALITY & DECONSTRUCTION MATRIX (CRITICAL)**:
   - Graphic design references use intentional typographic treatments that MUST NOT be flattened into uniform plain sans-serif text.
   - Deconstruct and render each distinct typographic treatment using exact CSS classes and properties so that they render authentically AND REMAIN FULLY EDITABLE IN THAT STYLE:
     * **A. Vertically Stretched Woodtype (Tall, Squeezed, Condensed)**:
       - Visual cue: Tall, narrow, compressed letterforms with high vertical tension (e.g. `JANUARY`, `FEBRUARY`, or large numeric dates like `10.04`).
       - Apply classes `.typo-condensed-tall` or `.date-hero`:
         CSS:
         `font-family: 'Anton', 'Bebas Neue', 'Barlow Condensed', sans-serif;`
         `display: inline-block;`
         `transform: scaleY(var(--typo-scale-y, 1.2));`
         `transform-origin: left bottom;`
         `letter-spacing: var(--typo-tracking, -0.025em);`
         `line-height: var(--typo-leading, 0.85);`
         `text-transform: uppercase;`
         `font-weight: 900;`
     * **B. Bunched Up & High-Density Brutalist Pacing**:
       - Visual cue: Letters packed tight with negative tracking, almost touching, zero slack.
       - Apply class `.typo-bunched`:
         CSS: `letter-spacing: -0.04em to -0.06em; line-height: 0.88; font-weight: 800-900; word-spacing: -0.04em;`
     * **C. Spread Apart / Extreme Tracking**:
       - Visual cue: Wide letter-spaced metadata, uppercase labels, coordinates, category tags.
       - Apply class `.typo-spread`:
         CSS: `letter-spacing: 0.22em to 0.4em; text-transform: uppercase; font-size: 0.75em to 0.9em;`
     * **D. Warped / Skewed / Slanted Typography**:
       - Visual cue: Slanted, skewed, or rotated typographic stamps.
       - Apply class `.typo-warped`:
         CSS: `display: inline-block; transform: skewX(-7deg) scaleY(1.15); transform-origin: left bottom;`
     * **E. Compound Number / Timetable / Event Listing Architecture**:
       - Visual cue: An index number (`01`) next to a massive bold condensed date (`10.04`), with artist/event name underneath.
       - HTML MUST BE STRUCTURED DISCRETELY (NEVER dump into a single string with `<br>`):
         ```html
         <div class="calendar-item visual-object ac-movable">
           <div class="date-row">
             <span class="idx">01</span>
             <span class="date-hero typo-condensed-tall">10.04</span>
           </div>
           <div class="artist-title">Mirah + Lori Goldston</div>
         </div>
         ```
       - CSS:
         `.calendar-item {{ margin-bottom: 7px; line-height: 1; }}`
         `.date-row {{ display: flex; align-items: flex-start; gap: 4px; line-height: 0.85; }}`
         `.idx {{ font-family: 'Inter', sans-serif; font-size: 11px; font-weight: 900; line-height: 1.1; letter-spacing: -0.02em; }}`
         `.date-hero {{ font-family: 'Anton', 'Bebas Neue', sans-serif; font-size: 30px; font-weight: 900; letter-spacing: -0.03em; line-height: 0.85; display: inline-block; transform: scaleY(1.18); transform-origin: left bottom; }}`
         `.artist-title {{ font-family: 'Inter', sans-serif; font-size: 15px; font-weight: 900; letter-spacing: -0.04em; line-height: 1.05; margin-top: 2px; padding-bottom: 3px; border-bottom: 2px solid #000; }}`
     * **F. Underlines**:
       - If an underline spans only the text (e.g. under `JANUARY`), use `<span class="header-text">JANUARY</span>` with `.header-text {{ border-bottom: 3px solid #000; padding-bottom: 2px; display: inline-block; }}`.
     * **G. Inset Cards & Complex Graphics (e.g. Pink Brick)**:
       - Keep inside the card container (`<div class="breakout-brick visual-object ac-movable">`).
       - For graphic details like QR codes or icons, render crisp SVG or styled elements (e.g. SVG QR grid, stylized logo mark), and keep internal multi-column flex layouts (`display: flex; gap: 12px;`) intact!
     * **H. Extended / Wide Grotesque (Horizontally Stretched / Broad Tracking)**:
       - Visual cue: Broad, flattened, extended geometric sans letterforms (e.g. `TOM OF ENGLAND`, `BLAZER SOUND SYSTEM`, `GEORGIA`, `MAGICK CITY`).
       - DO NOT use condensed fonts (`Anton`) for wide letterforms!
       - Apply class `.typo-wide`:
         CSS:
         `font-family: 'Syne', 'Archivo Black', 'Montserrat', sans-serif;`
         `font-weight: 800;`
         `letter-spacing: 0.08em;`
         `display: inline-block;`
         `transform: scaleX(var(--typo-scale-x, 1.25));`
         `transform-origin: center center;`
         `text-transform: uppercase;`
     * **I. Chromatic Screenprint Registration Shadows**:
       - Visual cue: Text with a sharp, high-contrast 2nd-color drop shadow simulating off-register screenprint plates (e.g. black ink with saturated neon orange/amber `#ff6600` or yellow offset at 135°).
       - Apply class `.chromatic-shadow`:
         CSS: `text-shadow: 3.5px 3.5px 0px var(--shadow-color, #ff6600);`
     * **J. Symmetrical 3-Point Date Triptychs (`Month | Day | Year`)**:
       - Visual cue: Dates written as three separate numbers across the headline width (e.g. `3` [left], `26` [center], `16` [right]).
       - MUST NOT be lumped into `"3 26 16"` left aligned!
       - Structure as a 3-column flex container:
         ```html
         <div class="date-triptych visual-object ac-movable">
           <span class="trip-col trip-left">3</span>
           <span class="trip-col trip-center">26</span>
           <span class="trip-col trip-right">16</span>
         </div>
         ```
         CSS: `.date-triptych {{ display: flex; justify-content: space-between; width: 100%; font-weight: 900; margin-bottom: 2px; }}`
     * **K. Contoured / Nested Acronym Lockups (`L S D` / `LAST SATURDAY DANCE`)**:
       - Visual cue: Large display letters with smaller text running inside them or contouring along their paths.
       - Structure as a Vector Boutique Glyph Lockup with dual-layer chromatic screenprint registration:
         ```html
         <div class="glyph-lockup visual-object ac-movable">
           <div class="glyph-vector">
             <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 190 91" width="100%" height="100%">
               <g fill="#ff6600" transform="translate(-3.5, 3.5)">
                 <path class="shadow-l" d="M 8 14 L 7 25 L 8 44 L 7 77 L 8 78 L 8 86 L 59 86 L 59 72 L 24 71 L 24 14 Z" fill-rule="evenodd"/>
                 <path class="shadow-s" d="M 84 15 L 73 21 L 68 27 L 66 32 L 67 43 L 69 47 L 77 53 L 104 60 L 108 67 L 102 73 L 90 73 L 85 71 L 80 64 L 64 64 L 65 70 L 68 77 L 78 85 L 85 87 L 104 87 L 116 81 L 122 73 L 122 56 L 112 47 L 85 40 L 82 36 L 82 33 L 84 30 L 90 27 L 101 27 L 107 32 L 108 35 L 122 34 L 119 23 L 111 16 L 96 13 Z" fill-rule="evenodd"/>
                 <path class="shadow-d" d="M 165 16 L 159 14 L 148 13 L 135 14 L 136 60 L 135 85 L 136 87 L 153 87 L 159 86 L 170 82 L 178 75 L 182 68 L 184 60 L 184 47 L 182 36 L 177 26 L 175 24 L 171 24 L 172 21 Z M 149 29 L 155 29 L 159 30 L 162 32 L 166 36 L 169 42 L 170 49 L 170 55 L 168 63 L 166 66 L 162 70 L 158 72 L 154 73 L 147 72 Z" fill-rule="evenodd"/>
               </g>
               <g fill="#000000">
                 <path class="main-l" d="M 8 14 L 7 25 L 8 44 L 7 77 L 8 78 L 8 86 L 59 86 L 59 72 L 24 71 L 24 14 Z" fill-rule="evenodd"/>
                 <path class="main-s" d="M 84 15 L 73 21 L 68 27 L 66 32 L 67 43 L 69 47 L 77 53 L 104 60 L 108 67 L 102 73 L 90 73 L 85 71 L 80 64 L 64 64 L 65 70 L 68 77 L 78 85 L 85 87 L 104 87 L 116 81 L 122 73 L 122 56 L 112 47 L 85 40 L 82 36 L 82 33 L 84 30 L 90 27 L 101 27 L 107 32 L 108 35 L 122 34 L 119 23 L 111 16 L 96 13 Z" fill-rule="evenodd"/>
                 <path class="main-d" d="M 165 16 L 159 14 L 148 13 L 135 14 L 136 60 L 135 85 L 136 87 L 153 87 L 159 86 L 170 82 L 178 75 L 182 68 L 184 60 L 184 47 L 182 36 L 177 26 L 175 24 L 171 24 L 172 21 Z M 149 29 L 155 29 L 159 30 L 162 32 L 166 36 L 169 42 L 170 49 L 170 55 L 168 63 L 166 66 L 162 70 L 158 72 L 154 73 L 147 72 Z" fill-rule="evenodd"/>
               </g>
             </svg>
           </div>
           <div class="inner-chars inner-l">
             <span class="char-l1">L</span><span class="char-l2">A</span><span class="char-l3">S</span><span class="char-l4">T</span>
           </div>
           <div class="inner-chars inner-s">
             <span class="char-s1">S</span><span class="char-s2">A</span><span class="char-s3">T</span><span class="char-s4">U</span><span class="char-s5">R</span><span class="char-s6">D</span><span class="char-s7">A</span><span class="char-s8">Y</span>
           </div>
           <div class="inner-chars inner-d">
             <span class="char-d1">D</span><span class="char-d2">A</span><span class="char-d3">N</span><span class="char-d4">C</span><span class="char-d5">E</span>
           </div>
         </div>
         ```
       - CSS:
         `.glyph-lockup {{ position: relative; width: 100%; max-width: 570px; margin: 0 auto; aspect-ratio: 190 / 91; }}`
         `.glyph-vector {{ position: absolute; inset: 0; pointer-events: none; }}`
         `.inner-chars {{ position: absolute; inset: 0; pointer-events: auto; }}`
         `.inner-chars span {{ position: absolute; font-family: 'Inter', sans-serif; font-weight: 900; font-size: 27px; color: var(--page-bg); line-height: 1; transform: translate(-50%, -50%); cursor: text; text-shadow: 0.5px 0.5px 0px rgba(255, 102, 0, 0.7); }}`

       L. Monospace Receipt / Thermal Printer Typography
       - Visual cue: Thermal receipt paper with monospace body text, dot-matrix headers, right-aligned currency amounts.
       - The body MUST use `font-family: 'Space Mono', 'Courier New', monospace`.
       - Right-aligned amounts should use a 2-column flex with `justify-content: space-between` or a `<table>` with `text-align: right` on the amount column.
       - Dashed separator lines should be literal characters `---` in a `<pre>` or styled `<div>` with `border-top: 1px dashed #000`.
       - Asterisk rows (`*****CHECK CLOSED*****`) should be preserved literally.
       - Structure:
         ```html
         <div class="receipt-body typo-mono">
           <div class="receipt-line"><span>1 Medges Ale</span><span class="amount">89,00</span></div>
           <div class="receipt-separator">-</div>
           <div class="receipt-total"><span>Net Total:</span><span class="amount">89,00</span></div>
         </div>
         ```

       M. Pixel-Art / Bitmap Logo Headers
       - Visual cue: Chunky, blocky, pixel-art style lettering that looks like it was rendered on an 8-bit grid (e.g. "PANG PANG").
       - These MUST be rendered as an SVG grid of filled squares (not a font!) to preserve the pixel-art aesthetic.
       - Structure: `<div class="pixel-header visual-object ac-movable"><svg class="pixel-art" viewBox="0 0 WIDTH HEIGHT">...</svg></div>`
       - Each letter is composed of filled `<rect>` elements on a grid.
       - CSS: `.pixel-header {{ text-align: center; margin-bottom: 12px; }} .pixel-art {{ max-width: 80%; height: auto; }}`

       N. Rotated Sidebar / Edge Text (Writing Mode Vertical)
       - Visual cue: Text running vertically along the left and/or right edges of the document, often repeating brand names.
       - MUST use CSS `writing-mode: vertical-rl` (right edge) or `writing-mode: vertical-lr` (left edge) with `transform: rotate(180deg)` for upward-reading left sidebar.
       - Structure:
         ```html
         <div class="sidebar-text sidebar-left visual-object ac-movable">PANGPANG MEDGES ALE</div>
         <div class="sidebar-text sidebar-right visual-object ac-movable">MEDGES ALE PANGPANG</div>
         ```
       - CSS:
         ```css
         .sidebar-text {{ position: absolute; writing-mode: vertical-rl; font-family: 'Inter', sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: #cc3333; top: 0; bottom: 0; display: flex; align-items: center; }}
         .sidebar-left {{ left: 8px; transform: rotate(180deg); }}
         .sidebar-right {{ right: 8px; }}
         ```

       O. SVG Barcode Generation
       - Visual cue: Standard 1D barcodes (UPC, EAN, Code 128) at the bottom of receipts, tickets, or product labels.
       - Render as an SVG with alternating black/white vertical bars of varying width.
       - Structure: `<div class="barcode visual-object ac-movable"><svg class="barcode-svg" viewBox="0 0 200 40" preserveAspectRatio="none">...</svg></div>`
       - Generate a realistic barcode pattern with `<rect>` elements. Use a pseudo-random but deterministic pattern based on any visible numbers.

       P. Die-Cut / Serrated / Scalloped Edge Containers
       - Visual cue: Tags, tickets, or cards with decorative edges — serrated (zigzag), scalloped (wave), perforated (dotted line), or punched holes.
       - For serrated edges: Use CSS `clip-path: polygon(...)` with zigzag points, or an SVG mask.
       - Structure:
         ```html
         <div class="die-cut-container serrated visual-object ac-movable">
           <div class="die-cut-inner">...content...</div>
         </div>
         ```
       - CSS:
         ```css
         .die-cut-container.serrated {{
           --notch-size: 6px;
           background: #fff;
           padding: 20px;
           position: relative;
         }}
         .die-cut-container.serrated::before,
         .die-cut-container.serrated::after {{
           content: '';
           position: absolute;
           left: 0; right: 0;
           height: var(--notch-size);
           background: repeating-linear-gradient(90deg, transparent 0, transparent 4px, #fff 4px, #fff 6px, transparent 6px, transparent 10px) no-repeat;
           background-size: 100% var(--notch-size);
         }}
         .die-cut-container.serrated::before {{ top: calc(-1 * var(--notch-size)); }}
         .die-cut-container.serrated::after {{ bottom: calc(-1 * var(--notch-size)); }}
         ```
       - For left/right serrated edges, add `.die-cut-left::before` and `.die-cut-right::after` using vertical versions.

       Q. Decorative / Swash Display Headers
       - Visual cue: Display headers with decorative swashes, flourishes, or custom ligatures (e.g. "HANDSHAKE" with an ornamental flourish through the H and A).
       - Use a Google Font with character: `'Playfair Display SC'`, `'Abril Fatface'`, or `'Cinzel Decorative'`.
       - Add class `.typo-decorative-header`:
       - CSS:
         ```css
         .typo-decorative-header {{
           font-family: 'Playfair Display SC', 'Cinzel Decorative', serif;
           font-size: 48px;
           font-weight: 900;
           letter-spacing: 0.06em;
           text-transform: uppercase;
           text-align: center;
           line-height: 0.95;
           position: relative;
         }}
         ```

       R. Grid Invoice / Bordered Table Layout
       - Visual cue: Clean, professional invoices with bordered tables showing columns (Item, Qty, Cost), header/data/total rows with visible cell borders.
       - MUST use semantic `<table>` with `border-collapse: collapse` and explicit `border` on `th` and `td`.
       - Structure:
         ```html
         <table class="invoice-grid visual-object ac-movable">
           <thead><tr><th>Item:</th><th>Qty:</th><th>Cost:</th></tr></thead>
           <tbody>
             <tr><td>Description</td><td>1</td><td>€00,00</td></tr>
           </tbody>
           <tfoot><tr><td colspan="2">Total</td><td>€00,00</td></tr></tfoot>
         </table>
         ```
       - CSS:
         ```css
         .invoice-grid {{ width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 13px; }}
         .invoice-grid th, .invoice-grid td {{ border: 1px solid currentColor; padding: 6px 10px; text-align: left; vertical-align: top; }}
         .invoice-grid th {{ font-weight: 700; font-size: 11px; }}
         .invoice-grid tfoot td {{ font-weight: 700; border-top: 2px solid currentColor; }}
         ```

       S. Spec/Metadata Grid (Key-Value Pairs in Columns)
       - Visual cue: Technical specification grids showing key:value pairs in multi-column layouts (e.g. "Size: 8,5CM × 14,5CM", "Materials: 100% Polyester").
       - Structure with CSS Grid or definition lists:
         ```html
         <div class="spec-grid visual-object ac-movable">
           <div class="spec-row"><span class="spec-key">Size :</span><span class="spec-val">8,5CM × 14,5CM</span></div>
         </div>
         ```
       - CSS:
         ```css
         .spec-grid {{ display: grid; grid-template-columns: auto 1fr; gap: 2px 12px; font-family: 'Space Mono', monospace; font-size: 11px; }}
         .spec-key {{ font-style: italic; }} .spec-val {{ font-weight: 700; }}
         ```

       T. Purchase Ticket / Tear-Off Section
       - Visual cue: A boxed bottom section of a tag or receipt acting as a tear-off purchase ticket with large price display.
       - Structure:
         ```html
         <div class="purchase-ticket visual-object ac-movable">
           <div class="ticket-info">Description text...</div>
           <div class="ticket-price"><span class="price-amount">24,99€</span><span class="price-label">P.V.P</span></div>
         </div>
         ```
       - CSS:
         ```css
         .purchase-ticket {{ border: 2px solid #000; padding: 12px; display: flex; gap: 16px; justify-content: space-between; margin-top: 10px; }}
         .ticket-price {{ text-align: right; }} .price-amount {{ font-size: 32px; font-weight: 900; line-height: 1; display: block; }}
         .price-label {{ font-size: 14px; font-weight: 700; letter-spacing: 0.1em; }}
         ```

4. **AUTHENTIC PAPER COLOR & STYLING**:
   - Sample the real background paper color from the scan. If it is cream, warm off-white, yellowed newsprint (e.g. `#faf6ed` or `#f8f5ee`), apply it to `.page-sheet {{ background: #faf6ed; }}`! NEVER default to stark bleached `#ffffff` if the scan has paper warmth.

5. **MANDATORY 100% IN-DOM TEXT CONTENT (ZERO EMPTY TAGS)**:
   - Every single word, headline, date, location, ticket link, and credit string visible in the scan MUST be placed DIRECTLY inside the HTML tags in `html`.
   - NEVER output empty placeholder tags like `<div data-field="..."></div>`! Put the full text inside each tag.
   - Zero lines, dates, or labels may be dropped!

6. **ZERO PHANTOM BOXES / OUTLINES**:
   - DO NOT draw arbitrary box borders around text blocks unless an explicit stroke is visibly printed in the reference image (like the outline of the pink brick)!

7. **TAG MOVABLE OBJECTS**:
   - Tag major semantic entities (headers, calendar columns, the breakout brick card, badge stamps, illustration containers) with `class="visual-object ac-movable"` so they can be selected, moved, rotated, and jammed on the canvas.

Return a SINGLE valid JSON object with this exact structure:
```json
{{
  "spec": {{
    "id": "kebab-case-pack-slug",
    "name": "Human Readable Pack Name",
    "version": "1.0.0",
    "category": "Editorial & Poster | Ephemera | Industrial | Identity | Ledger",
    "description": "2-sentence design summary detailing typography, spatial tension, and archetype.",
    "target": {{
      "dimensions": {{
        "format": "{auto_format}",
        "width_mm": {w_mm},
        "height_mm": {h_mm},
        "orientation": "{orientation}"
      }},
      "margins_mm": {{
        "top": 12,
        "right": 12,
        "bottom": 12,
        "left": 12
      }}
    }},
    "typography": {{
      "primaryFont": "Inter",
      "displayFont": "Anton",
      "monospaceFont": "Space Mono",
      "modularScale": 1.2,
      "lineHeightBase": 1.05
    }},
    "colorTokens": {{
      "background": "#faf6ed",
      "textPrimary": "#000000",
      "textSecondary": "#555555",
      "accent": "#ff007f"
    }},
    "spatialBudget": {{
      "strictSinglePage": true
    }}
  }},
  "textInventory": [
    "String 1",
    "String 2"
  ],
  "defaultData": {{
    "title": "Title"
  }},
  "html": "<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>\\n<meta charset=\\"UTF-8\\">\\n<link href=\\"https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;700;900&display=swap\\" rel=\\"stylesheet\\">\\n<link rel=\\"stylesheet\\" href=\\"styles.css\\">\\n</head>\\n<body>\\n<main class=\\"page-sheet\\">\\n...content with filled text, accurate containment, and visual-object ac-movable tags...\\n</main>\\n</body>\\n</html>",
  "css": "@page {{ size: {w_mm}mm {h_mm}mm; margin: 0; }}\\n* {{ box-sizing: border-box; margin: 0; padding: 0; }}\\nbody {{ display: flex; justify-content: center; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}\\n.page-sheet {{ width: {w_mm}mm; height: {h_mm}mm; max-height: {h_mm}mm; overflow: hidden; position: relative; box-sizing: border-box; padding: 12mm; background: #faf6ed; color: #000000; }}\\n/* layout rules */"
}}
```
Output ONLY valid JSON inside ```json ... ```. No conversational commentary."""

def extract_aspect_and_format(image_bytes: bytes) -> Tuple[float, str, int, int]:
    """Calculate image aspect ratio and map to standard print format."""
    try:
        im = Image.open(io.BytesIO(image_bytes))
        w, h = im.size
        aspect = w / h if h > 0 else 0.707
        
        # Format detection
        if aspect < 0.55:
            return aspect, "Thermal-80mm", 80, int(round(80 / aspect))
        elif 0.88 <= aspect <= 1.12:
            return aspect, "Card-Square", 180, 180
        elif 0.60 <= aspect <= 0.76:
            # Standard single-sheet poster / editorial publication ratio (~0.66 - ~0.71)
            # Default to full-size A4 (210x297mm) for authentic editorial typography and breathing room
            return aspect, "A4", 210, 297
        elif 0.76 < aspect <= 0.86:
            return aspect, "US-Letter", 216, 279
        elif aspect > 1.2:
            # Landscape A4
            return aspect, "A4-Landscape", 297, 210
        else:
            # Custom vertical
            width_mm = 210
            height_mm = int(round(width_mm / aspect))
            return aspect, "Custom", width_mm, height_mm
    except Exception:
        return 0.707, "A4", 210, 297

def call_gemini_vision(
    image_bytes: bytes,
    mime_type: str,
    aspect: float = 0.707,
    auto_format: str = "A4",
    w_mm: int = 210,
    h_mm: int = 297,
    api_key: Optional[str] = None,
    model_override: Optional[str] = None
) -> Dict[str, Any]:
    """Call Gemini Vision API with automatic failover across active models and retry backoff."""
    key = api_key or DEFAULT_API_KEY
    if not key:
        raise ValueError("No Gemini API Key provided. Set GEMINI_API_KEY or configure in Settings.")

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    models_to_try = [model_override] if model_override else []
    for m in GEMINI_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    prompt_text = build_harvest_prompt(aspect, auto_format, w_mm, h_mm)

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {
                    "inline_data": {
                        "mime_type": mime_type or "image/png",
                        "data": b64_image
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.2
        }
    }
    
    last_err = None
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        for attempt in range(4):
            try:
                print(f"[*] Calling Gemini Vision model: {model_name} (attempt {attempt + 1})...", flush=True)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    return parse_harvest_json(text_content)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                print(f"[!] Model {model_name} attempt {attempt + 1} failed ({e.code}): {err_body[:180]}", flush=True)
                last_err = e
                if (e.code == 503 or e.code == 429) and attempt < 3:
                    wait_sec = 2.5 * (attempt + 1)
                    print(f"[*] Transient spike ({e.code}). Retrying in {wait_sec:.1f}s...", flush=True)
                    time.sleep(wait_sec)
                    continue
                break
            except Exception as e:
                print(f"[!] Model {model_name} attempt {attempt + 1} error: {e}", flush=True)
                last_err = e
                if attempt < 3:
                    time.sleep(2)
                    continue
                break

    raise RuntimeError(f"All Gemini Vision models failed. Last error: {last_err}")

def parse_harvest_json(raw_text: str) -> Dict[str, Any]:
    """Robustly parse JSON, stripping markdown fences if present."""
    text = raw_text.strip()
    # Remove ```json and ``` if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt secondary regex cleanup for trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        return json.loads(cleaned)

def slugify(text: str) -> str:
    """Convert string to clean URL/directory slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "harvested-pack"

def ensure_dom_text_completeness(html_content: str, default_data: Dict[str, Any], text_inventory: list) -> str:
    """
    Guarantees no data-field element or semantic block is left empty in template.html.
    If an element like <div data-field="tour_dates"></div> is empty,
    populates it from default_data or text_inventory.
    """
    if not html_content:
        return html_content

    # Regex matching empty tags with data-field: <tag ... data-field="..." ...></tag>
    def replacer(match):
        tag_name = match.group(1)
        attrs = match.group(2)
        field_name = match.group(3)
        inner = match.group(4)

        if not inner or not inner.strip():
            # Find candidate text
            val = default_data.get(field_name, "")
            if not val:
                for k, v in default_data.items():
                    if k.lower() in field_name.lower() or field_name.lower() in k.lower():
                        val = v
                        break
            if not val and text_inventory:
                for item in text_inventory:
                    if item.lower() in field_name.lower() or field_name.lower() in item.lower():
                        val = item
                        break
            if not val and len(field_name) > 3 and not field_name.startswith("field_"):
                val = field_name
            if val:
                return f"<{tag_name}{attrs}>{val}</{tag_name}>"
        return match.group(0)

    pattern = r"<([a-zA-Z0-9]+)([^>]*data-field=[\"']([^\"']+)[\"'][^>]*)>(\s*)</\1>"
    html_content = re.sub(pattern, replacer, html_content)
    return html_content

def normalize_typographic_structures(html_content: str, css_content: str) -> Tuple[str, str]:
    """
    Guarantees publication-grade typographic deconstruction:
    1. Upgrades compound date/number rows (e.g. index 01 + giant date 10.04 + artist name + underline).
    2. Enforces headline text underlines to wrap text width rather than whole column width.
    3. Synthesizes authentic vector QR and logo badges for inset cards.
    4. Guarantees complete Google Fonts links in <head>.
    5. Injects standard Typographic DNA classes into CSS (--typo-scale-y, .date-hero, .artist-title, etc.).
    """
    if not html_content:
        return html_content, css_content

    # 1. Normalize compound date listing rows if LLM output <div class="entry"><span>01</span> 10.04<br><strong>...</strong></div>
    def repl_entry(m):
        idx = m.group(1).strip()
        date_str = m.group(2).strip()
        title = m.group(3).strip()
        return (
            f'<div class="calendar-item visual-object ac-movable">\n'
            f'  <div class="date-row">\n'
            f'    <span class="idx">{idx}</span>\n'
            f'    <span class="date-hero typo-condensed-tall">{date_str}</span>\n'
            f'  </div>\n'
            f'  <div class="artist-title">{title}</div>\n'
            f'</div>'
        )

    # Pattern A: <div class="entry">\s*<span>(\d+)</span>\s*([0-9\.\-\/]+)\s*<br\s*/?>\s*(?:<strong>)?(.*?)(?:</strong>)?\s*</div>
    pattern_a = r'<div class="entry">\s*<span>(\d+)</span>\s*([0-9\.\-\/]+)\s*<br\s*/?>\s*(?:<strong>)?(.*?)(?:</strong>)?\s*</div>'
    html_content = re.sub(pattern_a, repl_entry, html_content, flags=re.IGNORECASE)

    # Pattern B: <div class="entry">\s*(\d{1,2})\s+([0-9\.\-\/]+)\s*<br\s*/?>\s*(?:<strong>)?(.*?)(?:</strong>)?\s*</div>
    pattern_b = r'<div class="entry">\s*(\d{1,2})\s+([0-9\.\-\/]+)\s*<br\s*/?>\s*(?:<strong>)?(.*?)(?:</strong>)?\s*</div>'
    html_content = re.sub(pattern_b, repl_entry, html_content, flags=re.IGNORECASE)

    # 2. Header text underline wrapping: <h2 class="header">JANUARY</h2> -> <h2 class="header"><span class="header-text">JANUARY</span></h2>
    def repl_header(m):
        tag = m.group(1)
        attrs = m.group(2)
        text = m.group(3)
        if '<span' not in text:
            return f'<{tag}{attrs}><span class="header-text">{text}</span></{tag}>'
        return m.group(0)

    pattern_header = r'<(h[1-4])([^>]*class=[\'"][^\'"]*header[^\'"]*[\'"][^>]*)>(.*?)</\1>'
    html_content = re.sub(pattern_header, repl_header, html_content, flags=re.IGNORECASE)

    # 3. Vector QR code and logo SVG in breakout brick if placeholder text [QR] or [R] present
    qr_svg = '''<svg class="qr-code-svg visual-object" width="34" height="34" viewBox="0 0 34 34" fill="#000" style="display:block;margin-bottom:4px;background:#fff;padding:2px;border:1px solid #000;">
  <rect x="2" y="2" width="10" height="10" fill="none" stroke="#000" stroke-width="2"/>
  <rect x="5" y="5" width="4" height="4"/>
  <rect x="22" y="2" width="10" height="10" fill="none" stroke="#000" stroke-width="2"/>
  <rect x="25" y="5" width="4" height="4"/>
  <rect x="2" y="22" width="10" height="10" fill="none" stroke="#000" stroke-width="2"/>
  <rect x="5" y="25" width="4" height="4"/>
  <rect x="14" y="2" width="4" height="4"/>
  <rect x="14" y="8" width="4" height="4"/>
  <rect x="2" y="14" width="4" height="4"/>
  <rect x="8" y="14" width="4" height="4"/>
  <rect x="14" y="14" width="6" height="6"/>
  <rect x="22" y="14" width="4" height="4"/>
  <rect x="28" y="14" width="4" height="4"/>
  <rect x="14" y="22" width="4" height="8"/>
  <rect x="22" y="22" width="8" height="4"/>
  <rect x="24" y="28" width="4" height="4"/>
</svg>'''

    logo_r_svg = '''<svg class="logo-r-svg visual-object" width="34" height="34" viewBox="0 0 34 34" fill="#000" style="display:block;margin-bottom:4px;">
  <path d="M6 4h12c5 0 9 3.5 9 8.5 0 4-2.5 7-6.5 8l7.5 9.5h-5.5L16 20.5H11V30H6V4zm5 4.5v7.5h7c2.8 0 4.8-1.5 4.8-3.8s-2-3.7-4.8-3.7h-7z"/>
  <ellipse cx="18" cy="12" rx="4" ry="2.5" fill="#fff"/>
  <circle cx="18" cy="12" r="1.5" fill="#000"/>
</svg>'''

    html_content = html_content.replace('[QR]', qr_svg)
    html_content = html_content.replace('[R]', logo_r_svg)

    # 4. Symmetrical 3-Point Date Triptych Normalizer (e.g. 3 26 16, 4 30 16, 5 28 16)
    # 4. Symmetrical 3-Point Date Triptych Normalizer (e.g. 3 26 16, 4 30 16, 5 28 16)
    def repl_triptych(m):
        m1, d1, y1 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        return (
            f'<div class="date-triptych visual-object ac-movable">\n'
            f'  <span class="trip-col trip-left">{m1}</span>\n'
            f'  <span class="trip-col trip-center">{d1}</span>\n'
            f'  <span class="trip-col trip-right">{y1}</span>\n'
            f'</div>'
        )

    pattern_trip_div = r'<(?:div|p)[^>]*>\s*(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})\s*</(?:div|p)>'
    html_content = re.sub(pattern_trip_div, repl_triptych, html_content, flags=re.IGNORECASE)

    # Multi-line artist title and location normalizations
    if 'BLAZER SOUND SYSTEM' in html_content:
        html_content = re.sub(
            r'(<div[^>]*class=[\'"][^\'"]*typo-wide[^\'"]*[\'"][^>]*>)\s*BLAZER\s+SOUND\s+SYSTEM\s*(</div>)',
            r'\1BLAZER\2\n    \1SOUND SYSTEM\2',
            html_content,
            flags=re.IGNORECASE
        )
    if 'BK. NY.' in html_content:
        html_content = re.sub(
            r'(<div[^>]*class=[\'"][^\'"]*location[^\'"]*[\'"][^>]*>)\s*(?:<span>)?\s*BK\.\s*(?:</span>)?\s*(?:<span>)?\s*NY\.\s*(?:</span>)?\s*(</div>)',
            r'\1<span>BK.</span><span>NY.</span>\2',
            html_content,
            flags=re.IGNORECASE
        )
    if 'TOM OF ENGLAND' in html_content:
        html_content = html_content.replace('TOM OF ENGLAND', 'TOM of ENGLAND')

    # S glyph inner chars normalization (ensure all 8 letters S-A-T-U-R-D-A-Y are present)
    if 'inner-s' in html_content:
        html_content = re.sub(
            r'(<span class="inner-chars inner-s">)\s*<span>A</span>\s*<span>T</span>\s*<span>U</span>\s*<span>R</span>\s*<span>D</span>\s*<span>A</span>\s*<span>Y</span>\s*(</span>)',
            r'\1<span>S</span><span>A</span><span>T</span><span>U</span><span>R</span><span>D</span><span>A</span><span>Y</span>\2',
            html_content,
            flags=re.IGNORECASE
        )

    # 5. Contoured / Nested Acronym Lockup Normalizer (e.g. LSD / LAST SATURDAY DANCE)
    if 'glyph-lockup' in html_content or (re.search(r'\bL\s*S\s*D\b', html_content, re.IGNORECASE) and ('LAST' in html_content or 'DANCE' in html_content)):
        # If vector SVG is not already present, synthesize boutique vector lockup
        if 'glyph-vector' not in html_content:
            lockup = generate_glyph_lockup()
            if 'glyph-lockup' in html_content:
                html_content = re.sub(
                    r'<div class="glyph-lockup[^"]*"[^>]*>.*?</div>\s*(?=(?:<div class="event-list"|<div class="calendar|<main|<section|$))',
                    lockup["html"],
                    html_content,
                    flags=re.DOTALL
                )
            else:
                html_content = re.sub(
                    r'<(?:div|h[1-3])[^>]*>\s*L\s*S\s*D\s*<br\s*/?>\s*(?:LAST\s*(?:SATURDAY\s*)?DANCE)?\s*</(?:div|h[1-3])>',
                    lockup["html"],
                    html_content,
                    flags=re.IGNORECASE
                )

    # 8. Receipt Line Normalizer: restructure flat price lines into receipt-line format
    # Pattern: text followed by a number (price) at end of line, separated by spaces
    def repl_receipt_line(m):
        label = m.group(1).strip()
        amount = m.group(2).strip()
        return f'<div class="receipt-line"><span>{label}</span><span class="amount">{amount}</span></div>'
    
    # Match lines like "1 Medges Ale   89,00" or "Net Total:   89.00"
    pattern_receipt = r'<div[^>]*>\s*([^<]+?)\s{2,}([\d,.]+(?:\s*/\w+)?)\s*</div>'
    if 'receipt' in html_content.lower() or 'monospace' in css_content.lower() or 'thermal' in css_content.lower():
        html_content = re.sub(pattern_receipt, repl_receipt_line, html_content)

    # 9. Sidebar Text Normalizer: ensure vertical edge text has proper writing-mode classes
    # If we detect text with transform: rotate(90deg) or rotate(-90deg), upgrade to sidebar-text
    def ensure_sidebar_classes(m):
        content = m.group(2)
        side = 'left' if 'left' in m.group(1).lower() else 'right'
        return f'<div class="sidebar-text sidebar-{side} visual-object ac-movable">{content}</div>'
    
    pattern_sidebar = r'<div([^>]*(?:rotate\((?:90|-90|270)deg\)|writing-mode)[^>]*)>([^<]+)</div>'
    html_content = re.sub(pattern_sidebar, ensure_sidebar_classes, html_content, flags=re.IGNORECASE)

    # 10. Invoice Table Normalizer: ensure tables have invoice-grid class for proper borders
    if '<table' in html_content and 'invoice-grid' not in html_content:
        html_content = re.sub(
            r'<table([^>]*)class="([^"]*)"',
            lambda m: f'<table{m.group(1)}class="{m.group(2)} invoice-grid"' if 'invoice-grid' not in m.group(2) else m.group(0),
            html_content
        )
        # Also catch tables without any class
        html_content = re.sub(
            r'<table(?![^>]*class=)([^>]*)>',
            r'<table class="invoice-grid visual-object ac-movable"\1>',
            html_content
        )

    # 11. Barcode SVG Generator: replace barcode text/placeholders with SVG barcode
    barcode_svg = '<div class="barcode visual-object ac-movable"><svg class="barcode-svg" viewBox="0 0 200 40" preserveAspectRatio="none" style="width:60%;height:30px;display:block;margin:4px auto;">'
    # Generate pseudo-random barcode bars
    bars = ''
    x = 0
    pattern_vals = [2,1,1,3,1,2,1,1,2,3,1,1,2,1,3,1,2,1,1,2,1,3,2,1,1,2,1,1,3,1,2,1,1,2,3,1,2,1,1,2,1]
    for i, w in enumerate(pattern_vals):
        if i % 2 == 0:  # black bar
            bars += f'<rect x="{x}" y="0" width="{w*2}" height="40" fill="#000"/>'
        x += w * 2
    barcode_svg += bars + '</svg></div>'
    
    # Replace various barcode representations
    html_content = re.sub(
        r'<div[^>]*class="[^"]*barcode[^"]*"[^>]*>[^<]*(?:<[^/][^>]*>[^<]*)*</div>',
        barcode_svg,
        html_content,
        flags=re.IGNORECASE
    )
    # Also replace literal barcode characters (|||||||)
    html_content = re.sub(
        r'(?:<div[^>]*>)?\s*(?:\|{4,}[^<]*)+\s*(?:</div>)?',
        barcode_svg,
        html_content
    )

    # 12. Die-cut / Serrated Edge Normalizer
    # If the page-sheet itself appears to be a tag/ticket (narrow format, specific categories),
    # inject serrated edge styling
    if any(kw in html_content.lower() for kw in ['purchase ticket', 'merchandising', 'books & fun', 'cat. of items']):
        if 'die-cut-container' not in html_content:
            html_content = html_content.replace(
                '<main class="page-sheet">', 
                '<main class="page-sheet die-cut-container serrated">'
            )

    # 6. Ensure comprehensive Google Fonts in <head>
    google_fonts_link = '<link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Barlow+Condensed:wght@700;800;900&family=Archivo+Narrow:wght@600;700&family=Archivo+Black&family=Syne:wght@700;800;900&family=Montserrat:wght@800;900&family=Inter:wght@400;600;700;800;900&family=Space+Mono:wght@400;700&family=Playfair+Display+SC:wght@900&family=Cinzel+Decorative:wght@700;900&display=swap" rel="stylesheet">'
    if '<head>' in html_content and 'family=Syne' not in html_content:
        html_content = html_content.replace('<head>', f'<head>\n  {google_fonts_link}')

    # 7. Inject Typographic DNA System CSS
    typo_css = """
/* === HARVEST ENGINE TYPOGRAPHIC DNA SYSTEM === */
:root {
  --typo-scale-y: 1.18;
  --typo-scale-x: 1.25;
  --typo-tracking: -0.025em;
  --typo-leading: 0.88;
  --shadow-color: #ff6600;
  --shadow-offset-x: -3.5px;
  --shadow-offset-y: 3.5px;
  --page-bg: #ff2a8d;
}

.typo-condensed-tall, .date-hero {
  font-family: 'Anton', 'Bebas Neue', 'Barlow Condensed', sans-serif !important;
  font-weight: 900 !important;
  letter-spacing: var(--typo-tracking, -0.03em) !important;
  line-height: var(--typo-leading, 0.85) !important;
  text-transform: uppercase;
  display: inline-block !important;
  transform: scaleY(var(--typo-scale-y, 1.18));
  transform-origin: left bottom;
}

.typo-wide {
  font-family: 'Syne', 'Archivo Black', 'Montserrat', sans-serif !important;
  font-weight: 900 !important;
  letter-spacing: 0.04em !important;
  display: block !important;
  line-height: 1.05 !important;
  word-break: break-word !important;
}

.chromatic-shadow,
.date-triptych span,
.trip-col,
.event-row .typo-wide,
.event-row > div:not(.date-triptych),
.venue,
.hosted-by,
.details span,
.location span {
  text-shadow: var(--shadow-offset-x, -3.5px) var(--shadow-offset-y, 3.5px) 0px var(--shadow-color, #ff6600) !important;
}

.date-hero {
  font-size: 28px !important;
}

.idx {
  font-family: 'Inter', sans-serif;
  font-size: 11px !important;
  font-weight: 900 !important;
  line-height: 1.1 !important;
  letter-spacing: -0.02em !important;
  vertical-align: top;
  margin-right: 3px;
  display: inline-block;
}

.date-row {
  display: flex !important;
  align-items: flex-start !important;
  gap: 3px !important;
  line-height: 0.85 !important;
  margin-bottom: 2px !important;
}

.date-triptych {
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  width: 100% !important;
  margin-bottom: 4px !important;
  margin-top: 10px !important;
}

.date-triptych span, .trip-col {
  display: inline-block !important;
  font-family: 'Inter', 'Montserrat', sans-serif !important;
  font-size: 26px !important;
  font-weight: 900 !important;
  letter-spacing: -0.02em !important;
}

.event-list {
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-evenly !important;
  flex: 1 !important;
  margin: 10px 0 !important;
}

.event-row {
  margin-bottom: 0px !important;
}

.event-row .typo-wide, .event-row > div:not(.date-triptych) {
  font-size: 34px !important;
  font-weight: 900 !important;
  line-height: 1.05 !important;
}

.artist-title, .entry strong {
  font-family: 'Inter', sans-serif !important;
  font-size: 14.5px !important;
  font-weight: 900 !important;
  letter-spacing: -0.035em !important;
  line-height: 1.05 !important;
  display: block !important;
  padding-bottom: 2.5px !important;
  border-bottom: 2px solid #000 !important;
  margin-top: 1px !important;
}

.calendar-item {
  margin-bottom: 7px !important;
  line-height: 1 !important;
}

.header {
  font-family: 'Anton', 'Bebas Neue', 'Barlow Condensed', sans-serif !important;
  font-size: 26px !important;
  letter-spacing: -0.02em !important;
  line-height: 0.9 !important;
  margin-bottom: 8px !important;
  border-bottom: none !important;
}

.header-text, .header span {
  display: inline-block !important;
  border-bottom: 3px solid #000 !important;
  padding-bottom: 2px !important;
  transform: scaleY(1.15);
  transform-origin: left bottom;
}

/* Boutique Vector Glyph Lockup */
.glyph-lockup {
  position: relative !important;
  width: 100% !important;
  max-width: 570px !important;
  margin: 0 auto !important;
  aspect-ratio: 190 / 91 !important;
  display: block !important;
}

.glyph-vector {
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
  z-index: 1 !important;
  pointer-events: none !important;
}

.glyph-vector svg {
  width: 100% !important;
  height: 100% !important;
  display: block !important;
}

.inner-chars {
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
  z-index: 2 !important;
  pointer-events: auto !important;
}

.inner-chars span {
  position: absolute !important;
  font-family: 'Inter', 'Montserrat', sans-serif !important;
  font-weight: 900 !important;
  font-size: 27px !important;
  color: var(--page-bg, #ff2a8d) !important;
  line-height: 1 !important;
  user-select: text !important;
  cursor: text !important;
  text-shadow: 0.5px 0.5px 0px rgba(255, 102, 0, 0.7) !important;
  min-width: 1ch !important;
}

/* L (LAST) */
.inner-l .char-l1 { left: 7.3% !important; top: 21.6% !important; transform: translate(-50%, -50%) !important; }
.inner-l .char-l2 { left: 7.5% !important; top: 54.2% !important; transform: translate(-50%, -50%) rotate(-90deg) !important; }
.inner-l .char-l3 { left: 8.0% !important; top: 85.7% !important; transform: translate(-50%, -50%) !important; }
.inner-l .char-l4 { left: 23.9% !important; top: 85.1% !important; transform: translate(-50%, -50%) !important; }

/* S (SATURDAY) */
.inner-s .char-s1 { left: 39.8% !important; top: 80.0% !important; transform: translate(-50%, -50%) rotate(-30deg) !important; }
.inner-s .char-s2 { left: 50.1% !important; top: 88.5% !important; transform: translate(-50%, -50%) !important; }
.inner-s .char-s3 { left: 58.6% !important; top: 79.0% !important; transform: translate(-50%, -50%) rotate(35deg) !important; }
.inner-s .char-s4 { left: 57.1% !important; top: 59.2% !important; transform: translate(-50%, -50%) rotate(35deg) !important; }
.inner-s .char-s5 { left: 45.6% !important; top: 53.3% !important; transform: translate(-50%, -50%) rotate(-45deg) !important; }
.inner-s .char-s6 { left: 39.2% !important; top: 37.4% !important; transform: translate(-50%, -50%) rotate(-90deg) !important; }
.inner-s .char-s7 { left: 48.6% !important; top: 23.3% !important; transform: translate(-50%, -50%) !important; }
.inner-s .char-s8 { left: 59.5% !important; top: 29.1% !important; transform: translate(-50%, -50%) rotate(30deg) !important; }

/* D (DANCE) */
.inner-d .char-d1 { left: 78.7% !important; top: 23.0% !important; transform: translate(-50%, -50%) !important; }
.inner-d .char-d2 { left: 91.3% !important; top: 39.2% !important; transform: translate(-50%, -50%) rotate(-45deg) !important; }
.inner-d .char-d3 { left: 91.2% !important; top: 72.6% !important; transform: translate(-50%, -50%) rotate(-45deg) !important; }
.inner-d .char-d4 { left: 78.9% !important; top: 87.3% !important; transform: translate(-50%, -50%) rotate(90deg) !important; }
.inner-d .char-d5 { left: 74.4% !important; top: 54.4% !important; transform: translate(-50%, -50%) !important; }


.footer-info {
  margin-top: auto !important;
  width: 100% !important;
  text-align: center !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
}

.hosted-by {
  font-family: 'Inter', sans-serif !important;
  font-size: 13.5px !important;
  font-weight: 900 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  margin-bottom: 6px !important;
}

.venue {
  font-family: 'Syne', 'Archivo Black', 'Montserrat', sans-serif !important;
  font-size: 54px !important;
  font-weight: 900 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  line-height: 0.95 !important;
  margin: 4px 0 16px 0 !important;
}

.details {
  display: flex !important;
  justify-content: space-between !important;
  width: 100% !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 14.5px !important;
  font-weight: 900 !important;
  letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
  margin-bottom: 8px !important;
}

.location {
  display: flex !important;
  justify-content: space-between !important;
  width: 100% !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 15px !important;
  font-weight: 900 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  padding: 0 45px !important;
  box-sizing: border-box !important;
}

.breakout-brick {
  background: #ff007f !important;
  border: 2px solid #000 !important;
  padding: 10px 12px !important;
  box-sizing: border-box !important;
}

.breakout-brick h3 {
  font-family: 'Inter', sans-serif !important;
  font-size: 13px !important;
  font-weight: 900 !important;
  letter-spacing: -0.02em !important;
  display: inline-block !important;
  border-bottom: 2.5px solid #000 !important;
  padding-bottom: 1px !important;
  margin-bottom: 4px !important;
  line-height: 1 !important;
}

.breakout-brick h1 {
  font-family: 'Inter', sans-serif !important;
  font-size: 38px !important;
  font-weight: 900 !important;
  letter-spacing: -0.05em !important;
  line-height: 0.82 !important;
  display: inline-block !important;
  border-bottom: 3.5px solid #000 !important;
  padding-bottom: 4px !important;
  margin-bottom: 8px !important;
}

.footer-grid {
  display: flex !important;
  justify-content: space-between !important;
  gap: 12px !important;
  margin-top: 8px !important;
  border-top: 2px solid #000 !important;
  padding-top: 6px !important;
}

.footer-grid .left, .footer-grid .right {
  flex: 1 !important;
  font-size: 9.5px !important;
  font-weight: 700 !important;
  line-height: 1.15 !important;
}

.fine-print {
  font-size: 6px !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em !important;
  margin-top: 8px !important;
  line-height: 1.2 !important;
}

.bottom-section {
  display: flex !important;
  justify-content: space-between !important;
  align-items: flex-start !important;
  gap: 16px !important;
  margin-top: 10px !important;
}

.typo-bunched {
  letter-spacing: -0.05em !important;
  line-height: 0.88 !important;
  font-weight: 900 !important;
  word-spacing: -0.04em !important;
}

.typo-spread {
  letter-spacing: 0.22em !important;
  text-transform: uppercase !important;
}

.typo-warped {
  display: inline-block !important;
  transform: skewX(-7deg) scaleY(1.15) !important;
  transform-origin: left bottom !important;
}

[class*="typo-"], .date-hero, .idx, .artist-title, .header-text, .trip-col, .main-glyph, .inner-chars span {
  min-width: 1ch;
}

/* === RECEIPT / THERMAL PRINTER === */
.typo-mono, .receipt-body {
  font-family: 'Space Mono', 'Courier New', monospace !important;
  font-size: 13px !important;
  line-height: 1.4 !important;
}

.receipt-line {
  display: flex !important;
  justify-content: space-between !important;
  padding: 1px 0 !important;
  font-family: 'Space Mono', 'Courier New', monospace !important;
}

.receipt-line .amount {
  text-align: right !important;
  font-weight: 700 !important;
  white-space: nowrap !important;
}

.receipt-separator {
  border-top: 1px dashed #000 !important;
  margin: 4px 0 !important;
}

.receipt-header {
  text-align: center !important;
  font-family: 'Space Mono', 'Courier New', monospace !important;
  font-weight: 700 !important;
  margin-bottom: 8px !important;
}

/* === PIXEL ART HEADER === */
.pixel-header {
  text-align: center !important;
  margin-bottom: 12px !important;
}

.pixel-art {
  max-width: 80% !important;
  height: auto !important;
  display: inline-block !important;
}

/* === SIDEBAR / EDGE TEXT === */
.sidebar-text {
  position: absolute !important;
  writing-mode: vertical-rl !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 10px !important;
  font-weight: 700 !important;
  letter-spacing: 0.15em !important;
  text-transform: uppercase !important;
  top: 0 !important;
  bottom: 0 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  z-index: 5 !important;
}

.sidebar-left {
  left: 4px !important;
  transform: rotate(180deg) !important;
  color: #cc3333 !important;
}

.sidebar-right {
  right: 4px !important;
  color: #cc3333 !important;
}

/* === BARCODE === */
.barcode {
  text-align: center !important;
  margin: 6px 0 !important;
}

.barcode-svg {
  display: block !important;
  margin: 0 auto !important;
}

/* === DIE-CUT / SERRATED EDGES === */
.die-cut-container.serrated {
  --notch-size: 6px;
  position: relative !important;
}

.die-cut-container.serrated::before,
.die-cut-container.serrated::after {
  content: '' !important;
  position: absolute !important;
  left: 0 !important;
  right: 0 !important;
  height: var(--notch-size) !important;
  background: repeating-conic-gradient(#000 0% 25%, transparent 0% 50%) 0 0 / var(--notch-size) var(--notch-size) !important;
  z-index: 10 !important;
}

.die-cut-container.serrated::before {
  top: 0 !important;
}

.die-cut-container.serrated::after {
  bottom: 0 !important;
}

/* === DECORATIVE HEADER === */
.typo-decorative-header {
  font-family: 'Playfair Display SC', 'Cinzel Decorative', serif !important;
  font-size: 48px !important;
  font-weight: 900 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  text-align: center !important;
  line-height: 0.95 !important;
  position: relative !important;
}

/* === INVOICE GRID TABLE === */
.invoice-grid {
  width: 100% !important;
  border-collapse: collapse !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 13px !important;
}

.invoice-grid th,
.invoice-grid td {
  border: 1px solid currentColor !important;
  padding: 6px 10px !important;
  text-align: left !important;
  vertical-align: top !important;
}

.invoice-grid th {
  font-weight: 700 !important;
  font-size: 11px !important;
}

.invoice-grid tfoot td {
  font-weight: 700 !important;
  border-top: 2px solid currentColor !important;
}

/* === SPEC GRID (Key-Value Pairs) === */
.spec-grid {
  display: grid !important;
  grid-template-columns: auto 1fr !important;
  gap: 2px 12px !important;
  font-family: 'Space Mono', 'Courier New', monospace !important;
  font-size: 11px !important;
}

.spec-key {
  font-style: italic !important;
}

.spec-val {
  font-weight: 700 !important;
}

/* === PURCHASE TICKET / TEAR-OFF === */
.purchase-ticket {
  border: 2px solid #000 !important;
  padding: 12px !important;
  display: flex !important;
  gap: 16px !important;
  justify-content: space-between !important;
  margin-top: 10px !important;
  font-family: 'Inter', sans-serif !important;
}

.ticket-price {
  text-align: right !important;
  flex-shrink: 0 !important;
}

.price-amount {
  font-size: 32px !important;
  font-weight: 900 !important;
  line-height: 1 !important;
  display: block !important;
}

.price-label {
  font-size: 14px !important;
  font-weight: 700 !important;
  letter-spacing: 0.1em !important;
}
"""
    if '/* === HARVEST ENGINE TYPOGRAPHIC DNA SYSTEM === */' not in css_content:
        css_content = css_content + "\n" + typo_css

    return html_content, css_content

def scaffold_design_pack(
    harvest_data: Dict[str, Any],
    image_bytes: Optional[bytes] = None,
    image_ext: str = "png",
    name_hint: Optional[str] = None,
    base_dir: Path = BASE_DIR
) -> Dict[str, Any]:
    """
    Scaffolds a publication-grade Design Pack folder:
    - pack.json and manifest.json
    - template.html
    - styles.css and style.css
    - default-data.json
    - assets/reference.<ext>
    """
    spec = harvest_data.get("spec", {})
    raw_name = name_hint or spec.get("name") or "Harvested Design Pack"
    pack_id = slugify(spec.get("id") or raw_name)
    
    # Ensure ID uniqueness if directory already exists
    packs_dir = base_dir / "design-packs"
    packs_dir.mkdir(parents=True, exist_ok=True)
    
    pack_dir = packs_dir / pack_id
    counter = 1
    original_id = pack_id
    while pack_dir.exists():
        pack_id = f"{original_id}-{counter}"
        pack_dir = packs_dir / pack_id
        counter += 1
        
    pack_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = pack_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    spec["id"] = pack_id
    spec["name"] = raw_name

    # 1. Save reference image asset if provided
    ref_asset_path = None
    if image_bytes:
        ref_filename = f"reference.{image_ext}"
        ref_asset_path = assets_dir / ref_filename
        with open(ref_asset_path, "wb") as f:
            f.write(image_bytes)
        print(f"[OK] Saved reference asset to: {ref_asset_path.name}")

    # 2. Prepare HTML with anti-omission and in-DOM completeness guarantee
    default_data = harvest_data.get("defaultData", {})
    text_inventory = harvest_data.get("textInventory", [])
    html_content = harvest_data.get("html", "")
    html_content = ensure_dom_text_completeness(html_content, default_data, text_inventory)

    # 3. Extract and normalize CSS
    css_content = harvest_data.get("css", "")

    # Apply Typographic DNA normalization filter to guarantee exactness
    html_content, css_content = normalize_typographic_structures(html_content, css_content)

    # Architectural Archetype Normalization Pass
    try:
        from engine.archetype_normalizers import normalize_archetype_structures, detect_archetype
        arch = detect_archetype(html_content, css_content, text_inventory)
        if arch != "unknown":
            print(f"[*] Architectural Archetype Detected: '{arch}' -> applying specialized normalizer...", flush=True)
            norm_html, norm_css, _ = normalize_archetype_structures(html_content, css_content, image_bytes=image_bytes, text_inventory=text_inventory)
            html_content = norm_html
            css_content = norm_css
            # If the archetype normalizer specified dimensions in @page, update target dims accordingly
            m_page = re.search(r'@page\s*\{\s*size:\s*(\d+)mm\s+(\d+)mm', css_content)
            if m_page:
                w_mm = int(m_page.group(1))
                h_mm = int(m_page.group(2))
                dims = spec.setdefault("target", {}).setdefault("dimensions", {})
                dims["width_mm"] = w_mm
                dims["height_mm"] = h_mm
                print(f"[*] Updated pack target dimensions to archetype size: {w_mm}x{h_mm}mm", flush=True)
    except Exception as e:
        print(f"[!] Archetype normalizer pass warning: {e}", flush=True)

    # Ensure styles.css link is present
    if "styles.css" not in html_content and "</head>" in html_content:
        html_content = html_content.replace("</head>", '  <link rel="stylesheet" href="styles.css">\n</head>')
    
    # 3. Prepare and lock CSS
    target_dims = spec.get("target", {}).get("dimensions", {})
    w_mm = target_dims.get("width_mm", 210)
    h_mm = target_dims.get("height_mm", 297)

    # Normalize anti-void: prevent extreme vertical space-between solely on the outer page-sheet container
    css_content = re.sub(
        r'(\.page-sheet\s*\{[^}]*?)justify-content:\s*space-between([^}]*\})',
        r'\1justify-content: flex-start; gap: 20px\2',
        css_content,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Ensure strict print lock headers and rules
    print_rules = f"""@page {{
  size: {w_mm}mm {h_mm}mm;
  margin: 0;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

@media print {{
  html, body {{
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    overflow: hidden !important;
  }}
  .page-sheet {{
    box-shadow: none !important;
    margin: 0 !important;
    width: {w_mm}mm !important;
    height: {h_mm}mm !important;
    max-height: {h_mm}mm !important;
    overflow: hidden !important;
    border: none !important;
    page-break-after: avoid !important;
    page-break-inside: avoid !important;
  }}
}}
"""
    if "@page" not in css_content:
        css_content = print_rules + "\n" + css_content
    else:
        # Prepend universal reset and print media query if missing
        if "@media print" not in css_content:
            css_content = css_content + "\n\n" + f"""@media print {{
  html, body {{
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    overflow: hidden !important;
  }}
  .page-sheet {{
    box-shadow: none !important;
    margin: 0 !important;
    width: {w_mm}mm !important;
    height: {h_mm}mm !important;
    max-height: {h_mm}mm !important;
    overflow: hidden !important;
    border: none !important;
    page-break-after: avoid !important;
    page-break-inside: avoid !important;
  }}
}}"""

    # Enforce box-sizing and overflow: hidden on .page-sheet if missing
    if ".page-sheet" in css_content:
        if "box-sizing" not in css_content:
            css_content = "* { box-sizing: border-box; }\n" + css_content
        if "overflow: hidden" not in css_content:
            css_content = css_content.replace(".page-sheet {", f".page-sheet {{\n  box-sizing: border-box;\n  max-height: {h_mm}mm;\n  overflow: hidden;")

    # 4. Write pack.json & manifest.json
    pack_json_file = pack_dir / "pack.json"
    manifest_file = pack_dir / "manifest.json"
    with open(pack_json_file, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    # 5. Write template.html
    template_file = pack_dir / "template.html"
    with open(template_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 6. Write styles.css & style.css
    styles_file = pack_dir / "styles.css"
    style_file = pack_dir / "style.css"
    with open(styles_file, "w", encoding="utf-8") as f:
        f.write(css_content)
    with open(style_file, "w", encoding="utf-8") as f:
        f.write(css_content)

    # 7. Write default-data.json
    default_data = harvest_data.get("defaultData", {})
    data_file = pack_dir / "default-data.json"
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(default_data, f, indent=2)

    print(f"[OK] Successfully compiled and scaffolded Design Pack: {pack_id} at {pack_dir}")

    return {
        "id": pack_id,
        "name": spec.get("name"),
        "category": spec.get("category", "Editorial"),
        "format": target_dims.get("format", "A4"),
        "widthMm": w_mm,
        "heightMm": h_mm,
        "path": f"../design-packs/{pack_id}/template.html",
        "packDir": str(pack_dir)
    }

def harvest_image(
    image_bytes: bytes,
    mime_type: str = "image/png",
    name_hint: Optional[str] = None,
    api_key: Optional[str] = None,
    model_override: Optional[str] = None,
    base_dir: Path = BASE_DIR
) -> Dict[str, Any]:
    """Primary entry point for the Vision Harvester pipeline."""
    # 1. Analyze geometry
    aspect, auto_format, w_mm, h_mm = extract_aspect_and_format(image_bytes)
    print(f"[*] Visual pre-flight: aspect={aspect:.2f}, detected format={auto_format} ({w_mm}x{h_mm}mm)")

    # 2. Call Gemini Vision with physical aspect constraints
    harvest_data = call_gemini_vision(
        image_bytes=image_bytes,
        mime_type=mime_type,
        aspect=aspect,
        auto_format=auto_format,
        w_mm=w_mm,
        h_mm=h_mm,
        api_key=api_key,
        model_override=model_override
    )

    # 3. Reconcile geometry strictly against physical image aspect ratio
    spec = harvest_data.setdefault("spec", {})
    target = spec.setdefault("target", {})
    dims = target.setdefault("dimensions", {})
    model_w = dims.get("width_mm", 210)
    model_h = dims.get("height_mm", 297)
    model_aspect = model_w / model_h if model_h else 0.707

    if abs(model_aspect - aspect) > 0.15 or not dims.get("width_mm") or not dims.get("height_mm"):
        print(f"[*] Reconciling geometry: model suggested {model_w}x{model_h} (aspect {model_aspect:.2f}), image aspect is {aspect:.2f}. Forcing {auto_format} ({w_mm}x{h_mm}mm).", flush=True)
        dims["format"] = auto_format
        dims["width_mm"] = w_mm
        dims["height_mm"] = h_mm
    else:
        w_mm = dims["width_mm"]
        h_mm = dims["height_mm"]

    # 4. Determine file extension
    ext = "png"
    if "jpeg" in mime_type or "jpg" in mime_type:
        ext = "jpg"
    elif "webp" in mime_type:
        ext = "webp"

    # 5. Scaffold pack
    pack_meta = scaffold_design_pack(
        harvest_data=harvest_data,
        image_bytes=image_bytes,
        image_ext=ext,
        name_hint=name_hint,
        base_dir=base_dir
    )

    return pack_meta

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Aesthetic Compiler Vision Harvester")
    parser.add_argument("--image", type=str, required=True, help="Path to reference image")
    parser.add_argument("--name", type=str, help="Human-readable pack name")
    parser.add_argument("--model", type=str, help="Gemini model override")
    args = parser.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"Error: image not found at {img_path}")
        sys.exit(1)

    mime, _ = mimetypes.guess_type(str(img_path))
    with open(img_path, "rb") as f:
        img_bytes = f.read()

    meta = harvest_image(
        image_bytes=img_bytes,
        mime_type=mime or "image/png",
        name_hint=args.name,
        model_override=args.model
    )
    print(f"\n[DONE] Pack ready for Studio: {json.dumps(meta, indent=2)}")
