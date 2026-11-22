import base64
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest


class _Workspace(BaseHTTPRequestHandler):
    """Just enough of a workspace for `databricks bundle validate` to run offline, plus workspace
    files kept in `files`, by path, for the Deployment Manifest."""

    files: dict[str, str] = {}

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        if "/scim/v2/Me" in self.path:
            self._reply(200, {"id": "1", "userName": "ci@example.com"})
        elif "/workspace/get-status" in self.path:
            self._reply(200, {"object_type": "DIRECTORY", "object_id": 1})
        elif "/workspace/list" in self.path:
            folder = query["path"][0]
            listed = [
                {"path": path, "object_type": "FILE"}
                for path in sorted(self.files)
                if path.rsplit("/", 1)[0] == folder
            ]
            self._reply(200, {"objects": listed})
        else:
            self._reply(404, {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/workspace/import"):
            self.files[body["path"]] = base64.b64decode(body.get("content", "")).decode()
        elif self.path.endswith("/workspace/delete"):
            self.files.pop(body["path"], None)
        self._reply(200, {})

    def _reply(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format: str, *args: object) -> None:
        pass  # Keeps test output clean.


@pytest.fixture
def stub_workspace() -> Iterator[str]:
    _Workspace.files = {}
    server = HTTPServer(("127.0.0.1", 0), _Workspace)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def stub_files() -> dict[str, str]:
    """The files written to `stub_workspace`, by path."""
    return _Workspace.files
