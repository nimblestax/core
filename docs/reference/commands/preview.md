---
title: nstx preview
description: Deploy your working tree to your own Preview Environment, and build every table.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nstx preview [<action>] [OPTIONS]
```

## Arguments

| Argument | Meaning |
| --- | --- |
| `action` | `down` removes your Preview Environment of this project instead. |

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
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
