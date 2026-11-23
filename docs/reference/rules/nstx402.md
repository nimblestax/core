---
title: NSTX402 test-could-not-run
description: The SQL warehouse refused a Test's query.
generated: true
nimblestax_version: 0.1.0
---

## What it checks

The SQL warehouse refused a Test's query.

## Why

Each Test runs as one query on the model's table. The warehouse refuses it when the Test doesn't match the table, such as a column the table doesn't have. Nimblestax can't see a table's columns without a workspace, so `nstx validate` can't catch this. The other Tests still run, and `nstx test` exits 1.

## Example

`fct_orders` has no column `order_no`. In a project, this fails:

```console
$ nstx test
```

## Fix

Correct the Test so it matches the model's table, such as a column's name.
