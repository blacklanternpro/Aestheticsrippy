import subprocess
from pathlib import Path

svg_text = Path('export/pangpang_vector_header.svg').read_text(encoding='utf-8')
html = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background:#faf6ed;margin:40px;display:flex;justify-content:center;">
  <div style="width:400px;color:#222;">
    {svg_text}
  </div>
</body>
</html>'''

preview_path = Path('export/test_svg_preview.html')
preview_path.write_text(html, encoding='utf-8')

# Render to PDF then PNG
chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\edtli\AppData\Local\Google\Chrome\Application\chrome.exe"
]
chrome = next((p for p in chrome_paths if Path(p).exists()), "chrome")

pdf_out = Path('export/test_svg_preview.pdf')
cmd = [
    chrome,
    "--headless=new",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={pdf_out.resolve()}",
    str(preview_path.resolve())
]
subprocess.run(cmd, check=True)

import pypdfium2 as pdfium
pdf = pdfium.PdfDocument(str(pdf_out))
page = pdf[0]
bitmap = page.render(scale=2)
img = bitmap.to_pil()
img.save('export/test_svg_preview.png')
pdf.close()
print("Preview PNG generated: export/test_svg_preview.png")
