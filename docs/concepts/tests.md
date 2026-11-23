---
title: Tests
description: The rules a gold model's whole table is checked against, where they run, and how they differ from expectations.
---

A test is a rule about a gold model's whole table, such as no two rows sharing an `order_id`. You declare a gold model's tests beside its SQL, with its `owner`, the team or person who answers for the table. `nstx test` runs them on a preview environment's tables.

A test is not an [expectation](expectations.md). An expectation checks one row as it's written to silver, on every refresh. A test checks a whole table once it's built, before your change merges. [Tests and expectations](#tests-and-expectations) sets them side by side.

In Kettle, the tea shop that `nstx init --example kettle` writes, finance's daily revenue has one row per day and region, every region is one the shop knows, and the table is never empty:

```yaml title="domains/finance/models/gold/fct_revenue.yaml"
# yaml-language-server: $schema=../../../../.nimblestax/schemas/model.v1.json
kind: model
version: 1
sql: fct_revenue.sql
owner: finance-analytics
tests:
  - unique: [date_day, region_code]
  - references:
      column: region_code
      to: sales.silver.regions
  - row_count: {}
```

Every gold model has an `owner`. A gold model without one fails `nstx validate` with [`NSTX134`](../reference/rules/nstx134.md).

## What each test checks

| Test | Passes when |
| --- | --- |
| `unique: [<column>, ...]` | No two rows share a value of these columns. A row with a NULL in any of them is skipped. |
| `row_count: {min: <n>, max: <n>}` | The table has at least `min` rows and at most `max`. `min` is 1 when you leave it out, and `max` has no limit, so `row_count: {}` checks the table isn't empty. |
| `references: {column: <column>, to: <table>}` | Every value of `column` is in the table `to`, a logical name such as `sales.silver.regions`. Its column has the same name unless you give `key`. A NULL is skipped. |

`nstx test` says on stderr when each test starts and how it ended, so `--json` output on stdout stays one envelope. A test fails with [`NSTX401`](../reference/rules/nstx401.md), which names the test and the table and shows up to five values that broke it. A test the warehouse can't run, such as one naming a column the table doesn't have, fails with [`NSTX402`](../reference/rules/nstx402.md). The other tests still run.

## Where tests run

Tests run on the tables your [preview environment](preview-environments.md) built, so you deploy it first:

```sh
nstx preview
nstx test
```

```text
Running 2 Tests on your Preview Environment (u_priya__), on warehouse 4b9b953939869799, 4 at a time.
  started      sales.gold.fct_orders: unique(order_id)
  started      sales.gold.fct_orders: row_count(min: 1)
  passed       sales.gold.fct_orders: row_count(min: 1)  (1/2)
  failed       sales.gold.fct_orders: unique(order_id)  (2/2)
NSTX401 domains/sales/models/gold/fct_orders.yaml: `unique(order_id)` failed on `sales.gold.fct_orders`: 2 values appear in more than one row, such as {"order_id":1001}, {"order_id":1002}.
  Fix: Fix the model's SQL or the data it reads, or correct the Test, then run `nstx preview` and `nstx test` again.
```

To run only some gold models' tests, name each one with `--model`, by its name or, when two domains share the name, its logical name:

```sh
nstx test --model fct_orders --model finance.gold.fct_revenue
```

A preview builds every table from all of dev's rows, so a test sees the data it would see in dev. No test fails only because it ran on a preview. A `references` test reads the preview's own copy of the other table, so a new row your change adds there counts. Kettle runs in catalogs of its own and has no preview, so you run `nstx test` in your own project.

On a pull request, the GitHub workflow runs `nstx test --pr <N>` right after `nstx preview --pr <N>`, in the same job, so a failed test fails the pull request's checks.

Each test is one SQL query on a warehouse in the development environment's workspace. Nimblestax uses the warehouse that `warehouse` names under the development environment in `nimblestax.platform.yaml`. When you leave it out and you can see only one warehouse, Nimblestax uses that one. Whoever runs `nstx test`, you or CI's identity, needs the `databricks-sql-access` entitlement and `CAN USE` on that warehouse. Without the entitlement, `nstx test` stops with [`NSTX925`](../reference/rules/nstx925.md). Tests run 4 at a time. Set how many in `nimblestax.platform.yaml`:

```yaml
tests:
  concurrency: 8
```

`1` runs them one after another. A warehouse queues the queries it can't run yet, so a number above what it handles only waits.

Tests don't run after a refresh in test or prod yet.

## Tests and expectations

An [expectation](expectations.md) and a test both guard data, at different points.

| | Expectation | Test |
| --- | --- | --- |
| Checks | One row at a time | The whole table |
| Declared on | A source's silver | A gold model |
| Runs | In the pipeline, as each row is written to silver | In `nstx test`, on a preview's tables |
| When it fails | The row goes to quarantine, is counted, or stops the update | `nstx test` exits 1, and a pull request's checks fail |

A rule that needs more than one row, such as uniqueness or a row count, can't be an expectation. It is a test.
