"""`nstx preview`: a person's working tree, deployed to their own schemas in dev's catalogs.

A Preview Environment builds every table. Its bundle state sits in the person's own workspace
folder, so it never touches the Development Environment's pipelines, and destroying it removes
only what it deployed.
"""

from pathlib import Path
from typing import NamedTuple, Protocol

from nimblestax import names, scaffold
from nimblestax.build import bundle, compiler
from nimblestax.check import rules
from nimblestax.deploy import deploy
from nimblestax.deploy.databricks import Workspace
from nimblestax.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error, errors
from nimblestax.load.project import Project


class PreviewWorkspace(Workspace, Protocol):
    """What a Preview Environment needs from the Databricks boundary, beyond a deploy."""

    def current_user(self, host: str) -> str:
        """The user name the person signed in with."""
        ...

    def schema_properties(self, host: str, catalog: str) -> dict[str, dict[str, str]]:
        """Each schema in a catalog, with its properties."""
        ...

    def deployed_schemas(self, package: Path, target: str) -> list[tuple[str, str]]:
        """The schemas a target's bundle state holds, as (catalog, schema)."""
        ...

    def destroy_bundle(self, package: Path, target: str) -> None: ...


class Previewed(NamedTuple):
    schemas: list[str]
    warnings: list[Diagnostic]


def preview(project: Project, workspace: PreviewWorkspace) -> Previewed:
    """Deploy the working tree to the signed-in person's Preview Environment, refresh it, and
    write its Deployment Manifest in the preview's own bundle folder.

    Returns its schemas, as `catalog.schema`.
    """
    _refuse_example(project)
    problems = errors(rules.check(project))
    if problems:
        raise Failure(problems)
    target = _whose(project, workspace)
    _refuse_taken(project, target, workspace)
    package = compiler.write_package(project, target)
    shipped = deploy.ship(package, bundle.PREVIEW_TARGET, workspace)
    schemas = names.preview_schemas(project.platform, target.prefix).values()
    return Previewed(sorted(f"{c}.{s}" for c, s in schemas), shipped.warnings)


def _refuse_example(project: Project) -> None:
    """An example already runs in catalogs of its own, so it has no preview."""
    if project.platform.name in scaffold.examples():
        found = error(
            "NSTX921",
            "",
            f"`{project.platform.name}` is an example, which already runs in catalogs of its own,"
            " so it has no Preview Environment.",
            f"Deploy it directly, with `nstx deploy --env"
            f" {project.platform.development_environment}`.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)


def _whose(project: Project, workspace: PreviewWorkspace) -> bundle.Preview:
    platform = project.platform
    user = workspace.current_user(platform.hosts[platform.development_environment])
    return bundle.Preview(names.personal_prefix(user), user)


def _refuse_taken(project: Project, target: bundle.Preview, workspace: PreviewWorkspace) -> None:
    """Stops before any change if a schema the preview needs was created by anyone else."""
    platform = project.platform
    host = platform.hosts[platform.development_environment]
    by_catalog: dict[str, list[str]] = {}
    for catalog, schema in names.preview_schemas(platform, target.prefix).values():
        by_catalog.setdefault(catalog, []).append(schema)
    ours = {bundle.PROJECT_LABEL: platform.name, bundle.USER_LABEL: target.user}
    found = []
    for catalog, schemas in by_catalog.items():
        # Unity Catalog matches names whatever their case.
        existing = {
            name.lower(): properties
            for name, properties in workspace.schema_properties(host, catalog).items()
        }
        for schema in schemas:
            properties = existing.get(schema.lower())
            labels = {key: (properties or {}).get(key) for key in ours}
            if properties is not None and labels != ours:
                found.append(_taken(f"{catalog}.{schema}", labels))
    if found:
        raise Failure(found, USAGE_OR_ENVIRONMENT)


def _taken(schema: str, labels: dict[str, str | None]) -> Diagnostic:
    project, user = labels[bundle.PROJECT_LABEL], labels[bundle.USER_LABEL]
    if project is None:
        whose = "Nimblestax didn't create it"
    else:
        whose = f"Nimblestax created it for the project `{project}`, for {user}"
    return error(
        "NSTX920",
        "",
        f"The schema `{schema}` already exists, and {whose}. Your preview never deploys into, or"
        " removes, a schema it didn't create.",
        (
            f"Remove the other preview with `nstx preview down` from `{project}`, then run `nstx"
            " preview` again."
            if project
            else "Drop the schema if nobody needs it, then run `nstx preview` again."
        ),
    )


def down(project: Project, workspace: PreviewWorkspace) -> None:
    """Destroy this project's Preview Environment for the signed-in person, from its bundle
    state."""
    _refuse_example(project)
    target = _whose(project, workspace)
    package = compiler.write_package(project, target)
    _fence(project, target, workspace.deployed_schemas(package, bundle.PREVIEW_TARGET))
    workspace.destroy_bundle(package, bundle.PREVIEW_TARGET)


def _fence(project: Project, target: bundle.Preview, deployed: list[tuple[str, str]]) -> None:
    """Refuses anything outside the person's own schemas in the Development Environment's
    catalogs, whatever the bundle state says."""
    platform = project.platform
    dev_catalogs, _ = names.platform_objects(platform, [platform.development_environment])
    allowed = {catalog.lower() for catalog in dev_catalogs}
    outside = [
        f"{catalog}.{schema}"
        for catalog, schema in deployed
        if catalog.lower() not in allowed or not schema.lower().startswith(target.prefix)
    ]
    if outside:
        listed = ", ".join(f"`{schema}`" for schema in outside)
        found = error(
            "NSTX922",
            "",
            f"Your preview's bundle state holds {listed}, outside your `{target.prefix}*` schemas"
            f" in {platform.development_environment}'s catalogs. `nstx preview down` removes"
            " nothing rather than drop it.",
            "Find out how it got into the preview's bundle state before removing anything. Drop"
            " the preview's own schemas by hand if you need to.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)
