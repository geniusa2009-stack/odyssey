"""Local viewer server for the ODYSSEY asset pack (localhost only).

    python3 -I ArtSource/OdysseyAssetPack/Viewer/serve.py [port]       -> http://127.0.0.1:8765/Viewer/

Serves the pack folder read-only. POST /save-render?name=<file>.png writes an inspection render
(PNG body) into Renders/ - used by the viewer's "Capture inspection set" button.
"""
import http.server
import os
import re
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDERS = os.path.join(PACK, "Renders")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PACK, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        m = re.match(r"^/save-render\?name=([A-Za-z0-9_\-]+\.png)$", self.path)
        if not m:
            self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0 or n > 20_000_000:
            self.send_error(400); return
        data = self.rfile.read(n)
        if not data.startswith(b"\x89PNG"):
            self.send_error(400); return
        os.makedirs(RENDERS, exist_ok=True)
        with open(os.path.join(RENDERS, m.group(1)), "wb") as fh:
            fh.write(data)
        self.send_response(204); self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
