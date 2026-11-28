---
title: Naming
description: The three naming styles, how a logical name is a real table name without the environment, and what to do when none of them fits.
---

Your SQL reads a table by its logical name: its real name without the environment. Nimblestax adds the environment for each place it deploys. The naming style in `nimblestax.platform.yaml` says where tables live, and so how you write their names.

```yaml
naming:
  style: layer-catalogs
  layers:
    models: [gold]
```

`nsx init` asks for the style and writes it here. Pressing Enter takes `system-and-domain-catalogs`.

## The three styles

Each style is named for what its catalogs are. The sales domain's silver `orders`:

| Style | Each catalog is | Real name in prod | Logical name |
| --- | --- | --- | --- |
| `layer-catalogs` | a layer | `prod_silver.sales.orders` | `silver.sales.orders` |
| `system-and-domain-catalogs` | a domain | `prod_sales.silver.orders` | `sales.silver.orders` |
| `environment-catalogs` | an environment | `prod.sales_silver.orders` | `sales_silver.orders` |

- `layer-catalogs` gives each layer its own catalog in each environment, with a schema per domain. It's the medallion layout most Databricks teams know, and the number of catalogs grows only with layers, never with domains. One grant on the bronze catalog keeps raw data from analysts.
- `system-and-domain-catalogs` gives each domain its own catalog in each environment, with a schema per layer. It suits teams that fence each domain at catalog level, with its own owner, workspace binding or storage. Nimblestax 0.1.0 called it `domain-catalogs`, and a `nimblestax.platform.yaml` that says `domain-catalogs` is read as `system-and-domain-catalogs`.
- `environment-catalogs` puts each environment in one catalog, with a schema for each domain and layer. It has the fewest catalogs, so it suits a workspace where you can create only a few.

Every style works with one workspace for all environments, or one workspace per environment. The environment is always part of the catalog name, so environments sharing a workspace never share a table.

On one workspace, the production environment is kept apart from the others by its catalogs, each environment's CI identity and their grants. See [Environments](environments.md#one-shared-workspace).

## How a logical name resolves

A logical name is what Catalog Explorer shows, minus the `prod_` or `dev_`. Under `environment-catalogs`, the whole catalog is the environment, so a logical name has two parts.

The SQL is the same in every environment. Only the real name changes. With `layer-catalogs`, `silver.sales.orders` is:

| Environment | Real table |
| --- | --- |
| `dev` | `dev_silver.sales.orders` |
| `test` | `test_silver.sales.orders` |
| `prod` | `prod_silver.sales.orders` |

Each domain and layer pair gets its own catalog and schema. A gold model in the same project, `gold.sales.fct_orders`, is `prod_gold.sales.fct_orders` in prod, and a finance source, `silver.finance.invoices`, is `prod_silver.finance.invoices`.

A name written in another style's shape fails `nsx validate` with [`NSX214`](../reference/rules/nsx214.md), which gives the name to write. So does a real name, with [`NSX205`](../reference/rules/nsx205.md).

Under `layer-catalogs` and `system-and-domain-catalogs`, no catalog is called `silver` or `sales`, so a logical name run by hand in a notebook fails rather than reading data. Under `environment-catalogs`, `sales_silver.orders` run by hand reads the session's current catalog.

`nsx init` prints every catalog and schema your project needs, so you can create them before your first deploy. Nimblestax never creates them. `nsx compile --env prod` shows the real names in the code it generates.

`nsx validate --platform` signs in to an environment's workspace and checks that its catalogs and schemas are there, so a missing one fails before a deploy rather than halfway through one. It checks the default environment, or the one `--env` names:

```console
$ nsx validate --platform --env dev
NSX302 nimblestax.platform.yaml: The schema `dev_sales.silver` isn't in dev's workspace, https://kettle.cloud.databricks.com, or the identity Nimblestax signed in as can't see it. The project's tables in dev need it.
  Fix: Create the schema `silver` in the catalog `dev_sales`, or grant the identity `USE SCHEMA` on it. Nimblestax never creates schemas.
```

It checks one environment at a time, because each CI job signs in as one environment's identity. The workflows `nsx init --ci github` writes run it as dev, before anything else. Plain `nsx validate` reads no workspace.

## Changing the style

Before your first deploy, change the style by editing that one word. Every logical name in your SQL changes shape with it, and `nsx validate` names the new spelling of each one.

> **Warning**
> After a deploy, a new style gives every table a new catalog or schema. The next deploy creates empty tables there and leaves the old ones where they are. Nimblestax doesn't stop this yet, so don't change the style of a deployed project.

## When none of these fit

You name the environments, the domains and the model layers yourself, so most conventions fit one of the styles. A prefix is part of the name you choose. If your catalogs start with `acme_prod`, name the environment `acme_prod`, and `layer-catalogs` gives `acme_prod_silver.sales.orders`. For now, the environment you develop in must still be called `dev`.

Nimblestax fixes two things:

- **The environment comes first.** Catalogs then sort by environment, so when you review grants, everything in prod sits together.
- **Every environment, domain and layer gets its own catalog and schema.** Grants, expectations and quarantine all apply per schema, so two domains or two layers in one schema would share them. Two environments in one schema would write to the same tables, so a change in dev would reach prod.

Patterns of your own, set as `catalog` and `schema`, aren't supported yet. A version 1 `nimblestax.platform.yaml` with patterns that match a style is read as that style. Patterns that match none fail with [`NSX124`](../reference/rules/nsx124.md), which names the closest style.

If your convention still doesn't fit, [open an issue on nimblestax](https://github.com/nimblestax/core/issues/new) with the catalog and schema names you use. Real names help decide what custom patterns must allow.
