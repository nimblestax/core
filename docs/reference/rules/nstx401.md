---
title: NSTX401 test-failed
description: A Gold Model's Test failed on its table in your Preview Environment.
generated: true
nimblestax_version: 0.1.0
---

## What it checks

A Gold Model's Test failed on its table in your Preview Environment.

## Why

A Test is a rule about a whole table, such as no two rows sharing an `order_id`. `nstx test` runs each one on the table your preview built from all of dev's rows, so a Test that fails there would fail in dev too. It exits 1.

## Example

Two rows of the preview's `fct_orders` have the same `order_id`. In a project, this fails:

```console
$ nstx test
```

## Fix

Fix the model's SQL or the data it reads, or correct the Test. Then run `nstx preview` and `nstx test` again.
