---
title: nsx deploy
description: Deploy to an Environment, refresh its tables, and write its Deployment Manifest.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nsx deploy [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--env` | text |  | The Environment to deploy. Required: a deploy never uses the default Environment. |
| `--package` | path |  | The Build Package to deploy, as `nsx compile` wrote it. It is deployed as it is, never rebuilt. Left out, the project is validated and built first. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `nimblestax.deploy/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `env` | string | The Environment deployed and refreshed. |
| `commit` | string or null | The commit the Build Package was built from, or `null` if it was built outside Git. |
| `package_checksum` | string | The Build Package's checksum, as its Deployment Manifest records it. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
