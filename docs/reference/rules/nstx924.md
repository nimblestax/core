---
title: NSTX924 no-preview-to-test
description: '`nstx test` found no Preview Environment of this project to run Tests on.'
generated: true
nimblestax_version: 0.1.0
---

## What it checks

`nstx test` found no Preview Environment of this project to run Tests on.

## Why

Tests run on the tables a Preview Environment built, so the preview must be deployed, and its refresh must have succeeded, first. Nimblestax knows it did when the preview's Deployment Manifest is in its bundle folder. It exits 2.

## Example

You haven't run `nstx preview` yet. In a project, this fails:

```console
$ nstx test
```

## Fix

Run `nstx preview`, or `nstx preview --pr <number>` for a pull request's preview, then `nstx test` again.
