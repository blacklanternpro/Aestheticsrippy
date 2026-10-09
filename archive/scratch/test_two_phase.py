import os
import urllib.request
import urllib.error
import json
import base64
import time
from pathlib import Path

key = os.environ.get("GEMINI_API_KEY", "")
img_path = Path(r'C:\Users\edtli\reference_images\img_7.png')

with open(img_path, 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('utf-8')

print("[Phase 1] Extracting Visual DNA from image...", flush=True)
p1_prompt = """Deconstruct this graphic design scan into its precise design DNA. Return a JSON object with:
- archetype: (e.g. Editorial Poster, Exhibition Card, Tabular Ledger, Thermal Receipt, Industrial Slip)
- format: (A4 | A5 | Thermal-80mm | Card-Square | US-Letter)
- width_mm: integer
- height_mm: integer
- background_hex: string
- primary_ink_hex: string
- accent_hex: string
- fonts: { primary: string, display: string, monospace: string }
- visual_objects: list of objects (cutouts, photos, stamps, logos, barcodes)
- content_blocks: list of text blocks with estimated hierarchy (headline, subtitle, metadata, body) and actual text from image.
Output ONLY JSON."""

p1_payload = {
    'contents': [{
        'parts': [
            {'text': p1_prompt},
            {'inline_data': {'mime_type': 'image/png', 'data': b64}}
        ]
    }]
}

url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={key}'
req = urllib.request.Request(url, data=json.dumps(p1_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})

with urllib.request.urlopen(req, timeout=30) as res:
    d1 = json.loads(res.read())
    spec_text = d1['candidates'][0]['content']['parts'][0]['text']
    print("[Phase 1 SUCCESS!]", flush=True)
    print(spec_text[:300], flush=True)

# Clean json
spec_clean = spec_text.strip()
if spec_clean.startswith('```'):
    spec_clean = spec_clean.split('```')[1]
    if spec_clean.startswith('json'):
        spec_clean = spec_clean[4:]
spec_obj = json.loads(spec_clean.strip())

print("\n[Phase 2] Synthesizing print-locked HTML and CSS from Visual DNA (text-only call)...", flush=True)
p2_prompt = f"""You are a master print CSS and semantic HTML engineer.
Given this design specification extracted from a graphic scan:
{json.dumps(spec_obj, indent=2)}

Synthesize a boutique, publication-grade single-sheet Design Pack.
Output a JSON object with:
- html: Complete valid HTML5 starting with <!DOCTYPE html>, linking Google Fonts and styles.css, with <main class="page-sheet"> containing semantic elements with data-field="..." on all text, and class="visual-object" on graphic containers.
- css: Complete CSS starting with @page {{ size: {spec_obj.get('width_mm', 180)}mm {spec_obj.get('height_mm', 180)}mm; margin: 0; }} and .page-sheet locked to that size, with print-color-adjust: exact, and zero overflow.
Output ONLY valid JSON."""

p2_payload = {
    'contents': [{
        'parts': [{'text': p2_prompt}]
    }]
}

req2 = urllib.request.Request(url, data=json.dumps(p2_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req2, timeout=30) as res:
    d2 = json.loads(res.read())
    code_text = d2['candidates'][0]['content']['parts'][0]['text']
    print("\n[Phase 2 SUCCESS!]", flush=True)
    print(code_text[:400], flush=True)
