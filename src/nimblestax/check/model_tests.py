"""`nstx test`: each Gold Model's Tests, run through a SQL warehouse on a Preview Environment's
tables.

A preview builds every table from all of dev's rows, so a Test sees the data it would see in dev,
and no Test type fails only because it ran on a preview.
"""

import json
import sys
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nimblestax import names
from nimblestax.build import bundle, compiler
from nimblestax.check import rules
from nimblestax.deploy import manifest, preview
from nimblestax.deploy.databricks import QueryFailed
from nimblestax.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error, errors
from nimblestax.kinds.model import Model, References, RowCount, Test, Unique
from nimblestax.load.project import Project
from nimblestax.names import LogicalName

# How many failing values a Test shows. Enough to start looking, few enough to read.
EXAMPLES = 5


class TestWorkspace(preview.SignedIn, Protocol):
    def bundle_root(self, package: Path, target: str) -> str:
        """The workspace folder the bundle deploys into for `target`."""
        ...

    def exists(self, package: Path, target: str, path: str) -> bool:
        """Whether a file or folder is in `target`'s workspace."""
        ...

    def warehouses(self, host: str) -> list[tuple[str, str]]:
        """Each SQL warehouse the signed-in identity can see, as (ID, name)."""
        ...

    def query(self, host: str, warehouse: str, statement: str) -> list[list]:
        """The rows a SQL statement returns, each value as the warehouse prints it."""
        ...


@dataclass(frozen=True)
class Ran:
    """One Test on one Gold Model: why it failed, or why it couldn't run, or neither if it
    passed."""

    model: LogicalName
    test: str
    file: str
    failure: str | None = None
    error: str | None = None


def run(
    project: Project,
    workspace: TestWorkspace,
    pull_request: int | None = None,
    models: Sequence[str] = (),
) -> list[Ran]:
    """Run the Tests of `models`, by default every Gold Model's, on the signed-in person's
    Preview Environment, or on `pull_request`'s.

    Fails with a diagnostic per failed Test.
    """
    preview.refuse_example(project)
    problems = errors(rules.check(project))
    if problems:
        raise Failure(problems)
    chosen = select(project, models)
    platform = project.platform
    host = platform.hosts[platform.development_environment]
    target = preview.whose(project, workspace, pull_request)
    _require_deployed(project, workspace, target, pull_request)
    warehouse = _warehouse(project, workspace, host)
    schemas = names.preview_schemas(platform, target.prefix)
    tests = [(model, test) for model in chosen for test in model.tests]
    at_once = platform.tests.concurrency
    if tests:
        whose = "your" if pull_request is None else f"pull request {pull_request}'s"
        counted = "1 Test" if len(tests) == 1 else f"{len(tests)} Tests"
        _say(
            f"Running {counted} on {whose} Preview Environment ({target.prefix}), on warehouse"
            f" {warehouse}, {at_once} at a time."
        )
    finished = Counter(len(tests))

    def run_one(model: Model, test: Test) -> Ran:
        # Said before the query, because a warehouse that's starting up can take minutes.
        _say(f"  {'started':<12} {_dotted(model)}: {test.name}")
        found = _run(workspace, host, warehouse, project, model, test, schemas)
        _say(f"  {_outcome(found):<12} {_dotted(model)}: {test.name}  ({finished.next()})")
        return found

    with ThreadPoolExecutor(max_workers=at_once) as pool:
        # `map` keeps the order Tests are declared in, however they finish.
        ran = list(pool.map(lambda pair: run_one(*pair), tests))
    failed = [_failed(found) for found in ran if found.failure or found.error]
    if failed:
        raise Failure(failed)
    return ran


_SAYING = threading.Lock()


def select(project: Project, names: Sequence[str]) -> list[Model]:
    """The Gold Models `names` pick, in the project's order. Each name is a Model's name, or its
    Logical Name when two Domains have a Model of that name. No names picks every Model."""
    if not names:
        return list(project.models)
    picked: set[str] = set()
    for name in names:
        wanted = name.lower()
        found = [m for m in project.models if wanted in (_dotted(m), m.name.lower())]
        if len(found) != 1:
            raise Failure([_unselected(name, found or list(project.models))], USAGE_OR_ENVIRONMENT)
        picked.add(_dotted(found[0]))
    return [model for model in project.models if _dotted(model) in picked]


def _unselected(name: str, candidates: list[Model]) -> Diagnostic:
    listed = ", ".join(f"`{_dotted(model)}`" for model in candidates)
    if len(candidates) > 1 and all(model.name.lower() == name.lower() for model in candidates):
        message = f"`{name}` names a Gold Model in more than one Domain."
        fix = f"Give its Logical Name instead, one of: {listed}."
    else:
        message = f"`{name}` isn't a Gold Model in this project."
        fix = f"Give a Gold Model's name or its Logical Name, one of: {listed}."
    return error("NSTX926", "", message, fix)


def _say(line: str) -> None:
    """Progress goes to stderr, so stdout holds only what the command prints, such as `--json`.
    One whole line at a time, so lines from Tests running at once never interleave."""
    with _SAYING:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


class Counter:
    """How many of `total` Tests have finished, as `3/10`, counted safely across threads."""

    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self.lock = threading.Lock()

    def next(self) -> str:
        with self.lock:
            self.done += 1
            return f"{self.done}/{self.total}"


def _dotted(model: Model) -> str:
    return f"{model.domain}.{model.layer}.{model.name}".lower()


def _outcome(ran: Ran) -> str:
    if ran.error:
        return "couldn't run"
    return "failed" if ran.failure else "passed"


def _require_deployed(
    project: Project, workspace: TestWorkspace, target: bundle.Preview, pull_request: int | None
) -> None:
    """A preview whose deploy and refresh succeeded has written its Deployment Manifest."""
    package = compiler.write_package(project, target)
    root = workspace.bundle_root(package, bundle.PREVIEW_TARGET)
    if workspace.exists(package, bundle.PREVIEW_TARGET, f"{root}/{manifest.PATH}"):
        return
    if pull_request is None:
        command, whose = "nstx preview", "You have"
    else:
        command, whose = f"nstx preview --pr {pull_request}", f"Pull request {pull_request} has"
    problem = error(
        "NSTX924",
        "",
        f"{whose} no Preview Environment of this project to test. Tests run on a preview's"
        " tables, so it must be deployed first.",
        f"Run `{command}`, then `nstx test` again.",
    )
    raise Failure([problem], USAGE_OR_ENVIRONMENT)


def _warehouse(project: Project, workspace: TestWorkspace, host: str) -> str:
    """The Development Environment's `warehouse`, or else the only one in its workspace."""
    platform = project.platform
    dev = platform.development_environment
    named = platform.environments[dev].warehouse
    if named:
        return named
    found = workspace.warehouses(host)
    if len(found) == 1:
        return found[0][0]
    listed = ", ".join(f"{id} ({name})" for id, name in found) or "none"
    problem = error(
        "NSTX923",
        "nimblestax.platform.yaml",
        f"Nimblestax can't tell which SQL warehouse to run Tests on. You can see: {listed}.",
        f"Add `warehouse: <id>` under `environments.{dev}` in `nimblestax.platform.yaml`, set to"
        " the warehouse your team runs Tests on.",
    )
    raise Failure([problem], USAGE_OR_ENVIRONMENT)


def _run(
    workspace: TestWorkspace,
    host: str,
    warehouse: str,
    project: Project,
    model: Model,
    test: Test,
    schemas: dict[str, tuple[str, str]],
) -> Ran:
    logical = LogicalName(model.domain, model.layer, model.name)

    def in_preview(name: LogicalName) -> str:
        catalog, schema = schemas[f"{name.domain}_{name.layer}"]
        return f"{catalog}.{schema}.{name.entity}"

    file = model.config_file.relative_to(project.root).as_posix()
    try:
        [measured] = workspace.query(host, warehouse, _sql(test, in_preview(logical), in_preview))
    except QueryFailed as refused:
        return Ran(logical, test.name, file, error=str(refused))
    return Ran(logical, test.name, file, _failure(test, measured))


def _sql(test: Test, table: str, in_preview: Callable[[LogicalName], str]) -> str:
    match test:
        case Unique(unique=columns):
            listed = ", ".join(columns)
            present = " AND ".join(f"{column} IS NOT NULL" for column in columns)
            return (
                f"SELECT COUNT(*), to_json(slice(collect_list(to_json(struct({listed}))), 1,"
                f" {EXAMPLES}))\n"
                f"FROM (SELECT {listed} FROM {table} WHERE {present}"
                f" GROUP BY {listed} HAVING COUNT(*) > 1)"
            )
        case RowCount():
            return f"SELECT COUNT(*) FROM {table}"
        case References(references=found):
            other = in_preview(LogicalName(*found.to.split(".")))
            return (
                f"SELECT COUNT(*), to_json(slice(collect_set(CAST(t.{found.column} AS STRING)),"
                f" 1, {EXAMPLES}))\n"
                f"FROM {table} AS t LEFT ANTI JOIN {other} AS r"
                f" ON t.{found.column} = r.{found.key_column}\n"
                f"WHERE t.{found.column} IS NOT NULL"
            )


def _failure(test: Test, measured: list) -> str | None:
    match test:
        case Unique():
            duplicated, examples = int(measured[0]), json.loads(measured[1] or "[]")
            if not duplicated:
                return None
            appear = "value appears" if duplicated == 1 else "values appear"
            return f"{duplicated} {appear} in more than one row, such as {', '.join(examples)}."
        case RowCount(row_count=limits):
            rows = int(measured[0])
            if rows >= limits.min and (limits.max is None or rows <= limits.max):
                return None
            return f"The table has {_rows(rows)}."
        case References(references=found):
            missing, examples = int(measured[0]), json.loads(measured[1] or "[]")
            if not missing:
                return None
            have = "has" if missing == 1 else "have"
            return (
                f"{_rows(missing)} {have} a `{found.column}` that isn't a `{found.key_column}` in"
                f" `{found.to}`, such as {', '.join(examples)}."
            )


def _rows(count: int) -> str:
    return "1 row" if count == 1 else f"{count} rows"


def _failed(ran: Ran) -> Diagnostic:
    dotted = f"{ran.model.domain}.{ran.model.layer}.{ran.model.entity}"
    if ran.error:
        return error(
            "NSTX402",
            ran.file,
            f"`{ran.test}` couldn't run on `{dotted}`. The warehouse said: {ran.error}",
            "Correct the Test, such as a column's name, so it matches the model's table.",
        )
    return error(
        "NSTX401",
        ran.file,
        f"`{ran.test}` failed on `{dotted}`: {ran.failure}",
        "Fix the model's SQL or the data it reads, or correct the Test, then run `nstx preview`"
        " and `nstx test` again.",
    )
