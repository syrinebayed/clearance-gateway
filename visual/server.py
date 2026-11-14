"""Local web server for the visual demo: static page plus the JSON API. Standard library only.

Run from clearance-gateway/:  .venv/bin/python -m visual
"""
import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from clearance import gateway as gw

from .api import Api
from .session import Session

HERE = Path(__file__).parent
STATIC = HERE / "static"
DEFAULT_DATA_DIR = HERE.parent / "visual_run"
LOCAL_HOSTS = ("127.0.0.1", "localhost")
MAX_BODY = 64 * 1024
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}


def _static_file(url_path: str) -> Path | None:
    """Resolve a URL path inside static/, or None if it escapes the folder or is missing."""
    target = (STATIC / (url_path.lstrip("/") or "index.html")).resolve()
    return target if target.is_file() and STATIC.resolve() in target.parents else None


def make_handler(api: Api) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, TYPES[".json"], json.dumps(payload).encode())

        def _local(self) -> bool:
            """Only answer requests addressed to this machine (blocks DNS-rebinding tricks)."""
            return self.headers.get("Host", "").rsplit(":", 1)[0] in LOCAL_HOSTS

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            if not self._local():
                return self._json(403, {"error": "local requests only"})
            if url.path.startswith("/api/"):
                return self._json(*api.handle("GET", url.path, dict(parse_qsl(url.query))))
            file = _static_file(url.path)
            if file is None:
                return self._json(404, {"error": "not found"})
            self._send(200, TYPES.get(file.suffix, "application/octet-stream"), file.read_bytes())

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            is_json = self.headers.get("Content-Type", "").startswith("application/json")
            if not (self._local() and is_json and length <= MAX_BODY):
                return self._json(403, {"error": "local JSON requests only"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "body must be JSON"})
            self._json(*api.handle("POST", urlsplit(self.path).path, body=body))

        def log_message(self, format: str, *args) -> None:
            """Keep the terminal quiet; the page is the display."""

    return Handler


def make_server(host: str, port: int, data_dir: Path, biomcp_cmd: str, live: bool = True) -> ThreadingHTTPServer:
    """Build the server (port 0 picks a free port). The caller runs serve_forever()."""
    api = Api(Session(Path(data_dir), biomcp_cmd, live))
    return ThreadingHTTPServer((host, port), make_handler(api))


def main() -> None:
    ap = argparse.ArgumentParser(description="Clearance Gateway visual demo")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--biomcp", default=gw._default_biomcp())
    ap.add_argument("--offline", action="store_true", help="never contact BioMCP; use the cached gene summary")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = ap.parse_args()
    server = make_server("127.0.0.1", args.port, Path(args.data_dir), args.biomcp, live=not args.offline)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Clearance Gateway visual demo\n  {url}\n  BioMCP: "
          f"{'offline, cached gene summary' if args.offline else 'live when reachable, cached copy otherwise'}"
          "\n  Ctrl+C to stop", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()

