---
title: Deployment manifests
description: The record each environment keeps of the build package it last received, where it lives, and how many copies are kept.
---

A deployment manifest is an environment's record of what it runs: which [build package](build-packages.md) it last received, from which commit, and the tables that package writes. Each successful `nstx deploy` writes one into that environment's workspace.

It is the baseline a change is compared against. Nimblestax can't tell from Unity Catalog alone which config made a table, so it reads what it recorded instead.

## What it holds

```json
{
  "env": "dev",
  "deployed_at": "2026-11-18T09:12:00Z",
  "commit": "3f9c2a1e8b7d4c6f0a9e2b1d3c5f7a8e9b0c1d2e",
  "nimblestax_version": "0.1.0",
  "package_checksum": "sha256:6a0e5aa74e7f41a766a676aa2329e4dbf7356f4eef528d38970e9a7706c06b18",
  "tables": {
    "sales.silver.orders": {"type": "streaming_table", "file": "src/sales/ingest/orders.sql"}
  }
}
```

`package_checksum` is the checksum in the package's `nimblestax.package.json`, so you can tell whether two environments run the same package.

## Where it lives

Next to the deployed bundle, in the environment's workspace:

```text
<bundle folder>/nimblestax/
├── manifest.json
└── manifests/
    ├── 20261117T143005Z-8b04e7d….json
    └── 20261118T091200Z-3f9c2a1….json
```

- **`manifest.json`** is the current one. Each deploy replaces it.
- **`manifests/`** keeps a copy per deployed commit, named by when it was deployed and then the commit, so the names sort oldest first. Deploying a commit again replaces its earlier copy. The newest 100 are kept, and older ones are removed after each deploy.

The bundle folder is the deploying identity's, such as `/Workspace/Users/<identity>/.bundle/kettle/dev`. `nstx databricks bundle validate --target dev` prints it as `root_path`.

## When it is written

Only after a deploy succeeds, refresh included. A deploy whose bundle or refresh fails writes nothing, so the manifest never names a package the environment didn't take.

If old copies can't be removed, the deploy still succeeds and warns with [`NSTX919`](../reference/rules/nstx919.md). The next deploy tries again.

`databricks bundle destroy` removes the bundle folder, and the manifests with it.
