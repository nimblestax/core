---
title: Rules
description: Every Rule Nimblestax checks, by series, with what each one checks.
generated: true
nimblestax_version: 0.1.0
---

A Rule's ID is `NSTX` plus three digits, and its first digit is its series. Each Rule's page says what it checks, why, an example that fails and the fix.

## `NSTX1xx` Config files

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSTX101`](nstx101.md) | `missing-kind` | A config file has no `kind`. |
| [`NSTX102`](nstx102.md) | `unknown-kind` | A `kind` isn't one Nimblestax knows. |
| [`NSTX103`](nstx103.md) | `missing-version` | A config file has no `version`. |
| [`NSTX104`](nstx104.md) | `unknown-version` | This Nimblestax doesn't support that `version`. |
| [`NSTX105`](nstx105.md) | `wrong-kind` | A file's `kind` doesn't belong in its location. |
| [`NSTX106`](nstx106.md) | `invalid-field` | A field doesn't match its Kind's schema. |
| [`NSTX107`](nstx107.md) | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file isn't valid CSV. |
| [`NSTX108`](nstx108.md) | `sql-without-config` | A SQL file has no config file beside it. |
| [`NSTX109`](nstx109.md) | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| [`NSTX110`](nstx110.md) | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| [`NSTX111`](nstx111.md) | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| [`NSTX112`](nstx112.md) | `missing-seed-file` | A Seed's `file` doesn't exist beside it. |
| [`NSTX113`](nstx113.md) | `seed-header-mismatch` | The first line of a Seed's file doesn't name each declared column once. |
| [`NSTX114`](nstx114.md) | `seed-row-mismatch` | A row of a Seed's file has the wrong number of values, or a value that doesn't fit its column's type. |
| [`NSTX115`](nstx115.md) | `unsupported-seed-type` | A Seed's column has a type Nimblestax can't check values against. |
| [`NSTX116`](nstx116.md) | `invalid-expectation` | An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`NSTX117`](nstx117.md) | `invalid-name` | A config file's name isn't an identifier, so the table named after it can't be written in SQL: it must hold only letters, digits and underscores, and not start with a digit. |
| [`NSTX118`](nstx118.md) | `invalid-delete-when` | A Source's `silver.delete_when` isn't one SQL condition on one row, for the same reasons as `NSTX116`. |
| [`NSTX119`](nstx119.md) | `invalid-sequence-by` | A Source's `silver.sequence_by` isn't one SQL expression on one row, such as `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`NSTX120`](nstx120.md) | `duplicate-config-file` | Two config files share a name in one Domain's Layer: in one folder, such as `orders.yaml` and `orders.yml`, or in two folders, such as `sources/erp/orders.yaml` and `sources/crm/orders.yaml`. Nimblestax reads either ending, and writes `.yaml`. |
| [`NSTX121`](nstx121.md) | `unlisted-domain-folder` | A folder under `domains/` isn't listed in `domains` in `nimblestax.platform.yaml`, in the same case, so nothing in it is validated or deployed. |
| [`NSTX122`](nstx122.md) | `dev-host-missing` | `nimblestax.platform.yaml` has no `host` on the Development Environment. In a version 1 file, which knows Environments by name, it has no `host` on `dev`. |
| [`NSTX123`](nstx123.md) | `two-default-environments` | More than one Environment in `nimblestax.platform.yaml` sets `default: true`. |
| [`NSTX124`](nstx124.md) | `naming-patterns-not-supported` | `nimblestax.platform.yaml` sets `catalog` and `schema` patterns that aren't a Naming Style, or sets any patterns at version 2, which takes only `naming.style`. |
| [`NSTX125`](nstx125.md) | `source-layers-fixed` | A version 1 `nimblestax.platform.yaml` lists source Layers other than `[bronze, silver]`. |
| [`NSTX126`](nstx126.md) | `model-layer-named-like-a-source-layer` | A model Layer in `naming.layers.models` is called `bronze` or `silver`, in any case. |
| [`NSTX127`](nstx127.md) | `model-outside-a-layer` | A file sits directly in a Domain's `models/` folder, or in a first folder under it that isn't a model Layer in `naming.layers.models`. |
| [`NSTX129`](nstx129.md) | `skill-version-drift` | A Nimblestax Skill in `.agents/skills/` or `.claude/skills/` was written by another version of Nimblestax than the one installed. |
| [`NSTX130`](nstx130.md) | `no-development-environment` | No Environment in `nimblestax.platform.yaml` sets `role: development`. |
| [`NSTX131`](nstx131.md) | `two-environments-with-one-role` | More than one Environment in `nimblestax.platform.yaml` sets the same `role`. |
| [`NSTX132`](nstx132.md) | `environment-name-not-an-identifier` | An Environment's name in `nimblestax.platform.yaml` isn't an identifier: letters, digits and underscores, starting with a letter or underscore. |
| [`NSTX133`](nstx133.md) | `reserved-environment-name` | An Environment is named `preview`. |

## `NSTX2xx` SQL and reads between tables

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSTX201`](nstx201.md) | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| [`NSTX202`](nstx202.md) | `duplicate-table` | A Seed and a Source in one Domain share a name, so they would be one table. |
| [`NSTX203`](nstx203.md) | `unparseable-sql` | A Gold Model's SQL doesn't parse as one Databricks SQL query. |
| [`NSTX204`](nstx204.md) | `computed-table-name` | SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Nimblestax can't see what it reads. |
| [`NSTX205`](nstx205.md) | `real-table-name` | SQL reads a real table name, which names one Environment, instead of its Logical Name. |
| [`NSTX206`](nstx206.md) | `file-read` | A Gold Model reads files or external data, such as `read_files(...)` or ``parquet.`/path` ``, instead of a table. |
| [`NSTX207`](nstx207.md) | `raw-string-placeholder` | A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`. |
| [`NSTX208`](nstx208.md) | `model-cycle` | Gold Models read themselves, or each other in a loop, so none of them can run first. |
| [`NSTX209`](nstx209.md) | `cross-domain-read` | A Gold Model reads another Domain's gold, or silver that Domain hasn't Exported. |
| [`NSTX210`](nstx210.md) | `read-against-build-order` | A Gold Model reads bronze. |
| [`NSTX211`](nstx211.md) | `stream-of-upsert-silver` | A Gold Model reads silver that has `keys` with `STREAM(...)`. |
| [`NSTX212`](nstx212.md) | `stream-of-materialized-view` | A Gold Model reads a Seed, or a Gold Model that doesn't stream, with `STREAM(...)`. |
| [`NSTX213`](nstx213.md) | `test-references-unknown-table` | A `references` Test names a table that isn't in the project. |

## `NSTX3xx` The workspace a project deploys to

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSTX301`](nstx301.md) | `missing-catalog` | With `--platform`, a catalog the project's tables need isn't in the Environment's workspace, or the identity Nimblestax signs in as can't see it. |
| [`NSTX302`](nstx302.md) | `missing-schema` | With `--platform`, a schema the project's tables need isn't in its catalog in the Environment's workspace, or the identity Nimblestax signs in as can't see it. |
| [`NSTX303`](nstx303.md) | `developer-group-missing-grant` | With `--platform` on the Development Environment, the group `developers` names lacks `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` or `READ VOLUME` on one of its catalogs. |

## `NSTX4xx` Tests on a Preview Environment's tables

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSTX401`](nstx401.md) | `test-failed` | A Gold Model's Test failed on its table in your Preview Environment. |
| [`NSTX402`](nstx402.md) | `test-could-not-run` | The SQL warehouse refused a Test's query. |

## `NSTX9xx` The command line and running against Databricks

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSTX901`](nstx901.md) | `usage-error` | The command line is wrong. |
| [`NSTX902`](nstx902.md) | `unknown-environment` | `--env` isn't an Environment in the project. |
| [`NSTX903`](nstx903.md) | `databricks-cli-missing` | `NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI that Nimblestax can't run. |
| [`NSTX904`](nstx904.md) | `databricks-command-failed` | A Databricks CLI command failed. |
| [`NSTX905`](nstx905.md) | `unexpected-error` | Nimblestax stopped on something it didn't expect, with a traceback on stderr. |
| [`NSTX906`](nstx906.md) | `pipeline-column-not-found` | The refresh failed because a pipeline names a column its table doesn't have, often an Expectation on a column bronze doesn't have yet. |
| [`NSTX907`](nstx907.md) | `expectation-failed` | The refresh failed because a row broke an Expectation whose `action` is `fail`. |
| [`NSTX908`](nstx908.md) | `pipeline-failed` | The refresh failed with another pipeline error. The message is the pipeline's own. |
| [`NSTX909`](nstx909.md) | `project-already-exists` | `nstx init` was run in a folder that already holds `nimblestax.platform.yaml`. |
| [`NSTX910`](nstx910.md) | `databricks-cli-checksum-mismatch` | The Databricks CLI Nimblestax downloaded doesn't match the checksum its release names. |
| [`NSTX911`](nstx911.md) | `databricks-cli-unsupported` | `NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI older than this Nimblestax supports. |
| [`NSTX912`](nstx912.md) | `databricks-cli-download-failed` | Nimblestax couldn't download its Databricks CLI. |
| [`NSTX913`](nstx913.md) | `no-databricks-cli-for-platform` | Databricks publishes no CLI for this operating system and architecture. |
| [`NSTX914`](nstx914.md) | `skills-folder-ignored` | `nstx init` wrote Nimblestax Skills into a folder Git ignores, such as `.claude/`. |
| [`NSTX915`](nstx915.md) | `skill-edited` | `nstx skills update` found a Nimblestax Skill edited since Nimblestax wrote it. |
| [`NSTX916`](nstx916.md) | `unknown-example` | `nstx init --example` names an example Nimblestax doesn't ship. |
| [`NSTX917`](nstx917.md) | `not-a-build-package` | `nstx deploy --package` names a folder that isn't a Build Package. |
| [`NSTX918`](nstx918.md) | `build-package-changed` | A file in the Build Package `nstx deploy --package` was given differs from what was built. |
| [`NSTX919`](nstx919.md) | `manifest-copies-not-removed` | A deploy succeeded, but old copies of the Deployment Manifest couldn't be removed. |
| [`NSTX920`](nstx920.md) | `preview-schema-taken` | `nstx preview` would deploy into a schema that another project, another person, or someone by hand already created. |
| [`NSTX921`](nstx921.md) | `example-has-no-preview` | `nstx preview`, or `nstx test`, was run in an example project, such as Kettle. |
| [`NSTX922`](nstx922.md) | `preview-down-outside-fence` | `nstx preview down` found a schema in the preview's bundle state outside your `u_<user>__` schemas, or outside the Development Environment's catalogs. |
| [`NSTX923`](nstx923.md) | `no-warehouse-for-tests` | `nstx test` can't tell which SQL warehouse to run Tests on. |
| [`NSTX924`](nstx924.md) | `no-preview-to-test` | `nstx test` found no Preview Environment of this project to run Tests on. |
| [`NSTX925`](nstx925.md) | `no-databricks-sql-access` | The identity `nstx test` runs as isn't allowed to use Databricks SQL. |
| [`NSTX926`](nstx926.md) | `no-such-model` | `--model` names no Gold Model in the project, or a name more than one Gold Model has. |
