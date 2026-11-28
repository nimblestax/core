"""A Logical Name is the real name without the Environment, in the shape the Naming Style gives."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nimblestax import names
from nimblestax.cli import app
from nimblestax.load.project import load
from nimblestax.names import Table

ORDERS = Table("sales", "silver", "orders")
REVENUE = Table("finance", "gold", "fct_revenue")

# Each style, a table, its Logical Name, and its real name in dev, prod and pull request 42's
# Preview Environment.
CASES = [
    (
        "layer-catalogs",
        ORDERS,
        "silver.sales.orders",
        "dev_silver.sales.orders",
        "prod_silver.sales.orders",
        "dev_silver.pr42__sales.orders",
    ),
    (
        "layer-catalogs",
        REVENUE,
        "gold.finance.fct_revenue",
        "dev_gold.finance.fct_revenue",
        "prod_gold.finance.fct_revenue",
        "dev_gold.pr42__finance.fct_revenue",
    ),
    (
        "system-and-domain-catalogs",
        ORDERS,
        "sales.silver.orders",
        "dev_sales.silver.orders",
        "prod_sales.silver.orders",
        "dev_sales.pr42__silver.orders",
    ),
    (
        "environment-catalogs",
        ORDERS,
        "sales_silver.orders",
        "dev.sales_silver.orders",
        "prod.sales_silver.orders",
        "dev.pr42__sales_silver.orders",
    ),
    (
        "environment-catalogs",
        REVENUE,
        "finance_gold.fct_revenue",
        "dev.finance_gold.fct_revenue",
        "prod.finance_gold.fct_revenue",
        "dev.pr42__finance_gold.fct_revenue",
    ),
]


@pytest.mark.parametrize(("style", "table", "logical", "dev", "prod", "preview"), CASES)
def test_each_style_gives_a_tables_logical_name_and_its_real_name_in_each_environment(
    style: str, table: Table, logical: str, dev: str, prod: str, preview: str
):
    assert names.logical_name(style, table) == logical
    assert names.real_name(style, "dev", table) == dev
    assert names.real_name(style, "prod", table) == prod
    assert names.real_name(style, "dev", table, prefix="pr42__") == preview


@pytest.mark.parametrize(("style", "table", "logical", "dev", "prod", "preview"), CASES)
def test_the_logical_name_is_the_real_name_without_the_environment(
    style: str, table: Table, logical: str, dev: str, prod: str, preview: str
):
    for env, real in (("dev", dev), ("prod", prod)):
        without = real.removeprefix(f"{env}_").removeprefix(f"{env}.")
        assert without == logical


runner = CliRunner()
STARTER_SQL = "domains/sales/models/gold/fct_orders.sql"


def nsx(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


def init(project: Path, style: str) -> Path:
    result = runner.invoke(app, ["init", str(project), "--naming-style", style])
    assert result.exit_code == 0, result.output
    return project


@pytest.mark.parametrize(
    ("style", "logical", "real"),
    [
        ("layer-catalogs", "silver.sales.orders", "dev_silver.sales.orders"),
        ("system-and-domain-catalogs", "sales.silver.orders", "dev_sales.silver.orders"),
        ("environment-catalogs", "sales_silver.orders", "dev.sales_silver.orders"),
    ],
)
def test_the_starter_gold_model_reads_the_styles_logical_name_and_compiles_to_the_real_one(
    tmp_path: Path, style: str, logical: str, real: str
):
    project = init(tmp_path, style)

    assert f"FROM {logical}\n" in (project / STARTER_SQL).read_text()
    validated = nsx(project, "validate")
    assert validated.exit_code == 0, validated.output
    compiled = nsx(project, "compile", "--env", "dev")
    assert compiled.exit_code == 0, compiled.output
    assert f"FROM {real}\n" in compiled.stdout


VERSION_2_DOMAIN_CATALOGS = (
    "kind: platform\nversion: 2\nname: shop\nenvironments:\n  dev:\n"
    "    host: https://dev.example.com\n    role: development\n"
    "naming:\n  style: domain-catalogs\n  layers:\n    models: [gold]\ndomains:\n  - sales\n"
)


def test_a_0_1_0_domain_catalogs_project_upgrades_with_every_name_unchanged(tmp_path: Path):
    project = init(tmp_path, "system-and-domain-catalogs")
    (project / "nimblestax.platform.yaml").write_text(VERSION_2_DOMAIN_CATALOGS)

    assert load(project).platform.naming.style == "system-and-domain-catalogs"
    assert "FROM sales.silver.orders\n" in (project / STARTER_SQL).read_text()
    validated = nsx(project, "validate")
    assert validated.exit_code == 0, validated.output
    compiled = nsx(project, "compile", "--env", "dev")
    assert "STREAMING TABLE dev_sales.silver.orders" in compiled.stdout
    assert "MATERIALIZED VIEW dev_sales.gold.fct_orders" in compiled.stdout
    assert "FROM dev_sales.silver.orders\n" in compiled.stdout


def failures(project: Path) -> list[dict]:
    result = nsx(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


@pytest.mark.parametrize(
    ("style", "written", "other", "right"),
    [
        (
            "layer-catalogs",
            "sales.silver.orders",
            "system-and-domain-catalogs",
            "silver.sales.orders",
        ),
        ("layer-catalogs", "sales_silver.orders", "environment-catalogs", "silver.sales.orders"),
        (
            "system-and-domain-catalogs",
            "silver.sales.orders",
            "layer-catalogs",
            "sales.silver.orders",
        ),
        ("environment-catalogs", "silver.sales.orders", "layer-catalogs", "sales_silver.orders"),
        (
            "environment-catalogs",
            "sales.silver.orders",
            "system-and-domain-catalogs",
            "sales_silver.orders",
        ),
    ],
)
def test_a_logical_name_in_another_styles_shape_fails_naming_the_right_spelling(
    tmp_path: Path, style: str, written: str, other: str, right: str
):
    project = init(tmp_path, style)
    (project / STARTER_SQL).write_text(f"SELECT order_id, amount\nFROM {written}\n")

    [failure] = failures(project)

    assert failure["rule"] == "NSX214"
    assert failure["line"] == 2
    assert failure["message"] == (
        f"{written} is a Logical Name under `{other}`, and this project's Naming Style is"
        f" `{style}`."
    )
    assert failure["fix"] == f"Write it as {right}, its Logical Name under `{style}`."


def test_a_two_part_name_is_a_logical_name_only_under_environment_catalogs(tmp_path: Path):
    project = init(tmp_path, "layer-catalogs")
    (project / STARTER_SQL).write_text("SELECT order_id, amount\nFROM sales.orders\n")

    [failure] = failures(project)

    assert failure["rule"] == "NSX201"
    assert "Write the table as a Logical Name, such as silver.sales.orders" in failure["fix"]


def test_a_column_qualified_by_a_two_part_logical_name_compiles_to_the_real_table(tmp_path: Path):
    project = init(tmp_path, "environment-catalogs")
    (project / STARTER_SQL).write_text(
        "SELECT sales_silver.orders.order_id, amount\n"
        "FROM sales_silver.orders -- not sales_silver.orders in a comment\n"
    )

    compiled = nsx(project, "compile", "--env", "dev")

    assert compiled.exit_code == 0, compiled.output
    assert "SELECT dev.sales_silver.orders.order_id, amount\n" in compiled.stdout
    assert "FROM dev.sales_silver.orders -- not sales_silver.orders in a comment\n" in (
        compiled.stdout
    )


@pytest.mark.parametrize(
    ("style", "bronze", "silver"),
    [
        ("layer-catalogs", "bronze.sales.orders", "silver.sales.orders"),
        ("environment-catalogs", "sales_bronze.orders", "sales_silver.orders"),
    ],
)
def test_rule_messages_write_logical_names_in_the_projects_style(
    tmp_path: Path, style: str, bronze: str, silver: str
):
    project = init(tmp_path, style)
    (project / STARTER_SQL).write_text(f"SELECT order_id, amount\nFROM {bronze}\n")

    [failure] = failures(project)

    assert failure["rule"] == "NSX210"
    assert failure["fix"] == f"Read {silver} instead."


def test_a_references_test_names_its_table_by_a_two_part_logical_name(tmp_path: Path):
    project = init(tmp_path, "environment-catalogs")
    config = project / "domains/sales/models/gold/fct_orders.yaml"
    config.write_text(
        config.read_text() + "tests:\n  - references: {column: order_id, to: sales_silver.orders}\n"
    )
    assert nsx(project, "validate").exit_code == 0

    config.write_text(
        config.read_text().replace("to: sales_silver.orders", "to: sales.silver.orders")
    )
    [failure] = failures(project)
    assert failure["rule"] == "NSX213"
    assert "such as `shared_gold.dim_customers`" in failure["fix"]


def test_the_build_packages_tables_are_keyed_by_logical_name(tmp_path: Path):
    project = init(tmp_path, "layer-catalogs")

    compiled = nsx(project, "compile")

    assert compiled.exit_code == 0, compiled.output
    record = json.loads((project / "build/nimblestax.package.json").read_text())
    assert set(record["tables"]) == {
        "bronze.sales.orders",
        "silver.sales.orders",
        "gold.sales.fct_orders",
        "gold.sales.dim_date",
    }
