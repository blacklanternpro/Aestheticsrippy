"""
Aesthetic Compiler - CLI Engine
Compiles Design Packs and Data Payloads into pixel-perfect HTML and Vector PDFs.
"""

import os
import sys
import json
import argparse
import subprocess
import re
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from engine.schema import DesignPackSpec

CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def list_packs():
    packs_dir = BASE_DIR / "design-packs"
    return [p.name for p in packs_dir.iterdir() if p.is_dir() and (p / "pack.json").exists()]

def validate_pack(pack_id: str) -> DesignPackSpec:
    pack_path = BASE_DIR / "design-packs" / pack_id / "pack.json"
    if not pack_path.exists():
        raise FileNotFoundError(f"Pack '{pack_id}' not found at {pack_path}")
    
    with open(pack_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    spec = DesignPackSpec.from_dict(data)
    return spec

def compile_pack(pack_id: str, output_pdf: Optional[str] = None):
    spec = validate_pack(pack_id)
    print(f"[*] Validated Design Pack: '{spec.name}' ({spec.id})")
    
    pack_dir = BASE_DIR / "design-packs" / pack_id
    template_path = pack_dir / "template.html"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found at {template_path}")
        
    export_dir = BASE_DIR / "export"
    export_dir.mkdir(exist_ok=True)
    
    if not output_pdf:
        output_pdf = export_dir / f"{pack_id}.pdf"
    else:
        output_pdf = Path(output_pdf)

    # Compile using Headless Chromium
    print(f"[*] Rendering vector PDF with headless Chromium: {output_pdf.name}")
    cmd = [
        CHROME_BIN,
        "--headless=new",
        "--disable-gpu",
        f"--print-to-pdf={output_pdf}",
        "--no-pdf-header-footer",
        template_path.as_uri()
    ]
    subprocess.run(cmd, check=True)
    
    # Verify Page Count
    with open(output_pdf, "rb") as f:
        content = f.read().decode("latin1", errors="ignore")
    page_count = len(re.findall(r"/Type\s*/Page\b", content))
    
    status = "SUCCESS (Strict 1-Sheet Locked)" if page_count == 1 else f"WARNING ({page_count} Pages)"
    print(f"[OK] Compiled {spec.name} -> {output_pdf} [{status}]")
    return output_pdf, page_count

def compile_all():
    packs = list_packs()
    print(f"Found {len(packs)} Design Packs: {', '.join(packs)}")
    results = {}
    for p in packs:
        _, pages = compile_pack(p)
        results[p] = pages
    
    print("\n--- Summary ---")
    all_single_sheet = True
    for p, pages in results.items():
        print(f"  • {p}: {pages} page(s)")
        if pages > 1:
            all_single_sheet = False
    
    if all_single_sheet:
        print("\nAll Design Packs verified strictly single-sheet!")
    else:
        print("\nSome Design Packs exceeded 1 sheet.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aesthetic Compiler CLI")
    parser.add_argument("--pack", type=str, help="Design Pack ID to compile")
    parser.add_argument("--all", action="store_true", help="Compile all available packs")
    parser.add_argument("--output", type=str, help="Path to output PDF")
    
    args = parser.parse_args()
    
    if args.all or not args.pack:
        compile_all()
    else:
        compile_pack(args.pack, args.output)
