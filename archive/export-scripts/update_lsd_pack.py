from pathlib import Path

pack_dir = Path('design-packs/lsd-event-poster')
svg_text = Path('export/lsd_traced.svg').read_text(encoding='utf-8')

html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Barlow+Condensed:wght@700;800;900&family=Archivo+Narrow:wght@600;700&family=Archivo+Black&family=Syne:wght@700;800;900&family=Montserrat:wght@800;900&family=Inter:wght@400;600;700;800;900&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
  <meta charset="UTF-8">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
<main class="page-sheet">
  <div class="glyph-lockup visual-object ac-movable">
    <div class="glyph-vector">
      {svg_text}
    </div>
    <div class="inner-chars inner-l">
      <span class="char-l1">L</span>
      <span class="char-l2">A</span>
      <span class="char-l3">S</span>
      <span class="char-l4">T</span>
    </div>
    <div class="inner-chars inner-s">
      <span class="char-s1">S</span>
      <span class="char-s2">A</span>
      <span class="char-s3">T</span>
      <span class="char-s4">U</span>
      <span class="char-s5">R</span>
      <span class="char-s6">D</span>
      <span class="char-s7">A</span>
      <span class="char-s8">Y</span>
    </div>
    <div class="inner-chars inner-d">
      <span class="char-d1">D</span>
      <span class="char-d2">A</span>
      <span class="char-d3">N</span>
      <span class="char-d4">C</span>
      <span class="char-d5">E</span>
    </div>
  </div>

  <div class="event-list visual-object ac-movable">
    <div class="event-row">
      <div class="date-triptych"><span>3</span><span>26</span><span>16</span></div>
      <div class="typo-wide">TOM of ENGLAND</div>
      <div class="typo-wide">IVAN BERKO</div>
    </div>
    <div class="event-row">
      <div class="date-triptych"><span>4</span><span>30</span><span>16</span></div>
      <div class="typo-wide">BLAZER</div>
      <div class="typo-wide">SOUND SYSTEM</div>
    </div>
    <div class="event-row">
      <div class="date-triptych"><span>5</span><span>28</span><span>16</span></div>
      <div class="typo-wide">GEORGIA</div>
    </div>
  </div>

  <div class="footer-info visual-object ac-movable">
    <div class="hosted-by">HOSTED BY DJ KAYGEE</div>
    <div class="venue typo-wide">MAGICK CITY</div>
    <div class="details"><span>FREE TEA</span> <span>ALL NIGHT</span> <span>'TILL DAYLIGHT!</span></div>
    <div class="location"><span>BK.</span><span>NY.</span></div>
  </div>
</main>
</body>
</html>'''

css_content = '''@page {
  size: 210mm 297mm;
  margin: 0;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --page-bg: #ff2a8d;
  --shadow-color: #ff6600;
  --shadow-offset-x: -3.5px;
  --shadow-offset-y: 3.5px;
}

body {
  margin: 0;
  padding: 0;
  display: flex;
  justify-content: center;
  background: #111;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

.page-sheet {
  width: 210mm;
  height: 297mm;
  max-height: 297mm;
  padding: 14mm 18mm 12mm 18mm;
  background: var(--page-bg, #ff2a8d);
  color: #000000;
  font-family: 'Syne', 'Archivo Black', sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
}

/* === VECTOR BOUTIQUE GLYPH LOCKUP === */
.glyph-lockup {
  position: relative;
  width: 100%;
  max-width: 570px;
  margin: 0 auto;
  aspect-ratio: 190 / 91;
  display: block;
}

.glyph-vector {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
}

.glyph-vector svg {
  width: 100%;
  height: 100%;
  display: block;
}

.inner-chars {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
  pointer-events: auto;
}

.inner-chars span {
  position: absolute;
  font-family: 'Inter', 'Montserrat', sans-serif;
  font-weight: 900;
  font-size: 24px;
  color: var(--page-bg, #ff2a8d);
  line-height: 1;
  transform: translate(-50%, -50%);
  user-select: text;
  cursor: text;
  text-shadow: 0.5px 0.5px 0px rgba(255, 102, 0, 0.5);
  min-width: 1ch;
}

/* L (LAST) */
.inner-l .char-l1 { left: 11.0%; top: 24.0%; }
.inner-l .char-l2 { left: 11.0%; top: 46.0%; transform: translate(-50%, -50%) rotate(-90deg); }
.inner-l .char-l3 { left: 11.0%; top: 78.0%; }
.inner-l .char-l4 { left: 24.0%; top: 78.0%; }

/* S (SATURDAY) */
.inner-s .char-s1 { left: 40.5%; top: 77.0%; transform: translate(-50%, -50%) rotate(-20deg); }
.inner-s .char-s2 { left: 51.5%; top: 84.0%; }
.inner-s .char-s3 { left: 61.0%; top: 74.0%; transform: translate(-50%, -50%) rotate(35deg); }
.inner-s .char-s4 { left: 57.0%; top: 54.0%; transform: translate(-50%, -50%) rotate(-30deg); }
.inner-s .char-s5 { left: 46.5%; top: 44.0%; transform: translate(-50%, -50%) rotate(-60deg); }
.inner-s .char-s6 { left: 41.5%; top: 28.0%; transform: translate(-50%, -50%) rotate(-20deg); }
.inner-s .char-s7 { left: 51.5%; top: 18.0%; }
.inner-s .char-s8 { left: 61.0%; top: 24.0%; transform: translate(-50%, -50%) rotate(30deg); }

/* D (DANCE) */
.inner-d .char-d1 { left: 77.0%; top: 18.0%; }
.inner-d .char-d2 { left: 88.5%; top: 29.0%; transform: translate(-50%, -50%) rotate(35deg); }
.inner-d .char-d3 { left: 91.0%; top: 52.0%; transform: translate(-50%, -50%) rotate(75deg); }
.inner-d .char-d4 { left: 83.5%; top: 76.0%; transform: translate(-50%, -50%) rotate(125deg); }
.inner-d .char-d5 { left: 74.5%; top: 49.0%; }

/* === TRIPTYCH DATES === */
.date-triptych {
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  width: 100% !important;
  margin-bottom: 2px !important;
  margin-top: 6px !important;
}

.date-triptych span, .trip-col {
  display: inline-block !important;
  font-family: 'Inter', 'Montserrat', sans-serif !important;
  font-size: 26px !important;
  font-weight: 900 !important;
  letter-spacing: -0.02em !important;
  text-shadow: var(--shadow-offset-x, -3px) var(--shadow-offset-y, 3px) 0px var(--shadow-color, #ff6600) !important;
}

/* === EVENT LIST & LINEUP === */
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
  font-family: 'Syne', 'Archivo Black', 'Montserrat', sans-serif !important;
  font-size: 36px !important;
  font-weight: 900 !important;
  letter-spacing: 0.04em !important;
  line-height: 1.05 !important;
  display: block !important;
  word-break: break-word !important;
  text-shadow: var(--shadow-offset-x, -3.5px) var(--shadow-offset-y, 3.5px) 0px var(--shadow-color, #ff6600) !important;
}

/* === FOOTER INFO === */
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
  font-size: 14px !important;
  font-weight: 900 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  margin-bottom: 6px !important;
  text-shadow: var(--shadow-offset-x, -2px) var(--shadow-offset-y, 2px) 0px var(--shadow-color, #ff6600) !important;
}

.venue {
  font-family: 'Syne', 'Archivo Black', 'Montserrat', sans-serif !important;
  font-size: 56px !important;
  font-weight: 900 !important;
  letter-spacing: 0.06em !important;
  line-height: 0.95 !important;
  margin: 4px 0 16px 0 !important;
  text-shadow: var(--shadow-offset-x, -4px) var(--shadow-offset-y, 4px) 0px var(--shadow-color, #ff6600) !important;
}

.details {
  display: flex !important;
  justify-content: space-between !important;
  width: 100% !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 15px !important;
  font-weight: 900 !important;
  letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
  margin-bottom: 8px !important;
}

.details span {
  display: inline-block !important;
  text-shadow: var(--shadow-offset-x, -2px) var(--shadow-offset-y, 2px) 0px var(--shadow-color, #ff6600) !important;
}

.location {
  display: flex !important;
  justify-content: space-between !important;
  width: 100% !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 16px !important;
  font-weight: 900 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  padding: 0 40px !important;
  box-sizing: border-box !important;
}

.location span {
  display: inline-block !important;
  text-shadow: var(--shadow-offset-x, -2px) var(--shadow-offset-y, 2px) 0px var(--shadow-color, #ff6600) !important;
}

@media print {
  html, body {
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    overflow: hidden !important;
  }
  .page-sheet {
    box-shadow: none !important;
    margin: 0 !important;
    width: 210mm !important;
    height: 297mm !important;
    max-height: 297mm !important;
    overflow: hidden !important;
    border: none !important;
    page-break-after: avoid !important;
    page-break-inside: avoid !important;
  }
}
'''

(pack_dir / 'template.html').write_text(html_content, encoding='utf-8')
(pack_dir / 'styles.css').write_text(css_content, encoding='utf-8')
(pack_dir / 'style.css').write_text(css_content, encoding='utf-8')
print('Updated lsd-event-poster with vector boutique glyph lockup!')
