---
title: nsx preview
description: Deploy your working tree to a Preview Environment, yours or a pull request's.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nsx preview [<action>] [OPTIONS]
```

## Arguments

| Argument | Meaning |
| --- | --- |
| `action` | `down` removes your Preview Environment of this project instead. |

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--pr` | number |  | The pull request whose Preview Environment this is, in `pr<N>__` schemas. CI passes it, signed in as the Development Environment's identity. Left out, the preview is your own. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `nimblestax.preview/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `schemas` | array of string | The Preview Environment's schemas, as `catalog.schema`, in the Development Environment's catalogs. |

With `down`, `preview` removes the Preview Environment instead.

| Field | Type | Meaning |
| --- | --- | --- |
| `removed` | boolean | Always `true`: the Preview Environment is gone. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
