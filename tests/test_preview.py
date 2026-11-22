"""`nstx preview`: a person's working tree, deployed to their own schemas in dev's catalogs."""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from nimblestax import cli, names
from nimblestax.build import bundle, compiler
from nimblestax.cli import app
from nimblestax.deploy import pinned_cli
from nimblestax.load.project import load

runner = CliRunner()

HOST = "https://kettle.cloud.databricks.com"
ME = "bijil@nimblestax.com"
ROOT = f"/Workspace/Users/{ME}/.bundle/shop/preview"


class FakeWorkspace:
    """The Databricks boundary, as one person signed in to dev's workspace sees it."""

    def __init__(self, user: str = ME):
        self.user = user
        self.calls: list[tuple] = []
        # Each catalog's schemas, with their properties.
        self.schemas: dict[str, dict[str, dict[str, str]]] = {}
        # The schemas the preview's bundle state holds, as (catalog, schema).
        self.state: list[tuple[str, str]] = []
        self.packages: list[dict] = []
        # The workspace's files, by path.
        self.files: dict[str, str] = {}

    def current_user(self, host: str) -> str:
        self.calls.append(("current_user", host))
        return self.user

    def schema_properties(self, host: str, catalog: str) -> dict[str, dict[str, str]]:
        self.calls.append(("schema_properties", host, catalog))
        return self.schemas.get(catalog, {})

    def deploy_bundle(self, package: Path, target: str) -> None:
        self.calls.append(("deploy", target))
        self.packages.append(yaml.safe_load((package / "databricks.yaml").read_text()))

    def run_job(self, package: Path, target: str, job: str) -> None:
        self.calls.append(("run", target, job))

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        return []

    def deployed_schemas(self, package: Path, target: str) -> list[tuple[str, str]]:
        self.calls.append(("deployed_schemas", target))
        return self.state

    def destroy_bundle(self, package: Path, target: str) -> None:
        self.calls.append(("destroy", target))
        # Destroying a bundle removes its root folder, with everything in it.
        root = self.bundle_root(package, target)
        self.files = {path: text for path, text in self.files.items() if not path.startswith(root)}

    def bundle_root(self, package: Path, target: str) -> str:
        """The target's `root_path`, with `~` the signed-in identity's home, as Databricks
        resolves it."""
        bundled = yaml.safe_load((package / "databricks.yaml").read_text())
        name = bundled["bundle"]["name"]
        configured = bundled["targets"][target].get("workspace", {}).get("root_path")
        root = configured or f"~/.bundle/{name}/{target}"
        return root.replace("~", f"/Workspace/Users/{self.user}", 1)

    def write_file(self, package: Path, target: str, path: str, content: str) -> None:
        self.files[path] = content

    def list_folder(self, package: Path, target: str, folder: str) -> list[str]:
        return [path for path in self.files if path.rsplit("/", 1)[0] == folder]

    def delete_file(self, package: Path, target: str, path: str) -> None:
        del self.files[path]


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


def preview_target(workspace: FakeWorkspace) -> dict:
    [package] = workspace.packages
    return package["targets"]["preview"]


def test_a_preview_deploys_every_table_to_the_persons_own_schemas(
    project: Path, workspace: FakeWorkspace
):
    result = nstx(project, "preview", "--json")

    assert result.exit_code == 0, result.output
    assert ("deploy", "preview") in workspace.calls
    assert ("run", "preview", "refresh") in workspace.calls
    # Nothing it does reaches dev's own bundle.
    assert not [call for call in workspace.calls if "dev" in call[1:2]]
    target = preview_target(workspace)
    schemas = {
        (schema["catalog_name"], schema["name"])
        for schema in target["resources"]["schemas"].values()
    }
    assert schemas == {
        ("dev_sales", "u_bijil__bronze"),
        ("dev_sales", "u_bijil__silver"),
        ("dev_sales", "u_bijil__gold"),
    }
    assert target["variables"]["schema_sales_gold"] == "u_bijil__gold"
    assert target["variables"]["catalog_sales_gold"] == "dev_sales"
    # Every table is built: no Pointer View, so the SQL is the same as every other target's.
    gold = (project / "build/src/sales/gold/fct_orders.sql").read_text()
    assert "VIEW" not in gold.replace("MATERIALIZED VIEW", "")
    assert json.loads(result.stdout)["result"]["schemas"] == sorted(
        f"{catalog}.{schema}" for catalog, schema in schemas
    )


def validated(package: Path, host: str, target: str, home: Path) -> dict:
    """The bundle as the Databricks CLI resolves one target."""
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "DATABRICKS_HOST": host,
        "DATABRICKS_TOKEN": "not-a-real-token",
    }
    ran = subprocess.run(
        [pinned_cli.databricks(), "bundle", "validate", "--target", target, "--output", "json"],
        cwd=package,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    return json.loads(ran.stdout)


def test_databricks_accepts_the_preview_target_in_development_mode_and_dev_stays_production(
    tmp_path: Path, stub_workspace: str
):
    folder = tmp_path / "shop"
    assert runner.invoke(app, ["init", str(folder), "--host", stub_workspace]).exit_code == 0
    package = compiler.write_package(load(folder), bundle.personal(ME))

    preview = validated(package, stub_workspace, "preview", tmp_path)
    dev = validated(package, stub_workspace, "dev", tmp_path)

    pipelines = preview["resources"]["pipelines"]
    assert pipelines["sales_ingest"]["name"] == "u_bijil__shop_sales_ingest"
    # A reference, resolved at deploy, so the schema is created before its pipeline.
    assert pipelines["sales_ingest"]["schema"] == "${resources.schemas.sales_bronze.name}"
    assert preview["resources"]["schemas"]["sales_bronze"]["name"] == "u_bijil__bronze"
    assert pipelines["sales_gold"]["development"] is True
    assert pipelines["sales_gold"]["configuration"]["schema_sales_silver"] == "u_bijil__silver"
    [job] = preview["resources"]["jobs"].values()
    assert job["name"] == "u_bijil__shop_refresh"
    assert "schedule" not in job
    schema = preview["resources"]["schemas"]["sales_silver"]
    assert schema["properties"] == {"nimblestax.project": "shop", "nimblestax.user": ME}
    assert preview["workspace"]["root_path"] != dev["workspace"]["root_path"]
    assert preview.get("bundle", {}).get("mode") is None
    # Long-lived Environments keep production mode, with none of the preview's schemas.
    assert not dev["resources"]["pipelines"]["sales_gold"].get("development")
    assert "schemas" not in dev["resources"]
    assert dev["resources"]["pipelines"]["sales_ingest"]["name"] == "shop_dev_sales_ingest"


def test_a_sources_env_resolves_to_the_development_environment_in_a_preview(
    project: Path, workspace: FakeWorkspace
):
    nstx(project, "preview")

    paths = preview_target(workspace)["variables"]
    assert paths["path_sales__orders"] == "/Volumes/dev_sales/bronze/landing/orders"


def test_a_previews_generated_files_match_every_other_targets_byte_for_byte(
    project: Path, workspace: FakeWorkspace
):
    nstx(project, "compile")
    compiled = {
        path.relative_to(project / "build"): path.read_bytes()
        for path in (project / "build/src").rglob("*.sql")
    }

    nstx(project, "preview")

    previewed = {
        path.relative_to(project / "build"): path.read_bytes()
        for path in (project / "build/src").rglob("*.sql")
    }
    assert compiled and previewed == compiled


@pytest.mark.parametrize(
    "style, schema",
    [
        ("domain-catalogs", "dev_sales.u_bijil__silver"),
        ("layer-catalogs", "dev_silver.u_bijil__sales"),
        ("environment-catalogs", "dev.u_bijil__sales_silver"),
    ],
)
def test_preview_schemas_follow_the_naming_style(
    tmp_path: Path, workspace: FakeWorkspace, style: str, schema: str
):
    folder = tmp_path / "shop"
    runner.invoke(app, ["init", str(folder), "--host", HOST, "--naming-style", style])

    result = nstx(folder, "preview", "--json")

    assert schema in json.loads(result.stdout)["result"]["schemas"]


def test_two_peoples_previews_of_one_project_share_no_schema_pipeline_or_bundle_state(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    seen = []
    for user in (ME, "priya.sharma@nimblestax.com"):
        fake = FakeWorkspace(user)
        monkeypatch.setattr(cli, "DatabricksCli", lambda fake=fake: fake)
        assert nstx(project, "preview").exit_code == 0
        seen.append(preview_target(fake))

    mine, theirs = seen
    assert not set(_schema_names(mine)) & set(_schema_names(theirs))
    assert not {p["name"] for p in mine["resources"]["pipelines"].values()} & {
        p["name"] for p in theirs["resources"]["pipelines"].values()
    }
    # Bundle state sits under each person's own home folder in the workspace.
    assert mine["workspace"]["root_path"].startswith("~/")


def _schema_names(target: dict) -> list[str]:
    return [
        f"{schema['catalog_name']}.{schema['name']}"
        for schema in target["resources"]["schemas"].values()
    ]


def test_a_preview_deploys_uncommitted_changes(project: Path, workspace: FakeWorkspace):
    model = project / "domains/sales/models/gold/fct_orders.sql"
    model.write_text(model.read_text() + "\n-- tried in a preview\n")

    nstx(project, "preview")

    gold = (project / "build/src/sales/gold/fct_orders.sql").read_text()
    assert "-- tried in a preview" in gold


@pytest.mark.parametrize(
    "user, prefix",
    [
        ("bijil@nimblestax.com", "u_bijil__"),
        ("Priya.Sharma@acme.com", "u_priya_sharma__"),
    ],
)
def test_a_user_name_becomes_a_readable_schema_prefix(user: str, prefix: str):
    assert names.personal_prefix(user) == prefix


@pytest.mark.parametrize(
    "first, second",
    [
        ("priya.sharma@acme.com", "priya_sharma@acme.com"),
        ("priya.sharma@acme.com", "priya-sharma@acme.com"),
        ("priya..sharma@acme.com", "priya.sharma@acme.com"),
        ("o'neil@acme.com", "o.neil@acme.com"),
    ],
)
def test_two_user_names_never_clean_to_one_prefix(first: str, second: str):
    assert names.personal_prefix(first) != names.personal_prefix(second)


@pytest.mark.parametrize(
    "user", ["7da8a1ae-c185-4974-9329-a5695a79d47b", "o'neil+data@acme.com", "_x_@acme.com"]
)
def test_every_prefix_is_a_valid_schema_name_start(user: str):
    prefix = names.personal_prefix(user)
    assert re.fullmatch(r"u_[a-z0-9]+(_[a-z0-9]+)*__", prefix), prefix


def test_a_preview_never_deploys_into_a_schema_another_project_created(
    project: Path, workspace: FakeWorkspace
):
    workspace.schemas["dev_sales"] = {
        "u_bijil__silver": {"nimblestax.project": "warehouse", "nimblestax.user": ME}
    }

    result = nstx(project, "preview", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX920"
    assert "dev_sales.u_bijil__silver" in diagnostic["message"]
    assert "warehouse" in diagnostic["message"]
    assert not [call for call in workspace.calls if call[0] in ("deploy", "run")]


@pytest.mark.parametrize(
    "properties, named",
    [
        ({}, "Nimblestax didn't create it"),
        ({"nimblestax.project": "shop", "nimblestax.user": "bijil@acme.com"}, "bijil@acme.com"),
    ],
)
def test_a_preview_never_deploys_into_a_schema_made_by_hand_or_for_someone_else(
    project: Path, workspace: FakeWorkspace, properties: dict, named: str
):
    workspace.schemas["dev_sales"] = {"u_bijil__gold": properties}

    result = nstx(project, "preview", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX920"
    assert named in diagnostic["message"]


def test_a_preview_deploys_again_into_the_schemas_it_created(
    project: Path, workspace: FakeWorkspace
):
    workspace.schemas["dev_sales"] = {
        "u_bijil__silver": {"nimblestax.project": "shop", "nimblestax.user": ME},
        "silver": {},
    }

    result = nstx(project, "preview")

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("args", [["preview"], ["preview", "down"]])
def test_an_example_has_no_preview_and_points_at_deploying_it(
    tmp_path: Path, workspace: FakeWorkspace, args: list[str]
):
    folder = tmp_path / "kettle"
    runner.invoke(app, ["init", str(folder), "--example", "kettle", "--host", HOST])

    result = nstx(folder, *args, "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX921"
    assert "nstx deploy" in diagnostic["fix"]
    assert workspace.calls == []


def test_preview_down_destroys_this_projects_preview_for_this_person(
    project: Path, workspace: FakeWorkspace
):
    workspace.state = [("dev_sales", "u_bijil__silver"), ("dev_sales", "u_bijil__gold")]

    result = nstx(project, "preview", "down", "--json")

    assert result.exit_code == 0, result.output
    assert ("destroy", "preview") in workspace.calls
    assert not [call for call in workspace.calls if call[0] in ("deploy", "run")]


def test_a_preview_ends_by_naming_preview_down(project: Path, workspace: FakeWorkspace):
    result = nstx(project, "preview")

    assert (
        result.stdout.strip()
        .splitlines()[-1]
        .endswith("Remove it with `nstx preview down` when you're done.")
    )


def test_a_preview_writes_its_own_manifest_in_its_bundle_folder_and_down_removes_it(
    project: Path, workspace: FakeWorkspace
):
    result = nstx(project, "preview")

    assert result.exit_code == 0, result.output
    folder = f"/Workspace/Users/{ME}/.bundle/shop/preview/nimblestax"
    current = json.loads(workspace.files[f"{folder}/manifest.json"])
    assert current["env"] == "preview"
    assert "sales.gold.fct_orders" in current["tables"]
    record = json.loads((project / "build/nimblestax.package.json").read_text())
    assert current["package_checksum"] == record["checksum"]
    [copy] = [path for path in workspace.files if path.startswith(f"{folder}/manifests/")]
    assert json.loads(workspace.files[copy]) == current
    # Nothing is written outside the person's own preview folder.
    assert all(path.startswith(folder) for path in workspace.files)

    result = nstx(project, "preview", "down")

    assert result.exit_code == 0, result.output
    assert workspace.files == {}


@pytest.mark.parametrize(
    "outside",
    [
        ("dev_sales", "silver"),
        ("dev_sales", "u_priya__silver"),
        ("prod_sales", "u_bijil__silver"),
        ("test_sales", "u_bijil__silver"),
    ],
)
def test_preview_down_refuses_anything_outside_the_persons_schemas_in_dev(
    project: Path, workspace: FakeWorkspace, outside: tuple[str, str]
):
    workspace.state = [("dev_sales", "u_bijil__silver"), outside]

    result = nstx(project, "preview", "down", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX922"
    assert ".".join(outside) in diagnostic["message"]
    assert ("destroy", "preview") not in workspace.calls


def test_an_environment_named_preview_would_collide_with_previews(project: Path):
    contract = project / "nimblestax.platform.yaml"
    contract.write_text(contract.read_text().replace("naming:\n", "  preview: {}\nnaming:\n", 1))

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX133"


def fake_databricks(folder: Path, user: str, summary: dict) -> Path:
    """A Databricks CLI that answers what a preview asks, and records each call."""
    script = folder / "fake-databricks"
    answers = {
        "current-user me": {"userName": user},
        "schemas list": [{"name": "silver", "properties": {}}],
        "bundle summary": summary,
        "bundle validate": {"workspace": {"root_path": ROOT}},
        "workspace list": [],
    }
    cases = "".join(
        f"  \"{command}\") echo '{json.dumps(answer)}' ;;\n" for command, answer in answers.items()
    )
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$DATABRICKS_HOST $@" >> {folder}/calls\n'
        'case "$1 $2" in\n'
        f'  "--version ") echo "Databricks CLI v{pinned_cli.MINIMUM}" ;;\n'
        f"{cases}"
        '  "bundle deploy"|"bundle run"|"bundle destroy") ;;\n'
        '  "workspace mkdirs"|"workspace import") ;;\n'
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    script.chmod(0o755)
    return script


def test_the_databricks_cli_deploys_and_removes_the_preview_target_as_the_signed_in_person(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    summary = {
        "resources": {
            "schemas": {
                "sales_silver": {
                    "id": "dev_sales.u_bijil__silver",
                    "catalog_name": "dev_sales",
                    "name": "u_bijil__silver",
                },
                "sales_gold": {"catalog_name": "dev_sales", "name": "u_bijil__gold"},
            }
        }
    }
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(fake_databricks(tmp_path, ME, summary)))

    previewed = nstx(project, "preview", "--json")
    removed = nstx(project, "preview", "down", "--json")

    assert previewed.exit_code == 0, previewed.output
    assert removed.exit_code == 0, removed.output
    calls = (tmp_path / "calls").read_text().splitlines()
    assert f"{HOST} current-user me --output json" in calls
    assert f"{HOST} schemas list dev_sales --output json" in calls
    # The manifest goes in the preview's own bundle folder, which the destroy removes.
    imported = [call.split(" ")[3] for call in calls if " workspace import " in call]
    assert len(imported) == 2
    assert re.fullmatch(rf"{ROOT}/nimblestax/manifests/\d{{8}}T\d{{6}}Z-.+\.json", imported[0])
    assert imported[1] == f"{ROOT}/nimblestax/manifest.json"
    ran = [call.split(" ", 1)[1] for call in calls if " bundle " in f" {call.split(' ', 1)[1]}"]
    assert ran == [
        "bundle deploy --target preview",
        "bundle run --target preview refresh",
        "bundle validate --target preview -o json",
        "bundle summary --target preview -o json",
        "bundle destroy --target preview --auto-approve",
    ]


# Pull request previews: the same machinery, run by CI with `--pr <N>`.

CI = "7da8a1ae-c185-4974-9329-a5695a79d47b"


@pytest.fixture
def ci(monkeypatch: pytest.MonkeyPatch) -> FakeWorkspace:
    """The Databricks boundary as dev's service principal sees it, from CI."""
    fake = FakeWorkspace(CI)
    monkeypatch.setattr(cli, "DatabricksCli", lambda: fake)
    return fake


def test_a_pull_request_preview_deploys_every_table_to_its_own_schemas_under_cis_root(
    project: Path, ci: FakeWorkspace
):
    model = project / "domains/sales/models/gold/fct_orders.sql"
    model.write_text(model.read_text() + "\n-- changed in pull request 42\n")

    result = nstx(project, "preview", "--pr", "42", "--json")

    assert result.exit_code == 0, result.output
    assert ("deploy", "preview") in ci.calls
    assert ("run", "preview", "refresh") in ci.calls
    target = preview_target(ci)
    assert set(_schema_names(target)) == {
        "dev_sales.pr42__bronze",
        "dev_sales.pr42__silver",
        "dev_sales.pr42__gold",
    }
    assert json.loads(result.stdout)["result"]["schemas"] == sorted(_schema_names(target))
    # Every table is built, the changed one included.
    assert (
        "-- changed in pull request 42"
        in (project / "build/src/sales/gold/fct_orders.sql").read_text()
    )
    # Its bundle state sits under the deploying identity's own root, apart from every
    # Environment's and from any personal preview's.
    assert target["workspace"]["root_path"] == "~/.bundle/shop/pull-requests/42"
    manifest = f"/Workspace/Users/{CI}/.bundle/shop/pull-requests/42/nimblestax/manifest.json"
    assert json.loads(ci.files[manifest])["env"] == "preview"


@pytest.mark.parametrize(
    "style, schema",
    [
        ("domain-catalogs", "dev_sales.pr42__silver"),
        ("layer-catalogs", "dev_silver.pr42__sales"),
        ("environment-catalogs", "dev.pr42__sales_silver"),
    ],
)
def test_pull_request_preview_schemas_follow_the_naming_style(
    tmp_path: Path, ci: FakeWorkspace, style: str, schema: str
):
    folder = tmp_path / "shop"
    runner.invoke(app, ["init", str(folder), "--host", HOST, "--naming-style", style])

    result = nstx(folder, "preview", "--pr", "42", "--json")

    assert schema in json.loads(result.stdout)["result"]["schemas"]


@pytest.mark.parametrize("style", ["domain-catalogs", "layer-catalogs", "environment-catalogs"])
def test_a_pull_request_preview_shares_no_schema_pipeline_or_folder_with_a_person_or_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, style: str
):
    folder = tmp_path / "shop"
    runner.invoke(app, ["init", str(folder), "--host", HOST, "--naming-style", style])
    seen = {}
    for user, args in ((CI, ["--pr", "1"]), ("u@acme.com", []), ("pr1@acme.com", [])):
        fake = FakeWorkspace(user)
        monkeypatch.setattr(cli, "DatabricksCli", lambda fake=fake: fake)
        assert nstx(folder, "preview", *args).exit_code == 0
        [package] = fake.packages
        seen[user] = package
    dev = seen[CI]["targets"]["dev"]["variables"]
    dev_schemas = {
        f"{dev[key.replace('schema_', 'catalog_')]}.{value}"
        for key, value in dev.items()
        if key.startswith("schema_")
    }

    targets = [package["targets"]["preview"] for package in seen.values()]
    schemas = [set(_schema_names(target)) for target in targets]
    pipelines = [{p["name"] for p in t["resources"]["pipelines"].values()} for t in targets]
    roots = [target["workspace"]["root_path"] for target in targets]
    pull_request, *people = range(3)
    for person in people:
        assert not schemas[pull_request] & schemas[person]
        assert not pipelines[pull_request] & pipelines[person]
        assert roots[pull_request] != roots[person]
    assert not schemas[pull_request] & dev_schemas


def test_a_pull_request_preview_never_deploys_into_another_projects_and_names_its_removal(
    project: Path, ci: FakeWorkspace
):
    ci.schemas["dev_sales"] = {
        "pr42__silver": {"nimblestax.project": "warehouse", "nimblestax.pull_request": "42"}
    }

    result = nstx(project, "preview", "--pr", "42", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX920"
    assert "for pull request 42" in diagnostic["message"]
    assert "nstx preview down --pr 42" in diagnostic["fix"]
    assert not [call for call in ci.calls if call[0] in ("deploy", "run")]


def test_a_pull_request_preview_deploys_again_into_the_schemas_it_created(
    project: Path, ci: FakeWorkspace
):
    ci.schemas["dev_sales"] = {
        "pr42__silver": {"nimblestax.project": "shop", "nimblestax.pull_request": "42"}
    }

    result = nstx(project, "preview", "--pr", "42")

    assert result.exit_code == 0, result.output
    # Nobody is asked who is signed in: the prefix comes from `--pr` alone.
    assert not [call for call in ci.calls if call[0] == "current_user"]


def test_preview_down_with_pr_removes_that_pull_requests_preview_and_its_manifest(
    project: Path, ci: FakeWorkspace
):
    nstx(project, "preview", "--pr", "42")
    ci.state = [("dev_sales", "pr42__silver"), ("dev_sales", "pr42__gold")]

    result = nstx(project, "preview", "down", "--pr", "42", "--json")

    assert result.exit_code == 0, result.output
    assert ("destroy", "preview") in ci.calls
    assert ci.files == {}


@pytest.mark.parametrize(
    "outside",
    [
        ("dev_sales", "silver"),
        ("dev_sales", "u_bijil__silver"),
        ("dev_sales", "pr4__silver"),
        ("dev_sales", "pr420__silver"),
        ("prod_sales", "pr42__silver"),
    ],
)
def test_preview_down_with_pr_refuses_anything_outside_that_pull_requests_schemas_in_dev(
    project: Path, ci: FakeWorkspace, outside: tuple[str, str]
):
    ci.state = [("dev_sales", "pr42__silver"), outside]

    result = nstx(project, "preview", "down", "--pr", "42", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX922"
    assert ".".join(outside) in diagnostic["message"]
    assert ("destroy", "preview") not in ci.calls


def test_a_pull_request_number_starts_at_one(project: Path, ci: FakeWorkspace):
    result = nstx(project, "preview", "--pr", "0", "--json")

    assert result.exit_code == 2, result.output
    assert ci.calls == []


def test_databricks_accepts_a_pull_request_preview_target_apart_from_dev_and_people(
    tmp_path: Path, stub_workspace: str
):
    folder = tmp_path / "shop"
    assert runner.invoke(app, ["init", str(folder), "--host", stub_workspace]).exit_code == 0
    package = compiler.write_package(load(folder), bundle.pull_request(42))

    preview = validated(package, stub_workspace, "preview", tmp_path)

    pipelines = preview["resources"]["pipelines"]
    assert pipelines["sales_gold"]["name"] == "pr42__shop_sales_gold"
    assert pipelines["sales_gold"]["development"] is True
    assert pipelines["sales_gold"]["configuration"]["schema_sales_silver"] == "pr42__silver"
    [job] = preview["resources"]["jobs"].values()
    assert job["name"] == "pr42__shop_refresh"
    schema = preview["resources"]["schemas"]["sales_silver"]
    assert schema["properties"] == {"nimblestax.project": "shop", "nimblestax.pull_request": "42"}
    assert "nstx preview down --pr 42" in schema["comment"]
    assert preview["workspace"]["root_path"].endswith("/.bundle/shop/pull-requests/42")


def test_the_pull_request_workflow_previews_each_pull_request_as_dev_after_validating(
    project: Path,
):
    workflow = project / ".github/workflows/nimblestax-pull-request.yaml"
    jobs = yaml.safe_load(workflow.read_text())["jobs"]

    preview = jobs["preview"]
    assert preview["needs"] == "validate"
    assert preview["environment"] == "dev"
    runs = [step["run"] for step in preview["steps"] if "run" in step]
    assert runs == [
        'uvx --from "$NIMBLESTAX_SPEC" nstx preview --pr ${{ github.event.pull_request.number }}'
    ]
    # Two pushes to one pull request deploy one after the other, never into one bundle at once.
    assert preview["concurrency"] == {
        "group": "nimblestax-preview-${{ github.event.pull_request.number }}",
        "cancel-in-progress": False,
    }
