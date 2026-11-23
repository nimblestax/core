import base64
import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture(autouse=True)
def _outside_any_git_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Git sets GIT_DIR, GIT_INDEX_FILE and friends while it runs a hook, such as the pre-commit
    check. Left in place, a test's own git commands act on this repo instead of its throwaway one:
    they commit here, write into the commit's index, or mark this repo bare."""
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)


class _Workspace(BaseHTTPRequestHandler):
    """Just enough of a workspace for `databricks bundle validate` to run offline, plus workspace
    files kept in `files`, by path, for the Deployment Manifest, and a SQL warehouse that answers
    each statement with the next of `answers`, recording what it was sent in `statements`."""

    files: dict[str, str] = {}
    warehouses: list[dict] = []
    answers: list[dict] = []
    statements: list[dict] = []

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        if "/scim/v2/Me" in self.path:
            self._reply(200, {"id": "1", "userName": "ci@example.com"})
        elif "/workspace/get-status" in self.path:
            path = query["path"][0]
            if path in self.files:
                self._reply(200, {"object_type": "FILE", "object_id": 2, "path": path})
            elif path.endswith(".json"):  # A file nobody wrote. Any other path is a folder.
                message = f"Path ({path}) doesn't exist."
                self._reply(404, {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": message})
            else:
                self._reply(200, {"object_type": "DIRECTORY", "object_id": 1})
        elif self.path.startswith("/api/2.0/sql/warehouses"):
            self._reply(200, {"warehouses": self.warehouses})
        elif self.path.startswith("/api/2.0/sql/statements/"):
            self._reply(200, self.answers.pop(0))
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
        elif self.path.endswith("/sql/statements"):
            self.statements.append(body)
            self._reply(200, self.answers.pop(0))
            return
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
    _Workspace.warehouses = []
    _Workspace.answers = []
    _Workspace.statements = []
    server = HTTPServer(("127.0.0.1", 0), _Workspace)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def stub_files() -> dict[str, str]:
    """The files written to `stub_workspace`, by path."""
    return _Workspace.files


@pytest.fixture
def stub_warehouse() -> type[_Workspace]:
    """The SQL warehouse of `stub_workspace`: set its `warehouses` and `answers`, read its
    `statements`."""
    return _Workspace
