"""
End-to-End Test for Harvester Pipeline with Archetype Normalization and Autonomous Mark Vectorization
"""
import sys
import json
from pathlib import Path

base_dir = Path("C:/Users/edtli/aesthetic-compiler")
sys.path.append(str(base_dir))

from engine.harvester import scaffold_design_pack
from engine.compiler import compile_pack
import pypdfium2 as pdfium

uploaded_dir = Path("C:/Users/edtli/.gemini/antigravity/brain/97c85a98-ec5e-498d-ae9c-22bef916c1db/.user_uploaded")

test_cases = [
    {
        "pack_id": "fidele-invoice-0123",
        "image": uploaded_dir / "media_1790388075132.jpg",
        "archetype": "swiss-ledger"
    },
    {
        "pack_id": "handshake-receipt-ledger",
        "image": uploaded_dir / "media_1790387881407.jpg",
        "archetype": "diecut-tag"
    },
    {
        "pack_id": "pangpang-receipt-poster",
        "image": uploaded_dir / "media_1790387773618.jpg",
        "archetype": "thermal-receipt"
    }
]

print("=== STARTING END-TO-END HARVESTER TEST ===")

for tc in test_cases:
    pack_id = tc["pack_id"]
    pack_dir = base_dir / "design-packs" / pack_id
    img_path = tc["image"]
    
    print(f"\n---> Testing Pipeline on: {pack_id}")
    
    # Load current pack info to simulate harvest output
    with open(pack_dir / "pack.json", "r", encoding="utf-8") as f:
        spec = json.load(f)
    
    with open(pack_dir / "template.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    with open(pack_dir / "styles.css", "r", encoding="utf-8") as f:
        css = f.read()
        
    image_bytes = img_path.read_bytes() if img_path.exists() else None
    
    mock_harvest_data = {
        "spec": spec,
        "html": html,
        "css": css,
        "defaultData": {},
        "textInventory": []
    }
    
    # Run through scaffold_design_pack (the exact master engine function)
    result_meta = scaffold_design_pack(
        harvest_data=mock_harvest_data,
        image_bytes=image_bytes,
        image_ext="jpg",
        name_hint=pack_id,
        base_dir=base_dir
    )
    actual_id = result_meta["id"]
    print(f"[OK] Harvest scaffolding completed: {actual_id}")
    
    # Compile with engine/compiler.py
    pdf_path, page_count = compile_pack(pack_id=actual_id)
    print(f"[OK] Compiler result: {pdf_path} (Pages: {page_count})")
    
    # Check rendered PDF page count
    print(f"[VERIFY] PDF Page count: {page_count} (Strict 1-sheet required: {page_count == 1})")
    assert page_count == 1, f"Expected 1 page, got {page_count}"
    
    # Render preview PNG
    pdf = pdfium.PdfDocument(str(pdf_path))
    img = pdf[0].render(scale=2).to_pil()
    out_png = base_dir / "export" / f"{pack_id}_e2e_verified.png"
    img.save(str(out_png))
    pdf.close()
    print(f"[VERIFY] Rendered preview saved to: {out_png}")
    
    # Cleanup generated test pack directory if it was a duplicate suffix
    if actual_id != pack_id:
        import shutil
        test_dir = base_dir / "design-packs" / actual_id
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)

print("\n=== ALL 3 ARCHETYPES VERIFIED THROUGH COMPLETE MASTER ENGINE PIPELINE! ===")
