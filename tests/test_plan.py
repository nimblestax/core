"""`nsx plan` compares the project with an Environment's Deployment Manifest, and classes each
change it finds."""

import json
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from nimblestax import cli
from nimblestax.deploy.databricks import DatabricksCli

runner = CliRunner()

ROOT = "/Workspace/Users/ci@example.com/.bundle/sales_platform/{target}"
FCT_ORDERS = "domains/sales/models/gold/fct_orders.sql"
DIM_DATE = "domains/sales/models/gold/dim_date.sql"
FROM_FCT_ORDERS = "SELECT order_id\nFROM sales.gold.fct_orders\n"
WITH_TAX = "SELECT order_id, amount, amount * 0.1 AS tax\nFROM sales.silver.orders\n"


class FakeWorkspace:
    """Bundle calls that do nothing, and workspace files kept in memory."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def deploy_bundle(self, package: Path, target: str) -> None:
        pass

    def run_job(self, package: Path, target: str, job: str) -> None:
        pass

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        return []

    def bundle_root(self, package: Path, target: str) -> str:
        return ROOT.format(target=target)

    def write_file(self, package: Path, target: str, path: str, content: str) -> None:
        self.files[path] = content

    def read_file(self, package: Path, target: str, path: str) -> str | None:
        return self.files.get(path)

    def list_folder(self, package: Path, target: str, folder: str) -> list[str]:
        return sorted(path for path in self.files if path.rsplit("/", 1)[0] == folder)

    def delete_file(self, package: Path, target: str, path: str) -> None:
        del self.files[path]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    result = runner.invoke(cli.app, ["init", str(tmp_path / "sales_platform")])
    assert result.exit_code == 0, result.output
    return tmp_path / "sales_platform"


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch) -> FakeWorkspace:
    fake = FakeWorkspace()
    monkeypatch.setattr(cli, "DatabricksCli", lambda: fake)
    return fake


def nsx(project: Path, *args: str):
    return runner.invoke(cli.app, [*args, "--project", str(project)])


def deployed(project: Path) -> None:
    result = nsx(project, "deploy", "--env", "dev", "--json")
    assert result.exit_code == 0, result.output


def plan(project: Path) -> dict:
    result = nsx(project, "plan", "--env", "dev", "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_a_new_column_on_a_gold_model_is_one_safe_change_with_no_warning(
    project: Path, workspace: FakeWorkspace
):
    deployed(project)
    (project / FCT_ORDERS).write_text(WITH_TAX)

    printed = plan(project)

    assert printed["schema"] == "nimblestax.plan/1"
    assert printed["diagnostics"] == []
    assert printed["result"]["changes"] == [
        {
            "id": "update:sales.gold.fct_orders",
            "object": "sales.gold.fct_orders",
            "object_type": "materialized_view",
            "action": "update",
            "change_class": "safe",
            "reason": "Adds the column `tax`.",
            "rule": None,
            "refresh_tables": [],
            "downstream_domains": [],
        }
    ]
    assert printed["result"]["summary"] == {"safe": 1, "refresh": 0, "destructive": 0}
    assert printed["result"]["blocked"] is False


def add_model(project: Path, domain: str, layer: str, name: str, sql: str) -> None:
    folder = project / "domains" / domain / "models" / layer
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.sql").write_text(sql)
    (folder / f"{name}.yaml").write_text(f"kind: model\nversion: 1\nsql: {name}.sql\n")


def contract(project: Path, old: str, new: str) -> None:
    path = project / "nimblestax.platform.yaml"
    path.write_text(path.read_text().replace(old, new))


def test_a_new_gold_model_is_a_safe_create(project: Path, workspace: FakeWorkspace):
    deployed(project)
    add_model(project, "sales", "gold", "big_orders", FROM_FCT_ORDERS)

    [change] = plan(project)["result"]["changes"]

    assert change["id"] == "create:sales.gold.big_orders"
    assert (change["action"], change["change_class"]) == ("create", "safe")
    assert change["object_type"] == "materialized_view"
    assert change["reason"] == "A new materialized view."


def test_adding_a_domain_or_a_model_layer_is_safe(project: Path, workspace: FakeWorkspace):
    deployed(project)
    contract(project, "models: [gold]", "models: [gold, marts]")
    contract(project, "  - sales\n", "  - sales\n  - finance\n")
    add_model(project, "finance", "gold", "fct_revenue", "SELECT 1 AS revenue\n")
    add_model(project, "sales", "marts", "orders_by_day", FROM_FCT_ORDERS)

    printed = plan(project)

    assert printed["diagnostics"] == []
    changes = printed["result"]["changes"]
    assert [(c["object"], c["action"], c["change_class"]) for c in changes] == [
        ("finance.gold.fct_revenue", "create", "safe"),
        ("sales.marts.orders_by_day", "create", "safe"),
    ]


def test_an_unchanged_project_plans_nothing(project: Path, workspace: FakeWorkspace):
    deployed(project)

    result = plan(project)["result"]

    assert result["changes"] == []
    assert result["summary"] == {"safe": 0, "refresh": 0, "destructive": 0}
    assert result["baseline"]["env"] == "dev"


@pytest.mark.parametrize(
    "changed",
    [
        "SELECT order_id, amount\nFROM sales.silver.orders\nWHERE amount > 0\n",
        "SELECT order_id\nFROM sales.silver.orders\n",
        "SELECT order_id, amount * 100 AS amount\nFROM sales.silver.orders\n",
        f"{WITH_TAX}WHERE amount > 0\n",
    ],
    ids=["filter", "dropped-column", "changed-column", "new-column-and-filter"],
)
def test_a_change_the_plan_cant_class_yet_warns_and_isnt_guessed(
    project: Path, workspace: FakeWorkspace, changed: str
):
    deployed(project)
    (project / FCT_ORDERS).write_text(changed)

    printed = plan(project)

    assert printed["result"]["changes"] == []
    [warned] = printed["diagnostics"]
    assert (warned["rule"], warned["severity"]) == ("NSX501", "warning")
    assert "sales.gold.fct_orders" in warned["message"]


def test_a_removed_table_warns_that_the_plan_cant_class_it_yet(
    project: Path, workspace: FakeWorkspace
):
    deployed(project)
    for suffix in (".sql", ".yaml"):
        (project / FCT_ORDERS).with_suffix(suffix).unlink()

    printed = plan(project)

    assert printed["result"]["changes"] == []
    [warned] = printed["diagnostics"]
    assert warned["rule"] == "NSX501"
    assert "sales.gold.fct_orders" in warned["message"]


def test_with_no_manifest_every_table_is_new_and_the_plan_warns_why(
    project: Path, workspace: FakeWorkspace
):
    printed = plan(project)

    result = printed["result"]
    assert result["baseline"] is None
    assert {c["action"] for c in result["changes"]} == {"create"}
    assert "sales.gold.fct_orders" in {c["object"] for c in result["changes"]}
    [warned] = printed["diagnostics"]
    assert (warned["rule"], warned["severity"]) == ("NSX502", "warning")
    assert ROOT.format(target="dev") in warned["message"]


def test_a_manifest_from_before_definitions_were_recorded_warns_once(
    project: Path, workspace: FakeWorkspace
):
    deployed(project)
    path = f"{ROOT.format(target='dev')}/nimblestax/manifest.json"
    older = json.loads(workspace.files[path])
    older["tables"] = {
        name: {"type": table["type"], "file": table["file"]}
        for name, table in older["tables"].items()
    }
    workspace.files[path] = json.dumps(older)
    add_model(project, "sales", "gold", "big_orders", FROM_FCT_ORDERS)

    printed = plan(project)

    assert [c["object"] for c in printed["result"]["changes"]] == ["sales.gold.big_orders"]
    [warned] = printed["diagnostics"]
    assert warned["rule"] == "NSX503"


def test_printed_without_json_the_plan_is_a_comment_to_post_on_the_pull_request(
    project: Path, workspace: FakeWorkspace
):
    deployed(project)
    (project / FCT_ORDERS).write_text(WITH_TAX)
    add_model(project, "sales", "gold", "big_orders", FROM_FCT_ORDERS)
    (project / DIM_DATE).write_text("SELECT DATE'2020-01-01' AS date_day\n")

    result = nsx(project, "plan", "--env", "dev")

    assert result.exit_code == 0, result.output
    comment = result.output
    assert comment.startswith("## Plan against dev\n")
    assert "| safe | create | `sales.gold.big_orders` | A new materialized view. |" in comment
    assert "| safe | update | `sales.gold.fct_orders` | Adds the column `tax`. |" in comment
    assert (
        "[**NSX501**](https://github.com/nimblestax/core/blob/main/docs/reference/rules/nsx501.md)"
        " (warning): sales.gold.dim_date changed"
    ) in comment
    footer = comment.rstrip().splitlines()[-1]
    assert footer == (
        f"Nimblestax {version('nimblestax')} ·"
        " [changelog](https://github.com/nimblestax/core/blob/main/docs/changelog.md#"
        f"{version('nimblestax').replace('.', '')})"
    )


def test_a_plan_with_nothing_to_change_says_so(project: Path, workspace: FakeWorkspace):
    deployed(project)

    result = nsx(project, "plan", "--env", "dev")

    assert "No changes to dev's tables." in result.output


def test_the_pull_request_workflow_posts_the_plan_against_dev_as_devs_identity(project: Path):
    workflow = project / ".github/workflows/nimblestax-pull-request.yaml"
    jobs = yaml.safe_load(workflow.read_text())["jobs"]

    job = jobs["plan"]
    assert job["needs"] == "validate"
    # Pull request code holds only dev's identity, so the Plan never needs test's or prod's.
    assert job["environment"] == "dev"
    assert job["permissions"]["pull-requests"] == "write"
    runs = [step["run"] for step in job["steps"] if "run" in step]
    assert runs[0] == 'uvx --from "$NIMBLESTAX_SPEC" nsx plan --env dev > plan.md'
    assert "gh pr comment ${{ github.event.pull_request.number }} --body-file plan.md" in runs[1]


def test_the_databricks_cli_reads_a_workspace_file_or_says_there_is_none(
    tmp_path: Path, stub_workspace: str, stub_files: dict, monkeypatch: pytest.MonkeyPatch
):
    result = runner.invoke(cli.app, ["init", str(tmp_path / "p"), "--host", stub_workspace])
    assert result.exit_code == 0, result.output
    assert nsx(tmp_path / "p", "compile").exit_code == 0
    package = tmp_path / "p" / "build"
    monkeypatch.setenv("DATABRICKS_TOKEN", "not-a-real-token")
    workspace = DatabricksCli()
    root = workspace.bundle_root(package, "dev")
    stub_files[f"{root}/nimblestax/manifest.json"] = '{"env": "dev"}\n'

    assert workspace.read_file(package, "dev", f"{root}/nimblestax/manifest.json") == (
        '{"env": "dev"}\n'
    )
    assert workspace.read_file(package, "dev", f"{root}/nimblestax/missing.json") is None


def test_the_comment_says_which_commit_dev_last_received_or_that_it_had_none(
    project: Path, workspace: FakeWorkspace
):
    deployed(project)

    comment = nsx(project, "plan", "--env", "dev").output

    # The project isn't a Git repo, so its package was built from no commit.
    assert "Compared with what dev last received: a package built outside Git, deployed" in comment
