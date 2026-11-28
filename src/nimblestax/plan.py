"""The Plan: what a change alters in an Environment, found by comparing the tables the project
writes now with the ones its Deployment Manifest says the Environment last received."""

from dataclasses import dataclass, field
from importlib.metadata import version

from nimblestax.build import compiler
from nimblestax.check import rules
from nimblestax.deploy import manifest
from nimblestax.deploy.databricks import Workspace
from nimblestax.diagnostics import DOCS_ROOT, Diagnostic, Failure, errors, warning
from nimblestax.load.project import Project

SAFE = "safe"
REFRESH = "refresh"
DESTRUCTIVE = "destructive"
CHANGE_CLASSES = (SAFE, REFRESH, DESTRUCTIVE)

CREATE = "create"
UPDATE = "update"


@dataclass(frozen=True)
class Change:
    object: str
    object_type: str
    action: str
    change_class: str
    reason: str
    rule: str | None = None
    refresh_tables: list[str] = field(default_factory=list)
    downstream_domains: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """The same change gets the same ID each time the Plan runs."""
        return f"{self.action}:{self.object}"


@dataclass(frozen=True)
class Plan:
    env: str
    baseline: dict | None
    changes: list[Change]
    warnings: list[Diagnostic] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {
            name: sum(change.change_class == name for change in self.changes)
            for name in CHANGE_CLASSES
        }

    @property
    def blocked(self) -> bool:
        return False


def against(project: Project, env: str, workspace: Workspace) -> Plan:
    """The Plan of the project against `env`, read from its Deployment Manifest."""
    problems = errors(rules.check(project))
    if problems:
        raise Failure(problems)
    package = compiler.write_package(project)
    baseline = manifest.read(workspace, package, env)
    found = compare(env, compiler.tables(project), baseline)
    if baseline is None:
        where = f"{workspace.bundle_root(package, env)}/{manifest.PATH}"
        found.warnings.insert(0, _no_manifest(env, where))
    return found


def compare(env: str, tables: dict[str, dict], baseline: dict | None) -> Plan:
    """Each table new since `baseline`, or changed in a way the Plan can class. Any other
    change warns rather than being given a class it might not have."""
    deployed = (baseline or {}).get("tables", {})
    if any("definition" not in table for table in deployed.values()):
        new = [_new_table(name, table) for name, table in tables.items() if name not in deployed]
        return Plan(env, baseline, _most_at_risk_first(new), [_no_definitions(env, baseline or {})])
    changes: list[Change] = []
    unclassed: list[str] = []
    for name, table in tables.items():
        before = deployed.get(name)
        if before is None:
            changes.append(_new_table(name, table))
        elif before != table:
            added = _only_new_columns(before, table)
            if added:
                changes.append(_new_columns(name, table, added))
            else:
                unclassed.append(name)
    unclassed += [name for name in deployed if name not in tables]
    warnings = [_not_classed(name) for name in sorted(unclassed)]
    return Plan(env, baseline, _most_at_risk_first(changes), warnings)


def _most_at_risk_first(changes: list[Change]) -> list[Change]:
    def risk(change: Change) -> tuple[int, str]:
        return (-CHANGE_CLASSES.index(change.change_class), change.object)

    return sorted(changes, key=risk)


def _only_new_columns(before: dict, now: dict) -> list[str]:
    """The columns `now` adds, if adding them is all that changed, or none."""
    old, new = before.get("columns"), now.get("columns")
    if old is None or new is None or before["definition"] != now["definition"]:
        return []
    if any(new.get(column) != made for column, made in old.items()):
        return []
    return [column for column in new if column not in old]


def markdown(plan: Plan) -> str:
    """The Plan as a comment for a pull request, which reads as plain text in a terminal too."""
    lines = [f"## Plan against {plan.env}", ""]
    if plan.baseline:
        commit = plan.baseline["commit"]
        received = f"commit `{commit[:7]}`" if commit else "a package built outside Git"
        lines += [
            f"Compared with what {plan.env} last received: {received}, deployed"
            f" {plan.baseline['deployed_at']}.",
            "",
        ]
    if plan.changes:
        counts = ", ".join(f"{count} {name}" for name, count in plan.summary.items())
        lines += [f"{counts}.", "", "| Class | Action | Table | What changes |"]
        lines += ["| --- | --- | --- | --- |"]
        lines += [
            f"| {c.change_class} | {c.action} | `{c.object}` | {c.reason} |" for c in plan.changes
        ]
    else:
        lines.append(f"No changes to {plan.env}'s tables.")
    for found in plan.warnings:
        page = f"{DOCS_ROOT}/reference/rules/{found.rule.lower()}.md"
        lines += ["", f"[**{found.rule}**]({page}) ({found.severity}): {found.message} {found.fix}"]
    installed = version("nimblestax")
    changelog = f"{DOCS_ROOT}/changelog.md#{installed.replace('.', '')}"
    lines += ["", "---", "", f"Nimblestax {installed} · [changelog]({changelog})"]
    return "\n".join(lines)


def _new_table(name: str, table: dict) -> Change:
    return Change(name, table["type"], CREATE, SAFE, f"A new {table['type'].replace('_', ' ')}.")


def _new_columns(name: str, table: dict, added: list[str]) -> Change:
    listed = ", ".join(f"`{column}`" for column in added)
    reason = f"Adds the column {listed}." if len(added) == 1 else f"Adds the columns {listed}."
    return Change(name, table["type"], UPDATE, SAFE, reason)


def _not_classed(name: str) -> Diagnostic:
    return warning(
        "NSX501",
        "",
        f"{name} changed in a way the Plan doesn't class yet, so it isn't listed as a change.",
        f"Read the change to {name}'s config or SQL in the pull request before you approve it.",
    )


def _no_manifest(env: str, where: str) -> Diagnostic:
    return warning(
        "NSX502",
        "",
        f"{env} has no Deployment Manifest at {where}, so the Plan shows every table as new."
        f" Tables that already exist in {env} are listed too.",
        f"Nothing to do if {env} hasn't been deployed yet: its first deploy writes the manifest."
        f" Otherwise, check that you're signed in as the identity that deploys {env}.",
    )


def _no_definitions(env: str, baseline: dict) -> Diagnostic:
    return warning(
        "NSX503",
        "",
        f"{env}'s Deployment Manifest was written by Nimblestax"
        f" {baseline.get('nimblestax_version', 'unknown')}, which didn't record how each table is"
        " made, so the Plan shows only new tables.",
        f"Deploy {env} again with this Nimblestax. Until then, read each table's change in the"
        " pull request.",
    )
