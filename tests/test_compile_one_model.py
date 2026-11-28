"""`nsx compile --env <env> --model <name>` prints one Gold Model's query, ready to run."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nimblestax.cli import app

runner = CliRunner()


def nsx(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path), "--skills", "none"]).exit_code == 0
    return tmp_path


def test_prints_only_the_models_query_resolved_for_the_environment(project: Path):
    result = nsx(project, "compile", "--env", "dev", "--model", "fct_orders")

    assert result.exit_code == 0, result.output
    assert result.stdout == "SELECT order_id, amount\nFROM dev_sales.silver.orders\n"


@pytest.mark.parametrize(
    ("style", "silver"),
    [
        ("domain-catalogs", "dev_sales.silver.orders"),
        ("layer-catalogs", "dev_silver.sales.orders"),
        ("environment-catalogs", "dev.sales_silver.orders"),
    ],
)
def test_resolves_the_query_in_every_naming_style(tmp_path: Path, style: str, silver: str):
    init = runner.invoke(app, ["init", str(tmp_path), "--skills", "none", "--naming-style", style])
    assert init.exit_code == 0, init.output

    result = nsx(tmp_path, "compile", "--env", "dev", "--model", "fct_orders")

    assert result.exit_code == 0, result.output
    assert result.stdout == f"SELECT order_id, amount\nFROM {silver}\n"


def test_finds_a_model_by_its_logical_name(project: Path):
    result = nsx(project, "compile", "--env", "dev", "--model", "sales.gold.fct_orders")

    assert result.exit_code == 0, result.output
    assert "FROM dev_sales.silver.orders" in result.stdout


def test_a_model_that_reads_another_model_reads_its_real_table(project: Path):
    marts = project / "domains/sales/models/gold"
    (marts / "big_orders.sql").write_text(
        "SELECT order_id FROM sales.gold.fct_orders WHERE amount > 100\n"
    )
    (marts / "big_orders.yaml").write_text("kind: model\nversion: 1\nsql: big_orders.sql\n")

    result = nsx(project, "compile", "--env", "dev", "--model", "big_orders")

    assert result.exit_code == 0, result.output
    assert result.stdout == ("SELECT order_id FROM dev_sales.gold.fct_orders WHERE amount > 100\n")


def test_json_gives_the_environment_the_model_and_its_sql(project: Path):
    result = nsx(project, "compile", "--env", "dev", "--model", "fct_orders", "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"] == {
        "env": "dev",
        "model": "sales.gold.fct_orders",
        "sql": "SELECT order_id, amount\nFROM dev_sales.silver.orders",
    }


def test_model_without_env_is_a_usage_error(project: Path):
    result = nsx(project, "compile", "--model", "fct_orders", "--json")

    assert result.exit_code == 2, result.output
    assert not (project / "build").exists()
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX901"
    assert "--env" in found["message"]
    assert "nsx compile --env dev --model fct_orders" in found["fix"]


def test_a_name_that_matches_no_model_exits_2_listing_the_models(project: Path):
    result = nsx(project, "compile", "--env", "dev", "--model", "fct_order", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX926"
    assert "`fct_order`" in found["message"]
    assert "sales.gold.dim_date" in found["fix"] and "sales.gold.fct_orders" in found["fix"]


def test_a_name_two_domains_share_exits_2_listing_both_logical_names(project: Path):
    platform = project / "nimblestax.platform.yaml"
    platform.write_text(platform.read_text().replace("  - sales\n", "  - sales\n  - finance\n"))
    finance = project / "domains/finance/models/gold"
    finance.mkdir(parents=True)
    (finance / "fct_orders.sql").write_text("SELECT 1 AS order_id\n")
    (finance / "fct_orders.yaml").write_text("kind: model\nversion: 1\nsql: fct_orders.sql\n")

    result = nsx(project, "compile", "--env", "dev", "--model", "fct_orders", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX926"
    assert found["message"] == "`fct_orders` names more than one Gold Model."
    assert "sales.gold.fct_orders" in found["fix"] and "finance.gold.fct_orders" in found["fix"]


def test_one_model_is_picked_at_a_time(project: Path):
    result = nsx(project, "compile", "--env", "dev", "--model", "fct_orders,dim_date", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX926"
