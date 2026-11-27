"""`nsx preview`: a working tree, deployed to its own schemas in dev's catalogs, for the person
signed in or, with `--pr`, for a pull request.

A Preview Environment builds every table. Its bundle state sits in its own folder under whoever
deploys it, the person or CI's identity, so it never touches the Development Environment's
pipelines, and destroying it removes only what it deployed.
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


class SignedIn(Protocol):
    def current_user(self, host: str) -> str:
        """The user name the person signed in with."""
        ...


class PreviewWorkspace(Workspace, SignedIn, Protocol):
    """What a Preview Environment needs from the Databricks boundary, beyond a deploy."""

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


def preview(
    project: Project, workspace: PreviewWorkspace, pull_request: int | None = None
) -> Previewed:
    """Deploy the working tree to the signed-in person's Preview Environment, or to
    `pull_request`'s, refresh it, and write its Deployment Manifest in the preview's own bundle
    folder.

    Returns its schemas, as `catalog.schema`.
    """
    refuse_example(project)
    problems = errors(rules.check(project))
    if problems:
        raise Failure(problems)
    target = whose(project, workspace, pull_request)
    _refuse_taken(project, target, workspace)
    package = compiler.write_package(project, target)
    shipped = deploy.ship(package, bundle.PREVIEW_TARGET, workspace)
    schemas = names.preview_schemas(project.platform, target.prefix).values()
    return Previewed(sorted(f"{c}.{s}" for c, s in schemas), shipped.warnings)


def refuse_example(project: Project) -> None:
    """An example already runs in catalogs of its own, so it has no preview."""
    if project.platform.name in scaffold.examples():
        found = error(
            "NSX921",
            "",
            f"`{project.platform.name}` is an example, which already runs in catalogs of its own,"
            " so it has no Preview Environment.",
            f"Deploy it directly, with `nsx deploy --env"
            f" {project.platform.development_environment}`.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)


def whose(project: Project, workspace: SignedIn, pull_request: int | None) -> bundle.Preview:
    """A pull request's preview comes from `--pr`, never from CI's environment, and a person's
    from who is signed in."""
    if pull_request is not None:
        return bundle.pull_request(pull_request)
    platform = project.platform
    user = workspace.current_user(platform.hosts[platform.development_environment])
    return bundle.personal(user)


def _refuse_taken(project: Project, target: bundle.Preview, workspace: PreviewWorkspace) -> None:
    """Stops before any change if a schema the preview needs was created by anyone else."""
    platform = project.platform
    host = platform.hosts[platform.development_environment]
    by_catalog: dict[str, list[str]] = {}
    for catalog, schema in names.preview_schemas(platform, target.prefix).values():
        by_catalog.setdefault(catalog, []).append(schema)
    ours = {bundle.PROJECT_LABEL: platform.name, **target.labels}
    found = []
    for catalog, schemas in by_catalog.items():
        # Unity Catalog matches names whatever their case.
        existing = {
            name.lower(): properties
            for name, properties in workspace.schema_properties(host, catalog).items()
        }
        for schema in schemas:
            properties = existing.get(schema.lower())
            if properties is None:
                continue
            if {key: properties.get(key) for key in ours} != ours:
                found.append(_taken(f"{catalog}.{schema}", properties))
    if found:
        raise Failure(found, USAGE_OR_ENVIRONMENT)


def _taken(schema: str, labels: dict[str, str]) -> Diagnostic:
    project = labels.get(bundle.PROJECT_LABEL)
    number = labels.get(bundle.PULL_REQUEST_LABEL)
    other = bundle.pull_request(int(number)) if number and number.isdecimal() else None
    remove = other.remove if other else "nsx preview down"
    if project is None:
        whose = "Nimblestax didn't create it"
    else:
        owner = other.owner if other else labels.get(bundle.USER_LABEL)
        whose = f"Nimblestax created it for the project `{project}`, for {owner}"
    return error(
        "NSX920",
        "",
        f"The schema `{schema}` already exists, and {whose}. Your preview never deploys into, or"
        " removes, a schema it didn't create.",
        (
            f"Remove the other preview with `{remove}` from `{project}`, then run `nsx"
            " preview` again."
            if project
            else "Drop the schema if nobody needs it, then run `nsx preview` again."
        ),
    )


def down(project: Project, workspace: PreviewWorkspace, pull_request: int | None = None) -> None:
    """Destroy this project's Preview Environment for the signed-in person, or for
    `pull_request`, from its bundle state."""
    refuse_example(project)
    target = whose(project, workspace, pull_request)
    package = compiler.write_package(project, target)
    _fence(project, target, workspace.deployed_schemas(package, bundle.PREVIEW_TARGET))
    workspace.destroy_bundle(package, bundle.PREVIEW_TARGET)


def _fence(project: Project, target: bundle.Preview, deployed: list[tuple[str, str]]) -> None:
    """Refuses anything outside the preview's own prefixed schemas in the Development
    Environment's catalogs, whatever the bundle state says."""
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
            "NSX922",
            "",
            f"The preview's bundle state holds {listed}, outside its `{target.prefix}*` schemas"
            f" in {platform.development_environment}'s catalogs. `nsx preview down` removes"
            " nothing rather than drop it.",
            "Find out how it got into the preview's bundle state before removing anything. Drop"
            " the preview's own schemas by hand if you need to.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)
