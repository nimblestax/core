"""The installed `nsx` and `nimblestax` commands, run as a user runs them."""

import json
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from nimblestax.registry import RULES

BIN = Path(sys.executable).parent


def run(command: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(BIN / command), *args], capture_output=True, text=True)


def nsx(*args: str) -> subprocess.CompletedProcess[str]:
    return run("nsx", *args)


def test_init_writes_nimblestax_platform_yaml(tmp_path: Path):
    result = nsx("init", str(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "nimblestax.platform.yaml").exists()


def test_validate_reports_an_unresolved_logical_name_as_nsx201(tmp_path: Path):
    nsx("init", str(tmp_path))
    model = tmp_path / "domains/sales/models/gold/fct_orders.sql"
    model.write_text("SELECT * FROM sales.silver.nonexistent")

    result = nsx("validate", "--json", "--project", str(tmp_path))

    assert result.returncode == 1, result.stdout + result.stderr
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "NSX201"


def test_nimblestax_is_the_long_form_of_nsx():
    short = nsx("--version")
    long = run("nimblestax", "--version")

    assert short.returncode == 0, short.stdout + short.stderr
    assert long.stdout == short.stdout
    assert short.stdout.startswith("nsx ")


def test_nsx_and_nimblestax_are_the_only_commands_installed():
    commands = {script.name for script in distribution("nimblestax").entry_points}

    assert commands == {"nsx", "nimblestax"}


def test_every_rule_code_is_spelled_nsx():
    assert [code for code in RULES if not code.startswith("NSX")] == []
