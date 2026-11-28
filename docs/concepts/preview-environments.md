---
title: Preview environments
description: How a change is tried on all of a project's data, in its own schemas beside dev, before it merges, from your laptop or from CI on every pull request.
---

A preview environment is a short-lived set of schemas in the development environment's catalogs, where a change is deployed and built before it merges. A personal preview is yours alone: `nsx preview` deploys your working tree, with your own login, into schemas named for you. A pull request preview is the same thing, run by CI on every pull request.

When a team runs Kettle's project, Priya changes `fct_orders` and runs `nsx preview` from her laptop. Her change builds in `dev_sales.u_priya_sharma__gold.fct_orders`, while CI keeps deploying `dev_sales.gold.fct_orders` beside it. Kettle itself can't be previewed, because the copy you make with `nsx init --example kettle` already runs in catalogs of its own.

```console
$ nsx preview
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
Remove it with `nsx preview down` when you're done.
```

## What a preview builds

A preview builds every table, from the same generated code every environment runs. Each source reads the files that land for the development environment, so `{env}` in a source's `path` is `dev`, not `preview`. Your preview's tables keep their state between runs, so only the first `nsx preview` builds everything from scratch.

A preview built from dev's landing files can differ from dev in two ways: rows dev took from files that have since gone are missing, and history is rebuilt from the files rather than copied.

## Your own schemas

Each schema is the development environment's own, with `u_` and your user name in front, under every naming style. Under `layer-catalogs`, `silver.sales.orders` is `dev_silver.u_priya_sharma__sales.orders`. Your user name is cleaned into a schema name: `priya.sharma@acme.com` becomes `priya_sharma`. A name with other characters, such as `priya_sharma` or `o'neil`, gets a short code after it, so two people never share a prefix.

Your pipelines and Job carry the same prefix, such as `u_priya_sharma__kettle_sales_gold`. Your bundle's state sits in your own workspace folder, with your preview's [deployment manifest](deployment-manifests.md#a-previews-manifest). So two people's previews never share a schema, a pipeline or a deploy, and neither touches dev's.

Nimblestax creates your schemas and labels each one with the project's name. It never deploys into a schema it didn't create for this project and for you, and stops with [`NSX920`](../reference/rules/nsx920.md) instead.

A preview runs its pipelines in development mode: a failed update isn't retried, and compute is kept for your next run. It has no schedule. Your long-lived environments, such as dev and prod, stay in production mode.

## Pull request previews

Every pull request gets its own preview. CI runs `nsx preview --pr <N>`, signed in as the development environment's identity, and builds the pull request's code in `pr<N>__` schemas. When Priya opens pull request 42 with her change to `fct_orders`, its preview builds `dev_sales.pr42__gold.fct_orders`, and a reviewer can read those tables before approving.

```console
$ nsx preview --pr 42
Deployed pull request 42 to its Preview Environment, in:
  dev_finance.pr42__bronze
  dev_finance.pr42__gold
  dev_finance.pr42__silver
  dev_sales.pr42__bronze
  dev_sales.pr42__gold
  dev_sales.pr42__silver
  dev_shared.pr42__bronze
  dev_shared.pr42__gold
  dev_shared.pr42__silver
`nsx preview down --pr 42` removes it when the pull request closes.
```

It builds every table, like a personal preview, and its schemas follow `pr<N>__<schema>` under every naming style: under `layer-catalogs`, `silver.sales.orders` is `dev_silver.pr42__sales.orders`. A `pr` prefix never starts like a `u_` one, so a pull request's preview never shares a schema with a person's or with dev's.

The prefix comes from `--pr` alone. Nimblestax reads no CI variables, so the workflow passes the number. Its bundle state sits under the deploying identity's own `.bundle/<project>/pull-requests/<N>` folder, never in a person's folder, and each push to the pull request deploys into the same preview. The workflow `nsx init --ci github` writes runs it after `nsx validate`, one push at a time.

The development environment's identity creates the preview's schemas, so it needs `CREATE SCHEMA` on the development environment's catalogs, beside what it already holds to deploy dev.

## Removing a preview

`nsx preview down` removes what your preview of this project deployed, read from its bundle state, and its bundle folder with its deployment manifest. Your preview of another project, in the same catalogs, stays. It refuses anything outside your `u_` schemas in the development environment's catalogs, with [`NSX922`](../reference/rules/nsx922.md). Nothing else removes a personal preview, so run it when you're done.

`nsx preview down --pr <N>` removes a pull request's preview the same way, signed in as the identity that deployed it, and refuses anything outside its `pr<N>__` schemas.

## What your team grants

Name the group your team works in as `developers` in `nimblestax.platform.yaml`:

```yaml
developers: data-engineers
```

That group needs `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` and `READ VOLUME` on the development environment's catalogs, and on no other environment's. `nsx validate --platform` checks it, and fails with [`NSX303`](../reference/rules/nsx303.md) and the `GRANT` to run when one is missing. Your preview reads nothing of dev's but its landing files, so you can preview a project CI has never deployed.

To run [tests](tests.md) on a preview, the group, and CI's identity for pull request previews, also needs the `databricks-sql-access` entitlement and `CAN USE` on the SQL warehouse `nsx test` runs on.
