"""`nstx validate --platform`: the platform objects a project needs exist in its workspace."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nimblestax import cli
from nimblestax.cli import app
from nimblestax.deploy import deploy, pinned_cli
from nimblestax.load.project import load

runner = CliRunner()

HOST = "https://kettle.cloud.databricks.com"


class FakeUnityCatalog:
    """A workspace's catalogs and schemas, as the Databricks boundary reports them."""

    def __init__(self, schemas: dict[str, set[str]]):
        self.schemas_by_catalog = schemas
        self.calls: list[tuple] = []

    def catalogs(self, host: str) -> set[str]:
        self.calls.append(("catalogs", host))
        return set(self.schemas_by_catalog)

    def schemas(self, host: str, catalog: str) -> set[str]:
        self.calls.append(("schemas", host, catalog))
        return self.schemas_by_catalog[catalog]


def nstx(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path), "--host", HOST]).exit_code == 0
    return tmp_path


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch) -> FakeUnityCatalog:
    """Everything `nstx init` lists for dev, until a test takes something away."""
    fake = FakeUnityCatalog({"dev_sales": {"bronze", "silver", "gold"}})
    monkeypatch.setattr(cli, "DatabricksCli", lambda: fake)
    return fake


def test_a_missing_catalog_fails_with_a_rule_naming_it(project: Path, workspace: FakeUnityCatalog):
    del workspace.schemas_by_catalog["dev_sales"]

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "NSTX301"
    assert "dev_sales" in diagnostic["message"]


def test_plain_validate_makes_no_workspace_call(project: Path, workspace: FakeUnityCatalog):
    del workspace.schemas_by_catalog["dev_sales"]

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 0, result.output
    assert workspace.calls == []


def test_a_missing_schema_fails_with_a_rule_naming_it(project: Path, workspace: FakeUnityCatalog):
    workspace.schemas_by_catalog["dev_sales"] = {"bronze", "gold"}

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX302"
    assert "dev_sales.silver" in diagnostic["message"]


PROD_HOST = "https://kettle-prod.cloud.databricks.com"


def add_prod(project: Path, host: str | None) -> None:
    contract = project / "nimblestax.platform.yaml"
    settings = "\n    role: production" + (f"\n    host: {host}" if host else "")
    contract.write_text(
        contract.read_text().replace("naming:\n", f"  prod:{settings}\nnaming:\n", 1)
    )


def test_env_checks_that_environment_in_its_own_workspace(
    project: Path, workspace: FakeUnityCatalog
):
    add_prod(project, PROD_HOST)
    workspace.schemas_by_catalog = {"prod_sales": {"bronze", "silver", "gold"}}

    result = nstx(project, "validate", "--platform", "--env", "prod", "--json")

    assert result.exit_code == 0, result.output
    assert workspace.calls == [
        ("catalogs", PROD_HOST),
        ("schemas", PROD_HOST, "prod_sales"),
    ]


@pytest.mark.parametrize("host", [None, PROD_HOST])
def test_prod_in_a_shared_or_its_own_workspace_validates_with_no_warning(
    project: Path, host: str | None
):
    # Every Naming Style puts the Environment in the catalog, so a shared workspace shares no
    # table, and its identities and grants are nothing Nimblestax checks.
    add_prod(project, host)

    result = nstx(project, "validate", "--json")

    assert json.loads(result.stdout)["diagnostics"] == []


class ShippingWorkspace:
    def __init__(self) -> None:
        self.deployed: list[str] = []

    def deploy_bundle(self, package: Path, target: str) -> None:
        self.deployed.append(target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        pass

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        return []


def test_the_warning_never_stops_a_deploy(project: Path):
    add_prod(project, None)
    workspace = ShippingWorkspace()

    deploy.deploy(load(project), "prod", workspace)

    assert workspace.deployed == ["prod"]


def test_the_generated_ci_checks_the_platform_as_dev_before_anything_else(project: Path):
    workflows = project / ".github/workflows"
    pull_request = (workflows / "nimblestax-pull-request.yaml").read_text()
    merge = (workflows / "nimblestax-merge.yaml").read_text()

    assert "nstx validate --platform --env dev" in pull_request
    assert "nstx validate --platform --env dev" in merge
    assert merge.index("nstx validate --platform") < merge.index("nstx deploy")
    # The check signs in, so the pull request job needs dev's identity.
    assert "id-token: write" in pull_request
    assert "environment: dev" in pull_request
    assert "DATABRICKS_AUTH_TYPE: github-oidc" in pull_request


def fake_cli(folder: Path, catalogs: list[str], schemas: list[str]) -> Path:
    """A Databricks CLI that answers the two listings and records each call with its host."""
    script = folder / "fake-databricks"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$DATABRICKS_HOST $@" >> {folder}/calls\n'
        'case "$1 $2" in\n'
        f'  "--version ") echo "Databricks CLI v{pinned_cli.MINIMUM}" ;;\n'
        f"  \"catalogs list\") echo '{json.dumps([{'name': name} for name in catalogs])}' ;;\n"
        f"  \"schemas list\") echo '{json.dumps([{'name': name} for name in schemas])}' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    script.chmod(0o755)
    return script


def test_the_databricks_cli_lists_catalogs_and_schemas_in_the_environments_workspace(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cli_folder = tmp_path / "cli"
    cli_folder.mkdir()
    script = fake_cli(cli_folder, ["DEV_SALES", "main"], ["bronze", "gold"])
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(script))
    monkeypatch.setenv("DATABRICKS_HOST", "https://somewhere-else.cloud.databricks.com")

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX302"
    assert "dev_sales.silver" in diagnostic["message"]
    calls = (cli_folder / "calls").read_text().splitlines()
    assert f"{HOST} catalogs list --output json" in calls
    assert f"{HOST} schemas list dev_sales --output json" in calls


def test_env_without_platform_is_a_usage_error(project: Path, workspace: FakeUnityCatalog):
    result = nstx(project, "validate", "--env", "dev", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX901"
    assert "--platform" in diagnostic["fix"]


class GrantedUnityCatalog(FakeUnityCatalog):
    """Also reports each principal's privileges on a catalog."""

    def __init__(self, schemas: dict[str, set[str]], granted: dict[str, set[str]]):
        super().__init__(schemas)
        self.granted = granted

    def privileges(self, host: str, catalog: str, principal: str) -> set[str]:
        self.calls.append(("privileges", host, catalog, principal))
        return self.granted.get(catalog, set())


ALL_FOUR = {"USE_CATALOG", "USE_SCHEMA", "CREATE_SCHEMA", "READ_VOLUME"}


def name_developers(project: Path) -> None:
    contract = project / "nimblestax.platform.yaml"
    contract.write_text(
        contract.read_text().replace("naming:\n", "developers: data-engineers\nnaming:\n", 1)
    )


@pytest.fixture
def granted(monkeypatch: pytest.MonkeyPatch) -> GrantedUnityCatalog:
    fake = GrantedUnityCatalog({"dev_sales": {"bronze", "silver", "gold"}}, {"dev_sales": ALL_FOUR})
    monkeypatch.setattr(cli, "DatabricksCli", lambda: fake)
    return fake


def test_the_developer_group_with_its_four_grants_on_dev_validates(
    project: Path, granted: GrantedUnityCatalog
):
    name_developers(project)

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 0, result.output
    assert ("privileges", HOST, "dev_sales", "data-engineers") in granted.calls


@pytest.mark.parametrize("missing", sorted(ALL_FOUR))
def test_a_missing_developer_grant_fails_with_the_sql_that_grants_it(
    project: Path, granted: GrantedUnityCatalog, missing: str
):
    name_developers(project)
    granted.granted["dev_sales"] = ALL_FOUR - {missing}

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX303"
    assert "data-engineers" in diagnostic["message"]
    assert "dev_sales" in diagnostic["message"]
    privilege = missing.replace("_", " ")
    assert f"GRANT {privilege} ON CATALOG dev_sales TO `data-engineers`;" in diagnostic["fix"]


def test_all_privileges_holds_every_developer_grant(project: Path, granted: GrantedUnityCatalog):
    name_developers(project)
    granted.granted["dev_sales"] = {"ALL_PRIVILEGES"}

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 0, result.output


def test_developer_grants_are_checked_only_in_the_development_environment(
    project: Path, granted: GrantedUnityCatalog
):
    add_prod(project, None)
    name_developers(project)
    granted.schemas_by_catalog = {"prod_sales": {"bronze", "silver", "gold"}}

    result = nstx(project, "validate", "--platform", "--env", "prod", "--json")

    assert result.exit_code == 0, result.output
    assert not [call for call in granted.calls if call[0] == "privileges"]


def test_without_a_developer_group_no_grant_is_read(project: Path, granted: GrantedUnityCatalog):
    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 0, result.output
    assert not [call for call in granted.calls if call[0] == "privileges"]


def test_the_databricks_cli_reads_the_developer_groups_effective_grants(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    name_developers(project)
    cli_folder = tmp_path / "cli"
    cli_folder.mkdir()
    script = fake_cli(cli_folder, ["dev_sales"], ["bronze", "silver", "gold"])
    granted = {
        "privilege_assignments": [
            {
                "principal": "data-engineers",
                "privileges": [{"privilege": "USE_CATALOG"}, {"privilege": "USE_SCHEMA"}],
            }
        ]
    }
    script.write_text(
        script.read_text().replace(
            "  *) exit 1 ;;\n",
            f"  \"grants get-effective\") echo '{json.dumps(granted)}' ;;\n  *) exit 1 ;;\n",
        )
    )
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(script))

    result = nstx(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX303"
    assert "CREATE SCHEMA, READ VOLUME" in diagnostic["message"]
    calls = (cli_folder / "calls").read_text().splitlines()
    assert (
        f"{HOST} grants get-effective catalog dev_sales --principal data-engineers --output json"
        in calls
    )
