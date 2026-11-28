---
title: nsx plan
description: Compare the project with what an Environment last received, and class each change.
generated: true
nimblestax_version: 0.1.0
---

```console
$ nsx plan [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--env` | text |  | The Environment to compare with. Left out, the default Environment. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `nimblestax.plan/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `env` | string | The Environment the change is compared with. |
| `baseline` | object or null | The Deployment Manifest compared with, or `null` when the Environment has none yet. |
| `baseline.env` | string | The Environment compared with. |
| `baseline.commit` | string or null | The commit it last received. |
| `baseline.deployed_at` | string | When it received it, in UTC. |
| `baseline.nimblestax_version` | string | The Nimblestax that deployed it. |
| `summary` | object | How many changes are in each Change Class: `safe`, `refresh` and `destructive`. |
| `blocked` | boolean | Whether Nimblestax refuses the change outright. A blocked Plan exits 1. |
| `changes` | array of object | Every change, most at risk first. |
| `changes[].id` | string | Names the change the same way each time the Plan runs, such as `update:sales.gold.fct_orders`. |
| `changes[].object` | string | What changes: a table's Logical Name. |
| `changes[].object_type` | string | What kind of object it is: `streaming_table` or `materialized_view`. |
| `changes[].action` | string | What happens to it: `create`, `update` or `retire`. |
| `changes[].change_class` | string | What is at risk: `safe` (nothing is lost), `refresh` (named tables are rebuilt) or `destructive` (data or history is removed from a table). |
| `changes[].reason` | string | What changed, in words. |
| `changes[].rule` | string or null | The Rule behind the change, or `null` when none is. |
| `changes[].refresh_tables` | array of string | The tables the change rebuilds, by Logical Name. Empty unless `change_class` is `refresh`. |
| `changes[].downstream_domains` | array of string | The Domains whose gold reads the changed table. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
