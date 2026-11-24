import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

from app.agency import backfill_sapphic
from app.api import ApiError, dispatch, dumps, move_ships
from app.collect import apply_schema, connect, fill_drama_details, move_credits


def serve(host: str, port: int) -> None:
    with connect() as conn:
        apply_schema(conn)
        backfill_sapphic(conn)
        move_credits(conn)
        move_ships(conn)
        conn.commit()
    Thread(target=fill_drama_details, daemon=True).start()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"http://{host}:{port}", flush=True)
    server.serve_forever()


class Handler(BaseHTTPRequestHandler):
    def respond_json(self, status: int, payload: dict) -> None:
        raw = dumps(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def serve_api(self, method: str, query: dict, body: dict | None) -> None:
        path = urlparse(self.path).path
        try:
            status, payload = dispatch(method, path, query, body)
        except ApiError as exc:
            status, payload = exc.status, {"error": exc.message}
        self.respond_json(status, payload)

    def do_GET(self) -> None:
        path = urlparse(self.path)
        if path.path.startswith("/api/"):
            self.serve_api("GET", parse_qs(path.query), None)
            return
        self.respond_json(404, {"error": "없는 화면입니다."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not parsed.path.startswith("/api/"):
            self.respond_json(404, {"error": "없는 화면입니다."})
            return
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.respond_json(400, {"error": "JSON 객체가 아닙니다"})
            return
        try:
            body = json.loads(raw.decode() or "null")
        except json.JSONDecodeError:
            body = None
        if not isinstance(body, dict):
            self.respond_json(400, {"error": "JSON 객체가 아닙니다"})
            return
        self.serve_api("POST", {}, body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)
