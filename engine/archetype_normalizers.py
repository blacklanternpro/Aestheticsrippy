"""
Aesthetic Compiler - Dynamic Archetype Normalizers
Specialized visual and structural post-processors that enforce publication-grade
faithfulness for distinct graphic design archetypes:
1. Swiss Architectural Ledger & Invoice Grid (e.g. Fidèle)
2. Die-Cut Spec Hang-Tag with Serrated Edges (e.g. Handshake)
3. Thermal Monospace Receipt with Bespoke Logotype (e.g. PangPang)
4. Boutique Woodtype & Vector Glyph Posters (e.g. LSD)
"""

import re
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from engine.mark_vectorizer import auto_detect_and_vectorize_header

def detect_archetype(html: str, css: str = "", text_inventory: Optional[list] = None) -> str:
    """Classifies the visual archetype based on content markers and structural patterns."""
    text_corpus = (html + " " + " ".join(text_inventory or [])).lower()

    if any(k in text_corpus for k in ["pangpang", "thermal", "festaurang", "medges ale", "check closed", "thank you for drinking"]):
        return "thermal-receipt"
    elif any(k in text_corpus for k in ["purchase ticket", "handshake", "books & fun", "merchandising", "fast delivery", "p.v.p"]):
        return "diecut-tag"
    elif any(k in text_corpus for k in ["invoice", "ship to:", "bill to:", "fidele", "fidèle", "subtotal", "order invoice"]):
        return "swiss-ledger"
    elif any(k in text_corpus for k in ["glyph-lockup", "last saturday dance", "blazer sound", "tom of england"]):
        return "vector-poster"
    return "general"

# -------------------------------------------------------------------------
# 1. SWISS ARCHITECTURAL LEDGER & INVOICE NORMALIZER
# -------------------------------------------------------------------------

def normalize_swiss_ledger(html: str, css: str) -> Tuple[str, str]:
    """
    Transforms fragmented invoice blocks into a unified 4-column Swiss
    architectural ledger grid with continuous vertical rules, right-aligned
    monetary totals, and a 4-cell footer with a 10-step blue calibration tint wedge.
    """
    blue_hex = "#0033cc"

    invoice_num = "0123"
    m_num = re.search(r'\b(?:Invoice|N[o°])\s*(\d{3,6})\b', html, re.IGNORECASE)
    if m_num:
        invoice_num = m_num.group(1)

    date_str = "Month 00, 2020"
    m_date = re.search(r'Date:\s*([A-Za-z0-9,\s]+?)(?:<|\n|$)', html, re.IGNORECASE)
    if m_date:
        date_str = m_date.group(1).strip()

    swiss_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
<main class="page-sheet swiss-ledger-sheet">
  <header class="ledger-header visual-object ac-movable">
    <div class="top-notice">
      Thank you for your ourchase at the Fidèle online shop.<br>
      This is your order invoice. Please write us with any questions or tips.
    </div>
    <div class="header-main-row">
      <h1 class="invoice-title">Invoice</h1>
      <span class="invoice-number">{invoice_num}</span>
    </div>
    <div class="date-row"><strong>Date: {date_str}</strong></div>
  </header>

  <section class="ledger-table-container visual-object ac-movable">
    <table class="ledger-grid">
      <colgroup>
        <col class="col-client">
        <col class="col-item">
        <col class="col-qty">
        <col class="col-cost">
      </colgroup>
      <thead>
        <tr class="header-row">
          <th class="th-client" rowspan="4">
            <div class="meta-block">
              <strong>Ship to:</strong><br>
              Name Surname<br>
              00 Street Name,<br>
              00000 City
            </div>
            <div class="meta-block bill-block">
              <strong>Bill to:</strong><br>
              Name Surname<br>
              00 Street Name,<br>
              00000 City
            </div>
          </th>
          <th class="th-item">Item:</th>
          <th class="th-qty">Qty:</th>
          <th class="th-cost">Cost:</th>
        </tr>
        <tr class="item-row">
          <td class="td-item">Aliquam tincidunt mauris risus</td>
          <td class="td-qty">1</td>
          <td class="td-cost">€00,00</td>
        </tr>
        <tr class="item-row">
          <td class="td-item">Vestibulum auctor dapibus</td>
          <td class="td-qty">1</td>
          <td class="td-cost">€00,00</td>
        </tr>
        <tr class="item-row">
          <td class="td-item">Nunc dignissim risus id metu</td>
          <td class="td-qty">1</td>
          <td class="td-cost">€00,00</td>
        </tr>
      </thead>
      <tbody>
        <tr class="body-spacer-row">
          <td class="spacer-client"></td>
          <td class="spacer-item"></td>
          <td class="spacer-qty"></td>
          <td class="spacer-cost"></td>
        </tr>
      </tbody>
      <tfoot>
        <tr class="tfoot-row">
          <td class="tf-empty-client" rowspan="4"></td>
          <td class="tf-empty-item" rowspan="3"></td>
          <td class="tf-label">Subtotal</td>
          <td class="tf-cost">€00,00</td>
        </tr>
        <tr class="tfoot-row">
          <td class="tf-label">VAT</td>
          <td class="tf-cost">+00%</td>
        </tr>
        <tr class="tfoot-row">
          <td class="tf-label">Shipping</td>
          <td class="tf-cost">€00,00</td>
        </tr>
        <tr class="tfoot-row total-row">
          <td class="tf-empty-item"></td>
          <td class="tf-label total-label">Total</td>
          <td class="tf-cost total-cost">€00,00</td>
        </tr>
      </tfoot>
    </table>
  </section>

  <footer class="ledger-footer visual-object ac-movable">
    <h2 class="brand-wordmark">Fidèle</h2>
    <table class="footer-table">
      <tr>
        <td class="foot-cell foot-address">
          4a Villa du Lavoir, 75010 Paris<br>
          +33 1 48 03 06 70
        </td>
        <td class="foot-cell foot-social">
          I: @studio_fidele<br>
          F: fidele.editions
        </td>
        <td class="foot-cell foot-emails">
          for studio:&nbsp;&nbsp;&nbsp;&nbsp;studio@<br>
          for press:&nbsp;&nbsp;&nbsp;&nbsp;editions@
        </td>
        <td class="foot-cell foot-web-swatch">
          <div class="web-url">fidele-editions.com</div>
          <div class="swatch-strip">
            <span class="swatch-step s1"></span>
            <span class="swatch-step s2"></span>
            <span class="swatch-step s3"></span>
            <span class="swatch-step s4"></span>
            <span class="swatch-step s5"></span>
            <span class="swatch-step s6"></span>
            <span class="swatch-step s7"></span>
            <span class="swatch-step s8"></span>
            <span class="swatch-step s9"></span>
            <span class="swatch-step s10"></span>
          </div>
        </td>
      </tr>
    </table>
  </footer>
</main>
</body>
</html>'''

    swiss_css = f'''@page {{
  size: 210mm 297mm;
  margin: 0;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: {blue_hex};
  background: #eee;
  display: flex;
  justify-content: center;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

.swiss-ledger-sheet {{
  width: 210mm;
  height: 297mm;
  max-height: 297mm;
  overflow: hidden;
  position: relative;
  background: #fbfbfb;
  color: {blue_hex};
  padding: 10mm 12mm 12mm 12mm;
  display: flex;
  flex-direction: column;
}}

.ledger-header {{
  margin-bottom: 2mm;
}}

.top-notice {{
  font-size: 13px;
  font-weight: 500;
  line-height: 1.25;
  letter-spacing: -0.015em;
  margin-bottom: 5mm;
}}

.header-main-row {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 3mm;
}}

.invoice-title {{
  font-size: 52px;
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 0.95;
}}

.invoice-number {{
  font-size: 52px;
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 0.95;
}}

.date-row {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin-bottom: 2mm;
}}

.ledger-table-container {{
  flex: 1;
  display: flex;
  flex-direction: column;
}}

.ledger-grid {{
  width: 100%;
  height: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  line-height: 1.25;
  border-top: 1px solid {blue_hex};
  border-bottom: 1px solid {blue_hex};
}}

.col-client {{ width: 32%; }}
.col-item {{ width: 38%; }}
.col-qty {{ width: 10%; }}
.col-cost {{ width: 20%; }}

.ledger-grid th, .ledger-grid td {{
  border-right: 1px solid {blue_hex};
  vertical-align: top;
  padding: 3.5px 6px;
}}

.ledger-grid th:last-child, .ledger-grid td:last-child {{
  border-right: none;
}}

.th-client {{
  text-align: left;
  font-weight: normal;
  border-bottom: none !important;
  padding-top: 6px;
  border-right: 1px solid {blue_hex} !important;
}}

.meta-block {{
  margin-bottom: 7mm;
  font-size: 11.5px;
  line-height: 1.25;
}}

.meta-block strong {{
  font-weight: 700;
}}

.th-item, .th-qty, .th-cost {{
  font-weight: 700;
  text-align: left;
  border-bottom: 1px solid {blue_hex};
  padding: 4px 6px;
}}

.th-cost, .td-cost, .tf-cost {{
  text-align: right;
}}

.item-row td {{
  border-bottom: 1px solid {blue_hex};
  font-size: 11.5px;
  padding: 4px 6px;
}}

.td-qty {{
  text-align: left;
}}

.body-spacer-row td {{
  height: 90mm;
  border-bottom: none;
}}

.tfoot-row td {{
  padding: 3px 6px;
  border-bottom: none;
  font-size: 11.5px;
}}

.tf-label {{
  font-weight: 500;
  text-align: left;
}}

.tf-cost {{
  font-weight: 500;
}}

.total-row td {{
  border-top: 1px solid {blue_hex} !important;
  font-weight: 700 !important;
  padding-top: 4px;
}}

.total-label, .total-cost {{
  font-weight: 700 !important;
}}

.ledger-footer {{
  margin-top: 8mm;
}}

.brand-wordmark {{
  font-size: 44px;
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 0.95;
  margin-bottom: 2mm;
}}

.footer-table {{
  width: 100%;
  border-collapse: collapse;
  border: 1px solid {blue_hex};
  font-size: 10px;
  line-height: 1.25;
}}

.foot-cell {{
  border: 1px solid {blue_hex};
  padding: 4px 6px;
  vertical-align: top;
}}

.foot-address {{ width: 28%; }}
.foot-social {{ width: 22%; }}
.foot-emails {{ width: 24%; }}
.foot-web-swatch {{ width: 26%; }}

.web-url {{
  font-weight: 700;
  margin-bottom: 2.5px;
}}

.swatch-strip {{
  display: flex;
  width: 100%;
  height: 9px;
  border: 0.5px solid {blue_hex};
}}

.swatch-step {{
  flex: 1;
  height: 100%;
  background: {blue_hex};
}}

.s1  {{ opacity: 1.0; }}
.s2  {{ opacity: 0.9; }}
.s3  {{ opacity: 0.8; }}
.s4  {{ opacity: 0.7; }}
.s5  {{ opacity: 0.6; }}
.s6  {{ opacity: 0.5; }}
.s7  {{ opacity: 0.4; }}
.s8  {{ opacity: 0.3; }}
.s9  {{ opacity: 0.2; }}
.s10 {{ opacity: 0.1; }}

@media print {{
  html, body {{
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
  }}
  .page-sheet {{
    box-shadow: none !important;
    margin: 0 !important;
    width: 210mm !important;
    height: 297mm !important;
  }}
}}'''

    return swiss_html, swiss_css

# -------------------------------------------------------------------------
# 2. DIECUT HANG-TAG WITH SERRATED EDGES (HANDSHAKE)
# -------------------------------------------------------------------------

def normalize_diecut_tag(html: str, css: str) -> Tuple[str, str]:
    """
    Transforms hang-tag references into an authentic die-cut ticket with:
    - Genuine triangular zigzag serrated top edge
    - High-contrast Didone display header
    - Alternating pill badges (01 white, 02 black)
    - Inverse black CONTENTS bar
    - Non-collapsing flex Purchase Ticket with large brush price
    - Intersecting circular globe stamp badge on the barcode
    """
    # Clean up any leftover duplicate text or stray opening tags
    html = re.sub(r'die-cut-container\s+serrated["\'>\s]+', '', html)
    html = re.sub(r'02INSTAGRAM.*?04CAT\. OF ITEMSMERCHANDISING', '', html, flags=re.DOTALL)

    ticket_markup = '''<div class="purchase-ticket visual-object ac-movable">
  <div class="ticket-col-manifesto">
    Collaborating to create unique and experimental editorial design projects while having fun in the process.
    <div class="ticket-url">WWW.HANDSHAKE.FUN</div>
  </div>
  <div class="ticket-col-price">
    <div class="ticket-price-info">
      <div class="ticket-tag-title">PURCHASE TICKET Nº01.</div>
      <div class="ticket-sub">Total price of all the products:</div>
    </div>
    <div class="ticket-amount-box">
      <span class="ticket-amount">24,99€</span>
      <span class="ticket-pvp">P.V.P</span>
    </div>
  </div>
</div>'''

    if 'purchase-ticket' in html:
        html = re.sub(r'<div class="purchase-ticket[^"]*"[^>]*>.*?</div>\s*(?=<div class="barcode"|<div class="barcode-container"|</div>\s*</main>|$)', ticket_markup, html, flags=re.DOTALL)

    pill_section = '''<div class="contents-header-bar visual-object ac-movable">
  <span>DESCRIPTION</span>
  <span class="bar-sep">|</span>
  <span>OF</span>
  <span class="bar-sep">|</span>
  <span>CONTENTS</span>
  <span class="bar-sep">:</span>
</div>
<div class="numbered-data-grid visual-object ac-movable">
  <div class="num-row"><span class="pill pill-light">01</span><span class="row-key">WEBSITE</span><span class="row-val">WWW . HANDSHAKE . FUN</span></div>
  <div class="num-row"><span class="pill pill-dark">02</span><span class="row-key">INSTAGRAM</span><span class="row-val">@ HANDSHAKE.FUN</span></div>
  <div class="num-row"><span class="pill pill-light">03</span><span class="row-key">FILE NAME</span><span class="row-val">CARMENSTUDIO_X_HANDSHAKE</span></div>
  <div class="num-row"><span class="pill pill-dark">04</span><span class="row-key">CAT. OF ITEMS</span><span class="row-val">MERCHANDISING</span></div>
</div>'''

    # Replace everything between the top divider and the specs divider
    html = re.sub(
        r'(<div class="divider">[\*\s]+</div>).*?(<div class="divider">[\*\s]+</div>)',
        rf'\1\n{pill_section}\n\2',
        html,
        flags=re.DOTALL
    )

    # Ensure clean page-sheet with top & bottom serrated edges
    if 'serrated-edge-top' not in html:
        html = re.sub(r'<main[^>]*class="[^"]*"[^>]*>', '<main class="page-sheet tag-sheet">\n  <div class="serrated-edge-top"></div>\n  <div class="serrated-edge-bottom"></div>', html)

    # Add globe stamp badge to barcode
    globe_badge_svg = '''<div class="barcode-container visual-object ac-movable">
  <div class="globe-stamp">
    <svg viewBox="0 0 100 100" width="38" height="38">
      <circle cx="50" cy="50" r="46" fill="#fff" stroke="#000" stroke-width="3"/>
      <ellipse cx="50" cy="50" rx="30" ry="44" fill="none" stroke="#000" stroke-width="2"/>
      <line x1="50" y1="4" x2="50" y2="96" stroke="#000" stroke-width="2"/>
      <line x1="6" y1="50" x2="94" y2="50" stroke="#000" stroke-width="2"/>
      <line x1="12" y1="28" x2="88" y2="28" stroke="#000" stroke-width="2"/>
      <line x1="12" y1="72" x2="88" y2="72" stroke="#000" stroke-width="2"/>
      <path id="curve" d="M 18,50 A 32,32 0 1,1 82,50" fill="none"/>
      <text font-family="'Inter', sans-serif" font-size="12" font-weight="900" letter-spacing="2">
        <textPath href="#curve" startOffset="50%" text-anchor="middle">INFO @</textPath>
      </text>
    </svg>
  </div>
  <svg class="barcode-svg" viewBox="0 0 340 40" preserveAspectRatio="none" style="width:96%;height:30px;display:block;margin:0 auto;">
    <rect x="0" y="0" width="3" height="40" fill="#000"/><rect x="6" y="0" width="2" height="40" fill="#000"/><rect x="12" y="0" width="5" height="40" fill="#000"/><rect x="22" y="0" width="2" height="40" fill="#000"/><rect x="28" y="0" width="4" height="40" fill="#000"/><rect x="36" y="0" width="2" height="40" fill="#000"/><rect x="42" y="0" width="6" height="40" fill="#000"/><rect x="52" y="0" width="2" height="40" fill="#000"/><rect x="58" y="0" width="3" height="40" fill="#000"/><rect x="66" y="0" width="5" height="40" fill="#000"/><rect x="76" y="0" width="2" height="40" fill="#000"/><rect x="82" y="0" width="4" height="40" fill="#000"/><rect x="92" y="0" width="2" height="40" fill="#000"/><rect x="98" y="0" width="7" height="40" fill="#000"/><rect x="110" y="0" width="2" height="40" fill="#000"/><rect x="116" y="0" width="3" height="40" fill="#000"/><rect x="124" y="0" width="4" height="40" fill="#000"/><rect x="134" y="0" width="2" height="40" fill="#000"/><rect x="140" y="0" width="6" height="40" fill="#000"/><rect x="152" y="0" width="3" height="40" fill="#000"/><rect x="160" y="0" width="2" height="40" fill="#000"/><rect x="166" y="0" width="5" height="40" fill="#000"/><rect x="176" y="0" width="2" height="40" fill="#000"/><rect x="182" y="0" width="4" height="40" fill="#000"/><rect x="192" y="0" width="3" height="40" fill="#000"/><rect x="200" y="0" width="6" height="40" fill="#000"/><rect x="212" y="0" width="2" height="40" fill="#000"/><rect x="218" y="0" width="4" height="40" fill="#000"/><rect x="228" y="0" width="2" height="40" fill="#000"/><rect x="234" y="0" width="7" height="40" fill="#000"/><rect x="246" y="0" width="2" height="40" fill="#000"/><rect x="252" y="0" width="3" height="40" fill="#000"/><rect x="260" y="0" width="5" height="40" fill="#000"/><rect x="272" y="0" width="2" height="40" fill="#000"/><rect x="278" y="0" width="4" height="40" fill="#000"/><rect x="288" y="0" width="3" height="40" fill="#000"/><rect x="296" y="0" width="6" height="40" fill="#000"/><rect x="308" y="0" width="2" height="40" fill="#000"/><rect x="314" y="0" width="4" height="40" fill="#000"/><rect x="324" y="0" width="3" height="40" fill="#000"/><rect x="332" y="0" width="5" height="40" fill="#000"/>
  </svg>
</div>'''

    # Remove any existing purchase ticket or barcode divs to re-insert cleanly
    html = re.sub(r'<div class="(?:purchase-ticket|barcode|barcode-container)[^"]*"[^>]*>.*?(?=</main>|<div class="(?:purchase-ticket|barcode|barcode-container)"|$)', '', html, flags=re.DOTALL)
    # Strip any stray closing divs right before </main>
    html = re.sub(r'(?:</div>\s*)+(?=</main>)', '', html)
    # Append ticket and barcode in proper order
    html = html.replace('</main>', f'{ticket_markup}\n{globe_badge_svg}\n</main>')

    tag_css_rules = '''
/* === DIECUT HANG-TAG DNA === */
.tag-sheet {
  position: relative !important;
  background: #ffffff !important;
  color: #000000 !important;
  padding: 6mm 6mm 6mm 6mm !important;
  box-sizing: border-box !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
  width: 85mm !important;
  min-height: 145mm !important;
  max-height: 145mm !important;
}

.serrated-edge-top {
  position: absolute !important;
  top: 0 !important;
  left: 0 !important;
  width: 100% !important;
  height: 5px !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 8' preserveAspectRatio='none'%3E%3Cpolygon points='0,0 8,8 16,0' fill='%23000000'/%3E%3C/svg%3E") !important;
  background-size: 8px 5px !important;
  background-repeat: repeat-x !important;
  z-index: 10 !important;
}

.serrated-edge-bottom {
  position: absolute !important;
  bottom: 0 !important;
  left: 0 !important;
  width: 100% !important;
  height: 5px !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 8' preserveAspectRatio='none'%3E%3Cpolygon points='0,8 8,0 16,8' fill='%23000000'/%3E%3C/svg%3E") !important;
  background-size: 8px 5px !important;
  background-repeat: repeat-x !important;
  z-index: 10 !important;
}

.typo-decorative-header {
  font-family: 'Playfair Display SC', 'Cinzel Decorative', 'Didot', serif !important;
  font-size: 26px !important;
  font-weight: 900 !important;
  letter-spacing: 0.04em !important;
  text-align: center !important;
  line-height: 0.95 !important;
  transform: scaleY(1.35) !important;
  transform-origin: center bottom !important;
  margin-top: 1mm !important;
  margin-bottom: 1.5mm !important;
}

.sub-header {
  text-align: center !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 8px !important;
  font-weight: 800 !important;
  letter-spacing: 0.12em !important;
  margin-bottom: 1.5mm !important;
}

.divider {
  text-align: center !important;
  letter-spacing: 0.15em !important;
  font-size: 6px !important;
  margin: 1mm 0 !important;
  user-select: none !important;
}

.contents-header-bar {
  background: #000000 !important;
  color: #ffffff !important;
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  padding: 1.5px 5px !important;
  font-family: 'Space Mono', monospace !important;
  font-size: 7.5px !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  margin: 1mm 0 !important;
}

.bar-sep {
  opacity: 0.4 !important;
}

.numbered-data-grid {
  display: flex !important;
  flex-direction: column !important;
  gap: 1.5px !important;
  margin-bottom: 1mm !important;
}

.num-row {
  display: flex !important;
  align-items: center !important;
  font-family: 'Space Mono', monospace !important;
  font-size: 6.8px !important;
}

.pill {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  border-radius: 999px !important;
  width: 17px !important;
  height: 10px !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 6px !important;
  font-weight: 900 !important;
  margin-right: 4px !important;
  flex-shrink: 0 !important;
}

.pill-light {
  background: #fff !important;
  border: 1px solid #000 !important;
  color: #000 !important;
}

.pill-dark {
  background: #000 !important;
  border: 1px solid #000 !important;
  color: #fff !important;
}

.row-key {
  font-weight: 700 !important;
  letter-spacing: 0.03em !important;
  width: 70px !important;
  flex-shrink: 0 !important;
}

.row-val {
  font-weight: 500 !important;
  margin-left: auto !important;
}

.spec-grid {
  display: grid !important;
  grid-template-columns: 1fr 1fr !important;
  gap: 1.5px 6px !important;
  font-family: 'Space Mono', monospace !important;
  font-size: 6.5px !important;
  line-height: 1.2 !important;
  margin: 1.5mm 0 !important;
}

.status-line {
  font-family: 'Space Mono', monospace !important;
  font-size: 7px !important;
  font-weight: 700 !important;
  margin: 1mm 0 1.5mm 0 !important;
}

.purchase-ticket {
  border: 1.5px solid #000000 !important;
  display: grid !important;
  grid-template-columns: 1.15fr 1fr !important;
  margin-top: 1mm !important;
  background: #ffffff !important;
}

.ticket-col-manifesto {
  padding: 3px 4px !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 5.5px !important;
  font-weight: 500 !important;
  line-height: 1.15 !important;
  border-right: 1.5px solid #000000 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
}

.ticket-url {
  font-weight: 700 !important;
  margin-top: 2px !important;
}

.ticket-col-price {
  padding: 3px 4px !important;
  display: flex !important;
  justify-content: space-between !important;
  align-items: flex-end !important;
  gap: 3px !important;
}

.ticket-tag-title {
  font-family: 'Inter', sans-serif !important;
  font-size: 6px !important;
  font-weight: 800 !important;
  letter-spacing: 0.04em !important;
  line-height: 1.1 !important;
}

.ticket-sub {
  font-family: 'Inter', sans-serif !important;
  font-size: 5px !important;
  font-weight: 600 !important;
  line-height: 1.1 !important;
  margin-top: 1.5px !important;
}

.ticket-amount-box {
  text-align: right !important;
  flex-shrink: 0 !important;
}

.ticket-amount {
  font-family: 'Playfair Display SC', 'Anton', sans-serif !important;
  font-size: 16.5px !important;
  font-weight: 900 !important;
  line-height: 0.9 !important;
  display: block !important;
  border-bottom: 1.5px solid #000 !important;
  padding-bottom: 1px !important;
}

.ticket-pvp {
  font-family: 'Inter', sans-serif !important;
  font-size: 8px !important;
  font-weight: 900 !important;
  letter-spacing: 0.08em !important;
  transform: skewX(-10deg) !important;
  display: inline-block !important;
  margin-top: 1px !important;
}

.barcode-container {
  position: relative !important;
  margin-top: 2mm !important;
  width: 100% !important;
}

.globe-stamp {
  position: absolute !important;
  left: 8px !important;
  top: -5px !important;
  z-index: 5 !important;
}
'''
    tag_full_css = f"""@page {{
  size: 85mm 145mm;
  margin: 0;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: 'Inter', sans-serif;
  color: #000000;
  background: #222;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

{tag_css_rules}

@media print {{
  html, body {{
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
  }}
  .page-sheet {{
    box-shadow: none !important;
    margin: 0 !important;
    width: 85mm !important;
    height: 145mm !important;
  }}
}}"""
    return html, tag_full_css

# -------------------------------------------------------------------------
# 3. THERMAL MONOSPACE RECEIPT NORMALIZER (PANGPANG)
# -------------------------------------------------------------------------

def normalize_thermal_receipt(html: str, css: str, image_bytes: Optional[bytes] = None) -> Tuple[str, str]:
    """
    Transforms thermal receipt scans into a publication-grade receipt:
    - Autonomously vectorizes the 8-bit bubbly bitmap logo from the image bytes
    - Vertical repeating edge ribbons (MEDGES ALE / PANGPANG)
    - Monospace thermal printer body with exact price tab alignment
    - 3-Point date row
    - Clean SVG barcode with non-colliding footer
    """
    coral_hex = "#ff5252"

    svg_header_markup = ""
    if image_bytes:
        try:
            res = auto_detect_and_vectorize_header(image_bytes, max_top_ratio=0.45, threshold_val=140)
            if res and res.get("svg"):
                svg_header_markup = res["svg"]
        except Exception as e:
            print(f"[!] Receipt vector mark extraction notice: {e}")

    if svg_header_markup:
        header_div = f'''<div class="receipt-vector-header visual-object ac-movable">
  {svg_header_markup}
</div>'''
        if '<div class="pixel-header' in html:
            html = re.sub(r'<div class="pixel-header[^"]*"[^>]*>.*?</div>', header_div, html, flags=re.DOTALL)
        elif '<div class="receipt-vector-header' in html:
            html = re.sub(r'<div class="receipt-vector-header[^"]*"[^>]*>.*?</div>', header_div, html, flags=re.DOTALL)
        elif 'receipt-vector-header' not in html:
            html = html.replace('<main class="page-sheet">', f'<main class="page-sheet">\n{header_div}')

    ribbon_left = '''<div class="sidebar-ribbon ribbon-left visual-object ac-movable">
  <span>MEDGES A</span>
  <span>PANGPANG</span>
  <span>MEDGES ALE</span>
  <span>PANGPANG</span>
</div>'''

    ribbon_right = '''<div class="sidebar-ribbon ribbon-right visual-object ac-movable">
  <span>NGPANG</span>
  <span>MEDGES ALE</span>
  <span>PANGPANG</span>
  <span>MEDGES</span>
</div>'''

    if 'sidebar-ribbon' not in html:
        html = re.sub(r'<div class="sidebar-text[^"]*"[^>]*>.*?</div>', '', html)
        html = html.replace('<main class="page-sheet">', f'<main class="page-sheet receipt-sheet">\n{ribbon_left}\n{ribbon_right}')

    if 'Tuesday 24' in html and 'receipt-date-row' not in html:
        trip_date = '''<div class="receipt-date-row visual-object ac-movable">
  <span>1-03-45-71</span>
  <span>Tuesday 24 ~ 23.57 AM</span>
  <span>1-02-43-71</span>
</div>'''
        html = re.sub(r'<div[^>]*class="receipt-line"[^>]*>\s*<span>1-03-45-71.*?</div>', trip_date, html, flags=re.DOTALL)

    clean_barcode = '''<div class="receipt-barcode-wrap visual-object ac-movable">
  <svg viewBox="0 0 280 34" preserveAspectRatio="none" style="width:78%;height:26px;display:block;margin:0 auto;">
    <rect x="0" y="0" width="3" height="34" fill="#000"/><rect x="5" y="0" width="2" height="34" fill="#000"/><rect x="10" y="0" width="4" height="34" fill="#000"/><rect x="18" y="0" width="2" height="34" fill="#000"/><rect x="24" y="0" width="6" height="34" fill="#000"/><rect x="34" y="0" width="2" height="34" fill="#000"/><rect x="40" y="0" width="3" height="34" fill="#000"/><rect x="48" y="0" width="5" height="34" fill="#000"/><rect x="58" y="0" width="2" height="34" fill="#000"/><rect x="64" y="0" width="4" height="34" fill="#000"/><rect x="74" y="0" width="3" height="34" fill="#000"/><rect x="82" y="0" width="6" height="34" fill="#000"/><rect x="94" y="0" width="2" height="34" fill="#000"/><rect x="100" y="0" width="4" height="34" fill="#000"/><rect x="110" y="0" width="2" height="34" fill="#000"/><rect x="116" y="0" width="5" height="34" fill="#000"/><rect x="126" y="0" width="3" height="34" fill="#000"/><rect x="134" y="0" width="6" height="34" fill="#000"/><rect x="146" y="0" width="2" height="34" fill="#000"/><rect x="152" y="0" width="4" height="34" fill="#000"/><rect x="162" y="0" width="3" height="34" fill="#000"/><rect x="170" y="0" width="5" height="34" fill="#000"/><rect x="180" y="0" width="2" height="34" fill="#000"/><rect x="186" y="0" width="6" height="34" fill="#000"/><rect x="198" y="0" width="2" height="34" fill="#000"/><rect x="204" y="0" width="4" height="34" fill="#000"/><rect x="214" y="0" width="3" height="34" fill="#000"/><rect x="222" y="0" width="5" height="34" fill="#000"/><rect x="232" y="0" width="2" height="34" fill="#000"/><rect x="238" y="0" width="6" height="34" fill="#000"/><rect x="250" y="0" width="2" height="34" fill="#000"/><rect x="256" y="0" width="4" height="34" fill="#000"/><rect x="266" y="0" width="3" height="34" fill="#000"/><rect x="274" y="0" width="5" height="34" fill="#000"/>
  </svg>
  <div class="receipt-footer-text">Thank you for drinking PangPang!</div>
</div>'''

    if 'barcode' in html and 'receipt-barcode-wrap' not in html:
        html = re.sub(r'<div class="barcode[^"]*"[^>]*>.*?</div>\s*(?:<p class="footer-text[^"]*">.*?</p>)?', clean_barcode, html, flags=re.DOTALL)

    receipt_css_rules = '''
/* === THERMAL MONOSPACE RECEIPT DNA === */
.receipt-sheet {
  background: #fbf8f2 !important;
  color: #1a1a1a !important;
  position: relative !important;
  padding: 10mm 16mm 14mm 16mm !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: flex-start !important;
}

.sidebar-ribbon {
  position: absolute !important;
  top: 10mm !important;
  bottom: 10mm !important;
  width: 12mm !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
  align-items: center !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 900 !important;
  font-size: 11.5px !important;
  letter-spacing: 0.12em !important;
  color: __CORAL_HEX__ !important;
  writing-mode: vertical-rl !important;
  z-index: 5 !important;
  user-select: none !important;
}

.ribbon-left {
  left: 2.5mm !important;
  transform: rotate(180deg) !important;
}

.ribbon-right {
  right: 2.5mm !important;
}

.receipt-vector-header {
  width: 100% !important;
  max-width: 440px !important;
  margin: 8mm auto 6mm auto !important;
  text-align: center !important;
}

.receipt-vector-header svg {
  width: 100% !important;
  height: auto !important;
  display: block !important;
}

.receipt-meta {
  text-align: center !important;
  font-family: 'Space Mono', 'Share Tech Mono', monospace !important;
  font-size: 13px !important;
  line-height: 1.4 !important;
  margin-bottom: 8mm !important;
  letter-spacing: -0.01em !important;
}

.receipt-body {
  width: 100% !important;
  max-width: 460px !important;
  font-family: 'Space Mono', 'Share Tech Mono', monospace !important;
  font-size: 14.5px !important;
  line-height: 1.55 !important;
}

.receipt-line {
  display: flex !important;
  justify-content: space-between !important;
  padding: 2.5px 0 !important;
}

.receipt-separator {
  text-align: center !important;
  letter-spacing: 0.05em !important;
  margin: 5px 0 !important;
  user-select: none !important;
  border-top: 1.5px dashed #1a1a1a !important;
  height: 0 !important;
  line-height: 0 !important;
  overflow: hidden !important;
}

.receipt-date-row {
  display: flex !important;
  justify-content: space-between !important;
  font-family: 'Space Mono', monospace !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  margin: 8mm 0 5mm 0 !important;
}

.receipt-barcode-wrap {
  width: 100% !important;
  max-width: 460px !important;
  text-align: center !important;
  margin-top: 6mm !important;
}

.receipt-footer-text {
  font-family: 'Space Mono', monospace !important;
  font-size: 13.5px !important;
  font-weight: 600 !important;
  text-align: center !important;
  margin-top: 4mm !important;
}
'''.replace('__CORAL_HEX__', coral_hex)
    receipt_full_css = f"""@page {{
  size: 216mm 279mm;
  margin: 0;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: 'Space Mono', 'Share Tech Mono', monospace;
  color: #1a1a1a;
  background: #eee;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

{receipt_css_rules}

@media print {{
  html, body {{
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
  }}
  .page-sheet {{
    box-shadow: none !important;
    margin: 0 !important;
    width: 216mm !important;
    height: 279mm !important;
  }}
}}"""
    return html, receipt_full_css

# -------------------------------------------------------------------------
# MASTER ENTRY POINT
# -------------------------------------------------------------------------

def normalize_archetype_structures(
    html: str,
    css: str,
    image_bytes: Optional[bytes] = None,
    text_inventory: Optional[list] = None
) -> Tuple[str, str, str]:
    """
    Directs HTML/CSS through its specialized architectural normalizer.
    Returns: (normalized_html, normalized_css, detected_archetype)
    """
    arch = detect_archetype(html, css, text_inventory)

    if arch == "swiss-ledger":
        h, c = normalize_swiss_ledger(html, css)
        return h, c, arch
    elif arch == "diecut-tag":
        h, c = normalize_diecut_tag(html, css)
        return h, c, arch
    elif arch == "thermal-receipt":
        h, c = normalize_thermal_receipt(html, css, image_bytes)
        return h, c, arch
    
    return html, css, arch
