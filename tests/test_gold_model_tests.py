"""`nstx test`: a Gold Model's Tests, run through a SQL warehouse on a Preview Environment's
tables."""

import json
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
import yaml
from typer.testing import CliRunner

from nimblestax import cli
from nimblestax.build import compiler
from nimblestax.cli import app
from nimblestax.deploy import databricks
from nimblestax.deploy.databricks import DatabricksCli, QueryFailed
from nimblestax.load.project import load

runner = CliRunner()

HOST = "https://kettle.cloud.databricks.com"
ME = "bijil@nimblestax.com"
WAREHOUSE = "4b9b953939869799"


class FakeWorkspace:
    """The Databricks boundary, as one person signed in to dev's workspace sees it, after
    `nstx preview` has deployed their preview."""

    def __init__(self, user: str = ME):
        self.user = user
        self.deployed = True
        self.warehouse_list = [(WAREHOUSE, "Starter Warehouse")]
        # What each table's Test queries measure, by the real table name the query reads.
        self.measures: dict[str, list | QueryFailed] = {}
        self.queries: list[tuple[str, str, str]] = []
        # Called as each query starts, so a test can see what was said before it.
        self.on_query: Callable[[], None] = lambda: None

    def current_user(self, host: str) -> str:
        return self.user

    def bundle_root(self, package: Path, target: str) -> str:
        bundled = yaml.safe_load((package / "databricks.yaml").read_text())
        name = bundled["bundle"]["name"]
        configured = bundled["targets"][target].get("workspace", {}).get("root_path")
        root = configured or f"~/.bundle/{name}/{target}"
        return root.replace("~", f"/Workspace/Users/{self.user}", 1)

    def exists(self, package: Path, target: str, path: str) -> bool:
        return self.deployed and path.endswith("/nimblestax/manifest.json")

    def warehouses(self, host: str) -> list[tuple[str, str]]:
        return self.warehouse_list

    def query(self, host: str, warehouse: str, statement: str) -> list[list]:
        self.on_query()
        self.queries.append((host, warehouse, statement))
        for table, measured in self.measures.items():
            if f" {table}" in statement:
                if isinstance(measured, Exception):
                    raise measured
                return [measured]
        raise AssertionError(f"No table this fake knows in:\n{statement}")


def nstx(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    result = runner.invoke(app, ["init", str(tmp_path / "shop"), "--host", HOST])
    assert result.exit_code == 0, result.output
    return tmp_path / "shop"


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch) -> FakeWorkspace:
    fake = FakeWorkspace()
    monkeypatch.setattr(cli, "DatabricksCli", lambda: fake)
    return fake


FCT_ORDERS = "domains/sales/models/gold/fct_orders.yaml"
PREVIEW_FCT_ORDERS = "dev_sales.u_bijil__gold.fct_orders"


def with_tests(project: Path, tests: str, file: str = FCT_ORDERS) -> None:
    config = project / file
    config.write_text(config.read_text() + f"tests:\n{tests}")


def test_a_failing_uniqueness_test_fails_and_is_reported_by_name(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["2", '["{\\"order_id\\":7}","{\\"order_id\\":9}"]']

    result = nstx(project, "test", "--json")

    assert result.exit_code == 1, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX401"
    assert found["file"] == FCT_ORDERS
    assert "unique(order_id)" in found["message"]
    assert "sales.gold.fct_orders" in found["message"]
    assert '{"order_id":7}' in found["message"]


def test_passing_tests_exit_0_and_run_on_the_only_warehouse_in_devs_workspace(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]

    result = nstx(project, "test", "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["tests"] == [
        {"model": "sales.gold.fct_orders", "test": "unique(order_id)"}
    ]
    [(host, warehouse, _)] = workspace.queries
    assert (host, warehouse) == (HOST, WAREHOUSE)


def test_the_development_environments_warehouse_wins_over_any_other(
    project: Path, workspace: FakeWorkspace
):
    platform = project / "nimblestax.platform.yaml"
    platform.write_text(
        platform.read_text().replace(
            "    role: development\n", "    role: development\n" "    warehouse: abc123\n"
        )
    )
    workspace.warehouse_list = [(WAREHOUSE, "Starter Warehouse"), ("abc123", "Tests")]
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]

    result = nstx(project, "test", "--json")

    assert result.exit_code == 0, result.output
    assert [warehouse for _, warehouse, _ in workspace.queries] == ["abc123"]


def test_with_several_warehouses_and_none_named_nstx_test_exits_2_listing_them(
    project: Path, workspace: FakeWorkspace
):
    workspace.warehouse_list = [(WAREHOUSE, "Starter Warehouse"), ("abc123", "Tests")]
    with_tests(project, "  - unique: [order_id]\n")

    result = nstx(project, "test", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX923"
    assert "abc123 (Tests)" in found["message"]
    assert "warehouse: " in found["fix"]
    assert not workspace.queries


def test_with_no_deployed_preview_nstx_test_exits_2_saying_to_preview_first(
    project: Path, workspace: FakeWorkspace
):
    workspace.deployed = False
    with_tests(project, "  - unique: [order_id]\n")

    result = nstx(project, "test", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX924"
    assert "`nstx preview`" in found["fix"]
    assert not workspace.queries


def test_a_pull_requests_preview_is_tested_on_its_own_tables(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures["dev_sales.pr42__gold.fct_orders"] = ["0", "[]"]

    result = nstx(project, "test", "--pr", "42", "--json")

    assert result.exit_code == 0, result.output


def test_with_no_deployed_pull_request_preview_the_fix_names_its_pull_request(
    project: Path, workspace: FakeWorkspace
):
    workspace.deployed = False

    result = nstx(project, "test", "--pr", "42", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert "`nstx preview --pr 42`" in found["fix"]


def failures(result) -> list[str]:
    assert result.exit_code == 1, result.output
    return [found["message"] for found in json.loads(result.stdout)["diagnostics"]]


def test_a_row_count_test_with_no_limits_fails_on_an_empty_table(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - row_count: {}\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0"]

    [message] = failures(nstx(project, "test", "--json"))

    assert "`row_count(min: 1)`" in message
    assert "has 0 rows" in message


@pytest.mark.parametrize(("rows", "passes"), [("99", False), ("100", True), ("501", False)])
def test_a_row_count_test_checks_its_minimum_and_maximum(
    project: Path, workspace: FakeWorkspace, rows: str, passes: bool
):
    with_tests(project, "  - row_count: {min: 100, max: 500}\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = [rows]

    result = nstx(project, "test", "--json")

    assert (result.exit_code == 0) is passes, result.output


REFERENCES_ORDERS = "  - references: {column: order_id, to: sales.silver.orders}\n"


def test_a_references_test_fails_on_values_missing_from_the_previews_own_table(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, REFERENCES_ORDERS)
    workspace.measures[PREVIEW_FCT_ORDERS] = ["3", '["7","9"]']

    [message] = failures(nstx(project, "test", "--json"))

    assert "`references(order_id, to: sales.silver.orders.order_id)`" in message
    assert "3 rows" in message and "7, 9" in message
    # The table it references is the one the preview built, not dev's.
    [(_, _, statement)] = workspace.queries
    assert "dev_sales.u_bijil__silver.orders" in statement


def test_a_references_test_can_name_a_key_with_another_name(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - references: {column: order_id, to: sales.silver.orders, key: id}\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]

    result = nstx(project, "test", "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["tests"][0]["test"] == (
        "references(order_id, to: sales.silver.orders.id)"
    )


def test_a_references_test_to_a_table_the_project_lacks_fails_validation(project: Path):
    with_tests(project, "  - references: {column: customer_id, to: sales.gold.dim_customers}\n")

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX213"
    assert found["file"] == FCT_ORDERS
    assert "sales.gold.dim_customers" in found["message"]


def test_a_test_of_a_type_nimblestax_lacks_is_one_problem_naming_the_types(project: Path):
    with_tests(project, "  - not_null: [order_id]\n")

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX106"
    assert "`references`" in found["message"]


def test_a_test_that_cant_run_fails_with_the_warehouses_error_and_the_rest_still_run(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_no]\n")
    with_tests(project, "  - row_count: {}\n", "domains/sales/models/gold/dim_date.yaml")
    workspace.measures[PREVIEW_FCT_ORDERS] = QueryFailed(
        "[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column `order_no` cannot be resolved."
    )
    workspace.measures["dev_sales.u_bijil__gold.dim_date"] = ["5844"]

    result = nstx(project, "test", "--json")

    assert result.exit_code == 1, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX402"
    assert "`unique(order_no)`" in found["message"]
    assert "UNRESOLVED_COLUMN" in found["message"]
    assert len(workspace.queries) == 2


def test_a_gold_model_with_no_owner_fails_validation(project: Path):
    config = project / FCT_ORDERS
    config.write_text(
        "\n".join(line for line in config.read_text().splitlines() if "owner" not in line) + "\n"
    )

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSTX134"
    assert found["file"] == FCT_ORDERS
    assert "owner: " in found["fix"]


def test_every_gold_model_nstx_init_writes_has_an_owner(project: Path):
    assert nstx(project, "validate").exit_code == 0
    for config in (project / "domains").rglob("models/**/*.yaml"):
        assert "owner: " in config.read_text()


def test_an_example_has_no_preview_so_nstx_test_refuses_it(
    tmp_path: Path, workspace: FakeWorkspace
):
    kettle = tmp_path / "kettle"
    assert runner.invoke(app, ["init", str(kettle), "--example", "kettle"]).exit_code == 0

    result = nstx(kettle, "test", "--json")

    assert result.exit_code == 2, result.output
    assert [found["rule"] for found in json.loads(result.stdout)["diagnostics"]] == ["NSTX921"]


@pytest.fixture
def cli_project(tmp_path: Path, stub_workspace: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    result = runner.invoke(app, ["init", str(tmp_path / "shop"), "--host", stub_workspace])
    assert result.exit_code == 0, result.output
    monkeypatch.setenv("DATABRICKS_TOKEN", "not-a-real-token")
    return tmp_path / "shop"


def test_the_databricks_cli_tells_a_written_file_from_a_missing_one(
    cli_project: Path, stub_files: dict
):
    package = compiler.write_package(load(cli_project))
    workspace = DatabricksCli()
    root = workspace.bundle_root(package, "dev")
    stub_files[f"{root}/nimblestax/manifest.json"] = "{}"

    assert workspace.exists(package, "dev", f"{root}/nimblestax/manifest.json")
    assert not workspace.exists(package, "dev", f"{root}/nimblestax/other.json")


def test_the_databricks_cli_lists_warehouses_and_runs_a_statement_until_it_finishes(
    cli_project: Path, stub_workspace: str, stub_warehouse, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(databricks, "POLL_SECONDS", 0)
    stub_warehouse.warehouses = [{"id": WAREHOUSE, "name": "Starter Warehouse"}]
    stub_warehouse.answers = [
        {"statement_id": "s1", "status": {"state": "PENDING"}},
        {"statement_id": "s1", "status": {"state": "RUNNING"}},
        {
            "statement_id": "s1",
            "status": {"state": "SUCCEEDED"},
            "result": {"data_array": [["2", None]]},
        },
    ]
    workspace = DatabricksCli()

    assert workspace.warehouses(stub_workspace) == [(WAREHOUSE, "Starter Warehouse")]
    assert workspace.query(stub_workspace, WAREHOUSE, "SELECT 1") == [["2", None]]
    [sent] = stub_warehouse.statements
    assert (sent["warehouse_id"], sent["statement"]) == (WAREHOUSE, "SELECT 1")


def test_a_statement_the_warehouse_refuses_raises_its_message(
    cli_project: Path, stub_workspace: str, stub_warehouse
):
    stub_warehouse.answers = [
        {
            "statement_id": "s1",
            "status": {
                "state": "FAILED",
                "error": {"message": "[UNRESOLVED_COLUMN] A column `x` cannot be resolved."},
            },
        }
    ]

    with pytest.raises(QueryFailed, match="UNRESOLVED_COLUMN"):
        DatabricksCli().query(stub_workspace, WAREHOUSE, "SELECT x")


def test_a_statement_with_no_rows_returns_none(
    cli_project: Path, stub_workspace: str, stub_warehouse
):
    stub_warehouse.answers = [{"statement_id": "s1", "status": {"state": "SUCCEEDED"}}]

    assert DatabricksCli().query(stub_workspace, WAREHOUSE, "SELECT 1 WHERE false") == []


def test_each_test_is_reported_on_stderr_as_it_runs_leaving_stdout_one_envelope(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    with_tests(project, "  - row_count: {}\n", "domains/sales/models/gold/dim_date.yaml")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]
    workspace.measures["dev_sales.u_bijil__gold.dim_date"] = ["0"]

    result = nstx(project, "test", "--json")

    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["ok"] is False
    assert result.stderr.splitlines() == [
        f"Running 2 Tests on your Preview Environment (u_bijil__), on warehouse {WAREHOUSE}.",
        "  [1/2] sales.gold.dim_date: row_count(min: 1) ... failed",
        "  [2/2] sales.gold.fct_orders: unique(order_id) ... passed",
    ]


def test_each_test_is_announced_before_its_query_runs(project: Path, workspace: FakeWorkspace):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]
    seen: list[str] = []
    # What CliRunner has caught on stderr when the query starts.
    workspace.on_query = lambda: seen.append(cast(BytesIO, sys.stderr.buffer).getvalue().decode())

    result = nstx(project, "test")

    assert result.exit_code == 0, result.output
    assert seen and seen[0].endswith("sales.gold.fct_orders: unique(order_id) ... ")


def test_a_test_that_cant_run_is_reported_as_such_as_it_runs(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_no]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = QueryFailed("[UNRESOLVED_COLUMN] order_no")

    result = nstx(project, "test")

    assert "  [1/1] sales.gold.fct_orders: unique(order_no) ... couldn't run" in result.stderr
    assert result.stderr.startswith("Running 1 Test on your Preview Environment")
