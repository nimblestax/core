"""`nstx deploy`: ships one Environment and refreshes it."""

from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from nimblestax.build import bundle, compiler
from nimblestax.build import package as build_package
from nimblestax.check import rules
from nimblestax.deploy import manifest
from nimblestax.deploy.databricks import Workspace, WorkspaceError
from nimblestax.diagnostics import (
    DOCS_ROOT,
    USAGE_OR_ENVIRONMENT,
    Diagnostic,
    Failure,
    error,
    errors,
)
from nimblestax.load.project import Project

RECOVERY_GUIDE = f"{DOCS_ROOT}/guides/recover-from-a-failed-refresh.md"


class InvalidProject(Failure):
    pass


class Deployment(NamedTuple):
    manifest: dict
    warnings: list[Diagnostic]


def deploy(
    project: Project, env: str, workspace: Workspace, package: Path | None = None
) -> Deployment:
    """Deploy `package`, or a package built now from the project, then refresh it.

    A given package is deployed as it is and never rebuilt: CI validated the project before
    building it.
    Only a deploy that succeeded, refresh included, writes the Deployment Manifest.
    """
    if package is None:
        problems = errors(rules.check(project))
        if problems:
            raise InvalidProject(problems)
        package = compiler.write_package(project)
    record = build_package.read_record(package)
    started = ship(package, env, workspace)
    written = manifest.manifest(env, record, started)
    return Deployment(written, manifest.store(workspace, package, env, written))


def ship(package: Path, target: str, workspace: Workspace) -> datetime:
    """Deploy a written package to one target, then refresh its tables.

    Returns when the refresh started.
    """
    workspace.deploy_bundle(package, target)
    started = datetime.now().astimezone()
    try:
        workspace.run_job(package, target, bundle.REFRESH_JOB)
    except WorkspaceError as failure:
        try:
            messages = workspace.pipeline_errors(package, target, started)
        except WorkspaceError as lookup:
            raise _unexplained(failure, lookup) from failure
        if not messages:
            raise failure
        found = [refresh_failure(message) for message in messages]
        raise Failure(found, USAGE_OR_ENVIRONMENT) from failure
    return started


def _unexplained(failure: WorkspaceError, lookup: WorkspaceError) -> WorkspaceError:
    """The refresh's own failure, saying Nimblestax tried to read why and couldn't."""
    [ran] = failure.diagnostics
    [read] = lookup.diagnostics
    return WorkspaceError(
        f"{ran.message}\nNimblestax couldn't read the pipelines' errors to say why: {read.message}"
    )


def refresh_failure(message: str) -> Diagnostic:
    """A pipeline's error during the refresh, with how to recover from it."""
    if "UNRESOLVED_COLUMN" in message:
        fix = (
            "Correct the column's name. If an Expectation names a column bronze doesn't have"
            " yet, deploy without the rule so bronze picks up the column, then add the rule back."
            f" See {RECOVERY_GUIDE}."
        )
        return error("NSTX906", "", message, fix)
    if "EXPECTATION_VIOLATION" in message:
        fix = (
            "The row that broke the rule stays in bronze, so every refresh fails on it again."
            " Correct the rule, or change its `action` to `quarantine` or `warn`, then deploy."
            f" See {RECOVERY_GUIDE}."
        )
        return error("NSTX907", "", message, fix)
    fix = "Fix the cause, then deploy again. The pipeline's event log in the workspace has more."
    return error("NSTX908", "", message, fix)
