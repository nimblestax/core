---
title: NSTX919 manifest-copies-not-removed
description: A deploy succeeded, but old copies of the Deployment Manifest couldn't be removed.
generated: true
nimblestax_version: 0.1.0
---

## What it checks

A deploy succeeded, but old copies of the Deployment Manifest couldn't be removed.

## Why

Each deploy writes the Deployment Manifest next to the deployed bundle, plus a copy named for its commit, and keeps only the newest 100 copies. Removing older ones failed, so there are more than 100 for now. Nothing reads the copies to deploy or plan, so the deploy still succeeds.

## Example

The deploying identity can write files in the bundle's folder but not delete them. In a project, this fails:

```console
$ nstx deploy --env dev
```

## Fix

Nothing to do now: the next deploy tries again. If this repeats, check that the deploying identity can delete files in the bundle's `nimblestax/manifests` folder.
