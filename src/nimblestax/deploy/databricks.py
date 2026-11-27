"""The Databricks boundary: every workspace call goes through here."""

import json
import os
import subprocess
import sys
import tempfile
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any, Protocol

from nimblestax.deploy import pinned_cli
from nimblestax.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error

# How many of the CLI's last lines a failure keeps, since the CLI's own output goes to stderr.
KEPT_LINES = 10

# The workspace's clock and this machine's can differ a little, so errors are read from a bit
# before the refresh started. A failed deploy takes longer than this, so no older error shows up.
CLOCK_SKEW = timedelta(minutes=1)

# A statement waits this long for its answer before Nimblestax polls for it, the most the
# Statement Execution API allows. A warehouse that's starting up takes longer.
STATEMENT_WAIT = "50s"
POLL_SECONDS = 2
# A Test that runs longer than this is stuck, or reads far more than a Test should.
STATEMENT_TIMEOUT = timedelta(minutes=30)
UNFINISHED = {"PENDING", "RUNNING"}
# What Databricks says when an identity may not use Databricks SQL at all.
SQL_ENTITLEMENT = "databricks-sql-access"


class WorkspaceError(Failure):
    def __init__(self, message: str, rule: str = "NSX904", fix: str = "Read the log on stderr."):
        super().__init__([error(rule, "", message, fix)], USAGE_OR_ENVIRONMENT)


class QueryFailed(Exception):
    """A SQL statement the warehouse ran and refused, such as one naming a missing column."""


class Workspace(Protocol):
    def deploy_bundle(self, package: Path, target: str) -> None: ...

    def run_job(self, package: Path, target: str, job: str) -> None: ...

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        """The errors of each pipeline's newest update that failed since `since`."""
        ...

    def bundle_root(self, package: Path, target: str) -> str:
        """The workspace folder the bundle deploys into for `target`."""
        ...

    def write_file(self, package: Path, target: str, path: str, content: str) -> None:
        """Write a file in `target`'s workspace, making its folder and replacing what's there."""
        ...

    def list_folder(self, package: Path, target: str, folder: str) -> list[str]:
        """The paths of the files in a folder of `target`'s workspace."""
        ...

    def delete_file(self, package: Path, target: str, path: str) -> None: ...


class DatabricksCli:
    """Runs Nimblestax's pinned Databricks CLI, found or downloaded at the first call."""

    @cached_property
    def _executable(self) -> str:
        return str(pinned_cli.databricks())

    def deploy_bundle(self, package: Path, target: str) -> None:
        self._stream(package, "bundle", "deploy", "--target", target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        self._stream(package, "bundle", "run", "--target", target, job)

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        summary = self._json(package, "bundle", "summary", "--target", target, "-o", "json")
        pipelines = summary.get("resources", {}).get("pipelines", {}).values()
        start = (since - CLOCK_SKEW).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        errors = []
        for pipeline in pipelines:
            if "id" not in pipeline:
                continue  # Never deployed, so it has no log.
            events = self._json(
                package,
                *("pipelines", "list-pipeline-events", pipeline["id"], "--target", target),
                *("-o", "json", "--filter", f"level='ERROR' AND timestamp >= '{start}'"),
            )
            errors.extend(failed_update_errors(events))
        return errors

    def destroy_bundle(self, package: Path, target: str) -> None:
        self._stream(package, "bundle", "destroy", "--target", target, "--auto-approve")

    def deployed_schemas(self, package: Path, target: str) -> list[tuple[str, str]]:
        summary = self._json(package, "bundle", "summary", "--target", target, "-o", "json")
        schemas = summary.get("resources", {}).get("schemas", {}).values()
        return [(schema["catalog_name"], schema["name"]) for schema in schemas]

    def current_user(self, host: str) -> str:
        return self._json(None, "current-user", "me", "--output", "json", host=host)["userName"]

    def schema_properties(self, host: str, catalog: str) -> dict[str, dict[str, str]]:
        listed = self._json(None, "schemas", "list", catalog, "--output", "json", host=host)
        return {schema["name"]: schema.get("properties") or {} for schema in listed}

    def privileges(self, host: str, catalog: str, principal: str) -> set[str]:
        found = self._json(
            None,
            *("grants", "get-effective", "catalog", catalog, "--principal", principal),
            *("--output", "json"),
            host=host,
        )
        return {
            granted["privilege"]
            for assignment in found.get("privilege_assignments") or []
            for granted in assignment.get("privileges") or []
        }

    def bundle_root(self, package: Path, target: str) -> str:
        validated = self._json(package, "bundle", "validate", "--target", target, "-o", "json")
        return validated["workspace"]["root_path"]

    def write_file(self, package: Path, target: str, path: str, content: str) -> None:
        folder = path.rsplit("/", 1)[0]
        self._call(package, "workspace", "mkdirs", folder, "--target", target)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as local:
            local.write(content)
        try:
            self._call(
                package,
                *("workspace", "import", path, "--file", local.name, "--format", "AUTO"),
                *("--overwrite", "--target", target),
            )
        finally:
            os.unlink(local.name)

    def list_folder(self, package: Path, target: str, folder: str) -> list[str]:
        listed = self._json(package, "workspace", "list", folder, "--target", target, "-o", "json")
        return [item["path"] for item in listed or [] if item.get("object_type") == "FILE"]

    def delete_file(self, package: Path, target: str, path: str) -> None:
        self._call(package, "workspace", "delete", path, "--target", target)

    def exists(self, package: Path, target: str, path: str) -> bool:
        printed, failure = self._try(
            package, "workspace", "get-status", path, "--target", target, "-o", "json"
        )
        if not failure:
            return True
        if "doesn't exist" in failure or "RESOURCE_DOES_NOT_EXIST" in failure:
            return False
        sys.stderr.write(failure)
        raise WorkspaceError(f"databricks workspace get-status {path} failed.")

    def warehouses(self, host: str) -> list[tuple[str, str]]:
        listed = self._sql(host, "warehouses", "list", "--output", "json")
        return [(warehouse["id"], warehouse["name"]) for warehouse in listed or []]

    def query(self, host: str, warehouse: str, statement: str) -> list[list]:
        """Run one statement through the Statement Execution API, polling until it finishes."""
        body = {"warehouse_id": warehouse, "statement": statement, "wait_timeout": STATEMENT_WAIT}
        ran = self._sql(host, "api", "post", "/api/2.0/sql/statements", "--json", json.dumps(body))
        deadline = datetime.now() + STATEMENT_TIMEOUT
        while ran["status"]["state"] in UNFINISHED:
            if datetime.now() > deadline:
                raise WorkspaceError(
                    f"The SQL warehouse {warehouse} didn't finish a Test's statement in"
                    f" {STATEMENT_TIMEOUT}.",
                    fix="Check the warehouse is running, then run `nsx test` again.",
                )
            time.sleep(POLL_SECONDS)
            path = f"/api/2.0/sql/statements/{ran['statement_id']}"
            ran = self._sql(host, "api", "get", path)
        state = ran["status"]["state"]
        if state == "FAILED":
            raise QueryFailed(ran["status"].get("error", {}).get("message", "No reason given."))
        if state != "SUCCEEDED":
            raise WorkspaceError(f"The SQL warehouse {warehouse} ended a Test's statement {state}.")
        return ran.get("result", {}).get("data_array") or []

    def _sql(self, host: str, *arguments: str) -> Any:
        """A Databricks SQL call, which needs an entitlement a workspace may not have given."""
        printed, failure = self._try(None, *arguments, host=host)
        if failure:
            sys.stderr.write(failure)
            if SQL_ENTITLEMENT in failure:
                raise WorkspaceError(
                    "The identity Nimblestax runs as can't use Databricks SQL, so it can't run"
                    " Tests.",
                    "NSX925",
                    f"Ask a workspace admin to give it the `{SQL_ENTITLEMENT}` entitlement, and"
                    " `CAN USE` on the SQL warehouse Tests run on. For CI, that's the Development"
                    " Environment's deploying identity.",
                )
            raise WorkspaceError(f"databricks {' '.join(arguments)} failed.")
        try:
            return json.loads(printed)
        except json.JSONDecodeError as problem:
            raise WorkspaceError(
                f"databricks {' '.join(arguments)} didn't print JSON."
            ) from problem

    def catalogs(self, host: str) -> set[str]:
        listed = self._json(None, "catalogs", "list", "--output", "json", host=host)
        return {catalog["name"] for catalog in listed}

    def schemas(self, host: str, catalog: str) -> set[str]:
        listed = self._json(None, "schemas", "list", catalog, "--output", "json", host=host)
        return {schema["name"] for schema in listed}

    def _stream(self, package: Path, *arguments: str) -> None:
        command = [self._executable, *arguments]
        last_lines: deque[str] = deque(maxlen=KEPT_LINES)
        # Its output goes to stderr, so stdout only ever holds what Nimblestax prints.
        with _start(command, package, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as cli:
            for line in cli.stdout or []:
                sys.stderr.write(line)
                last_lines.append(line.rstrip())
        if cli.returncode:
            shown = "\n".join(last_lines)
            raise WorkspaceError(
                f"databricks {' '.join(arguments)} failed. Its last lines:\n{shown}"
            )

    def _json(self, package: Path | None, *arguments: str, host: str | None = None) -> Any:
        """Run from a bundle `package`, which names each target's workspace, or with no package
        against `host`, whatever workspace the shell points at."""
        printed = self._call(package, *arguments, host=host)
        try:
            return json.loads(printed)
        except json.JSONDecodeError as failure:
            raise WorkspaceError(
                f"databricks {' '.join(arguments)} didn't print JSON."
            ) from failure

    def _call(self, package: Path | None, *arguments: str, host: str | None = None) -> str:
        """Run a command and return what it printed, as `_json` does without parsing it."""
        command = [self._executable, *arguments]
        env = {**os.environ, "DATABRICKS_HOST": host} if host else None
        # Its log goes to the stderr this process was started with, so stdout stays Nimblestax's.
        with _start(command, package, env=env, stdout=subprocess.PIPE, stderr=None) as cli:
            printed = cli.stdout.read() if cli.stdout else ""
        if cli.returncode:
            raise WorkspaceError(f"databricks {' '.join(arguments)} failed.")
        return printed

    def _try(
        self, package: Path | None, *arguments: str, host: str | None = None
    ) -> tuple[str, str]:
        """Run a command and return what it printed, and what it said on stderr if it failed."""
        command = [self._executable, *arguments]
        env = {**os.environ, "DATABRICKS_HOST": host} if host else None
        streams: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        with _start(command, package, env=env, **streams) as cli:
            printed, said = cli.communicate()
        if not cli.returncode:
            return printed, ""
        return printed, said or f"databricks {' '.join(arguments)} failed and said nothing."


def _start(command: list[str], package: Path | None, **streams: Any) -> subprocess.Popen[str]:
    try:
        return subprocess.Popen(command, cwd=package, text=True, **streams)
    except FileNotFoundError as failure:
        raise WorkspaceError(
            f"Nimblestax can't run the Databricks CLI at {command[0]}: {failure.strerror}.",
            "NSX903",
            f"Point {pinned_cli.OVERRIDE} at a Databricks CLI, or unset it so Nimblestax downloads"
            " its own.",
        ) from failure


def failed_update_errors(events: list[dict]) -> list[str]:
    """The first line of each error in the newest update, from a pipeline's ERROR events.

    Events come newest first. A failed flow logs its own error and then the update logs a summary,
    so the flows' errors are kept, and the update's own only when no flow failed.
    """
    if not events:
        return []
    newest = _origin(events[0]).get("update_id")
    in_update = [found for found in reversed(events) if _origin(found).get("update_id") == newest]
    from_flows = [found for found in in_update if _origin(found).get("flow_name")]
    errors = []
    for found in from_flows or in_update:
        message = _error_message(found)
        if message and message not in errors:
            errors.append(message)
    return errors


def _origin(found: dict) -> dict:
    return found.get("origin", {})


def _error_message(found: dict) -> str:
    exceptions = found.get("error", {}).get("exceptions") or [{}]
    message = exceptions[0].get("message") or found.get("message") or ""
    return message.splitlines()[0] if message else ""
