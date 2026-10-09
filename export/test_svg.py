from pathlib import Path
import subprocess
import pypdfium2 as pdfium

svg_text = Path('export/lsd_traced.svg').read_text(encoding='utf-8')

html_content = f'''<!DOCTYPE html>
<html>
<head>
<style>
body {{ background: #ff2a8d; margin: 40px; display: flex; justify-content: center; }}
.box {{ width: 600px; }}
</style>
</head>
<body>
<div class="box">
{svg_text}
</div>
</body>
</html>'''

Path('export/test_svg.html').write_text(html_content, encoding='utf-8')

cmd = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    '--headless=new',
    '--disable-gpu',
    f'--print-to-pdf={Path("export/test_svg.pdf").resolve()}',
    str(Path('export/test_svg.html').resolve())
]
subprocess.run(cmd, check=True)

pdf = pdfium.PdfDocument('export/test_svg.pdf')
pdf[0].render(scale=2).to_pil().save('export/test_svg.png')
print('Rendered SVG test to export/test_svg.png!')
