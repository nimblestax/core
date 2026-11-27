---
title: NSTX921 example-has-no-preview
description: '`nstx preview`, or `nstx test`, was run in an example project, such as Kettle.'
generated: true
nimblestax_version: 0.1.0
---

## What it checks

`nstx preview`, or `nstx test`, was run in an example project, such as Kettle.

## Why

An example already runs in catalogs of its own, made for the person who ran it, so a Preview Environment would add nothing. It exits 2, and changes nothing in the workspace.

## Example

The project is Kettle. In a project, this fails:

```console
$ nstx preview
```

## Fix

Deploy the example directly, with `nstx deploy --env <env>`.
