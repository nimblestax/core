"""A Gold Model: a dataset built from SQL that reads Logical Names."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator
from pydantic_core import PydanticCustomError

from nimblestax.diagnostics import Diagnostic, error
from nimblestax.kinds.base import (
    CONFIG_SUFFIXES,
    STRICT,
    ExactInteger,
    Identifier,
    InDomain,
    config_files,
)

KIND = "model"
FOLDER = "models"


class Unique(BaseModel):
    """No two rows share a value of these columns. Rows with a NULL in any of them are skipped."""

    model_config = ConfigDict(**STRICT, title="Unique")

    unique: list[Identifier] = Field(
        min_length=1, description="The columns that together hold a different value in each row."
    )

    @property
    def name(self) -> str:
        return f"unique({', '.join(self.unique)})"


class RowLimits(BaseModel):
    """How many rows a table may have."""

    model_config = ConfigDict(**STRICT, title="Row limits")

    min: int = Field(default=1, ge=0, description="The fewest rows the table may have.")
    max: int | None = Field(
        default=None, ge=0, description="The most rows the table may have. Left out, no limit."
    )


class RowCount(BaseModel):
    """The table has between `min` and `max` rows. `row_count: {}` checks it isn't empty."""

    model_config = ConfigDict(**STRICT, title="Row count")

    row_count: RowLimits = Field(description="How many rows the table may have.")

    @property
    def name(self) -> str:
        limits = self.row_count
        most = f", max: {limits.max}" if limits.max is not None else ""
        return f"row_count(min: {limits.min}{most})"


class Reference(BaseModel):
    """A column, and the table and key its values must be in."""

    model_config = ConfigDict(**STRICT, title="Reference")

    column: Identifier = Field(description="The column whose values must be in the other table.")
    to: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){2}$",
        description="The other table's Logical Name, such as `shared.gold.dim_customers`.",
    )
    key: Identifier | None = Field(
        default=None, description="The other table's column. Left out, it has `column`'s name."
    )

    @property
    def key_column(self) -> str:
        return self.key or self.column


class References(BaseModel):
    """Every value of `column` is a `key` in the table `to`. NULLs are skipped."""

    model_config = ConfigDict(**STRICT, title="References")

    references: Reference = Field(description="The column, and the table and key it refers to.")

    @property
    def name(self) -> str:
        found = self.references
        return f"references({found.column}, to: {found.to}.{found.key_column})"


def _test_type(value: Any) -> str | None:
    """A Test is a mapping with one key, its type, so a mistake is reported against that type."""
    if isinstance(value, BaseModel):
        return next(iter(type(value).model_fields))  # Each Test's one field is its type.
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value))
    return None


Test = Annotated[
    Annotated[Unique, Tag("unique")]
    | Annotated[RowCount, Tag("row_count")]
    | Annotated[References, Tag("references")],
    Discriminator(
        _test_type,
        custom_error_type="test_type",
        custom_error_message="A Test is one of `unique`, `row_count` or `references`, with its"
        " settings",
    ),
]


class ModelV1(InDomain):
    """A dataset built from a SQL file that reads Logical Names."""

    model_config = ConfigDict(**STRICT, title="Nimblestax Gold Model")

    kind: Literal["model"] = Field(description="The Kind of this file.")
    version: Annotated[Literal[1], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    sql: str = Field(
        pattern=r"^[^/\\]+\.sql$", description="The SQL file, in the same folder as this file."
    )
    owner: str = Field(
        min_length=1,
        description="Who answers for this table: a team or a person, such as `sales-analytics`.",
    )
    tests: list[Test] = Field(
        default=[],
        description="The Tests `nstx test` runs on this model's table in a Preview Environment.",
    )

    @model_validator(mode="before")
    @classmethod
    def _has_owner(cls, data: Any) -> Any:
        # Its own rule rather than a missing field, so the fix can say what an owner is.
        if isinstance(data, dict) and "owner" not in data:
            raise PydanticCustomError(
                "NSTX134",
                "This Gold Model has no `owner`, and every Gold Model has one.",
                {
                    "fix": "Add `owner: <team>` naming who answers for this table, such as"
                    " `owner: sales-analytics`."
                },
            )
        return data

    @property
    def layer(self) -> str:
        """The first folder under `models/` names the Layer. Any deeper folders only group files."""
        return self.folders[0]

    @property
    def sql_file(self) -> Path:
        return self.config_file.parent / self.sql

    @property
    def query(self) -> str:
        return self.sql_file.read_text()


VERSIONS: dict[int, type[BaseModel]] = {1: ModelV1}
Model = ModelV1

# `UPGRADES[n]` turns version n into version n + 1.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {}


def problems(root: Path, folder: Path, models: list[Model]) -> list[Diagnostic]:
    """A Model whose SQL file is missing, and a SQL file that no Model names."""
    missing = [
        _missing_sql(_relative(root, model.config_file), model.sql)
        for model in models
        if not model.sql_file.exists()
    ]
    unnamed = [
        _sql_without_config(_relative(root, sql_file), sql_file.stem)
        for sql_file in sorted(folder.glob("*.sql"))
        if not _has_config_beside(sql_file) and not _is_named(sql_file)
    ]
    return missing + unnamed


def generate(model: Model, target: str, sql: str, streaming: bool) -> str:
    """A Gold Model that reads `STREAM(...)` is a streaming table, and any other a materialized
    view. Databricks refuses a materialized view over a stream."""
    table = "STREAMING TABLE" if streaming else "MATERIALIZED VIEW"
    return f"CREATE OR REFRESH {table} {target} AS\n{sql}"


def _has_config_beside(sql_file: Path) -> bool:
    return any(sql_file.with_suffix(suffix).exists() for suffix in CONFIG_SUFFIXES)


def _is_named(sql_file: Path) -> bool:
    """Whether any config file beside it names it, even one that's invalid in other ways."""
    return any(_names(file, sql_file.name) for file in config_files(sql_file.parent))


def _names(file: Path, sql: str) -> bool:
    try:
        content = yaml.safe_load(file.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    return isinstance(content, dict) and content.get("sql") == sql


def _relative(root: Path, file: Path) -> str:
    return file.relative_to(root).as_posix()


def _sql_without_config(file: str, stem: str) -> Diagnostic:
    return error(
        "NSTX108",
        file,
        "This SQL file has no config file beside it.",
        f"Add `{stem}.yaml` beside it with `kind: model`, `version: 1` and `sql: {stem}.sql`.",
    )


def _missing_sql(file: str, sql: str) -> Diagnostic:
    return error(
        "NSTX109",
        file,
        f"`{sql}` doesn't exist beside this file.",
        "Correct `sql`, or add the SQL file to the same folder.",
    )
