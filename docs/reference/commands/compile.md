---
title: nsx compile
description: Write generated code, or print it for one Environment.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nsx compile [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--env` | text |  | Print runnable SQL for this Environment. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `nimblestax.compile/1`. When it succeeds, `result` is:

Without `--env`, `compile` writes the generated code.

| Field | Type | Meaning |
| --- | --- | --- |
| `package` | string | The folder the generated code was written to. |

With `--env`, `compile` prints it instead.

| Field | Type | Meaning |
| --- | --- | --- |
| `env` | string | The Environment the SQL is for. |
| `sql` | string | Every generated file as runnable SQL for that Environment. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
