---
title: nsx test
description: Run each Gold Model's Tests on a Preview Environment's tables, yours or a pull request's.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nsx test [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--pr` | number |  | Test this pull request's Preview Environment. CI passes it, after `nsx preview --pr`. Left out, Nimblestax tests your own. |
| `--model` | text |  | Run only this Gold Model's Tests: its name, such as `fct_orders`, or, when more than one model has that name, its Logical Name, such as `sales.gold.fct_orders`. List several separated by commas, such as `fct_orders,dim_date`, or give it more than once. Left out, every Gold Model's Tests run. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `nimblestax.test/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `tests` | array of object | Every Test that ran, and passed. When one fails, `nsx test` exits 1 with a diagnostic for each failure instead. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
