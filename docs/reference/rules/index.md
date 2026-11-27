---
title: Rules
description: Every Rule Nimblestax checks, by series, with what each one checks.
generated: true
nimblestax_version: 0.1.0
---

A Rule's ID is `NSX` plus three digits, and its first digit is its series. Each Rule's page says what it checks, why, an example that fails and the fix.

## `NSX1xx` Config files

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSX101`](nsx101.md) | `missing-kind` | A config file has no `kind`. |
| [`NSX102`](nsx102.md) | `unknown-kind` | A `kind` isn't one Nimblestax knows. |
| [`NSX103`](nsx103.md) | `missing-version` | A config file has no `version`. |
| [`NSX104`](nsx104.md) | `unknown-version` | This Nimblestax doesn't support that `version`. |
| [`NSX105`](nsx105.md) | `wrong-kind` | A file's `kind` doesn't belong in its location. |
| [`NSX106`](nsx106.md) | `invalid-field` | A field doesn't match its Kind's schema. |
| [`NSX107`](nsx107.md) | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file isn't valid CSV. |
| [`NSX108`](nsx108.md) | `sql-without-config` | A SQL file has no config file beside it. |
| [`NSX109`](nsx109.md) | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| [`NSX110`](nsx110.md) | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| [`NSX111`](nsx111.md) | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| [`NSX112`](nsx112.md) | `missing-seed-file` | A Seed's `file` doesn't exist beside it. |
| [`NSX113`](nsx113.md) | `seed-header-mismatch` | The first line of a Seed's file doesn't name each declared column once. |
| [`NSX114`](nsx114.md) | `seed-row-mismatch` | A row of a Seed's file has the wrong number of values, or a value that doesn't fit its column's type. |
| [`NSX115`](nsx115.md) | `unsupported-seed-type` | A Seed's column has a type Nimblestax can't check values against. |
| [`NSX116`](nsx116.md) | `invalid-expectation` | An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`NSX117`](nsx117.md) | `invalid-name` | A config file's name isn't an identifier, so the table named after it can't be written in SQL: it must hold only letters, digits and underscores, and not start with a digit. |
| [`NSX118`](nsx118.md) | `invalid-delete-when` | A Source's `silver.delete_when` isn't one SQL condition on one row, for the same reasons as `NSX116`. |
| [`NSX119`](nsx119.md) | `invalid-sequence-by` | A Source's `silver.sequence_by` isn't one SQL expression on one row, such as `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`NSX120`](nsx120.md) | `duplicate-config-file` | Two config files share a name in one Domain's Layer: in one folder, such as `orders.yaml` and `orders.yml`, or in two folders, such as `sources/erp/orders.yaml` and `sources/crm/orders.yaml`. Nimblestax reads either ending, and writes `.yaml`. |
| [`NSX121`](nsx121.md) | `unlisted-domain-folder` | A folder under `domains/` isn't listed in `domains` in `nimblestax.platform.yaml`, in the same case, so nothing in it is validated or deployed. |
| [`NSX122`](nsx122.md) | `dev-host-missing` | `nimblestax.platform.yaml` has no `host` on the Development Environment. In a version 1 file, which knows Environments by name, it has no `host` on `dev`. |
| [`NSX123`](nsx123.md) | `two-default-environments` | More than one Environment in `nimblestax.platform.yaml` sets `default: true`. |
| [`NSX124`](nsx124.md) | `naming-patterns-not-supported` | `nimblestax.platform.yaml` sets `catalog` and `schema` patterns that aren't a Naming Style, or sets any patterns at version 2, which takes only `naming.style`. |
| [`NSX125`](nsx125.md) | `source-layers-fixed` | A version 1 `nimblestax.platform.yaml` lists source Layers other than `[bronze, silver]`. |
| [`NSX126`](nsx126.md) | `model-layer-named-like-a-source-layer` | A model Layer in `naming.layers.models` is called `bronze` or `silver`, in any case. |
| [`NSX127`](nsx127.md) | `model-outside-a-layer` | A file sits directly in a Domain's `models/` folder, or in a first folder under it that isn't a model Layer in `naming.layers.models`. |
| [`NSX129`](nsx129.md) | `skill-version-drift` | A Nimblestax Skill in `.agents/skills/` or `.claude/skills/` was written by another version of Nimblestax than the one installed. |
| [`NSX130`](nsx130.md) | `no-development-environment` | No Environment in `nimblestax.platform.yaml` sets `role: development`. |
| [`NSX131`](nsx131.md) | `two-environments-with-one-role` | More than one Environment in `nimblestax.platform.yaml` sets the same `role`. |
| [`NSX132`](nsx132.md) | `environment-name-not-an-identifier` | An Environment's name in `nimblestax.platform.yaml` isn't an identifier: letters, digits and underscores, starting with a letter or underscore. |
| [`NSX133`](nsx133.md) | `reserved-environment-name` | An Environment is named `preview`. |

## `NSX2xx` SQL and reads between tables

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSX201`](nsx201.md) | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| [`NSX202`](nsx202.md) | `duplicate-table` | A Seed and a Source in one Domain share a name, so they would be one table. |
| [`NSX203`](nsx203.md) | `unparseable-sql` | A Gold Model's SQL doesn't parse as one Databricks SQL query. |
| [`NSX204`](nsx204.md) | `computed-table-name` | SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Nimblestax can't see what it reads. |
| [`NSX205`](nsx205.md) | `real-table-name` | SQL reads a real table name, which names one Environment, instead of its Logical Name. |
| [`NSX206`](nsx206.md) | `file-read` | A Gold Model reads files or external data, such as `read_files(...)` or ``parquet.`/path` ``, instead of a table. |
| [`NSX207`](nsx207.md) | `raw-string-placeholder` | A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`. |
| [`NSX208`](nsx208.md) | `model-cycle` | Gold Models read themselves, or each other in a loop, so none of them can run first. |
| [`NSX209`](nsx209.md) | `cross-domain-read` | A Gold Model reads another Domain's gold, or silver that Domain hasn't Exported. |
| [`NSX210`](nsx210.md) | `read-against-build-order` | A Gold Model reads bronze. |
| [`NSX211`](nsx211.md) | `stream-of-upsert-silver` | A Gold Model reads silver that has `keys` with `STREAM(...)`. |
| [`NSX212`](nsx212.md) | `stream-of-materialized-view` | A Gold Model reads a Seed, or a Gold Model that doesn't stream, with `STREAM(...)`. |
| [`NSX213`](nsx213.md) | `test-references-unknown-table` | A `references` Test names a table that isn't in the project. |

## `NSX3xx` The workspace a project deploys to

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSX301`](nsx301.md) | `missing-catalog` | With `--platform`, a catalog the project's tables need isn't in the Environment's workspace, or the identity Nimblestax signs in as can't see it. |
| [`NSX302`](nsx302.md) | `missing-schema` | With `--platform`, a schema the project's tables need isn't in its catalog in the Environment's workspace, or the identity Nimblestax signs in as can't see it. |
| [`NSX303`](nsx303.md) | `developer-group-missing-grant` | With `--platform` on the Development Environment, the group `developers` names lacks `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` or `READ VOLUME` on one of its catalogs. |

## `NSX4xx` Tests on a Preview Environment's tables

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSX401`](nsx401.md) | `test-failed` | A Gold Model's Test failed on its table in your Preview Environment. |
| [`NSX402`](nsx402.md) | `test-could-not-run` | The SQL warehouse refused a Test's query. |

## `NSX9xx` The command line and running against Databricks

| Rule | Name | What it checks |
| --- | --- | --- |
| [`NSX901`](nsx901.md) | `usage-error` | The command line is wrong. |
| [`NSX902`](nsx902.md) | `unknown-environment` | `--env` isn't an Environment in the project. |
| [`NSX903`](nsx903.md) | `databricks-cli-missing` | `NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI that Nimblestax can't run. |
| [`NSX904`](nsx904.md) | `databricks-command-failed` | A Databricks CLI command failed. |
| [`NSX905`](nsx905.md) | `unexpected-error` | Nimblestax stopped on something it didn't expect, with a traceback on stderr. |
| [`NSX906`](nsx906.md) | `pipeline-column-not-found` | The refresh failed because a pipeline names a column its table doesn't have, often an Expectation on a column bronze doesn't have yet. |
| [`NSX907`](nsx907.md) | `expectation-failed` | The refresh failed because a row broke an Expectation whose `action` is `fail`. |
| [`NSX908`](nsx908.md) | `pipeline-failed` | The refresh failed with another pipeline error. The message is the pipeline's own. |
| [`NSX909`](nsx909.md) | `project-already-exists` | `nsx init` was run in a folder that already holds `nimblestax.platform.yaml`. |
| [`NSX910`](nsx910.md) | `databricks-cli-checksum-mismatch` | The Databricks CLI Nimblestax downloaded doesn't match the checksum its release names. |
| [`NSX911`](nsx911.md) | `databricks-cli-unsupported` | `NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI older than this Nimblestax supports. |
| [`NSX912`](nsx912.md) | `databricks-cli-download-failed` | Nimblestax couldn't download its Databricks CLI. |
| [`NSX913`](nsx913.md) | `no-databricks-cli-for-platform` | Databricks publishes no CLI for this operating system and architecture. |
| [`NSX914`](nsx914.md) | `skills-folder-ignored` | `nsx init` wrote Nimblestax Skills into a folder Git ignores, such as `.claude/`. |
| [`NSX915`](nsx915.md) | `skill-edited` | `nsx skills update` found a Nimblestax Skill edited since Nimblestax wrote it. |
| [`NSX916`](nsx916.md) | `unknown-example` | `nsx init --example` names an example Nimblestax doesn't ship. |
| [`NSX917`](nsx917.md) | `not-a-build-package` | `nsx deploy --package` names a folder that isn't a Build Package. |
| [`NSX918`](nsx918.md) | `build-package-changed` | A file in the Build Package `nsx deploy --package` was given differs from what was built. |
| [`NSX919`](nsx919.md) | `manifest-copies-not-removed` | A deploy succeeded, but old copies of the Deployment Manifest couldn't be removed. |
| [`NSX920`](nsx920.md) | `preview-schema-taken` | `nsx preview` would deploy into a schema that another project, another person, or someone by hand already created. |
| [`NSX921`](nsx921.md) | `example-has-no-preview` | `nsx preview`, or `nsx test`, was run in an example project, such as Kettle. |
| [`NSX922`](nsx922.md) | `preview-down-outside-fence` | `nsx preview down` found a schema in the preview's bundle state outside your `u_<user>__` schemas, or outside the Development Environment's catalogs. |
| [`NSX923`](nsx923.md) | `no-warehouse-for-tests` | `nsx test` can't tell which SQL warehouse to run Tests on. |
| [`NSX924`](nsx924.md) | `no-preview-to-test` | `nsx test` found no Preview Environment of this project to run Tests on. |
| [`NSX925`](nsx925.md) | `no-databricks-sql-access` | The identity `nsx test` runs as isn't allowed to use Databricks SQL. |
| [`NSX926`](nsx926.md) | `no-such-model` | `--model` names no Gold Model in the project, or a name more than one Gold Model has. |
