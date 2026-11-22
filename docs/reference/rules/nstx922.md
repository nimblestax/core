---
title: NSTX922 preview-down-outside-fence
description: '`nstx preview down` found a schema in the preview''s bundle state outside your `u_<user>__` schemas, or outside the Development Environment''s catalogs.'
generated: true
nimblestax_version: 0.1.0
---

## What it checks

`nstx preview down` found a schema in the preview's bundle state outside your `u_<user>__` schemas, or outside the Development Environment's catalogs.

## Why

`nstx preview down` destroys what the preview's bundle deployed, read from its bundle state. A Preview Environment only ever has your own `u_<user>__` schemas in the Development Environment's catalogs, so anything else in that state is a mistake, and `nstx preview down` refuses to remove anything rather than drop it. It exits 2.

## Example

The preview's bundle state holds the schema `prod_sales.silver`. In a project, this fails:

```console
$ nstx preview down
```

## Fix

Find out how that schema got into the preview's bundle state before removing anything. Drop the preview's own schemas by hand if you need to.
