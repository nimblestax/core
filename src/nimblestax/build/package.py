"""The Build Package's checksum record: which commit and Nimblestax built it, and what it holds.

One build of one commit makes one package, and every Environment is deployed from it. The record
lets a deploy check that the package it was given is the one that was built, file for file.
"""

import hashlib
import json
import subprocess
from importlib.metadata import version
from pathlib import Path

from nimblestax.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error

RECORD = "nimblestax.package.json"


def write_record(package: Path, project_root: Path, tables: dict[str, dict]) -> dict:
    """Record every file already in `package`, so write this last."""
    files = _checksums(package)
    record = {
        "commit": _commit(project_root),
        "nimblestax_version": version("nimblestax"),
        "checksum": _checksum_of(files),
        "files": files,
        "tables": tables,
    }
    (package / RECORD).write_text(json.dumps(record, indent=2) + "\n")
    return record


def read_record(package: Path) -> dict:
    """The record of a package whose files are as they were built, or a Failure saying why not."""
    path = package / RECORD
    if not path.is_file():
        raise Failure([_not_a_package(package)], USAGE_OR_ENVIRONMENT)
    record = json.loads(path.read_text())
    files = _checksums(package)
    if files != record.get("files") or _checksum_of(files) != record.get("checksum"):
        raise Failure([_changed(package, record.get("files", {}), files)], USAGE_OR_ENVIRONMENT)
    return record


def _checksums(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): _sha256(path.read_bytes())
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != RECORD
    }


def _checksum_of(files: dict[str, str]) -> str:
    """One checksum for the whole package, from each file's path and checksum."""
    listing = "".join(f"{checksum}  {path}\n" for path, checksum in sorted(files.items()))
    return _sha256(listing.encode())


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _commit(root: Path) -> str | None:
    """The commit checked out in the project, or None outside a Git repo or before a commit."""
    try:
        ran = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True, text=True
        )
    except FileNotFoundError:
        return None  # Git isn't installed, so there's no commit to name.
    return ran.stdout.strip() if ran.returncode == 0 else None


def _not_a_package(package: Path) -> Diagnostic:
    return error(
        "NSTX917",
        "",
        f"{package} isn't a Build Package: it has no `{RECORD}`.",
        "Pass the folder `nstx compile` wrote, such as `build`, or the artifact CI downloaded"
        " from the run that built it.",
    )


def _changed(package: Path, built: dict[str, str], found: dict[str, str]) -> Diagnostic:
    differ = sorted(path for path in {*built, *found} if built.get(path) != found.get(path))
    return error(
        "NSTX918",
        "",
        f"{package} isn't the Build Package that was built. These files differ from its"
        f" `{RECORD}`: {', '.join(differ) or RECORD}.",
        "Deploy the package as `nstx compile` wrote it. To change what it holds, change the"
        " project and build a new one.",
    )
