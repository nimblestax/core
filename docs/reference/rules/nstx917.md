---
title: NSTX917 not-a-build-package
description: '`nstx deploy --package` names a folder that isn''t a Build Package.'
generated: true
nimblestax_version: 0.1.0
---

## What it checks

`nstx deploy --package` names a folder that isn't a Build Package.

## Why

A Build Package is what `nstx compile` writes: the generated code, every Environment's settings, and `nimblestax.package.json`, which records the commit it was built from and a checksum of every file. The folder has no `nimblestax.package.json`, so Nimblestax can't tell what it holds, and deploys nothing.

## Example

In a project, this fails:

```console
$ nstx deploy --env dev --package src
```

## Fix

Pass the folder `nstx compile` wrote, such as `build`, or the artifact CI downloaded from the run that built it.
