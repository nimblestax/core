"""Name mapping: the only module that builds a real table name."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nimblestax.statements import escaped

if TYPE_CHECKING:
    # Only for annotations, because the platform Kind reads the Naming Styles from here.
    from nimblestax.kinds.platform import Platform
    from nimblestax.kinds.source import Source
    from nimblestax.load.project import Project

PLACEHOLDER = re.compile(r"\$\{(\w+)\}")

# Each Naming Style's catalog and schema patterns, in the order `nsx init` offers them.
NAMING_STYLES = {
    "system-and-domain-catalogs": ("{env}_{domain}", "{layer}"),
    "layer-catalogs": ("{env}_{layer}", "{domain}"),
    "environment-catalogs": ("{env}", "{domain}_{layer}"),
}


def real_names(style: str, env: str, domain: str, layer: str) -> tuple[str, str]:
    """The catalog and schema that hold one Environment's tables for a Domain and Layer."""
    catalog, schema = NAMING_STYLES[style]
    parts = {"env": env, "domain": domain, "layer": layer}
    return catalog.format(**parts), schema.format(**parts)


def example(style: str) -> tuple[str, str]:
    """The sales Domain's silver `orders` under a Naming Style: its Logical Name, and its real
    name in prod."""
    orders = Table("sales", "silver", "orders")
    return logical_name(style, orders), real_name(style, "prod", orders)


def style_for(catalog: str, schema: str) -> str | None:
    """The Naming Style with exactly these patterns, if there is one."""
    for style, patterns in NAMING_STYLES.items():
        if patterns == (catalog, schema):
            return style
    return None


def closest_style(catalog: str, schema: str) -> str:
    """The style that puts the most placeholders where these patterns do, the first on a tie."""

    def shared(style: str) -> int:
        style_catalog, style_schema = NAMING_STYLES[style]
        return sum(
            (placeholder in catalog and placeholder in style_catalog)
            + (placeholder in schema and placeholder in style_schema)
            for placeholder in ("{env}", "{domain}", "{layer}")
        )

    return max(NAMING_STYLES, key=shared)


@dataclass(frozen=True)
class Table:
    """A table, by its Domain, its Layer and its own name. Always lowercase, because Databricks
    matches names whatever their case.

    How it's written, its Logical Name, depends on the Naming Style: see `logical_name`.
    """

    domain: str
    layer: str
    entity: str

    def __post_init__(self) -> None:
        for part in ("domain", "layer", "entity"):
            object.__setattr__(self, part, getattr(self, part).lower())


def real_name(style: str, env: str, table: Table, prefix: str = "") -> str:
    """The table's name in one Environment, or with `prefix` on its schema, in a Preview
    Environment."""
    catalog, schema = real_names(style, env, table.domain, table.layer)
    return f"{catalog}.{prefix}{schema}.{table.entity}"


def logical_name(style: str, table: Table) -> str:
    """The table's real name without the Environment: `silver.sales.orders` under
    `layer-catalogs`, and `sales_silver.orders` under `environment-catalogs`."""
    return ".".join((*_logical_prefix(style, table.domain, table.layer), table.entity))


def logical_name_parts(style: str) -> int:
    """How many parts a Logical Name has under a style: three, or two under
    `environment-catalogs`."""
    return len(_logical_prefix(style, "domain", "layer")) + 1


def _logical_prefix(style: str, domain: str, layer: str) -> tuple[str, ...]:
    """The parts before the table's own name, built from the style's real-name patterns with
    the Environment taken out, so a Logical Name and a real name can't drift apart."""
    catalog, schema = NAMING_STYLES[style]
    parts = {"domain": domain, "layer": layer}
    without_env = catalog.removeprefix("{env}").removeprefix("_")
    kept = (without_env, schema) if without_env else (schema,)
    return tuple(pattern.format(**parts).lower() for pattern in kept)


def placeholders(name: Table) -> str:
    """The table as generated code refers to it, the same in every Environment."""
    catalog = catalog_setting(name.domain, name.layer)
    schema = schema_setting(name.domain, name.layer)
    return f"${{{catalog}}}.${{{schema}}}.{name.entity}"


def catalog_setting(domain: str, layer: str) -> str:
    """The placeholder for a Domain and Layer's catalog, keyed in lowercase like Logical Names."""
    return f"catalog_{domain}_{layer}".lower()


def schema_setting(domain: str, layer: str) -> str:
    return f"schema_{domain}_{layer}".lower()


def path_placeholder(source: Source) -> str:
    """Where a Source's files land as generated code refers to it, the same in every Environment."""
    return f"${{{_path_setting(source)}}}"


def settings(project: Project, env: str) -> dict[str, str]:
    """The value of every placeholder in one Environment."""
    platform = project.platform
    values = {}
    for domain in platform.domains:
        for layer in (*platform.source_layers, *platform.model_layers):
            catalog, schema = real_names(platform.naming.style, env, domain, layer)
            values[catalog_setting(domain, layer)] = catalog
            values[schema_setting(domain, layer)] = schema
    for source in project.sources:
        # Escaped, because generated code substitutes it between the quotes of a string literal.
        values[_path_setting(source)] = escaped(source.path_in(env))
    return values


# A Preview Environment is named by its prefix, and lives in the Development Environment's catalogs.
# The two prefixes start differently, so a person's preview and a pull request's never share one.
PERSONAL = "u_"
PULL_REQUEST = "pr"


# A user name's part before the `@` that reads back from its cleaned form: words joined by dots.
PLAIN_USER = re.compile(r"[a-z0-9]+(\.[a-z0-9]+)*")


def personal_prefix(user: str) -> str:
    """The prefix of one person's Preview Environment schemas, from their user name.

    `priya.sharma@acme.com` is `u_priya_sharma__`. Any other character becomes `_` too, and
    then a short hash of the whole name keeps `priya_sharma` apart from `priya.sharma`.
    """
    local = user.split("@")[0].lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", local).strip("_") or "user"
    if not PLAIN_USER.fullmatch(local):
        cleaned += "_" + hashlib.sha256(user.lower().encode()).hexdigest()[:6]
    return f"{PERSONAL}{cleaned}__"


def pull_request_prefix(number: int) -> str:
    """The prefix of one pull request's Preview Environment schemas: `pr42__`."""
    return f"{PULL_REQUEST}{number}__"


def preview_schemas(platform: Platform, prefix: str) -> dict[str, tuple[str, str]]:
    """Each Domain and Layer's catalog and schema in a Preview Environment, by `<domain>_<layer>`.

    The catalogs are the Development Environment's, and each schema is its own with `prefix`.
    """
    found = {}
    for domain in platform.domains:
        for layer in (*platform.source_layers, *platform.model_layers):
            catalog, schema = real_names(
                platform.naming.style, platform.development_environment, domain, layer
            )
            found[f"{domain}_{layer}".lower()] = (catalog, f"{prefix}{schema}")
    return found


def preview_settings(project: Project, prefix: str) -> dict[str, str]:
    """The value of every placeholder in a Preview Environment.

    It is the Development Environment's, with each schema prefixed, so a Source reads the files
    that land in dev.
    """
    values = settings(project, project.platform.development_environment)
    return {
        key: f"{prefix}{value}" if key.startswith("schema_") else value
        for key, value in values.items()
    }


def platform_objects(
    platform: Platform, envs: Iterable[str] | None = None
) -> tuple[list[str], list[str]]:
    """Every catalog, and every schema as `catalog.schema`, the project's tables need in `envs`,
    by default every Environment, in Environment, Domain and Layer order."""
    catalogs: dict[str, None] = {}
    schemas: dict[str, None] = {}
    for env in platform.hosts if envs is None else envs:
        for domain in platform.domains:
            for layer in (*platform.source_layers, *platform.model_layers):
                catalog, schema = real_names(platform.naming.style, env, domain, layer)
                catalogs[catalog] = None
                schemas[f"{catalog}.{schema}"] = None
    return list(catalogs), list(schemas)


def table_named(
    platform: Platform, written: tuple[str, ...], style: str | None = None
) -> Table | None:
    """The table a Logical Name in `style`, by default the project's, names, if it names one.

    The Domain and Layer are found by lookup, not by splitting the name: every pairing's
    Logical Name is built the one way, and each pairing's real names are unique.
    """
    style = style or platform.naming.style
    *prefix, entity = (part.lower() for part in written)
    for domain in platform.domains:
        for layer in (*platform.source_layers, *platform.model_layers):
            if tuple(prefix) == _logical_prefix(style, domain, layer):
                return Table(domain, layer, entity)
    return None


def other_styles(platform: Platform) -> list[str]:
    """Every Naming Style but the project's, in the order `nsx init` offers them."""
    return [style for style in NAMING_STYLES if style != platform.naming.style]


def table_for_real_name(project: Project, written: tuple[str, ...]) -> Table | None:
    """The table behind a real table name in any Environment, if it is one."""
    if len(written) != 3:
        return None
    platform = project.platform
    catalog_written, schema_written, entity = (part.lower() for part in written)
    for env in platform.hosts:
        values = settings(project, env)
        for domain in platform.domains:
            for layer in (*platform.source_layers, *platform.model_layers):
                catalog = values[catalog_setting(domain, layer)].lower()
                schema = values[schema_setting(domain, layer)].lower()
                if (catalog_written, schema_written) == (catalog, schema):
                    return Table(domain, layer, entity)
    return None


def resolve(generated: str, project: Project, env: str) -> str:
    """Generated code with its placeholders replaced by one Environment's real names.

    `${word}` that names no setting is the author's own text, so it stays as written.
    """
    values = settings(project, env)
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), generated)


def _path_setting(source: Source) -> str:
    # The double underscore keeps `sales` + `eu_orders` apart from `sales_eu` + `orders`.
    return f"path_{source.domain}__{source.name}"
