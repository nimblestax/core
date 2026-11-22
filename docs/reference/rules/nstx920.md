---
title: NSTX920 preview-schema-taken
description: '`nstx preview` would deploy into a schema that another project, another person, or someone by hand already created.'
generated: true
nimblestax_version: 0.1.0
---

## What it checks

`nstx preview` would deploy into a schema that another project, another person, or someone by hand already created.

## Why

A Preview Environment creates its own schemas in the Development Environment's catalogs, each labelled with the project and the person in its properties, and `nstx preview down` removes them. A schema it didn't create isn't its to fill or to remove, so `nstx preview` stops before it changes anything. It exits 2.

## Example

Another of your projects, `warehouse`, already has a preview with the schema `dev_sales.u_priya_sharma__silver`. In a project, this fails:

```console
$ nstx preview
```

## Fix

Remove the other preview with `nstx preview down` from its project, or drop the schema if nobody needs it, then run `nstx preview` again.
