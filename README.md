<h1 align=center>Nimblestax</h1>

<div align=center>
  <a href=https://github.com/nimblestax/core/actions/workflows/ci.yaml>
    <img src=https://github.com/nimblestax/core/actions/workflows/ci.yaml/badge.svg alt="build status">
  </a>
  <a href=LICENSE>
    <img src=https://img.shields.io/badge/license-Apache%202.0-blue.svg alt="Apache 2.0 license">
  </a>
</div>
<br>

Nimblestax brings the software development lifecycle to Databricks. Today it covers pipelines, from bronze to gold: config-driven, reviewed in pull requests, tested, and promoted from dev to prod. It grows to cover more of the platform.

**Status:** early development, and below 1.0, so a minor release may need edits to your project. Install it into your project with `uv add --dev nimblestax`, which gives you the `nsx` command and `nimblestax`, its long form. The Plan shown on [nimblestax.com](https://nimblestax.com) is illustrative: Nimblestax has no Plan command today.

A pipeline is YAML and SQL in your repo. A Source says where data lands:

```yaml
# domains/sales/sources/orders.yaml
kind: source
version: 1
path: /Volumes/{env}_sales/bronze/landing/orders
format: json
```

A Model is the SQL you'd write anyway, using Logical Names:

```sql
-- domains/sales/models/fct_orders.sql
SELECT order_id, amount
FROM sales.silver.orders
```

`sales.silver.orders` is a **Logical Name**, not a table you can query: it's the same in every Environment, and Nimblestax points it at the real table for each one. To run a Model by hand, use `nsx compile --env dev --model <name>`.

Nimblestax compiles that for each Environment:

```console
$ nsx compile --env dev
CREATE OR REFRESH STREAMING TABLE dev_sales.bronze.orders
TBLPROPERTIES ('pipelines.reset.allowed' = 'false')
AS SELECT *
FROM STREAM read_files('/Volumes/dev_sales/bronze/landing/orders', format => 'json');
...
CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.fct_orders AS
SELECT order_id, amount
FROM dev_sales.silver.orders
```

And it catches mistakes before anything touches a workspace:

```console
$ nsx validate
NSX201 domains/sales/models/fct_orders.sql: sales.silver.ordrs isn't a table in this project.
  Fix: Declare a Source or Gold Model with this name, or correct the Logical Name.
```

## What works today

- `nsx init` creates a working project, with GitHub Actions workflows.
- `nsx validate` checks config and SQL references with no workspace. A Model's dependencies come from its SQL, with no list to keep: CTEs, aliases and `STREAM(...)` just work, and anything Nimblestax can't read, such as `IDENTIFIER(...)`, is an error rather than a guess.
- `nsx compile` writes generated code, or prints it for one Environment. With `--model`, it prints one Model's query, ready to run.
- `nsx deploy` deploys to an Environment and refreshes its tables.
- `nsx schema` prints any Kind's fields.
- Every command has [`--json` output](docs/reference/json-output.md), rule IDs and fixed exit codes.

## The Nimblestax Way

Nimblestax is built around an opinionated way of building on Databricks. Read the principles at [nimblestax.com/way](https://nimblestax.com/way).

## Follow progress

Watch this repo's releases on GitHub.

## License

[Apache License 2.0](LICENSE). Contributions are accepted under the [Developer Certificate of Origin](https://developercertificate.org/): sign off each commit with `git commit -s`.
