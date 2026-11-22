---
title: NSTX303 developer-group-missing-grant
description: With `--platform` on the Development Environment, the group `developers` names lacks `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` or `READ VOLUME` on one of its catalogs.
generated: true
nimblestax_version: 0.1.0
---

## What it checks

With `--platform` on the Development Environment, the group `developers` names lacks `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` or `READ VOLUME` on one of its catalogs.

## Why

Each person deploys their own Preview Environment with their own login, into schemas they create in the Development Environment's catalogs, and its sources read the files that land in its Volumes. The group needs those four privileges there, and only there.

## Example

`data-engineers` has no `CREATE SCHEMA` on `dev_sales`. In a project, this fails:

```console
$ nstx validate --platform
```

## Fix

Run the `GRANT` the diagnostic gives, as the catalog's owner.
