from pathlib import Path
import subprocess

html_content = '''<!DOCTYPE html>
<html>
<head>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Syne:wght@800;900&family=Bowlby+One&family=Paytone+One&family=Titan+One&family=Rubik+Mono+One&family=Bungee&family=Montserrat:wght@900&display=swap" rel="stylesheet">
<style>
body { background: #ff2a8d; margin: 20px; font-weight: 900; }
.test-row { margin-bottom: 24px; }
.label { font-family: monospace; font-size: 14px; color: #fff; margin-bottom: 4px; }
.lsd { font-size: 100px; line-height: 0.8; color: #000; text-shadow: -3px 3px 0 #ff6600; display: inline-block; letter-spacing: 0.05em; }
</style>
</head>
<body>
<div class="test-row"><div class="label">Archivo Black</div><div class="lsd" style="font-family: 'Archivo Black', sans-serif;">L S D</div></div>
<div class="test-row"><div class="label">Syne 900</div><div class="lsd" style="font-family: 'Syne', sans-serif;">L S D</div></div>
<div class="test-row"><div class="label">Bowlby One</div><div class="lsd" style="font-family: 'Bowlby One', cursive;">L S D</div></div>
<div class="test-row"><div class="label">Titan One</div><div class="lsd" style="font-family: 'Titan One', cursive;">L S D</div></div>
<div class="test-row"><div class="label">Paytone One</div><div class="lsd" style="font-family: 'Paytone One', sans-serif;">L S D</div></div>
<div class="test-row"><div class="label">Rubik Mono One</div><div class="lsd" style="font-family: 'Rubik Mono One', sans-serif;">L S D</div></div>
<div class="test-row"><div class="label">Bungee</div><div class="lsd" style="font-family: 'Bungee', cursive;">L S D</div></div>
</body>
</html>'''

test_file = Path('export/test_fonts.html')
test_file.write_text(html_content, encoding='utf-8')

cmd = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    '--headless=new',
    '--disable-gpu',
    f'--print-to-pdf={Path("export/test_fonts.pdf").resolve()}',
    str(test_file.resolve())
]
subprocess.run(cmd, check=True)

import pypdfium2 as pdfium
pdf = pdfium.PdfDocument('export/test_fonts.pdf')
pdf[0].render(scale=1.5).to_pil().save('export/test_fonts.png')
print('Rendered font test!')
