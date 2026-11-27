"""The contract machines rely on: one envelope, stable rule IDs and three exit codes."""

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nimblestax.cli import PASSED_THROUGH, app, every_command
from nimblestax.deploy import pinned_cli
from nimblestax.diagnostics import DOCS, RULES, error
from nimblestax.scaffold import PLACEHOLDER_HOST

runner = CliRunner()


def nstx(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def test_validate_prints_an_envelope_with_the_rule_id_and_exits_1(project: Path):
    (project / "domains/sales/models/gold/fct_orders.sql").write_text(
        "SELECT * FROM sales.silver.nope"
    )

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert list(envelope) == ["schema", "nimblestax_version", "ok", "result", "diagnostics"]
    assert envelope["schema"] == "nimblestax.validate/1"
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert list(diagnostic) == [
        "rule",
        "name",
        "severity",
        "file",
        "line",
        "message",
        "fix",
        "docs",
    ]
    assert diagnostic["rule"] == "NSTX201"
    assert diagnostic["file"] == "domains/sales/models/gold/fct_orders.sql"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            ["init", "kettle"],
            {
                "project": "kettle",
                "naming_style": "domain-catalogs",
                "catalogs": ["dev_sales"],
                "schemas": ["dev_sales.bronze", "dev_sales.silver", "dev_sales.gold"],
                "skills": [
                    ".agents/skills/nimblestax-add-model",
                    ".claude/skills/nimblestax-add-model",
                    ".agents/skills/nimblestax-add-source",
                    ".claude/skills/nimblestax-add-source",
                ],
                "skills_left_alone": [],
                "volumes": ["dev_sales.bronze.landing"],
                "example": None,
                "uploads": [],
            },
        ),
        (["validate"], {}),
        (["compile"], {"package": "build"}),
    ],
)
def test_a_command_reports_its_result_in_the_envelope(
    project: Path, monkeypatch, command: list[str], expected: dict
):
    monkeypatch.chdir(project)

    result = runner.invoke(app, [*command, "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == f"nimblestax.{command[0]}/1"
    assert envelope["ok"] is True
    assert envelope["result"] == expected
    assert envelope["diagnostics"] == []


def test_compile_for_an_environment_returns_the_sql_in_the_envelope(project: Path):
    result = nstx(project, "compile", "--env", "dev", "--json")

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["result"]["env"] == "dev"
    assert "dev_sales.gold.fct_orders" in envelope["result"]["sql"]


def test_every_registered_command_has_the_json_option():
    """A new command that doesn't register through the shared wrapper fails here."""
    commands = every_command()
    assert {"init", "validate", "schema", "compile", "deploy", "skills update"} <= set(commands)
    for name, registered in commands.items():
        if name in PASSED_THROUGH:
            continue  # Its arguments, `--json` among them, belong to the CLI it runs.
        options = [option for parameter in registered.params for option in parameter.opts]
        assert "--json" in options, f"`nstx {name}` has no --json"


def run_nimblestax(*args: str, databricks: Path) -> subprocess.CompletedProcess:
    """The installed command in its own process, so stdout and stderr are the real ones."""
    executable = Path(sys.executable).with_name("nstx")
    environment = {pinned_cli.OVERRIDE: str(databricks)}
    return subprocess.run([executable, *args], capture_output=True, text=True, env=environment)


def fake_databricks(folder: Path, exit_code: int = 0) -> Path:
    """A Databricks CLI that logs to stdout, as the real one does for bundle runs, and prints
    JSON where Nimblestax asks for it."""
    folder.mkdir()
    script = folder / "databricks"
    script.write_text(
        "#!/bin/sh\n"
        f"[ \"$1\" = --version ] && echo 'Databricks CLI v{pinned_cli.MINIMUM}' && exit 0\n"
        '[ "$1 $2" = \'bundle validate\' ] && echo \'{"workspace": {"root_path": "/r"}}\''
        " && exit 0\n"
        "[ \"$1 $2\" = 'workspace list' ] && echo '[]' && exit 0\n"
        '[ "$1" = workspace ] && exit 0\n'
        f"echo 'Uploading bundle files'\nexit {exit_code}\n"
    )
    script.chmod(0o755)
    return script


def test_stdout_is_pure_json_while_the_databricks_cli_logs(project: Path, tmp_path_factory):
    databricks = fake_databricks(tmp_path_factory.mktemp("cli") / "bin")

    result = run_nimblestax(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=databricks
    )

    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "nimblestax.deploy/1"
    assert envelope["result"]["env"] == "dev"
    assert "Uploading bundle files" in result.stderr


def test_a_failing_databricks_command_is_an_environment_error(project: Path, tmp_path_factory):
    databricks = fake_databricks(tmp_path_factory.mktemp("cli") / "bin", exit_code=3)

    result = run_nimblestax(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=databricks
    )

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX904"


def test_a_missing_databricks_cli_is_an_environment_error(project: Path, tmp_path_factory):
    missing = tmp_path_factory.mktemp("empty") / "databricks"

    result = run_nimblestax(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=missing
    )

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX903"
    assert pinned_cli.OVERRIDE in diagnostic["fix"]


@pytest.mark.parametrize(
    ("arguments", "schema"),
    [
        (["schema", "--json"], "nimblestax.schema/1"),
        (["validate", "--json", "--nope"], "nimblestax.validate/1"),
        (["init", "--ci", "gitlab", "--json"], "nimblestax.init/1"),
        (["nope", "--json"], "nimblestax.usage/1"),
    ],
)
def test_a_usage_error_is_an_envelope_that_exits_2(arguments: list[str], schema: str):
    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == schema
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "NSTX901"
    assert diagnostic["message"]
    assert "--help" in diagnostic["fix"]


def test_a_usage_error_without_json_stays_text_for_a_person():
    result = runner.invoke(app, ["schema"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Missing argument" in result.stderr


@pytest.mark.parametrize("command", ["compile", "deploy"])
def test_an_unknown_environment_is_a_usage_error_naming_the_environments(
    project: Path, command: str
):
    result = nstx(project, command, "--env", "staging", "--json")

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSTX902"
    assert "dev" in diagnostic["fix"]


@pytest.mark.parametrize("as_json", [True, False])
def test_a_crash_keeps_the_exit_code_contract(tmp_path: Path, as_json: bool):
    in_the_way = tmp_path / "a-file"
    in_the_way.write_text("not a folder")
    flags = ["--json"] if as_json else []

    result = runner.invoke(app, ["init", str(in_the_way), *flags])

    assert result.exit_code == 2
    assert "NSTX905" in result.stdout
    assert "Traceback" in result.stderr
    assert "Traceback" not in result.stdout
    if as_json:
        assert json.loads(result.stdout)["schema"] == "nimblestax.init/1"


def test_a_project_problem_without_json_stays_text_for_a_person(project: Path):
    (project / "domains/sales/models/gold/fct_orders.sql").write_text(
        "SELECT * FROM sales.silver.nope"
    )

    result = nstx(project, "validate")

    assert result.exit_code == 1
    assert "NSTX201 domains/sales/models/gold/fct_orders.sql:" in result.stdout
    assert "Fix: " in result.stdout


# Copied by hand on purpose. Editing a line here means a rule ID changed meaning, was removed or
# was reused, which breaks every agent and script that relies on it. Only ever add lines.
REGISTERED_RULES = {
    "NSTX101": "missing-kind",
    "NSTX102": "unknown-kind",
    "NSTX103": "missing-version",
    "NSTX104": "unknown-version",
    "NSTX105": "wrong-kind",
    "NSTX106": "invalid-field",
    "NSTX107": "unreadable-config",
    "NSTX108": "sql-without-config",
    "NSTX109": "missing-sql-file",
    "NSTX110": "keys-without-sequence-by",
    "NSTX111": "upsert-field-without-keys",
    "NSTX112": "missing-seed-file",
    "NSTX113": "seed-header-mismatch",
    "NSTX114": "seed-row-mismatch",
    "NSTX115": "unsupported-seed-type",
    "NSTX116": "invalid-expectation",
    "NSTX117": "invalid-name",
    "NSTX118": "invalid-delete-when",
    "NSTX119": "invalid-sequence-by",
    "NSTX120": "duplicate-config-file",
    "NSTX121": "unlisted-domain-folder",
    "NSTX122": "dev-host-missing",
    "NSTX123": "two-default-environments",
    "NSTX124": "naming-patterns-not-supported",
    "NSTX125": "source-layers-fixed",
    "NSTX126": "model-layer-named-like-a-source-layer",
    "NSTX127": "model-outside-a-layer",
    "NSTX129": "skill-version-drift",
    "NSTX130": "no-development-environment",
    "NSTX131": "two-environments-with-one-role",
    "NSTX132": "environment-name-not-an-identifier",
    "NSTX133": "reserved-environment-name",
    "NSTX201": "unresolved-logical-name",
    "NSTX202": "duplicate-table",
    "NSTX203": "unparseable-sql",
    "NSTX204": "computed-table-name",
    "NSTX205": "real-table-name",
    "NSTX206": "file-read",
    "NSTX207": "raw-string-placeholder",
    "NSTX208": "model-cycle",
    "NSTX209": "cross-domain-read",
    "NSTX210": "read-against-build-order",
    "NSTX211": "stream-of-upsert-silver",
    "NSTX212": "stream-of-materialized-view",
    "NSTX213": "test-references-unknown-table",
    "NSTX301": "missing-catalog",
    "NSTX302": "missing-schema",
    "NSTX303": "developer-group-missing-grant",
    "NSTX401": "test-failed",
    "NSTX402": "test-could-not-run",
    "NSTX901": "usage-error",
    "NSTX902": "unknown-environment",
    "NSTX903": "databricks-cli-missing",
    "NSTX904": "databricks-command-failed",
    "NSTX905": "unexpected-error",
    "NSTX906": "pipeline-column-not-found",
    "NSTX907": "expectation-failed",
    "NSTX908": "pipeline-failed",
    "NSTX909": "project-already-exists",
    "NSTX910": "databricks-cli-checksum-mismatch",
    "NSTX911": "databricks-cli-unsupported",
    "NSTX912": "databricks-cli-download-failed",
    "NSTX913": "no-databricks-cli-for-platform",
    "NSTX914": "skills-folder-ignored",
    "NSTX915": "skill-edited",
    "NSTX916": "unknown-example",
    "NSTX917": "not-a-build-package",
    "NSTX918": "build-package-changed",
    "NSTX919": "manifest-copies-not-removed",
    "NSTX920": "preview-schema-taken",
    "NSTX921": "example-has-no-preview",
    "NSTX922": "preview-down-outside-fence",
    "NSTX923": "no-warehouse-for-tests",
    "NSTX924": "no-preview-to-test",
    "NSTX925": "no-databricks-sql-access",
    "NSTX926": "no-such-model",
}


# Removed before any release, so no project ever saw them. Their IDs are still never reused.
RETIRED_RULES = {"NSTX128": "production-shares-a-workspace"}


def test_no_rule_id_is_removed_reused_or_changes_meaning():
    assert {code: rule.name for code, rule in RULES.items()} == REGISTERED_RULES
    assert not RETIRED_RULES.keys() & REGISTERED_RULES.keys()
    assert not set(RETIRED_RULES.values()) & set(REGISTERED_RULES.values())


def test_rule_ids_are_nstx_plus_three_digits_with_one_name_each():
    assert all(re.fullmatch(r"NSTX\d{3}", rule) for rule in RULES)
    assert len({rule.name for rule in RULES.values()}) == len(RULES)


def test_an_unregistered_rule_can_not_be_reported():
    with pytest.raises(KeyError):
        error("NSTX999", "", "A message.", "A fix.")


def replacing(file: str, old: str, new: str) -> Callable[[Path], None]:
    def change(project: Path) -> None:
        path = project / file
        assert old in path.read_text()
        path.write_text(path.read_text().replace(old, new))

    return change


SOURCE = "domains/sales/sources/orders.yaml"
PLATFORM = "nimblestax.platform.yaml"
MODEL = "domains/sales/models/gold/fct_orders"


def seed(column: str, rows: str | None, name: str = "countries") -> Callable[[Path], None]:
    def declare(project: Path) -> None:
        folder = project / "domains/sales/seeds"
        folder.mkdir()
        config = f"kind: seed\nversion: 1\nfile: {name}.csv\ncolumns:\n  {column}\n"
        (folder / f"{name}.yaml").write_text(config)
        if rows is not None:
            (folder / f"{name}.csv").write_text(rows)

    return declare


def read_a_domains_gold_from_shared(project: Path) -> None:
    """A Shared Domain Model reading a Domain's gold, which nobody outside that Domain reads."""
    replacing("nimblestax.platform.yaml", "  - sales\n", "  - sales\n  - shared\n")(project)
    folder = project / "domains/shared/models/gold"
    folder.mkdir(parents=True)
    (folder / "dim_order.yaml").write_text(
        "kind: model\nversion: 1\nsql: dim_order.sql\nowner: sales-analytics\n"
    )
    (folder / "dim_order.sql").write_text("SELECT * FROM sales.gold.fct_orders")


INVALID_PROJECTS = {
    "NSTX101": replacing(SOURCE, "kind: source\n", ""),
    "NSTX102": replacing(SOURCE, "kind: source\n", "kind: sauce\n"),
    "NSTX103": replacing(SOURCE, "version: 1\n", ""),
    "NSTX104": replacing(SOURCE, "version: 1\n", "version: 2\n"),
    "NSTX105": replacing(SOURCE, "kind: source\n", "kind: model\n"),
    "NSTX106": replacing(SOURCE, "format: json\n", "format: 7\n"),
    "NSTX107": lambda project: (project / SOURCE).write_text("just a string"),
    "NSTX108": lambda project: (project / f"{MODEL}.yaml").unlink(),
    "NSTX109": lambda project: (project / f"{MODEL}.sql").unlink(),
    "NSTX110": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  keys: [order_id]\n"),
    "NSTX111": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  scd: 2\n"),
    "NSTX112": seed("code: STRING", None),
    "NSTX113": seed("code: STRING", "nope\nAU\n"),
    "NSTX114": seed("code: INT", "code\nAU\n"),
    "NSTX115": seed("code: VARCAHR", "code\nAU\n"),
    "NSTX116": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  expectations:\n    - name: bad\n      expect: amount >\n",
    ),
    "NSTX117": seed("code: STRING", "code\nAU\n", name="vat-rates"),
    "NSTX118": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n"
        "  delete_when: op =\n",
    ),
    "NSTX119": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at DESC\n",
    ),
    "NSTX120": lambda project: (project / SOURCE.replace(".yaml", ".yml")).write_text(
        (project / SOURCE).read_text()
    ),
    "NSTX121": lambda project: (project / "domains/hr").mkdir(),
    "NSTX122": replacing(PLATFORM, f"    host: {PLACEHOLDER_HOST}\n", ""),
    "NSTX123": replacing(
        PLATFORM,
        "    role: development\n",
        "    role: development\n    default: true\n  prod:\n    default: true\n",
    ),
    "NSTX124": replacing(PLATFORM, "  style: domain-catalogs\n", '  catalog: "{env}"\n'),
    "NSTX125": lambda project: (project / PLATFORM).write_text(
        "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
        f"    host: {PLACEHOLDER_HOST}\n"
        'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
        "  layers:\n    sources: [bronze, curated]\n    models: [gold]\ndomains:\n  - sales\n"
    ),
    "NSTX126": replacing(PLATFORM, "models: [gold]", "models: [gold, silver]"),
    "NSTX127": lambda project: (project / "domains/sales/models/x.sql").write_text("SELECT 1"),
    "NSTX130": replacing(PLATFORM, "    role: development\n", ""),
    "NSTX131": replacing(
        PLATFORM,
        "    role: development\n",
        "    role: development\n  test:\n    role: development\n",
    ),
    "NSTX132": replacing(
        PLATFORM, "    role: development\n", "    role: development\n  prd-1: {}\n"
    ),
    "NSTX133": replacing(
        PLATFORM, "    role: development\n", "    role: development\n  preview: {}\n"
    ),
    "NSTX201": lambda project: (project / f"{MODEL}.sql").write_text("SELECT * FROM a.b.c"),
    "NSTX202": seed("code: STRING", "code\nAU\n", name="orders"),
    "NSTX203": lambda project: (project / f"{MODEL}.sql").write_text("SELECT FROM WHERE"),
    "NSTX204": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM IDENTIFIER(:table)"
    ),
    "NSTX205": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM dev_sales.silver.orders"
    ),
    "NSTX206": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM read_files('/Volumes/x')"
    ),
    "NSTX207": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT r'${env}' AS x FROM sales.silver.orders"
    ),
    "NSTX208": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.gold.fct_orders"
    ),
    "NSTX209": lambda project: read_a_domains_gold_from_shared(project),
    "NSTX210": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.bronze.orders"
    ),
    "NSTX211": lambda project: (
        replacing(
            SOURCE,
            "format: json\n",
            "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n",
        )(project),
        (project / f"{MODEL}.sql").write_text("SELECT * FROM STREAM(sales.silver.orders)"),
    ),
    "NSTX212": lambda project: (
        seed("code: STRING", "code\nAU\n")(project),
        (project / f"{MODEL}.sql").write_text("SELECT * FROM STREAM(sales.silver.countries)"),
    ),
    "NSTX213": replacing(
        f"{MODEL}.yaml",
        "sql: fct_orders.sql\n",
        "sql: fct_orders.sql\ntests:\n  - references: {column: id, to: sales.gold.nope}\n",
    ),
}


@pytest.mark.parametrize(("rule", "break_project"), INVALID_PROJECTS.items())
def test_every_project_rule_reports_a_message_and_a_fix_and_exits_1(
    project: Path, rule: str, break_project: Callable[[Path], None]
):
    break_project(project)

    result = nstx(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == rule
    assert diagnostic["name"] == RULES[rule].name
    assert diagnostic["severity"] == "error"
    assert diagnostic["message"]
    assert diagnostic["fix"]
    assert diagnostic["docs"] == DOCS


def test_a_new_rule_must_be_tested_here():
    """The tests above, and the refresh failure, init folder, pinned CLI, platform check,
    skills, Kettle, preview and Build Package tests, cover these by name. A new rule joins one."""
    usage_and_environment = {"NSTX901", "NSTX902", "NSTX903", "NSTX904", "NSTX905", "NSTX909"}
    refresh_failures = {"NSTX906", "NSTX907", "NSTX908"}
    pinned_cli_failures = {"NSTX910", "NSTX911", "NSTX912", "NSTX913"}
    platform_checks = {"NSTX301", "NSTX302", "NSTX303"}
    skills = {"NSTX129", "NSTX914", "NSTX915"}
    examples = {"NSTX916"}
    previews = {"NSTX920", "NSTX921", "NSTX922"}
    build_packages = {"NSTX917", "NSTX918", "NSTX919"}
    model_tests = {"NSTX401", "NSTX402", "NSTX923", "NSTX924", "NSTX925", "NSTX926"}

    assert set(RULES) == (
        set(INVALID_PROJECTS)
        | usage_and_environment
        | refresh_failures
        | pinned_cli_failures
        | platform_checks
        | skills
        | examples
        | previews
        | build_packages
        | model_tests
    )


def test_the_docs_state_every_exit_code_and_every_rule():
    reference = Path(__file__).parent.parent / "docs/reference"
    docs = (reference / "json-output.md").read_text()
    index = (reference / "rules/index.md").read_text()

    assert "| 0 | Clean" in docs
    assert "| 1 | Rule failures" in docs
    assert "| 2 | Usage or environment error" in docs
    for code, rule in RULES.items():
        assert f"| [`{code}`]({code.lower()}.md) | `{rule.name}` |" in index


def test_help_states_the_exit_codes():
    result = runner.invoke(app, ["--help"])

    assert "0 clean, 1 rule failures, 2 usage or environment error" in result.stdout
