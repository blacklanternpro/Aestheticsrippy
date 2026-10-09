from pathlib import Path
import subprocess
import pypdfium2 as pdfium

svg_text = Path('export/lsd_traced.svg').read_text(encoding='utf-8')

html_content = f'''<!DOCTYPE html>
<html>
<head>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@900&family=Montserrat:wght@900&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #ff2a8d;
  margin: 0;
  padding: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}}

.glyph-lockup {{
  position: relative;
  width: 580px;
  aspect-ratio: 190 / 91;
  display: block;
}}

.glyph-vector {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
}}

.inner-chars {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
  pointer-events: auto;
}}

.inner-chars span {{
  position: absolute;
  font-family: 'Inter', 'Montserrat', sans-serif;
  font-weight: 900;
  font-size: 26px;
  color: #ff2a8d;
  line-height: 1;
  transform: translate(-50%, -50%);
  user-select: text;
  cursor: text;
  text-shadow: 0.5px 0.5px 0px rgba(255, 102, 0, 0.4);
}}

/* L (LAST) */
.inner-l .char-l1 {{ left: 11.0%; top: 24.0%; }}
.inner-l .char-l2 {{ left: 11.0%; top: 46.0%; transform: translate(-50%, -50%) rotate(-90deg); }}
.inner-l .char-l3 {{ left: 11.0%; top: 78.0%; }}
.inner-l .char-l4 {{ left: 23.5%; top: 78.0%; }}

/* S (SATURDAY) */
.inner-s .char-s1 {{ left: 40.5%; top: 77.0%; transform: translate(-50%, -50%) rotate(-20deg); }}
.inner-s .char-s2 {{ left: 51.5%; top: 84.0%; }}
.inner-s .char-s3 {{ left: 61.0%; top: 74.0%; transform: translate(-50%, -50%) rotate(35deg); }}
.inner-s .char-s4 {{ left: 57.0%; top: 54.0%; transform: translate(-50%, -50%) rotate(-30deg); }}
.inner-s .char-s5 {{ left: 46.5%; top: 44.0%; transform: translate(-50%, -50%) rotate(-60deg); }}
.inner-s .char-s6 {{ left: 41.5%; top: 28.0%; transform: translate(-50%, -50%) rotate(-20deg); }}
.inner-s .char-s7 {{ left: 51.5%; top: 18.0%; }}
.inner-s .char-s8 {{ left: 61.0%; top: 24.0%; transform: translate(-50%, -50%) rotate(30deg); }}

/* D (DANCE) */
.inner-d .char-d1 {{ left: 77.0%; top: 18.0%; }}
.inner-d .char-d2 {{ left: 88.5%; top: 29.0%; transform: translate(-50%, -50%) rotate(35deg); }}
.inner-d .char-d3 {{ left: 91.0%; top: 52.0%; transform: translate(-50%, -50%) rotate(75deg); }}
.inner-d .char-d4 {{ left: 83.5%; top: 76.0%; transform: translate(-50%, -50%) rotate(125deg); }}
.inner-d .char-d5 {{ left: 74.5%; top: 49.0%; }}
</style>
</head>
<body>

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

</body>
</html>'''

test_html = Path('export/test_lockup_full.html')
test_html.write_text(html_content, encoding='utf-8')

cmd = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    '--headless=new',
    '--disable-gpu',
    f'--print-to-pdf={Path("export/test_lockup_full.pdf").resolve()}',
    str(test_html.resolve())
]
subprocess.run(cmd, check=True)

pdf = pdfium.PdfDocument('export/test_lockup_full.pdf')
pdf[0].render(scale=2).to_pil().save('export/test_lockup_full.png')
print('Rendered test_lockup_full.png with calibrated positions!')
