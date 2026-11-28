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


def nsx(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def test_validate_prints_an_envelope_with_the_rule_id_and_exits_1(project: Path):
    (project / "domains/sales/models/gold/fct_orders.sql").write_text(
        "SELECT * FROM sales.silver.nope"
    )

    result = nsx(project, "validate", "--json")

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
    assert diagnostic["rule"] == "NSX201"
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
    result = nsx(project, "compile", "--env", "dev", "--json")

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
        assert "--json" in options, f"`nsx {name}` has no --json"


def run_nimblestax(*args: str, databricks: Path) -> subprocess.CompletedProcess:
    """The installed command in its own process, so stdout and stderr are the real ones."""
    executable = Path(sys.executable).with_name("nsx")
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
    assert diagnostic["rule"] == "NSX904"


def test_a_missing_databricks_cli_is_an_environment_error(project: Path, tmp_path_factory):
    missing = tmp_path_factory.mktemp("empty") / "databricks"

    result = run_nimblestax(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=missing
    )

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSX903"
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
    assert diagnostic["rule"] == "NSX901"
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
    result = nsx(project, command, "--env", "staging", "--json")

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSX902"
    assert "dev" in diagnostic["fix"]


@pytest.mark.parametrize("as_json", [True, False])
def test_a_crash_keeps_the_exit_code_contract(tmp_path: Path, as_json: bool):
    in_the_way = tmp_path / "a-file"
    in_the_way.write_text("not a folder")
    flags = ["--json"] if as_json else []

    result = runner.invoke(app, ["init", str(in_the_way), *flags])

    assert result.exit_code == 2
    assert "NSX905" in result.stdout
    assert "Traceback" in result.stderr
    assert "Traceback" not in result.stdout
    if as_json:
        assert json.loads(result.stdout)["schema"] == "nimblestax.init/1"


def test_a_project_problem_without_json_stays_text_for_a_person(project: Path):
    (project / "domains/sales/models/gold/fct_orders.sql").write_text(
        "SELECT * FROM sales.silver.nope"
    )

    result = nsx(project, "validate")

    assert result.exit_code == 1
    assert "NSX201 domains/sales/models/gold/fct_orders.sql:" in result.stdout
    assert "Fix: " in result.stdout


# Copied by hand on purpose. Editing a line here means a rule ID changed meaning, was removed or
# was reused, which breaks every agent and script that relies on it. Only ever add lines.
REGISTERED_RULES = {
    "NSX101": "missing-kind",
    "NSX102": "unknown-kind",
    "NSX103": "missing-version",
    "NSX104": "unknown-version",
    "NSX105": "wrong-kind",
    "NSX106": "invalid-field",
    "NSX107": "unreadable-config",
    "NSX108": "sql-without-config",
    "NSX109": "missing-sql-file",
    "NSX110": "keys-without-sequence-by",
    "NSX111": "upsert-field-without-keys",
    "NSX112": "missing-seed-file",
    "NSX113": "seed-header-mismatch",
    "NSX114": "seed-row-mismatch",
    "NSX115": "unsupported-seed-type",
    "NSX116": "invalid-expectation",
    "NSX117": "invalid-name",
    "NSX118": "invalid-delete-when",
    "NSX119": "invalid-sequence-by",
    "NSX120": "duplicate-config-file",
    "NSX121": "unlisted-domain-folder",
    "NSX122": "dev-host-missing",
    "NSX123": "two-default-environments",
    "NSX124": "naming-patterns-not-supported",
    "NSX125": "source-layers-fixed",
    "NSX126": "model-layer-named-like-a-source-layer",
    "NSX127": "model-outside-a-layer",
    "NSX129": "skill-version-drift",
    "NSX130": "no-development-environment",
    "NSX131": "two-environments-with-one-role",
    "NSX132": "environment-name-not-an-identifier",
    "NSX133": "reserved-environment-name",
    "NSX201": "unresolved-logical-name",
    "NSX202": "duplicate-table",
    "NSX203": "unparseable-sql",
    "NSX204": "computed-table-name",
    "NSX205": "real-table-name",
    "NSX206": "file-read",
    "NSX207": "raw-string-placeholder",
    "NSX208": "model-cycle",
    "NSX209": "cross-domain-read",
    "NSX210": "read-against-build-order",
    "NSX211": "stream-of-upsert-silver",
    "NSX212": "stream-of-materialized-view",
    "NSX213": "test-references-unknown-table",
    "NSX301": "missing-catalog",
    "NSX302": "missing-schema",
    "NSX303": "developer-group-missing-grant",
    "NSX401": "test-failed",
    "NSX402": "test-could-not-run",
    "NSX501": "change-not-classed",
    "NSX502": "no-deployment-manifest",
    "NSX503": "manifest-without-definitions",
    "NSX901": "usage-error",
    "NSX902": "unknown-environment",
    "NSX903": "databricks-cli-missing",
    "NSX904": "databricks-command-failed",
    "NSX905": "unexpected-error",
    "NSX906": "pipeline-column-not-found",
    "NSX907": "expectation-failed",
    "NSX908": "pipeline-failed",
    "NSX909": "project-already-exists",
    "NSX910": "databricks-cli-checksum-mismatch",
    "NSX911": "databricks-cli-unsupported",
    "NSX912": "databricks-cli-download-failed",
    "NSX913": "no-databricks-cli-for-platform",
    "NSX914": "skills-folder-ignored",
    "NSX915": "skill-edited",
    "NSX916": "unknown-example",
    "NSX917": "not-a-build-package",
    "NSX918": "build-package-changed",
    "NSX919": "manifest-copies-not-removed",
    "NSX920": "preview-schema-taken",
    "NSX921": "example-has-no-preview",
    "NSX922": "preview-down-outside-fence",
    "NSX923": "no-warehouse-for-tests",
    "NSX924": "no-preview-to-test",
    "NSX925": "no-databricks-sql-access",
    "NSX926": "no-such-model",
}


# Removed before any release, so no project ever saw them. Their IDs are still never reused.
RETIRED_RULES = {"NSX128": "production-shares-a-workspace"}


def test_no_rule_id_is_removed_reused_or_changes_meaning():
    assert {code: rule.name for code, rule in RULES.items()} == REGISTERED_RULES
    assert not RETIRED_RULES.keys() & REGISTERED_RULES.keys()
    assert not set(RETIRED_RULES.values()) & set(REGISTERED_RULES.values())


def test_rule_ids_are_nsx_plus_three_digits_with_one_name_each():
    assert all(re.fullmatch(r"NSX\d{3}", rule) for rule in RULES)
    assert len({rule.name for rule in RULES.values()}) == len(RULES)


def test_an_unregistered_rule_can_not_be_reported():
    with pytest.raises(KeyError):
        error("NSX999", "", "A message.", "A fix.")


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
    "NSX101": replacing(SOURCE, "kind: source\n", ""),
    "NSX102": replacing(SOURCE, "kind: source\n", "kind: sauce\n"),
    "NSX103": replacing(SOURCE, "version: 1\n", ""),
    "NSX104": replacing(SOURCE, "version: 1\n", "version: 2\n"),
    "NSX105": replacing(SOURCE, "kind: source\n", "kind: model\n"),
    "NSX106": replacing(SOURCE, "format: json\n", "format: 7\n"),
    "NSX107": lambda project: (project / SOURCE).write_text("just a string"),
    "NSX108": lambda project: (project / f"{MODEL}.yaml").unlink(),
    "NSX109": lambda project: (project / f"{MODEL}.sql").unlink(),
    "NSX110": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  keys: [order_id]\n"),
    "NSX111": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  scd: 2\n"),
    "NSX112": seed("code: STRING", None),
    "NSX113": seed("code: STRING", "nope\nAU\n"),
    "NSX114": seed("code: INT", "code\nAU\n"),
    "NSX115": seed("code: VARCAHR", "code\nAU\n"),
    "NSX116": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  expectations:\n    - name: bad\n      expect: amount >\n",
    ),
    "NSX117": seed("code: STRING", "code\nAU\n", name="vat-rates"),
    "NSX118": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n"
        "  delete_when: op =\n",
    ),
    "NSX119": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at DESC\n",
    ),
    "NSX120": lambda project: (project / SOURCE.replace(".yaml", ".yml")).write_text(
        (project / SOURCE).read_text()
    ),
    "NSX121": lambda project: (project / "domains/hr").mkdir(),
    "NSX122": replacing(PLATFORM, f"    host: {PLACEHOLDER_HOST}\n", ""),
    "NSX123": replacing(
        PLATFORM,
        "    role: development\n",
        "    role: development\n    default: true\n  prod:\n    default: true\n",
    ),
    "NSX124": replacing(PLATFORM, "  style: domain-catalogs\n", '  catalog: "{env}"\n'),
    "NSX125": lambda project: (project / PLATFORM).write_text(
        "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
        f"    host: {PLACEHOLDER_HOST}\n"
        'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
        "  layers:\n    sources: [bronze, curated]\n    models: [gold]\ndomains:\n  - sales\n"
    ),
    "NSX126": replacing(PLATFORM, "models: [gold]", "models: [gold, silver]"),
    "NSX127": lambda project: (project / "domains/sales/models/x.sql").write_text("SELECT 1"),
    "NSX130": replacing(PLATFORM, "    role: development\n", ""),
    "NSX131": replacing(
        PLATFORM,
        "    role: development\n",
        "    role: development\n  test:\n    role: development\n",
    ),
    "NSX132": replacing(
        PLATFORM, "    role: development\n", "    role: development\n  prd-1: {}\n"
    ),
    "NSX133": replacing(
        PLATFORM, "    role: development\n", "    role: development\n  preview: {}\n"
    ),
    "NSX201": lambda project: (project / f"{MODEL}.sql").write_text("SELECT * FROM a.b.c"),
    "NSX202": seed("code: STRING", "code\nAU\n", name="orders"),
    "NSX203": lambda project: (project / f"{MODEL}.sql").write_text("SELECT FROM WHERE"),
    "NSX204": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM IDENTIFIER(:table)"
    ),
    "NSX205": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM dev_sales.silver.orders"
    ),
    "NSX206": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM read_files('/Volumes/x')"
    ),
    "NSX207": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT r'${env}' AS x FROM sales.silver.orders"
    ),
    "NSX208": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.gold.fct_orders"
    ),
    "NSX209": lambda project: read_a_domains_gold_from_shared(project),
    "NSX210": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.bronze.orders"
    ),
    "NSX211": lambda project: (
        replacing(
            SOURCE,
            "format: json\n",
            "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n",
        )(project),
        (project / f"{MODEL}.sql").write_text("SELECT * FROM STREAM(sales.silver.orders)"),
    ),
    "NSX212": lambda project: (
        seed("code: STRING", "code\nAU\n")(project),
        (project / f"{MODEL}.sql").write_text("SELECT * FROM STREAM(sales.silver.countries)"),
    ),
    "NSX213": replacing(
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

    result = nsx(project, "validate", "--json")

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
    usage_and_environment = {"NSX901", "NSX902", "NSX903", "NSX904", "NSX905", "NSX909"}
    refresh_failures = {"NSX906", "NSX907", "NSX908"}
    pinned_cli_failures = {"NSX910", "NSX911", "NSX912", "NSX913"}
    platform_checks = {"NSX301", "NSX302", "NSX303"}
    skills = {"NSX129", "NSX914", "NSX915"}
    examples = {"NSX916"}
    previews = {"NSX920", "NSX921", "NSX922"}
    build_packages = {"NSX917", "NSX918", "NSX919"}
    model_tests = {"NSX401", "NSX402", "NSX923", "NSX924", "NSX925", "NSX926"}
    plans = {"NSX501", "NSX502", "NSX503"}

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
        | plans
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
