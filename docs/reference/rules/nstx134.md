---
title: NSTX134 model-without-owner
description: A Gold Model has no `owner`.
generated: true
nimblestax_version: 0.1.0
---

## What it checks

A Gold Model has no `owner`.

## Why

Every Gold Model has someone who answers for it: who to ask when a Test fails, or before changing what it means. `owner` names that team or person beside the SQL, so it's reviewed with the model and never goes stale in a separate list.

## Example

Write these files into the project `nstx init` creates, and `nstx validate` fails:

`domains/sales/models/gold/fct_returns.yaml`:

```yaml
kind: model
version: 1
sql: fct_returns.sql
```

`domains/sales/models/gold/fct_returns.sql`:

```sql
SELECT order_id
FROM sales.silver.orders
```

## Fix

Add `owner` naming the team or person who answers for the table, such as `owner: sales-analytics`.
