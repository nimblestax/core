"""A merge builds one Build Package, and each deploy of it leaves a Deployment Manifest."""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from nimblestax import cli
from nimblestax.deploy.databricks import DatabricksCli, WorkspaceError

runner = CliRunner()

ROOT = "/Workspace/Users/ci@example.com/.bundle/sales_platform/{target}"


class FakeWorkspace:
    """Bundle calls that do nothing, and workspace files kept in memory."""

    def __init__(self, fail_on: str | None = None, cannot_delete: bool = False):
        self.fail_on = fail_on
        self.cannot_delete = cannot_delete
        self.files: dict[str, str] = {}
        self.deployed: list[tuple[Path, str]] = []

    def deploy_bundle(self, package: Path, target: str) -> None:
        if self.fail_on == "deploy":
            raise WorkspaceError("databricks bundle deploy failed.")
        self.deployed.append((package, target))

    def run_job(self, package: Path, target: str, job: str) -> None:
        if self.fail_on == "run":
            raise WorkspaceError("databricks bundle run failed.")

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        return []

    def bundle_root(self, package: Path, target: str) -> str:
        return ROOT.format(target=target)

    def write_file(self, package: Path, target: str, path: str, content: str) -> None:
        self.files[path] = content

    def list_folder(self, package: Path, target: str, folder: str) -> list[str]:
        return sorted(path for path in self.files if path.rsplit("/", 1)[0] == folder)

    def delete_file(self, package: Path, target: str, path: str) -> None:
        if self.cannot_delete:
            raise WorkspaceError(f"databricks workspace delete {path} failed.")
        del self.files[path]

    def manifest(self, target: str) -> dict:
        return json.loads(self.files[f"{ROOT.format(target=target)}/nimblestax/manifest.json"])

    def copies(self, target: str) -> list[str]:
        folder = f"{ROOT.format(target=target)}/nimblestax/manifests"
        return self.list_folder(Path(), target, folder)


@pytest.fixture(autouse=True)
def outside_a_git_hook(monkeypatch: pytest.MonkeyPatch):
    """Git sets GIT_DIR and friends while running a hook, such as the pre-commit check. Left in
    place, they point every git command, the tests' and Nimblestax's, at this repo rather than the
    throwaway one."""
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)


def git(project: Path, *args: str) -> str:
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    ran = subprocess.run(
        ["git", *identity, *args], cwd=project, capture_output=True, text=True, check=True
    )
    return ran.stdout.strip()


def commit(project: Path, message: str = "Change") -> str:
    git(project, "add", "-A")
    git(project, "commit", "-q", "--allow-empty", "-m", message)
    return git(project, "rev-parse", "HEAD")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    result = runner.invoke(cli.app, ["init", str(tmp_path / "sales_platform")])
    assert result.exit_code == 0, result.output
    folder = tmp_path / "sales_platform"
    git(folder, "init", "-q")
    return folder


def nsx(project: Path, *args: str, workspace: FakeWorkspace | None = None, monkeypatch=None):
    if workspace is not None and monkeypatch is not None:
        monkeypatch.setattr(cli, "DatabricksCli", lambda: workspace)
    return runner.invoke(cli.app, [*args, "--json", "--project", str(project)])


def build(project: Path) -> Path:
    result = nsx(project, "compile")
    assert result.exit_code == 0, result.output
    return project / "build"


def record(package: Path) -> dict:
    return json.loads((package / "nimblestax.package.json").read_text())


def test_deploying_a_package_to_dev_writes_a_manifest_with_its_commit_and_checksum(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    sha = commit(project)
    package = build(project)
    workspace = FakeWorkspace()

    result = nsx(
        project, "deploy", "--env", "dev", "--package", str(package),
        workspace=workspace, monkeypatch=monkeypatch,
    )  # fmt: skip

    assert result.exit_code == 0, result.output
    manifest = workspace.manifest("dev")
    assert manifest["commit"] == sha
    assert manifest["package_checksum"] == record(package)["checksum"]
    assert manifest["env"] == "dev"


def deploy(project: Path, env: str, package: Path, workspace: FakeWorkspace, monkeypatch):
    return nsx(
        project, "deploy", "--env", env, "--package", str(package),
        workspace=workspace, monkeypatch=monkeypatch,
    )  # fmt: skip


def add_test_environment(project: Path) -> None:
    contract = project / "nimblestax.platform.yaml"
    text = contract.read_text()
    assert "role: development\n" in text
    contract.write_text(text.replace("role: development\n", "role: development\n  test: {}\n", 1))


def test_the_checksum_record_holds_the_commit_and_nimblestax_version(project: Path):
    sha = commit(project)

    written = record(build(project))

    assert written["commit"] == sha
    assert written["nimblestax_version"] == version("nimblestax")
    assert written["checksum"].startswith("sha256:")
    assert "databricks.yaml" in written["files"]
    table = written["tables"]["sales.gold.fct_orders"]
    assert (table["type"], table["file"]) == ("materialized_view", "src/sales/gold/fct_orders.sql")
    assert table["definition"].startswith("sha256:")
    assert list(table["columns"]) == ["order_id", "amount"]


def test_a_package_built_outside_git_records_no_commit(project: Path):
    written = record(build(project))  # `git init` ran, but nothing is committed.

    assert written["commit"] is None


def test_every_environment_receives_byte_identical_code_from_one_package(
    project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    add_test_environment(project)
    commit(project)
    # CI hands each stage the artifact, wherever it downloads it, so move it out of the project.
    package = Path(shutil.move(build(project), tmp_path / "artifact"))
    before = {p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    # A later change to the project must not reach a stage deploying this package.
    (project / "domains/sales/models/gold/fct_orders.sql").write_text("SELECT 1 AS changed")
    workspace = FakeWorkspace()

    for env in ("dev", "test"):
        assert deploy(project, env, package, workspace, monkeypatch).exit_code == 0

    assert workspace.deployed == [(package, "dev"), (package, "test")]
    after = {p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    assert after == before
    assert not (project / "build").exists()
    targets = yaml.safe_load((package / "databricks.yaml").read_text())["targets"]
    assert set(targets) == {"dev", "test"}
    checksums = {workspace.manifest(env)["package_checksum"] for env in ("dev", "test")}
    assert checksums == {record(package)["checksum"]}


@pytest.mark.parametrize("fail_on", ["deploy", "run"])
def test_a_failed_deploy_writes_no_manifest(
    project: Path, monkeypatch: pytest.MonkeyPatch, fail_on: str
):
    commit(project)
    package = build(project)
    workspace = FakeWorkspace(fail_on=fail_on)

    result = deploy(project, "dev", package, workspace, monkeypatch)

    assert result.exit_code == 2, result.output
    assert workspace.files == {}


def test_the_current_file_and_a_copy_named_by_time_then_commit_are_both_written(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    sha = commit(project)
    workspace = FakeWorkspace()

    assert deploy(project, "dev", build(project), workspace, monkeypatch).exit_code == 0

    [copy] = workspace.copies("dev")
    assert re.fullmatch(rf".*/nimblestax/manifests/\d{{8}}T\d{{6}}Z-{sha}\.json", copy)
    assert json.loads(workspace.files[copy]) == workspace.manifest("dev")


def test_the_manifest_names_its_tables_and_when_they_were_deployed(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    commit(project)
    package = build(project)
    workspace = FakeWorkspace()

    deploy(project, "dev", package, workspace, monkeypatch)

    manifest = workspace.manifest("dev")
    assert manifest["tables"] == record(package)["tables"]
    assert manifest["nimblestax_version"] == version("nimblestax")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", manifest["deployed_at"])


def test_deploy_refuses_a_package_changed_since_it_was_built(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    commit(project)
    package = build(project)
    (package / "src/sales/gold/fct_orders.sql").write_text("SELECT 1")
    workspace = FakeWorkspace()

    result = deploy(project, "dev", package, workspace, monkeypatch)

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSX918"
    assert "src/sales/gold/fct_orders.sql" in diagnostic["message"]
    assert workspace.deployed == []


def test_deploy_refuses_a_folder_that_is_not_a_package(
    project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    workspace = FakeWorkspace()

    result = deploy(project, "dev", tmp_path / "empty", workspace, monkeypatch)

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSX917"
    assert workspace.deployed == []


def test_deploy_without_a_package_builds_one_and_records_it(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    sha = commit(project)
    workspace = FakeWorkspace()

    result = nsx(project, "deploy", "--env", "dev", workspace=workspace, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"] == {
        "env": "dev",
        "commit": sha,
        "package_checksum": record(project / "build")["checksum"],
    }
    assert workspace.manifest("dev")["commit"] == sha


def seed_copies(workspace: FakeWorkspace, count: int) -> list[str]:
    folder = f"{ROOT.format(target='dev')}/nimblestax/manifests"
    paths = [f"{folder}/20250101T{n // 60:02d}{n % 60:02d}00Z-{n:040x}.json" for n in range(count)]
    workspace.files.update({path: "{}" for path in paths})
    return paths


def test_only_the_newest_100_copies_are_kept(project: Path, monkeypatch: pytest.MonkeyPatch):
    commit(project)
    workspace = FakeWorkspace()
    older = seed_copies(workspace, 100)

    assert deploy(project, "dev", build(project), workspace, monkeypatch).exit_code == 0

    kept = workspace.copies("dev")
    assert len(kept) == 100
    assert older[0] not in kept
    assert older[1:] == kept[:-1]


def test_deploying_a_commit_again_replaces_its_earlier_copy(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    commit(project)
    package = build(project)
    workspace = FakeWorkspace()
    deploy(project, "dev", package, workspace, monkeypatch)
    [first] = workspace.copies("dev")
    # Make the first copy older than the second, however fast the test runs.
    earlier = first.replace("/manifests/2", "/manifests/1")
    workspace.files[earlier] = workspace.files.pop(first)

    deploy(project, "dev", package, workspace, monkeypatch)

    [only] = workspace.copies("dev")
    assert only != earlier


def test_old_copies_that_cannot_be_removed_only_warn(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    commit(project)
    workspace = FakeWorkspace(cannot_delete=True)
    seed_copies(workspace, 100)

    result = deploy(project, "dev", build(project), workspace, monkeypatch)

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    [diagnostic] = envelope["diagnostics"]
    assert (diagnostic["rule"], diagnostic["severity"]) == ("NSX919", "warning")
    assert "manifest.json" in " ".join(workspace.files)


def test_the_databricks_cli_writes_lists_and_deletes_manifests_beside_the_bundle(
    tmp_path: Path, stub_workspace: str, stub_files: dict, monkeypatch: pytest.MonkeyPatch
):
    result = runner.invoke(cli.app, ["init", str(tmp_path / "p"), "--host", stub_workspace])
    assert result.exit_code == 0, result.output
    package = build(tmp_path / "p")
    monkeypatch.setenv("DATABRICKS_TOKEN", "not-a-real-token")
    workspace = DatabricksCli()

    root = workspace.bundle_root(package, "dev")
    workspace.write_file(package, "dev", f"{root}/nimblestax/manifests/a.json", '{"a": 1}\n')
    workspace.write_file(package, "dev", f"{root}/nimblestax/manifests/b.json", '{"b": 2}\n')
    workspace.delete_file(package, "dev", f"{root}/nimblestax/manifests/a.json")

    assert root == "/Workspace/Users/ci@example.com/.bundle/p/dev"
    assert workspace.list_folder(package, "dev", f"{root}/nimblestax/manifests") == [
        f"{root}/nimblestax/manifests/b.json"
    ]
    assert stub_files == {f"{root}/nimblestax/manifests/b.json": '{"b": 2}\n'}


def test_the_merge_workflow_builds_one_package_and_deploys_it_to_dev_as_dev(tmp_path: Path):
    result = runner.invoke(cli.app, ["init", str(tmp_path / "p"), "--ci", "github"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "p/.github/workflows/nimblestax-merge.yaml").read_text()
    jobs = yaml.safe_load(text)["jobs"]

    package_steps = jobs["package"]["steps"]
    deploy_steps = jobs["deploy-dev"]["steps"]
    runs = [step["run"] for step in package_steps + deploy_steps if "run" in step]
    assert all(run.startswith('uvx --from "$NIMBLESTAX_SPEC" nsx ') for run in runs)
    assert [run.split(" nsx ")[1] for run in runs] == [
        "validate",
        "compile",
        "validate --platform --env dev",
        "deploy --env dev --package build",
    ]
    [upload] = [step for step in package_steps if "upload-artifact" in step.get("uses", "")]
    [download] = [step for step in deploy_steps if "download-artifact" in step.get("uses", "")]
    assert upload["with"]["name"] == download["with"]["name"]
    assert upload["with"]["path"] == download["with"]["path"] == "build"
    assert jobs["deploy-dev"]["needs"] == "package"
    assert jobs["deploy-dev"]["environment"] == "dev"
    # Building needs no workspace, so it holds no Environment's credentials.
    assert "environment" not in jobs["package"]
    uses = re.findall(r"uses: (\S+)(.*)", text)
    assert uses and all(re.fullmatch(r"\S+@[0-9a-f]{40}", used) for used, _ in uses)
    assert all(comment.startswith(" # v") for _, comment in uses)
