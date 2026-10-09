"""
Aestheticsrippy - local studio server.

  python server.py   ->  http://127.0.0.1:8080/studio/

Serves the studio and a small JSON API:

  GET  /api/health                 engine status
  GET  /api/packs                  every Design Pack (legacy + Rip)
  GET  /api/rip-packs              Rip packs with their rip.json and default data
  GET  /api/content                your files in content/private/
  GET  /api/content/<name>         one content file
  PUT  /api/content/<name>         save a content file (JSON only)
  POST /api/export                 render {pack, data, variant, styles, tokens} to PDF
  POST /api/harvest                vision-harvest an image into a legacy pack
  POST /api/ai/replace-image       legacy studio image helper

Only the folders the studio needs are served as static files, dotfiles never
are, and content/private serves photos only (its JSON goes through the API),
so a .env in the project root or your content cannot leak by URL. The server binds to
loopback by default (AC_HOST / AC_PORT to change).
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import random
import re
import socketserver
import sys
import threading
import traceback
import urllib.parse
from pathlib import Path

PORT = int(os.environ.get("AC_PORT", "8080"))
HOST = os.environ.get("AC_HOST", "127.0.0.1")
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

CONTENT_DIR = Path(os.environ.get("AC_CONTENT_DIR", BASE_DIR / "content" / "private"))
PACKS_DIR = BASE_DIR / "design-packs"
STATIC_PREFIXES = ("/studio/", "/design-packs/", "/fonts/", "/export/")
IMAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,120}\.(png|jpe?g|webp|gif)$", re.I)
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
CONTENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,120}\.json$")
MAX_BODY = 40 * 1024 * 1024  # photos travel as data URLs

class RenderWorker:
    """
    Playwright's sync API must stay on the thread that started it, and the
    server handles requests on many threads. So one worker thread owns a
    long-lived headless Chromium and runs renders from a queue.
    """

    def __init__(self):
        import queue
        self.jobs = queue.Queue()
        self.thread = None

    def _run(self):
        from engine.render import Renderer
        with Renderer() as renderer:
            while True:
                fn, box, done = self.jobs.get()
                try:
                    box["result"] = fn(renderer)
                except Exception as e:  # handed back to the request thread
                    box["error"] = e
                done.set()

    def submit(self, fn, timeout=120):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, name="render-worker", daemon=True)
            self.thread.start()
        box, done = {}, threading.Event()
        self.jobs.put((fn, box, done))
        if not done.wait(timeout):
            raise TimeoutError("Render took too long.")
        if "error" in box:
            raise box["error"]
        return box["result"]


RENDER = RenderWorker()


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    # -- plumbing ------------------------------------------------------------

    def log_message(self, fmt, *args):
        first = str(args[0]) if args else ""
        if "/api/" in first or fmt.startswith("code"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json({"status": "error", "error": message}, status)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            raise ValueError("Request is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def static_allowed(self, path: str) -> bool:
        if any(part.startswith(".") for part in path.split("/") if part):
            return False
        return path.startswith(STATIC_PREFIXES) or path in ("/studio", "/favicon.ico")

    # -- GET -----------------------------------------------------------------

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path in ("", "/"):
            self.send_response(302)
            self.send_header("Location", "/studio/")
            self.end_headers()
            return
        if path == "/api/health":
            return self.api_health()
        if path == "/api/packs":
            return self.api_packs()
        if path == "/api/rip-packs":
            return self.api_rip_packs()
        if path == "/api/content":
            return self.api_content_list()
        if path.startswith("/api/content/"):
            return self.api_content_get(urllib.parse.unquote(path[len("/api/content/"):]))
        if path.startswith("/api/"):
            return self.send_error_json(404, "No such endpoint.")
        if path.startswith("/content/private/"):
            return self.content_image(urllib.parse.unquote(path[len("/content/private/"):]))

        if not self.static_allowed(path):
            return self.send_error_json(404, "Not found.")
        return super().do_GET()

    def content_image(self, name: str):
        """Photos next to your content files. JSON stays behind the API; nothing else is served."""
        target = CONTENT_DIR / name
        if not IMAGE_NAME.match(name) or not target.is_file():
            return self.send_error_json(404, "Not found.")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", IMAGE_TYPES[target.suffix[1:].lower()])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api_health(self):
        from engine.harvester import DEFAULT_API_KEY, GEMINI_MODELS
        self.send_json({
            "status": "ok", "mode": "local",
            "defaultModel": os.environ.get("GEMINI_MODEL", GEMINI_MODELS[0]),
            "hasKey": bool(DEFAULT_API_KEY or os.environ.get("GEMINI_API_KEY")),
            "availableModels": GEMINI_MODELS,
        })

    def api_packs(self):
        packs = []
        for p in sorted(PACKS_DIR.iterdir()):
            spec_file = p / "pack.json"
            if not (p.is_dir() and spec_file.exists()):
                continue
            try:
                spec = json.loads(spec_file.read_text(encoding="utf-8"))
            except Exception as e:  # a broken pack should not break the list
                print(f"[!] Bad pack.json in {p.name}: {e}")
                continue
            dims = spec.get("target", {}).get("dimensions", {})
            packs.append({
                "id": spec.get("id", p.name), "name": spec.get("name", p.name),
                "category": spec.get("category", "Editorial"),
                "format": dims.get("format", "A4"),
                "widthMm": dims.get("width_mm", 210), "heightMm": dims.get("height_mm", 297),
                "rip": (p / "rip.json").exists(),
                "path": f"/design-packs/{p.name}/template.html",
            })
        self.send_json({"status": "success", "packs": packs})

    def api_rip_packs(self):
        packs = []
        for p in sorted(PACKS_DIR.iterdir()):
            if not (p / "rip.json").exists():
                continue
            rip = json.loads((p / "rip.json").read_text(encoding="utf-8"))
            data_file = p / "default-data.json"
            packs.append({
                "id": rip["id"], "name": rip.get("name", rip["id"]),
                "category": rip.get("category", ""),
                "description": rip.get("description", ""),
                "rip": rip,
                "defaultData": json.loads(data_file.read_text(encoding="utf-8")) if data_file.exists() else {},
                "assetBase": f"/design-packs/{p.name}/assets/",
            })
        self.send_json({"status": "success", "packs": packs})

    def api_content_list(self):
        files = []
        if CONTENT_DIR.exists():
            for f in sorted(CONTENT_DIR.glob("*.json")):
                try:
                    head = json.loads(f.read_text(encoding="utf-8")).get("_rip", {})
                except Exception:
                    head = {}
                files.append({"name": f.name, "size": f.stat().st_size,
                              "modified": f.stat().st_mtime, "pack": head.get("pack"),
                              "variant": head.get("variant")})
        self.send_json({"status": "success", "files": files, "folder": "content/private"})

    def content_path(self, name: str) -> Path:
        if not CONTENT_NAME.match(name):
            raise ValueError("Use a plain file name ending in .json.")
        return CONTENT_DIR / name

    def api_content_get(self, name: str):
        try:
            path = self.content_path(name)
        except ValueError as e:
            return self.send_error_json(400, str(e))
        if not path.exists():
            return self.send_error_json(404, f"{name} is not in content/private.")
        self.send_json({"status": "success", "name": name,
                        "data": json.loads(path.read_text(encoding="utf-8"))})

    # -- PUT -----------------------------------------------------------------

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if not path.startswith("/api/content/"):
            return self.send_error_json(404, "No such endpoint.")
        name = urllib.parse.unquote(path[len("/api/content/"):])
        try:
            target = self.content_path(name)
            payload = self.read_json()
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError("Send {\"data\": {...}}.")
        except (ValueError, json.JSONDecodeError) as e:
            return self.send_error_json(400, str(e))
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(target)
        self.send_json({"status": "success", "name": name})

    # -- POST ----------------------------------------------------------------

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as e:
            return self.send_error_json(400, str(e))

        if path == "/api/export":
            return self.api_export(payload)
        if path == "/api/harvest":
            return self.api_harvest(payload)
        if path == "/api/ai/replace-image":
            prompt = payload.get("prompt", "").strip() or "avant-garde graphic"
            url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote_plus(prompt)}"
                   f"?width=800&height=800&nologo=true&seed={random.randint(1000, 999999)}")
            return self.send_json({"status": "success", "imageUrl": url, "prompt": prompt})
        self.send_error_json(404, "No such endpoint.")

    def api_export(self, payload):
        from engine.rip import RipError, render_pdf
        pack = payload.get("pack", "")
        if not (PACKS_DIR / pack / "rip.json").exists():
            return self.send_error_json(400, f"'{pack}' is not a Rip pack.")
        data = payload.get("data") or {}
        source = payload.get("source")  # e.g. "jake-resume.json": its folder holds the photos
        data_dir = CONTENT_DIR if source else None
        try:
            res = RENDER.submit(lambda r: render_pdf(
                pack, data, data_dir=data_dir, variant=payload.get("variant") or None,
                styles=payload.get("styles") or {}, tokens=payload.get("tokens") or {},
                extra_assets={k: v for k, v in (payload.get("assets") or {}).items()
                              if isinstance(v, str) and v.startswith("data:image/")},
                renderer=r))
        except RipError as e:
            return self.send_error_json(400, str(e))
        except Exception as e:
            traceback.print_exc()
            return self.send_error_json(500, f"Export failed: {e}")
        report = res.report or {}
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(res.pdf)))
        self.send_header("X-Rip-Pages", str(res.pages))
        self.send_header("X-Rip-Overflow", ",".join(report.get("overflow", [])))
        self.end_headers()
        self.wfile.write(res.pdf)

    def api_harvest(self, payload):
        from engine.harvester import harvest_image
        try:
            image_b64 = payload.get("imageBase64", "")
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]
            if not image_b64:
                raise ValueError("No image data provided.")
            meta = harvest_image(
                image_bytes=base64.b64decode(image_b64),
                mime_type=payload.get("mimeType", "image/png"),
                name_hint=payload.get("packName") or "Harvested Design Pack",
                api_key=payload.get("apiKey"), model_override=payload.get("model"),
                base_dir=BASE_DIR,
            )
            self.send_json({"status": "success", "pack": meta})
        except Exception as e:
            traceback.print_exc()
            self.send_error_json(500, str(e))


def run_server():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    with socketserver.ThreadingTCPServer((HOST, PORT), StudioHandler) as httpd:
        print(f"[OK] Aestheticsrippy studio at http://{HOST}:{PORT}/studio/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    run_server()
