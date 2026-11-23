---
title: Changelog
description: What changed in each release of Nimblestax, newest first.
---

Every release of Nimblestax, newest first. Each section is also that release's notes on GitHub.

Each pull request that changes what you see adds its line under Unreleased, so each release's section is built up by its pull requests. A release renames Unreleased to its version.

Nimblestax follows [Semantic Versioning](https://semver.org). Before 1.0, a minor release, such as 0.2.0, may change config or commands in ways that need edits to your project, and its section here says what to change. A patch release, such as 0.2.1, never does.

## Unreleased

- Every gold model has an `owner`, the team or person who answers for its table, and a gold model without one fails `nstx validate` with [`NSTX134`](reference/rules/nstx134.md). Add `owner: <team>` to each gold model's YAML file, such as `owner: sales-analytics`.
- A gold model can declare `tests`: `unique`, `row_count` and `references`. [`nstx test`](reference/commands/test.md) runs them through a SQL warehouse on your preview environment's tables, or with `--pr <N>` on a pull request's, lists each one as it runs, and exits 1 when one fails. It runs on the warehouse `warehouse` names under the development environment in `nimblestax.platform.yaml`, or on the only one you can see. The GitHub pull request workflow runs `nstx test --pr <N>` after its preview deploys. Run `nstx init --ci github` in a new folder and copy `.github/workflows/nimblestax-pull-request.yaml` over yours to pick this up. See [Tests](concepts/tests.md).
- [`nstx preview`](reference/commands/preview.md) deploys your working tree to your own preview environment, in `u_<you>__` schemas in the development environment's catalogs, with your own login, and builds every table. `nstx preview down` removes it. `nimblestax.platform.yaml` can name your team's `developers` group, and `nstx validate --platform` checks it holds the grants a preview needs. No environment can be named `preview`. See [Preview environments](concepts/preview-environments.md).
- `nstx preview --pr <N>` deploys a pull request's preview, in `pr<N>__` schemas in the development environment's catalogs, with its bundle state under the deploying identity's `.bundle/<project>/pull-requests/<N>` folder. `nstx preview down --pr <N>` removes it. The GitHub pull request workflow gains a `preview` job that runs it as dev's identity, which needs `CREATE SCHEMA` on the development environment's catalogs. Run `nstx init --ci github` in a new folder and copy `.github/workflows/nimblestax-pull-request.yaml` over yours to pick this up. See [Preview environments](concepts/preview-environments.md#pull-request-previews).
- [`nstx compile`](reference/commands/compile.md) writes a build package: the generated code, every environment's settings, and `nimblestax.package.json`, which records the commit, the Nimblestax version and a checksum of each file. See [Build packages](concepts/build-packages.md).
- [`nstx deploy --package`](reference/commands/deploy.md) deploys the build package it is given, as it is, and never rebuilds it. A package changed since it was built is refused with [`NSTX918`](reference/rules/nstx918.md), and a folder that isn't one with [`NSTX917`](reference/rules/nstx917.md). With `--json`, the result adds `commit` and `package_checksum`.
- Each successful `nstx deploy` writes a deployment manifest into the environment's workspace, next to the bundle: `nimblestax/manifest.json`, plus a copy per commit, keeping the newest 100. A failed deploy writes none. `nstx preview` writes one too, in your preview's own bundle folder, and `nstx preview down` removes it. See [Deployment manifests](concepts/deployment-manifests.md).
- The GitHub merge workflow builds one package in a `package` job and deploys it to dev with `nstx deploy --env dev --package build`. Run `nstx init --ci github` in a new folder and copy `.github/workflows/nimblestax-merge.yaml` over yours to pick this up.

## 0.1.0

The first release. Install it into your project with `uv add --dev nimblestax`, which gives you the `nstx` command and `nimblestax`, its long form.

- [`nstx init`](reference/commands/init.md) creates a project folder and asks where your tables live: `domain-catalogs` (`dev_sales.silver.orders`, the default), `layer-catalogs` (`dev_silver.sales.orders`) or `environment-catalogs` (`dev.sales_silver.orders`). `nimblestax.platform.yaml` keeps that choice as `naming.style`. See [Naming](concepts/naming.md).
  - It refuses a folder that already holds `nimblestax.platform.yaml`, with [`NSTX909`](reference/rules/nstx909.md), and writes nothing.
  - `--ci github` adds GitHub Actions workflows, `.github/workflows/nimblestax-pull-request.yaml` and `.github/workflows/nimblestax-merge.yaml`. They install `nimblestax` at the version `NIMBLESTAX_SPEC` names.
  - It lists the Volumes the project's sources read in dev, with the catalogs and schemas to create.
  - `--example kettle` writes Kettle, the fictional tea shop every docs page draws its examples from, with two days of sample data and the commands that upload day 1.
- Environments are named freely and carry a role: `role: development` on exactly one, and `role: production` on at most one. Any other environment is a stage. Commands that read default to the development environment, and an environment without a `host` uses its host. See [Environments](concepts/environments.md).
- [`nstx validate`](reference/commands/validate.md) checks config and SQL with no workspace. A gold model's dependencies come from its SQL, and anything Nimblestax can't read, such as `IDENTIFIER(...)`, is an error rather than a guess.
  - Tables are read in build order. A gold model reads silver, a gold model in its own domain, another domain's exported silver, or gold in the shared domain. See [Domains and layers](concepts/domains-and-layers.md).
  - Model layers have no order, and a gold model's folder sets its layer. A loop of reads across model layers fails.
  - `--platform` signs in to an environment's workspace and checks that the catalogs and schemas the project needs are there.
  - It warns when a skill was written by another Nimblestax version.
- [`nstx compile`](reference/commands/compile.md) writes the generated code, or prints it for one environment. A gold model that reads `STREAM(...)` compiles to a streaming table, and any other gold model to a materialized view. See [How Nimblestax reads a gold model's SQL](concepts/how-nimblestax-reads-a-gold-models-sql.md).
- [`nstx deploy`](reference/commands/deploy.md) deploys to the environment `--env` names and refreshes its tables. When a refresh fails, it says why. See [Recover from a failed refresh](guides/recover-from-a-failed-refresh.md).
  - Each environment has one Job, named for it, such as `kettle_dev_refresh`. It waits only where one pipeline reads another's tables, so a failed pipeline skips only what reads from it.
  - An environment can refresh on a schedule. A schedule runs in the production environment and is paused elsewhere. See [Schedule refreshes](guides/schedule-refreshes.md).
- [`nstx schema`](reference/commands/schema.md) prints any Kind's fields.
- A source lands in bronze, and silver either appends it or upserts it by `keys` and `sequence_by`, with Type 1 or Type 2 history and `delete_when` for deletes.
- Seeds load small reference tables from CSV files in the repo.
- Expectations check silver rows, and rows that fail are kept in quarantine. See [Expectations](concepts/expectations.md).
- Nimblestax brings its own Databricks CLI, version 1.23.0, and never runs the `databricks` on your PATH. [`nstx databricks`](reference/commands/databricks.md) runs it, and `NIMBLESTAX_DATABRICKS_CLI` points Nimblestax at one you installed yourself. See [The Databricks CLI](concepts/the-databricks-cli.md).
- `nstx init` writes Nimblestax skills for coding agents, `nimblestax-add-source` and `nimblestax-add-model`, into `.agents/skills/` and `.claude/skills/`. [`nstx skills update`](reference/commands/skills.md#update) refreshes them. See [Nimblestax skills](concepts/nimblestax-skills.md).
- Every command but `nstx databricks` has `--json` output, with Rule IDs and fixed exit codes. See [JSON output](reference/json-output.md).
- Every Rule has its own reference page, listed in the [Rules index](reference/rules/index.md).
