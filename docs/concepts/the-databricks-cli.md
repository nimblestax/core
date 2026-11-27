---
title: The Databricks CLI
description: Nimblestax brings its own pinned Databricks CLI, so every machine deploys with the same version.
---

Nimblestax deploys through the Databricks CLI, and it brings its own. Each Nimblestax release names one CLI version. The `databricks` on your PATH is never used, so your laptop and CI deploy the same project the same way, whichever CLI you have installed.

```console
$ nsx --version
nsx 0.1.0
Databricks CLI 1.23.0
```

## Where it comes from

The first time a command needs the CLI, Nimblestax downloads that version from Databricks' GitHub releases. It checks the archive against the checksum its release names. An archive that doesn't match is refused with [`NSX910`](../reference/rules/nsx910.md), and nothing runs.

Nimblestax keeps the CLI in your cache folder, one folder per version, and reuses it after that:

| System | Folder |
| --- | --- |
| Linux | `~/.cache/nimblestax/databricks-cli/`, or under `$XDG_CACHE_HOME` |
| macOS | `~/Library/Caches/nimblestax/databricks-cli/` |
| Windows | `%LOCALAPPDATA%\nimblestax\databricks-cli\` |

Two projects on different Nimblestax versions each run their own CLI. Two runs that start at once download it once.

The download honours `HTTPS_PROXY` and `NO_PROXY`. If it fails, Nimblestax reports [`NSX912`](../reference/rules/nsx912.md).

## Run it yourself

[`nsx databricks`](../reference/commands/databricks.md) runs the same CLI, with your arguments passed through, so you don't need a CLI of your own:

```console
$ nsx databricks auth describe
```

A `databricks` command you run yourself uses your own CLI, which can be a different version and behave differently.

## A machine that can't download it

On a machine with no route to GitHub, install the Databricks CLI yourself and point `NIMBLESTAX_DATABRICKS_CLI` at it:

```console
$ export NIMBLESTAX_DATABRICKS_CLI=/opt/databricks/databricks
```

Nimblestax reads its version first. A CLI older than the release supports is refused with [`NSX911`](../reference/rules/nsx911.md), so an old CLI can't deploy your project differently.
