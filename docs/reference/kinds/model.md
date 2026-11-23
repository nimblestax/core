---
title: Gold Model
description: A dataset built from a SQL file that reads Logical Names.
generated: true
nimblestax_version: 0.1.0
---

A file with `kind: model`, at version 1. `nstx schema model` prints the same fields from the Nimblestax you installed.

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `kind` | `model` | yes |  | The Kind of this file. |
| `version` | `1` | yes |  | The schema version of this Kind. |
| `sql` | string | yes |  | The SQL file, in the same folder as this file. |
| `owner` | string | yes |  | Who answers for this table: a team or a person, such as `sales-analytics`. |
| `tests` | list of a mapping with one of `unique`, `row_count`, `references` | no | `[]` | The Tests `nstx test` runs on this model's table in a Preview Environment. |
| `tests[].unique` | list of string | yes |  | The columns that together hold a different value in each row. |
| `tests[].row_count` | object | yes |  | How many rows the table may have. |
| `tests[].row_count.min` | integer | no | `1` | The fewest rows the table may have. |
| `tests[].row_count.max` | integer | no | `null` | The most rows the table may have. Left out, no limit. |
| `tests[].references` | object | yes |  | The column, and the table and key it refers to. |
| `tests[].references.column` | string | yes |  | The column whose values must be in the other table. |
| `tests[].references.to` | string | yes |  | The other table's Logical Name, such as `shared.gold.dim_customers`. |
| `tests[].references.key` | string | no | `null` | The other table's column. Left out, it has `column`'s name. |
