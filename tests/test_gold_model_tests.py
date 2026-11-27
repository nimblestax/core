"""`nsx test`: a Gold Model's Tests, run through a SQL warehouse on a Preview Environment's
tables."""

import json
import sys
import threading
import time
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
from nimblestax.deploy.databricks import DatabricksCli, QueryFailed, WorkspaceError
from nimblestax.load.project import load

runner = CliRunner()

HOST = "https://kettle.cloud.databricks.com"
ME = "bijil@nimblestax.com"
WAREHOUSE = "4b9b953939869799"


class FakeWorkspace:
    """The Databricks boundary, as one person signed in to dev's workspace sees it, after
    `nsx preview` has deployed their preview."""

    def __init__(self, user: str = ME):
        self.user = user
        self.deployed = True
        self.warehouse_list = [(WAREHOUSE, "Starter Warehouse")]
        # What each table's Test queries measure, by the real table name the query reads.
        self.measures: dict[str, list | QueryFailed] = {}
        self.queries: list[tuple[str, str, str]] = []
        # Called as each query starts, so a test can see what was said before it.
        self.on_query: Callable[[], None] = lambda: None
        # How long each query takes, and the most that ran at once.
        self.delay = 0.0
        self.peak = 0
        self._running = 0
        self._lock = threading.Lock()

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
        with self._lock:
            self._running += 1
            self.peak = max(self.peak, self._running)
        time.sleep(self.delay)
        with self._lock:
            self._running -= 1
        self.queries.append((host, warehouse, statement))
        for table, measured in self.measures.items():
            if f" {table}" in statement:
                if isinstance(measured, Exception):
                    raise measured
                return [measured]
        raise AssertionError(f"No table this fake knows in:\n{statement}")


def nsx(project: Path, *args: str):
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

    result = nsx(project, "test", "--json")

    assert result.exit_code == 1, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX401"
    assert found["file"] == FCT_ORDERS
    assert "unique(order_id)" in found["message"]
    assert "sales.gold.fct_orders" in found["message"]
    assert '{"order_id":7}' in found["message"]


def test_passing_tests_exit_0_and_run_on_the_only_warehouse_in_devs_workspace(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]

    result = nsx(project, "test", "--json")

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

    result = nsx(project, "test", "--json")

    assert result.exit_code == 0, result.output
    assert [warehouse for _, warehouse, _ in workspace.queries] == ["abc123"]


def test_with_several_warehouses_and_none_named_nsx_test_exits_2_listing_them(
    project: Path, workspace: FakeWorkspace
):
    workspace.warehouse_list = [(WAREHOUSE, "Starter Warehouse"), ("abc123", "Tests")]
    with_tests(project, "  - unique: [order_id]\n")

    result = nsx(project, "test", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX923"
    assert "abc123 (Tests)" in found["message"]
    assert "warehouse: " in found["fix"]
    assert not workspace.queries


def test_with_no_deployed_preview_nsx_test_exits_2_saying_to_preview_first(
    project: Path, workspace: FakeWorkspace
):
    workspace.deployed = False
    with_tests(project, "  - unique: [order_id]\n")

    result = nsx(project, "test", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX924"
    assert "`nsx preview`" in found["fix"]
    assert not workspace.queries


def test_a_pull_requests_preview_is_tested_on_its_own_tables(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures["dev_sales.pr42__gold.fct_orders"] = ["0", "[]"]

    result = nsx(project, "test", "--pr", "42", "--json")

    assert result.exit_code == 0, result.output


def test_with_no_deployed_pull_request_preview_the_fix_names_its_pull_request(
    project: Path, workspace: FakeWorkspace
):
    workspace.deployed = False

    result = nsx(project, "test", "--pr", "42", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert "`nsx preview --pr 42`" in found["fix"]


def failures(result) -> list[str]:
    assert result.exit_code == 1, result.output
    return [found["message"] for found in json.loads(result.stdout)["diagnostics"]]


def test_a_row_count_test_with_no_limits_fails_on_an_empty_table(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - row_count: {}\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0"]

    [message] = failures(nsx(project, "test", "--json"))

    assert "`row_count(min: 1)`" in message
    assert "has 0 rows" in message


@pytest.mark.parametrize(("rows", "passes"), [("99", False), ("100", True), ("501", False)])
def test_a_row_count_test_checks_its_minimum_and_maximum(
    project: Path, workspace: FakeWorkspace, rows: str, passes: bool
):
    with_tests(project, "  - row_count: {min: 100, max: 500}\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = [rows]

    result = nsx(project, "test", "--json")

    assert (result.exit_code == 0) is passes, result.output


REFERENCES_ORDERS = "  - references: {column: order_id, to: sales.silver.orders}\n"


def test_a_references_test_fails_on_values_missing_from_the_previews_own_table(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, REFERENCES_ORDERS)
    workspace.measures[PREVIEW_FCT_ORDERS] = ["3", '["7","9"]']

    [message] = failures(nsx(project, "test", "--json"))

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

    result = nsx(project, "test", "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["tests"][0]["test"] == (
        "references(order_id, to: sales.silver.orders.id)"
    )


def test_a_references_test_to_a_table_the_project_lacks_fails_validation(project: Path):
    with_tests(project, "  - references: {column: customer_id, to: sales.gold.dim_customers}\n")

    result = nsx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX213"
    assert found["file"] == FCT_ORDERS
    assert "sales.gold.dim_customers" in found["message"]


def test_a_test_of_a_type_nimblestax_lacks_is_one_problem_naming_the_types(project: Path):
    with_tests(project, "  - not_null: [order_id]\n")

    result = nsx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX106"
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

    result = nsx(project, "test", "--json")

    assert result.exit_code == 1, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX402"
    assert "`unique(order_no)`" in found["message"]
    assert "UNRESOLVED_COLUMN" in found["message"]
    assert len(workspace.queries) == 2


def test_owner_is_optional(project: Path):
    config = project / FCT_ORDERS
    config.write_text(
        "\n".join(line for line in config.read_text().splitlines() if "owner" not in line) + "\n"
    )

    assert nsx(project, "validate").exit_code == 0


def test_an_empty_owner_is_a_mistake(project: Path):
    config = project / FCT_ORDERS
    config.write_text(config.read_text() + 'owner: ""\n')

    result = nsx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX106"


def test_an_example_has_no_preview_so_nsx_test_refuses_it(tmp_path: Path, workspace: FakeWorkspace):
    kettle = tmp_path / "kettle"
    assert runner.invoke(app, ["init", str(kettle), "--example", "kettle"]).exit_code == 0

    result = nsx(kettle, "test", "--json")

    assert result.exit_code == 2, result.output
    assert [found["rule"] for found in json.loads(result.stdout)["diagnostics"]] == ["NSX921"]


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


def run_tests_at_a_time(project: Path, concurrency: int) -> None:
    platform = project / "nimblestax.platform.yaml"
    platform.write_text(platform.read_text() + f"tests:\n  concurrency: {concurrency}\n")


def test_each_test_is_reported_on_stderr_as_it_starts_and_ends_leaving_stdout_one_envelope(
    project: Path, workspace: FakeWorkspace
):
    run_tests_at_a_time(project, 1)
    with_tests(project, "  - unique: [order_id]\n")
    with_tests(project, "  - row_count: {}\n", "domains/sales/models/gold/dim_date.yaml")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]
    workspace.measures["dev_sales.u_bijil__gold.dim_date"] = ["0"]

    result = nsx(project, "test", "--json")

    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["ok"] is False
    assert result.stderr.splitlines() == [
        f"Running 2 Tests on your Preview Environment (u_bijil__), on warehouse {WAREHOUSE},"
        " 1 at a time.",
        "  started      sales.gold.dim_date: row_count(min: 1)",
        "  failed       sales.gold.dim_date: row_count(min: 1)  (1/2)",
        "  started      sales.gold.fct_orders: unique(order_id)",
        "  passed       sales.gold.fct_orders: unique(order_id)  (2/2)",
    ]


def test_a_test_is_announced_before_its_query_runs(project: Path, workspace: FakeWorkspace):
    with_tests(project, "  - unique: [order_id]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]
    seen: list[str] = []
    # What CliRunner has caught on stderr when the query starts.
    workspace.on_query = lambda: seen.append(cast(BytesIO, sys.stderr.buffer).getvalue().decode())

    result = nsx(project, "test")

    assert result.exit_code == 0, result.output
    assert seen and seen[0].endswith("  started      sales.gold.fct_orders: unique(order_id)\n")


def test_a_test_that_cant_run_is_reported_as_such(project: Path, workspace: FakeWorkspace):
    with_tests(project, "  - unique: [order_no]\n")
    workspace.measures[PREVIEW_FCT_ORDERS] = QueryFailed("[UNRESOLVED_COLUMN] order_no")

    result = nsx(project, "test")

    assert "  couldn't run sales.gold.fct_orders: unique(order_no)  (1/1)" in result.stderr
    assert result.stderr.startswith("Running 1 Test on your Preview Environment")


SEVERAL_TESTS = (
    "  - unique: [order_id]\n  - unique: [amount]\n  - row_count: {}\n  - row_count: {min: 0}\n"
)


@pytest.mark.parametrize(("concurrency", "expected"), [(None, 4), (2, 2), (1, 1)])
def test_tests_run_as_many_at_a_time_as_the_platform_contract_says_by_default_4(
    project: Path, workspace: FakeWorkspace, concurrency: int | None, expected: int
):
    if concurrency:
        run_tests_at_a_time(project, concurrency)
    with_tests(project, SEVERAL_TESTS)
    workspace.measures[PREVIEW_FCT_ORDERS] = ["5", "[]"]  # Every Test passes or fails alike.
    workspace.delay = 0.05

    result = nsx(project, "test", "--json")

    assert workspace.peak == expected, result.output
    assert len(workspace.queries) == 4


def test_failures_are_reported_in_the_order_tests_are_declared_however_they_finish(
    project: Path, workspace: FakeWorkspace
):
    with_tests(project, "  - unique: [order_id]\n")
    with_tests(project, "  - row_count: {}\n", "domains/sales/models/gold/dim_date.yaml")
    workspace.measures[PREVIEW_FCT_ORDERS] = ["2", '["1","2"]']
    workspace.measures["dev_sales.u_bijil__gold.dim_date"] = ["0"]

    result = nsx(project, "test", "--json")

    files = [found["file"] for found in json.loads(result.stdout)["diagnostics"]]
    assert files == ["domains/sales/models/gold/dim_date.yaml", FCT_ORDERS]


@pytest.mark.parametrize("concurrency", ["0", "65", "two"])
def test_concurrency_is_a_whole_number_from_1_to_64(project: Path, concurrency: str):
    platform = project / "nimblestax.platform.yaml"
    platform.write_text(platform.read_text() + f"tests:\n  concurrency: {concurrency}\n")

    result = nsx(project, "validate", "--json")

    assert result.exit_code == 1
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX106"
    assert found["file"] == "nimblestax.platform.yaml"


@pytest.mark.parametrize("named_warehouse", [False, True])
def test_an_identity_without_databricks_sql_access_gets_the_grant_to_ask_for(
    cli_project: Path, stub_workspace: str, stub_warehouse, named_warehouse: bool
):
    stub_warehouse.sql_denied = True
    workspace = DatabricksCli()

    with pytest.raises(WorkspaceError) as raised:
        if named_warehouse:
            workspace.query(stub_workspace, WAREHOUSE, "SELECT 1")
        else:
            workspace.warehouses(stub_workspace)

    [found] = raised.value.diagnostics
    assert found.rule == "NSX925"
    assert "databricks-sql-access" in found.fix
    assert "CAN USE" in found.fix


DIM_DATE = "domains/sales/models/gold/dim_date.yaml"
PREVIEW_DIM_DATE = "dev_sales.u_bijil__gold.dim_date"


def queried_tables(workspace: FakeWorkspace) -> set[str]:
    return {
        table
        for table in (PREVIEW_FCT_ORDERS, PREVIEW_DIM_DATE)
        for *_, sql in workspace.queries
        if f" {table}" in sql
    }


@pytest.mark.parametrize("name", ["fct_orders", "sales.gold.fct_orders", "Sales.Gold.FCT_ORDERS"])
def test_model_selects_the_tests_of_one_model_by_name_or_logical_name(
    project: Path, workspace: FakeWorkspace, name: str
):
    with_tests(project, "  - unique: [order_id]\n")
    with_tests(project, "  - row_count: {}\n", DIM_DATE)
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]

    result = nsx(project, "test", "--model", name, "--json")

    assert result.exit_code == 0, result.output
    assert queried_tables(workspace) == {PREVIEW_FCT_ORDERS}
    assert json.loads(result.stdout)["result"]["tests"] == [
        {"model": "sales.gold.fct_orders", "test": "unique(order_id)"}
    ]


def test_model_can_be_given_more_than_once(project: Path, workspace: FakeWorkspace):
    with_tests(project, "  - unique: [order_id]\n")
    with_tests(project, "  - row_count: {}\n", DIM_DATE)
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]
    workspace.measures[PREVIEW_DIM_DATE] = ["5"]

    result = nsx(project, "test", "--model", "fct_orders", "--model", "dim_date")

    assert result.exit_code == 0, result.output
    assert queried_tables(workspace) == {PREVIEW_FCT_ORDERS, PREVIEW_DIM_DATE}


def test_a_name_that_matches_no_model_exits_2_listing_the_models_before_reaching_databricks(
    project: Path, workspace: FakeWorkspace
):
    workspace.deployed = False  # Nothing about the workspace should be asked.

    result = nsx(project, "test", "--model", "fct_order", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX926"
    assert "`fct_order`" in found["message"]
    assert "sales.gold.dim_date" in found["fix"] and "sales.gold.fct_orders" in found["fix"]


def test_a_name_two_domains_share_exits_2_asking_for_the_logical_name(
    project: Path, workspace: FakeWorkspace
):
    platform = project / "nimblestax.platform.yaml"
    platform.write_text(platform.read_text().replace("  - sales\n", "  - sales\n  - finance\n"))
    finance = project / "domains/finance/models/gold"
    finance.mkdir(parents=True)
    (finance / "fct_orders.sql").write_text("SELECT 1 AS order_id\n")
    (finance / "fct_orders.yaml").write_text(
        "kind: model\nversion: 1\nsql: fct_orders.sql\nowner: finance-analytics\n"
    )

    result = nsx(project, "test", "--model", "fct_orders", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX926"
    assert "finance.gold.fct_orders" in found["fix"] and "sales.gold.fct_orders" in found["fix"]


@pytest.mark.parametrize("given", ["fct_orders,dim_date", "fct_orders, sales.gold.dim_date"])
def test_model_takes_a_comma_separated_list(project: Path, workspace: FakeWorkspace, given: str):
    with_tests(project, "  - unique: [order_id]\n")
    with_tests(project, "  - row_count: {}\n", DIM_DATE)
    workspace.measures[PREVIEW_FCT_ORDERS] = ["0", "[]"]
    workspace.measures[PREVIEW_DIM_DATE] = ["5"]

    result = nsx(project, "test", "--model", given)

    assert result.exit_code == 0, result.output
    assert queried_tables(workspace) == {PREVIEW_FCT_ORDERS, PREVIEW_DIM_DATE}


def test_a_name_two_model_layers_share_exits_2_listing_both_logical_names(
    project: Path, workspace: FakeWorkspace
):
    platform = project / "nimblestax.platform.yaml"
    platform.write_text(platform.read_text().replace("models: [gold]", "models: [gold, marts]"))
    marts = project / "domains/sales/models/marts"
    marts.mkdir(parents=True)
    (marts / "fct_orders.sql").write_text("SELECT order_id FROM sales.gold.fct_orders\n")
    (marts / "fct_orders.yaml").write_text(
        "kind: model\nversion: 1\nsql: fct_orders.sql\nowner: sales-analytics\n"
    )

    result = nsx(project, "test", "--model", "fct_orders", "--json")

    assert result.exit_code == 2, result.output
    [found] = json.loads(result.stdout)["diagnostics"]
    assert found["rule"] == "NSX926"
    assert found["message"] == "`fct_orders` names more than one Gold Model."
    assert "sales.gold.fct_orders" in found["fix"] and "sales.marts.fct_orders" in found["fix"]

    result = nsx(project, "test", "--model", "sales.marts.fct_orders", "--json")
    assert result.exit_code == 0, result.output
