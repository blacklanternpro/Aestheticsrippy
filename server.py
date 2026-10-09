"""
Aesthetic Compiler - Local Studio Server
Serves static studio files and provides seamless zero-config local AI endpoints.
Includes dynamic Design Pack discovery and the Magic Vision Harvester endpoint.
"""

import http.server
import socketserver
import os
import sys
import json
import urllib.parse
import base64
from pathlib import Path

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from engine.harvester import harvest_image, DEFAULT_API_KEY, GEMINI_MODELS

class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_headers(self):
        # Enable CORS for local testing
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                "status": "ok",
                "mode": "local",
                "defaultModel": os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
                "hasKey": bool(DEFAULT_API_KEY or os.environ.get("GEMINI_API_KEY")),
                "availableModels": GEMINI_MODELS
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        elif parsed.path == '/api/packs':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            packs = []
            packs_dir = BASE_DIR / "design-packs"
            if packs_dir.exists():
                for p in sorted(packs_dir.iterdir()):
                    if p.is_dir():
                        spec_file = p / "pack.json"
                        if not spec_file.exists():
                            spec_file = p / "manifest.json"
                        if spec_file.exists():
                            try:
                                with open(spec_file, "r", encoding="utf-8") as f:
                                    spec = json.load(f)
                                dims = spec.get("target", {}).get("dimensions", {})
                                packs.append({
                                    "id": spec.get("id", p.name),
                                    "name": spec.get("name", p.name),
                                    "category": spec.get("category", "Editorial"),
                                    "format": dims.get("format", "A4"),
                                    "widthMm": dims.get("width_mm", 210),
                                    "heightMm": dims.get("height_mm", 297),
                                    "path": f"../design-packs/{p.name}/template.html"
                                })
                            except Exception as e:
                                print(f"[!] Error reading pack spec for {p.name}: {e}")
            self.wfile.write(json.dumps({"status": "success", "packs": packs}).encode('utf-8'))
            return
        
        # Redirect root to studio/
        if parsed.path in ('', '/'):
            self.send_response(302)
            self.send_header('Location', '/studio/')
            self.end_headers()
            return
            
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
        
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if parsed.path == '/api/harvest':
            try:
                image_b64 = payload.get("imageBase64", "")
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                if not image_b64:
                    raise ValueError("No image data provided in payload.")

                image_bytes = base64.b64decode(image_b64)
                mime_type = payload.get("mimeType", "image/png")
                pack_name = payload.get("packName") or "Harvested Design Pack"
                api_key = payload.get("apiKey")
                model = payload.get("model")

                print(f"[*] Studio Harvest request: '{pack_name}' ({len(image_bytes)} bytes)")
                pack_meta = harvest_image(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    name_hint=pack_name,
                    api_key=api_key,
                    model_override=model,
                    base_dir=BASE_DIR
                )

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "pack": pack_meta
                }).encode('utf-8'))
                return
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "error",
                    "error": str(e)
                }).encode('utf-8'))
                return

        elif parsed.path == '/api/ai/replace-image':
            prompt = payload.get("prompt", "").strip() or "avant-garde graphic"
            print(f"[*] Local AI Image Replacement prompt: {prompt}")
            
            import random
            seed = random.randint(1000, 999999)
            clean_query = urllib.parse.quote_plus(prompt)
            image_url = f"https://image.pollinations.ai/prompt/{clean_query}?width=800&height=800&nologo=true&seed={seed}"
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "imageUrl": image_url,
                "prompt": prompt
            }).encode('utf-8'))
            return

        elif parsed.path == '/api/ai/rewrite':
            text = payload.get("text", "")
            instruction = payload.get("instruction", "make punchier")
            print(f"[*] Local AI Rewrite: '{text}' ({instruction})")
            
            rewritten = text.strip()
            if "punchier" in instruction.lower():
                rewritten = " ".join(text.split()[:max(1, int(len(text.split()) * 0.8))])
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "rewritten": rewritten
            }).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StudioHandler) as httpd:
        print(f"[OK] Aesthetic Compiler Studio Server running at http://localhost:{PORT}/studio/")
        httpd.serve_forever()

if __name__ == '__main__':
    run_server()
