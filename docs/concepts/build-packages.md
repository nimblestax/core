---
title: Build packages
description: How one build of one commit becomes the package every environment is deployed from, and why it is never rebuilt.
---

A build package is what `nstx compile` writes into `build/`. Each merge builds one, and every environment is deployed from it. Prod runs the files that dev and every stage before it ran.

```console
$ nstx compile
Wrote build
```

For Kettle, the package holds:

```text
build/
├── databricks.yaml
├── nimblestax.package.json
└── src/
    ├── finance/gold/fct_revenue.sql
    ├── sales/gold/dim_product_prices.sql
    ├── sales/gold/fct_orders.sql
    ├── sales/ingest/customers.sql
    ├── sales/ingest/orders.sql
    ├── sales/ingest/product_prices.sql
    ├── sales/ingest/regions.sql
    ├── shared/gold/dim_customers.sql
    └── shared/gold/dim_date.sql
```

- **The SQL** names tables through placeholders, such as `${catalog_sales_silver}`, never real catalogs. So one copy works in every environment. `nstx compile --env dev` prints it with real names.
- **`databricks.yaml`** gives the placeholders their values, under one target per environment.
- **`nimblestax.package.json`** records the commit the package was built from, the Nimblestax version that built it, a checksum of each file and one for the whole package, and each table the package writes.

```json
{
  "commit": "3f9c2a1e8b7d4c6f0a9e2b1d3c5f7a8e9b0c1d2e",
  "nimblestax_version": "0.1.0",
  "checksum": "sha256:6a0e5aa74e7f41a766a676aa2329e4dbf7356f4eef528d38970e9a7706c06b18",
  "files": {
    "databricks.yaml": "sha256:9430f343…",
    "src/finance/gold/fct_revenue.sql": "sha256:c4d7944f…"
  },
  "tables": {
    "sales.silver.orders": {"type": "streaming_table", "file": "src/sales/ingest/orders.sql"}
  }
}
```

A package built outside a Git repo, or before the first commit, records `"commit": null`.

## Deploying a package

`nstx deploy --package` deploys the package it is given, as it is:

```console
$ nstx deploy --env dev --package build
Deployed to dev
```

Before it deploys anything, Nimblestax checks each file against `nimblestax.package.json`. A package with a file added, removed or edited since it was built is refused with [`NSTX918`](../reference/rules/nstx918.md), and a folder with no record with [`NSTX917`](../reference/rules/nstx917.md). A package is never rebuilt, so a newer Nimblestax or a later commit can't change what reaches prod.

Without `--package`, `nstx deploy` validates the project, builds a package into `build/`, and deploys that.

## In CI

The merge workflow that `nstx init --ci github` writes builds the package once, in a job that holds no environment's credentials. It keeps the package as a workflow artifact, and the job that deploys dev downloads it:

```yaml
- run: uvx --from "$NIMBLESTAX_SPEC" nstx validate
- run: uvx --from "$NIMBLESTAX_SPEC" nstx compile
- uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
  with:
    name: nimblestax-package
    path: build
```

Each later stage downloads the same artifact and runs `nstx deploy --env <env> --package build`. GitHub keeps artifacts for 90 days by default, which is how long a package can wait for promotion.

Each successful deploy records the package's commit and checksum in that environment's [deployment manifest](deployment-manifests.md).
