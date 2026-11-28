---
title: The plan
description: What the plan on a pull request shows, how to read one, and why it compares with dev.
---

The plan shows what a pull request changes in your tables. CI posts it on the pull request, so a reviewer reads what will change without reading generated code. It runs `nsx plan`, which compares the project with dev's [deployment manifest](deployment-manifests.md), the record of what dev last received. It uses dev unless another [environment](environments.md) sets `default: true`. To compare with a different one, pass `--env`, such as `nsx plan --env prod`.

In Kettle, Priya adds an `order_hour` column to `fct_orders`, and a new gold model, `daily_sales`, that totals each day's orders. Her pull request's plan is:

```console
$ nsx plan
## Plan against dev

Compared with what dev last received: commit `1c3e51b`, deployed 2026-11-28T01:28:25Z.

2 safe, 0 refresh, 0 destructive.

| Class | Action | Table | What changes |
| --- | --- | --- | --- |
| safe | create | `sales.gold.daily_sales` | A new materialized view. |
| safe | update | `sales.gold.fct_orders` | Adds the column `order_hour`. |

---

Nimblestax 0.1.0 · [changelog](https://github.com/nimblestax/core/blob/main/docs/changelog.md#010)
```

It prints Markdown, which reads the same in a terminal and as a comment.

## Reading a plan

Each row is one change to one table, most at risk first.

- **Class** says what is at risk. A safe change loses nothing. The plan also counts refresh changes, which rebuild the tables they name, and destructive ones, which remove data or history from a table.
- **Action** is `create` for a table dev doesn't have yet, and `update` for one it has.
- **Table** is the table's logical name.
- **What changes** says what changed, in words.

The plan classes two kinds of change, and both are safe:

- **A new table.** A new source, seed or gold model is a `create`. So is each table in a domain or model layer you add.
- **New columns on a gold model.** A gold model that only gains columns is an `update`. Every other column keeps the expression it had, and the rest of its SQL is the same. Nimblestax reads the columns from your SQL, so this needs each column named: a model that selects `*` changes in a way the plan doesn't class.

A new column on a materialized view needs no warning. A materialized view is recomputed from what it reads, so the new column has a value in every row, old rows included. A gold model is a materialized view unless it reads `STREAM(...)`.

Only tables appear. Catalogs, schemas and their grants belong to your team, so the plan never lists them. The Jobs and pipelines Nimblestax generates don't appear either.

## Changes the plan doesn't class yet

Any other change to a table isn't listed as a change: a changed filter or join, a changed or dropped column, a changed source or seed, or a removed gold model. The plan warns with [`NSX501`](../reference/rules/nsx501.md) instead, naming the table, so a change is never shown as safe when it might not be. When Kettle's finance team stops counting refunds in `fct_revenue`, the plan adds:

```text
[**NSX501**](https://github.com/nimblestax/core/blob/main/docs/reference/rules/nsx501.md) (warning): finance.gold.fct_revenue changed in a way the Plan doesn't class yet, so it isn't listed as a change. Read the change to finance.gold.fct_revenue's config or SQL in the pull request before you approve it.
```

Read that table's change in the pull request before you approve it.

## Why the plan compares with dev

A merge deploys to dev, and only CI deploys there, so dev holds what `main` holds. Comparing with dev shows only this pull request's change, not everything that has merged since prod last moved.

Dev's deployment manifest sits in dev's workspace, and pull request jobs already sign in as dev's deploying identity. So the plan never needs test's or prod's credentials, and a project with only dev can run one.

## On a pull request

The GitHub pull request workflow has a `plan` job. It runs `nsx plan --env dev` as dev's deploying identity and posts what it prints as a comment. It names dev, so marking another environment `default: true` never changes what a pull request is compared with. Each push edits that comment, so a pull request has one plan, and it is always the latest. The comment ends with the version of Nimblestax that wrote it, linking that version's changelog.

The job asks for `pull-requests: write`, so it can comment.

## When there's nothing to compare with

Before dev's first deploy, it has no manifest. The plan shows every table as a `create` and warns with [`NSX502`](../reference/rules/nsx502.md), because some may exist already.

The plan reads dev's manifest from the deploying identity's bundle folder. If you run `nsx plan` signed in as yourself, it looks in your own folder instead, finds no manifest, and warns with `NSX502`. The plan that counts is the one CI posts.

A manifest written by an earlier version of Nimblestax doesn't record how each table is made. The plan lists only new tables, and warns with [`NSX503`](../reference/rules/nsx503.md), until dev's next deploy.

## For scripts and agents

`nsx plan --json` prints the same plan as data, with `changes`, a `summary` by class, and `blocked`. Each change has a stable `id`, such as `update:sales.gold.fct_orders`. [`nsx plan`](../reference/commands/plan.md) lists every field.
