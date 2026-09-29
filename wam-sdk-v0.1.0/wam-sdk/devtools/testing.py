"""Loopback-only adversarial servers and HTTP helpers; exclusively synthetic data."""

from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading

from .privacy import private_write
from .rpc import Cookie, RPC

CANARY = "SYNTHETIC-PRIVATE-CANARY-83fce7c951"


@contextmanager
def fake_rpc(responder, max_response=4096, timeout=2):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.answer(request)

        def do_GET(self):
            self.answer({"jsonrpc":"2.0", "id":"synthetic-get", "method":"GET", "params":[]})

        def answer(self, request):
            calls.append((request, self.path, self.headers.get("Authorization")))
            status, body, headers = responder(request)
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    with tempfile.TemporaryDirectory() as tmp:
        cookie = Path(tmp) / ".cookie"
        private_write(cookie, "__cookie__:" + CANARY)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        rpc = RPC(f"http://127.0.0.1:{server.server_port}", Cookie(cookie),
                  timeout=timeout, max_response=max_response)
        try:
            yield rpc, calls, cookie
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


def reply(req, result=None):
    return 200, {"jsonrpc": "2.0", "id": req["id"], "result": result}, {}


def http_request(port, path, method="GET", body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        if body is not None and not isinstance(body, (bytes, str)):
            body = json.dumps(body).encode()
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read(1_000_000)
    finally:
        conn.close()
