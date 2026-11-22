---
title: Preview environments
description: How you try a change on all of a project's data, as yourself, in your own schemas beside dev, without touching dev's tables or pipelines.
---

A preview environment is a short-lived set of schemas in the development environment's catalogs, where a change is deployed and built before it merges. A personal preview is yours alone: `nstx preview` deploys your working tree, with your own login, into schemas named for you.

When a team runs Kettle's project, Priya changes `fct_orders` and runs `nstx preview` from her laptop. Her change builds in `dev_sales.u_priya_sharma__gold.fct_orders`, while CI keeps deploying `dev_sales.gold.fct_orders` beside it. Kettle itself can't be previewed, because the copy you make with `nstx init --example kettle` already runs in catalogs of its own.

```console
$ nstx preview
Deployed your working tree to your Preview Environment, in:
  dev_finance.u_priya_sharma__bronze
  dev_finance.u_priya_sharma__gold
  dev_finance.u_priya_sharma__silver
  dev_sales.u_priya_sharma__bronze
  dev_sales.u_priya_sharma__gold
  dev_sales.u_priya_sharma__silver
  dev_shared.u_priya_sharma__bronze
  dev_shared.u_priya_sharma__gold
  dev_shared.u_priya_sharma__silver
Remove it with `nstx preview down` when you're done.
```

## What a preview builds

A preview builds every table, from the same generated code every environment runs. Each source reads the files that land for the development environment, so `{env}` in a source's `path` is `dev`, not `preview`. Your preview's tables keep their state between runs, so only the first `nstx preview` builds everything from scratch.

A preview built from dev's landing files can differ from dev in two ways: rows dev took from files that have since gone are missing, and history is rebuilt from the files rather than copied.

## Your own schemas

Each schema is the development environment's own, with `u_` and your user name in front, under every naming style. Under `layer-catalogs`, `sales.silver.orders` is `dev_silver.u_priya_sharma__sales.orders`. Your user name is cleaned into a schema name: `priya.sharma@acme.com` becomes `priya_sharma`. A name with other characters, such as `priya_sharma` or `o'neil`, gets a short code after it, so two people never share a prefix.

Your pipelines and Job carry the same prefix, such as `u_priya_sharma__kettle_sales_gold`. Your bundle's state sits in your own workspace folder, with your preview's [deployment manifest](deployment-manifests.md#a-previews-manifest). So two people's previews never share a schema, a pipeline or a deploy, and neither touches dev's.

Nimblestax creates your schemas and labels each one with the project's name. It never deploys into a schema it didn't create for this project and for you, and stops with [`NSTX920`](../reference/rules/nstx920.md) instead.

A preview runs its pipelines in development mode: a failed update isn't retried, and compute is kept for your next run. It has no schedule. Your long-lived environments, such as dev and prod, stay in production mode.

## Removing a preview

`nstx preview down` removes what your preview of this project deployed, read from its bundle state, and its bundle folder with its deployment manifest. Your preview of another project, in the same catalogs, stays. It refuses anything outside your `u_` schemas in the development environment's catalogs, with [`NSTX922`](../reference/rules/nstx922.md). Nothing else removes a personal preview, so run it when you're done.

## What your team grants

Name the group your team works in as `developers` in `nimblestax.platform.yaml`:

```yaml
developers: data-engineers
```

That group needs `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` and `READ VOLUME` on the development environment's catalogs, and on no other environment's. `nstx validate --platform` checks it, and fails with [`NSTX303`](../reference/rules/nstx303.md) and the `GRANT` to run when one is missing. Your preview reads nothing of dev's but its landing files, so you can preview a project CI has never deployed.
