"""The Deployment Manifest: what each Environment last received, kept in its own workspace.

A successful deploy writes it next to the deployed bundle, in a `nimblestax` folder:

    <bundle root>/nimblestax/manifest.json                            the current one
    <bundle root>/nimblestax/manifests/20261118T091200Z-<commit>.json  a copy per commit

A copy's name starts with when it was deployed, so names sort oldest first. Only the newest
`KEPT_COPIES` are kept, and a commit deployed again replaces its earlier copy. Where and how
manifests are stored is this module's alone, so moving them changes nothing else.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from nimblestax.deploy.databricks import Workspace, WorkspaceError
from nimblestax.diagnostics import Diagnostic, warning

FOLDER = "nimblestax"
CURRENT = "manifest.json"
COPIES = "manifests"
KEPT_COPIES = 100
# A package built outside Git, or before the first commit, has no commit to name its copy by.
NO_COMMIT = "no-commit"
# The current manifest, from the bundle root.
PATH = f"{FOLDER}/{CURRENT}"


def manifest(env: str, record: dict, deployed_at: datetime) -> dict:
    """What `env` now holds: the package's record, less its file list, and when it arrived."""
    return {
        "env": env,
        "deployed_at": _iso(deployed_at),
        "commit": record["commit"],
        "nimblestax_version": record["nimblestax_version"],
        "package_checksum": record["checksum"],
        "tables": record["tables"],
    }


def store(workspace: Workspace, package: Path, env: str, written: dict) -> list[Diagnostic]:
    """Write the copy, then the current file, then remove copies past the newest kept.

    A copy that can't be removed only warns: the deploy succeeded, and the next one tries again.
    """
    root = f"{workspace.bundle_root(package, env)}/{FOLDER}"
    content = json.dumps(written, indent=2) + "\n"
    copies = f"{root}/{COPIES}"
    copy = f"{copies}/{_copy_name(written)}"
    workspace.write_file(package, env, copy, content)
    workspace.write_file(package, env, f"{root}/{CURRENT}", content)
    try:
        stale = _stale(workspace.list_folder(package, env, copies), copy)
        for path in stale:
            workspace.delete_file(package, env, path)
    except WorkspaceError as failure:
        return [_not_removed(copies, failure)]
    return []


def read(workspace: Workspace, package: Path, env: str) -> dict | None:
    """What `env` last received, or None if it has no Deployment Manifest yet."""
    content = workspace.read_file(package, env, f"{workspace.bundle_root(package, env)}/{PATH}")
    return None if content is None else json.loads(content)


def _copy_name(written: dict) -> str:
    deployed_at = datetime.fromisoformat(written["deployed_at"])
    return f"{deployed_at:%Y%m%dT%H%M%SZ}-{written['commit'] or NO_COMMIT}.json"


def _stale(listed: list[str], newest: str) -> list[str]:
    """Earlier copies of the newest's commit, and every copy older than the newest kept."""
    commit = _commit_of(newest)
    others = sorted(path for path in listed if path != newest and _commit_of(path) != commit)
    replaced = [path for path in listed if path != newest and _commit_of(path) == commit]
    room = KEPT_COPIES - 1  # The newest copy is always kept.
    return replaced + others[: max(len(others) - room, 0)]


def _commit_of(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".json").split("-", 1)[-1]


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_removed(copies: str, failure: WorkspaceError) -> Diagnostic:
    [cause] = failure.diagnostics
    return warning(
        "NSX919",
        "",
        f"The deploy succeeded, but Nimblestax couldn't remove old Deployment Manifest copies"
        f" from {copies}: {cause.message}",
        f"Nothing to do now: the next deploy tries again. If this repeats, check that the"
        f" deploying identity can delete files in {copies}.",
    )
