from pathlib import Path
import sys

base_dir = Path("C:/Users/edtli/aesthetic-compiler")
sys.path.append(str(base_dir))

from engine.archetype_normalizers import normalize_archetype_structures
import subprocess
import pypdfium2 as pdfium

packs = [
    ("fidele-invoice-0123", "media_1790388075132.jpg"),
    ("handshake-receipt-ledger", "media_1790387881407.jpg"),
    ("pangpang-receipt-poster", "media_1790387773618.jpg")
]

base_dir = Path("C:/Users/edtli/aesthetic-compiler")

for pack_id, img_name in packs:
    pack_dir = base_dir / "design-packs" / pack_id
    html_file = pack_dir / "template.html"
    css_file = pack_dir / "styles.css"
    img_file = Path("C:/Users/edtli/.gemini/antigravity/brain/97c85a98-ec5e-498d-ae9c-22bef916c1db/.user_uploaded") / img_name

    html = html_file.read_text(encoding="utf-8")
    css = css_file.read_text(encoding="utf-8")
    img_bytes = img_file.read_bytes() if img_file.exists() else None

    norm_html, norm_css, arch = normalize_archetype_structures(html, css, image_bytes=img_bytes)
    print(f"[{pack_id}] Detected archetype: {arch}")

    # Write normalized files
    html_file.write_text(norm_html, encoding="utf-8")
    css_file.write_text(norm_css, encoding="utf-8")
    (pack_dir / "style.css").write_text(norm_css, encoding="utf-8")

    # Compile with engine/compiler.py
    cmd = ["python", "engine/compiler.py", "--pack", pack_id]
    subprocess.run(cmd, check=True)

    # Render preview PNG
    pdf_path = base_dir / "export" / f"{pack_id}.pdf"
    if pdf_path.exists():
        pdf = pdfium.PdfDocument(str(pdf_path))
        img = pdf[0].render(scale=2).to_pil()
        out_png = base_dir / "export" / f"{pack_id}_normalized.png"
        img.save(str(out_png))
        pdf.close()
        print(f"[{pack_id}] Rendered preview -> {out_png}")

print("\nAll 3 packs successfully normalized and rendered!")
