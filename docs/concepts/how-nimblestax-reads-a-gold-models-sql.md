---
title: How Nimblestax reads a gold model's SQL
description: How Nimblestax finds the tables a gold model reads, why `STREAM(...)` makes it a streaming table, what a stream may read, and the SQL Nimblestax can't read yet.
---

A gold model is a SQL file. Nimblestax parses it to find every table it reads, and everything else follows from those reads: the real table names in each environment, which pipelines wait for which, and what `nsx validate` checks.

## Reads are logical names, found by parsing

A gold model reads tables by their logical name: the table's real name without the environment, so its shape follows the [naming style](naming.md). Under `layer-catalogs`, it has three parts: the layer, the domain and the table.

```sql
SELECT o.order_id, o.amount, c.vat_rate
FROM silver.sales.orders AS o
JOIN silver.sales.countries AS c
  ON o.country = c.code
```

Nimblestax parses the query and takes each table it reads, in `FROM`, `JOIN` and subqueries. A CTE's name isn't a table, so it isn't a read. Nimblestax never guesses. Anything that might read a table but isn't a logical name fails `nsx validate`:

- a name that isn't a CTE or a table in the project fails with [`NSX201`](../reference/rules/nsx201.md)
- a real table name, such as `prod_silver.sales.orders`, fails with [`NSX205`](../reference/rules/nsx205.md)
- a logical name in another naming style's shape, such as `sales.silver.orders` under `layer-catalogs`, fails with [`NSX214`](../reference/rules/nsx214.md)
- a name built as the query runs, such as `IDENTIFIER(...)`, fails with [`NSX204`](../reference/rules/nsx204.md)
- a read of files, such as `read_files(...)`, fails with [`NSX206`](../reference/rules/nsx206.md)
- SQL Nimblestax can't parse fails with [`NSX203`](../reference/rules/nsx203.md)

So every table a gold model reads shows in review, and the same SQL works in every environment.

## `STREAM(...)` makes a streaming table

A gold model that reads any table with `STREAM(...)` compiles to a streaming table. Any other gold model compiles to a materialized view. The SQL decides, and there's no setting for it.

```sql
SELECT order_id, amount
FROM STREAM(silver.sales.orders)
```

```sql
CREATE OR REFRESH STREAMING TABLE dev_gold.sales.fct_orders AS
SELECT order_id, amount
FROM STREAM(dev_silver.sales.orders)
```

A streaming table reads only the rows added since its last update. A materialized view reads its whole query each time, and Databricks refreshes it incrementally where it can.

A query that joins a stream to a table read without `STREAM(...)`, such as `STREAM(silver.sales.orders) JOIN silver.sales.countries`, is a streaming table too. Each new order is joined to the countries as they are when it arrives.

## What a stream may read

A stream reads only new rows, so it may read only a table that rows are added to and never changed in place.

| A gold model may stream from | It may not stream from |
| --- | --- |
| silver without `keys` | silver with `keys`, which upserts change in place: [`NSX211`](../reference/rules/nsx211.md) |
| a quarantine table | a seed, which is a materialized view: [`NSX212`](../reference/rules/nsx212.md) |
| a gold model that streams | a gold model that doesn't stream, which is a materialized view: [`NSX212`](../reference/rules/nsx212.md) |

Each of these would otherwise fail in the pipeline, after a deploy. `nsx validate` catches them before.

## Known gaps

Databricks accepts some SQL that Nimblestax can't parse yet. Each of these fails `nsx validate`, so none reaches a deploy.

- **`WATERMARK ... DELAY OF`** fails with [`NSX203`](../reference/rules/nsx203.md). A gold model can't do a watermarked streaming aggregation for now.
- **`STREAM x` without brackets**, as in `JOIN STREAM silver.sales.orders`, fails with [`NSX203`](../reference/rules/nsx203.md). Write `STREAM(silver.sales.orders)`.
- **`window(...)` as a table function** fails with [`NSX206`](../reference/rules/nsx206.md), because Nimblestax can't see what it reads.
