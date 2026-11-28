---
title: Deployment manifests
description: The record each environment keeps of the build package it last received, where it lives, and how many copies are kept.
---

A deployment manifest is an environment's record of what it runs: which [build package](build-packages.md) it last received, from which commit, and the tables that package writes. Each successful `nsx deploy` writes one into that environment's workspace, and each successful `nsx preview` writes one for your [preview environment](preview-environments.md).

It is the baseline a change is compared against: the [plan](plan.md) on a pull request compares the project with dev's. Nimblestax can't tell from Unity Catalog alone which config made a table, so it reads what it recorded instead.

## What it holds

```json
{
  "env": "dev",
  "deployed_at": "2026-11-18T09:12:00Z",
  "commit": "3f9c2a1e8b7d4c6f0a9e2b1d3c5f7a8e9b0c1d2e",
  "nimblestax_version": "0.1.0",
  "package_checksum": "sha256:6a0e5aa74e7f41a766a676aa2329e4dbf7356f4eef528d38970e9a7706c06b18",
  "tables": {
    "sales.gold.fct_orders": {
      "type": "materialized_view",
      "file": "src/sales/gold/fct_orders.sql",
      "definition": "sha256:509d08ee1435eeb7c77ebc2bc1873a5bff20e17de1ea0b9ce740598b40cfa71a",
      "columns": {
        "order_id": "sha256:ca13a6b2c9651b3841fc9ffe25a7a4fccea30a22caf1e8812a10631b958506a7",
        "amount": "sha256:cf38d95c9c6b1d9d5125c04d41a54df57727ef4cfb3f5116a602fe2b25115c13"
      }
    }
  }
}
```

Each table in `tables` has:

- **`type`**: `streaming_table` or `materialized_view`.
- **`file`**: the generated file that makes it, in the build package.
- **`definition`**: a checksum of what makes the table. For a gold model, its columns are left out, so adding a column leaves `definition` as it was.
- **`columns`**: a gold model's columns, each with a checksum of the expression that makes it. It's there only when the model's SQL names every column, with no `*`.

The plan compares these to tell a new column from any other change.

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

The bundle folder is the deploying identity's, such as `/Workspace/Users/<identity>/.bundle/kettle/dev`. `nsx databricks bundle validate --target dev` prints it as `root_path`.

## When it is written

Only after a deploy succeeds, refresh included. A deploy whose bundle or refresh fails writes nothing, so the manifest never names a package the environment didn't take.

If old copies can't be removed, the deploy still succeeds and warns with [`NSX919`](../reference/rules/nsx919.md). The next deploy tries again.

`databricks bundle destroy` removes the bundle folder, and the manifests with it.

## A preview's manifest

`nsx preview` writes its manifest the same way, with `"env": "preview"`, in your preview's own bundle folder, such as `/Workspace/Users/priya.sharma@acme.com/.bundle/kettle/preview`. A preview deploys your working tree, so its `commit` is the commit you're on, plus anything uncommitted: `package_checksum` tells two previews of one commit apart. `nsx preview down` removes the folder, and the manifests with it. A preview's manifest is never the baseline for anyone else's change.
