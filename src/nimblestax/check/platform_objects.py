"""Platform rules. `nsx validate --platform` runs these against one Environment's workspace.

Nimblestax never creates a team's catalogs or schemas. Whoever owns the platform does, so a missing
one fails here, before a deploy, rather than halfway through one. In the Development Environment,
the developer group needs the grants that let each person create their own Preview Environment.
"""

from typing import Protocol

from nimblestax import names
from nimblestax.diagnostics import Diagnostic, error
from nimblestax.kinds import platform
from nimblestax.load.project import Project


class UnityCatalog(Protocol):
    """What the Databricks boundary reports about a workspace's catalogs and schemas."""

    def catalogs(self, host: str) -> set[str]:
        """The catalogs the signed-in identity can see."""
        ...

    def schemas(self, host: str, catalog: str) -> set[str]:
        """The schemas in one catalog the signed-in identity can see."""
        ...

    def privileges(self, host: str, catalog: str, principal: str) -> set[str]:
        """The privileges a principal holds on a catalog, such as `USE_CATALOG`, directly or
        inherited."""
        ...


# What each person's Preview Environment needs on the Development Environment's catalogs: to
# create its schemas, and to read the files that land in its Volumes.
DEVELOPER_PRIVILEGES = ("USE_CATALOG", "USE_SCHEMA", "CREATE_SCHEMA", "READ_VOLUME")


def check(project: Project, env: str, workspace: UnityCatalog) -> list[Diagnostic]:
    host = project.platform.hosts[env]
    catalogs, schemas = names.platform_objects(project.platform, [env])
    present = _lowercase(workspace.catalogs(host))
    developers = project.platform.developers
    if env != project.platform.development_environment:
        developers = None  # Only the Development Environment holds Preview Environments.
    diagnostics = []
    for catalog in catalogs:
        needed = [schema for schema in schemas if schema.split(".")[0] == catalog]
        if catalog.lower() not in present:
            diagnostics.append(_missing_catalog(env, host, catalog, needed))
            continue
        found = _lowercase(workspace.schemas(host, catalog))
        diagnostics += [
            _missing_schema(env, host, schema)
            for schema in needed
            if schema.split(".")[1].lower() not in found
        ]
        if developers:
            held = workspace.privileges(host, catalog, developers)
            missing = (
                []
                if "ALL_PRIVILEGES" in held
                else [privilege for privilege in DEVELOPER_PRIVILEGES if privilege not in held]
            )
            if missing:
                diagnostics.append(_missing_grant(env, catalog, developers, missing))
    return diagnostics


def _lowercase(found: set[str]) -> set[str]:
    """Unity Catalog matches names whatever their case."""
    return {name.lower() for name in found}


def _missing_catalog(env: str, host: str, catalog: str, schemas: list[str]) -> Diagnostic:
    listed = ", ".join(f"`{schema}`" for schema in schemas)
    return error(
        "NSX301",
        platform.FILE_NAME,
        f"The catalog `{catalog}` isn't in {env}'s workspace, {host}, or the identity Nimblestax"
        f" signed in as can't see it. The project's tables in {env} need it.",
        f"Create the catalog `{catalog}` with the schemas {listed}, or grant the identity"
        " `USE CATALOG` on it. Nimblestax never creates catalogs.",
    )


def _missing_schema(env: str, host: str, schema: str) -> Diagnostic:
    catalog, name = schema.split(".")
    return error(
        "NSX302",
        platform.FILE_NAME,
        f"The schema `{schema}` isn't in {env}'s workspace, {host}, or the identity Nimblestax"
        f" signed in as can't see it. The project's tables in {env} need it.",
        f"Create the schema `{name}` in the catalog `{catalog}`, or grant the identity"
        " `USE SCHEMA` on it. Nimblestax never creates schemas.",
    )


def _missing_grant(env: str, catalog: str, group: str, missing: list[str]) -> Diagnostic:
    privileges = ", ".join(privilege.replace("_", " ") for privilege in missing)
    return error(
        "NSX303",
        platform.FILE_NAME,
        f"The developer group `{group}` has no {privileges} on the catalog `{catalog}` in {env}."
        " Each person's Preview Environment creates its schemas there, and its sources read the"
        " files that land in its Volumes.",
        f"As the catalog's owner, run `GRANT {privileges} ON CATALOG {catalog} TO `{group}`;`."
        " Grant it on the Development Environment's catalogs only.",
    )
