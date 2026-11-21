---
title: NSTX133 reserved-environment-name
description: An Environment is named `preview`.
generated: true
nimblestax_version: 0.1.0
---

## What it checks

An Environment is named `preview`.

## Why

`preview` is the bundle target every Preview Environment deploys through, so an Environment with that name would share its target.

## Example

In a project, this fails:

```console
$ nstx validate
```

## Fix

Rename the Environment, such as to `staging`.
