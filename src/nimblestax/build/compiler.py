"""Turns a Project into generated code: one file per table group, same in every Environment."""

import shutil
from pathlib import Path

from nimblestax import names, sql
from nimblestax.build import bundle
from nimblestax.build import package as build_package
from nimblestax.kinds import model, seed, source
from nimblestax.load.project import Project
from nimblestax.names import LogicalName

BUILD_FOLDER = "build"
STREAMING_TABLE = "streaming_table"
MATERIALIZED_VIEW = "materialized_view"


def generated_files(project: Project) -> dict[Path, str]:
    """Generated code by path relative to the package, using placeholders."""
    files: dict[Path, str] = {}
    bronze_layer, silver_layer = project.platform.source_layers
    for item in project.sources:
        bronze = names.placeholders(LogicalName(item.domain, bronze_layer, item.name))
        silver = names.placeholders(LogicalName(item.domain, silver_layer, item.name))
        quarantine = names.placeholders(LogicalName(item.domain, silver_layer, item.quarantine))
        path = Path("src") / item.domain / "ingest" / f"{item.name}.sql"
        files[path] = source.generate(
            item, names.path_placeholder(item), bronze, silver, quarantine
        )
    for item in project.seeds:
        target = names.placeholders(LogicalName(item.domain, silver_layer, item.name))
        files[Path("src") / item.domain / "ingest" / f"{item.name}.sql"] = seed.generate(
            item, target
        )
    for item in project.models:
        layer = item.layer
        target = names.placeholders(LogicalName(item.domain, layer, item.name))
        path = Path("src") / item.domain / "gold" / f"{item.name}.sql"
        query = sql.escape_placeholders(item.query)
        rewritten = sql.rewrite(query, names.placeholders)
        files[path] = model.generate(item, target, rewritten, sql.streams(item.query))
    return files


def tables(project: Project) -> dict[str, dict]:
    """Each table the package writes, by Logical Name, with its type and generated file."""
    found: dict[str, dict] = {}
    bronze_layer, silver_layer = project.platform.source_layers

    def add(name: LogicalName, kind: str, path: Path) -> None:
        found[f"{name.domain}.{name.layer}.{name.entity}"] = {"type": kind, "file": path.as_posix()}

    for item in project.sources:
        path = Path("src") / item.domain / "ingest" / f"{item.name}.sql"
        add(LogicalName(item.domain, bronze_layer, item.name), STREAMING_TABLE, path)
        add(LogicalName(item.domain, silver_layer, item.name), STREAMING_TABLE, path)
        if item.silver.quarantining:
            add(LogicalName(item.domain, silver_layer, item.quarantine), STREAMING_TABLE, path)
    for item in project.seeds:
        path = Path("src") / item.domain / "ingest" / f"{item.name}.sql"
        add(LogicalName(item.domain, silver_layer, item.name), MATERIALIZED_VIEW, path)
    for item in project.models:
        path = Path("src") / item.domain / "gold" / f"{item.name}.sql"
        kind = STREAMING_TABLE if sql.streams(item.query) else MATERIALIZED_VIEW
        add(LogicalName(item.domain, item.layer, item.name), kind, path)
    return dict(sorted(found.items()))


def write_package(project: Project, preview: bundle.Preview | None = None) -> Path:
    """The Build Package: generated code, every target's settings, then the checksum record."""
    package = project.root / BUILD_FOLDER
    shutil.rmtree(package, ignore_errors=True)
    package.mkdir()
    for relative, content in generated_files(project).items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (package / "databricks.yaml").write_text(bundle.render(project, preview))
    build_package.write_record(package, project.root, tables(project))
    return package


def print_for(project: Project, env: str) -> str:
    """Every generated file as runnable SQL for one Environment."""
    code = "\n".join(generated_files(project).values())
    return names.resolve(code, project, env)
