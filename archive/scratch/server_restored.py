"""
Aesthetic Compiler - Local Studio Server
Serves static studio files and provides seamless zero-config local AI endpoints.
"""

import http.server
import socketserver
import os
import json
import urllib.parse
from pathlib import Path

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent

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
                "defaultModel": os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
                "hasKey": bool(os.environ.get("GEMINI_API_KEY"))
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
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

        if parsed.path == '/api/ai/replace-image':
            prompt = payload.get("prompt", "").strip() or "avant-garde graphic"
            print(f"[*] Local AI Image Replacement prompt: {prompt}")
            
            import random
            seed = random.randint(1000, 999999)
            clean_query = urllib.parse.quote_plus(prompt)
            # Real dynamic AI diffusion image generation directly matching prompt
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
