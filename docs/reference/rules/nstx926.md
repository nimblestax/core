---
title: NSTX926 no-such-model
description: '`--model` names no Gold Model in the project, or a name that more than one Domain has.'
generated: true
nimblestax_version: 0.1.0
---

## What it checks

`--model` names no Gold Model in the project, or a name that more than one Domain has.

## Why

`--model` picks a Gold Model by its name, such as `fct_orders`, or by its Logical Name, such as `sales.gold.fct_orders`. A name two Domains share could mean either, so Nimblestax doesn't guess. It exits 2, before reaching the workspace.

## Example

In a project, this fails:

```console
$ nstx test --model fct_order
```

## Fix

Give a Gold Model's name, or its Logical Name when two Domains share the name. The diagnostic lists the ones it could be.
