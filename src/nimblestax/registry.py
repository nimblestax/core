"""Every Rule Nimblestax reports, and what its docs page says about it.

The reference pages are generated from here, so a Rule and its explanation can't drift apart.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principle:
    """A principle of the Nimblestax Way, published at nimblestax.com/way/<slug>."""

    title: str
    slug: str


@dataclass(frozen=True)
class Example:
    """Something that fails the Rule: files written into the project `nstx init` creates, or a
    command run in it. `when` says what else must be true, for a failure no file can cause."""

    files: dict[str, str] = field(default_factory=dict)
    command: str = ""
    when: str = ""


@dataclass(frozen=True)
class Rule:
    name: str
    checks: str
    why: str
    example: Example
    fix: str
    principle: Principle | None = None
    # A warning is reported but never fails a command, so it doesn't change the exit code.
    severity: str = "error"


CODE_NAMES_TABLES_LOGICALLY = Principle(
    "Code names tables logically; Nimblestax resolves the environment",
    "code-names-tables-logically",
)
DATA_FLOWS_ONE_WAY = Principle("Data flows one way", "data-flows-one-way")
SILVER_IS_TYPED = Principle(
    "Silver is typed, conformed and deduplicated by key", "silver-is-typed-and-conformed"
)
NO_ROW_DISAPPEARS_SILENTLY = Principle("No row disappears silently", "no-row-disappears-silently")
EVERY_CHANGE_IS_REVIEWED = Principle(
    "Every change goes through a pull request, with a Plan a human reviews",
    "every-change-goes-through-a-pull-request",
)

ORDERS = "domains/sales/sources/orders.yaml"
LANDED_AS_JSON = (
    "kind: source\nversion: 1\npath: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
)
COUNTRIES = "domains/sales/seeds/countries.yaml"
COUNTRIES_CSV = "domains/sales/seeds/countries.csv"
FCT_ORDERS = "domains/sales/models/gold/fct_orders.sql"
RECOVERY_GUIDE = "[Recover from a failed refresh](../../guides/recover-from-a-failed-refresh.md)"
COUNTRIES_CONFIG = "kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  code: STRING\n"
# `nimblestax.platform.yaml` as `nstx init` writes it, up to `domains`, for examples that add one.
PLATFORM_HEAD = (
    "kind: platform\nversion: 2\nname: shop\nenvironments:\n  dev:\n"
    "    host: https://your-workspace.cloud.databricks.com\n    role: development\n"
    "naming:\n  style: domain-catalogs\n  layers:\n    models: [gold]\n"
)
INVOICES = "domains/finance/sources/invoices.yaml"
INVOICES_AS_JSON = (
    "kind: source\nversion: 1\npath: /Volumes/{env}_finance/bronze/landing/invoices\n"
    "format: json\n"
)

# What each series of Rules covers, by its IDs without their last two digits.
# The Rules index has one table per series, under this heading.
SERIES = {
    "NSTX1": "Config files",
    "NSTX2": "SQL and reads between tables",
    "NSTX3": "The workspace a project deploys to",
    "NSTX4": "Tests on a Preview Environment's tables",
    "NSTX9": "The command line and running against Databricks",
}

# Append only. An ID never changes meaning, and a retired rule stays here so its ID isn't reused.
RULES = {
    "NSTX101": Rule(
        "missing-kind",
        checks="A config file has no `kind`.",
        why="`kind` says what a file declares, such as a Source or a Gold Model, and so which"
        " fields it may have. Without it, Nimblestax can't check the rest of the file.",
        example=Example(
            {ORDERS: "version: 1\npath: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"}
        ),
        fix="Add `kind` at the top of the file, naming the Kind its folder holds: `source` in"
        " `sources/`, `seed` in `seeds/` and `model` in `models/`.",
    ),
    "NSTX102": Rule(
        "unknown-kind",
        checks="A `kind` isn't one Nimblestax knows.",
        why="Nimblestax checks each file against its Kind's schema. A misspelt `kind` has no"
        " schema, so nothing in the file can be checked. `nstx schema` reports this Rule too when"
        " it's asked for a Kind that doesn't exist, and exits 2, because the mistake is on the"
        " command line.",
        example=Example(
            {
                ORDERS: "kind: sauce\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Use one of the Kinds: `model`, `platform`, `seed` or `source`."
        " `nstx schema <kind>` prints a Kind's fields.",
    ),
    "NSTX103": Rule(
        "missing-version",
        checks="A config file has no `version`.",
        why="A Kind's schema can change between Nimblestax releases. `version` says which schema a"
        " file is written against, so a newer Nimblestax reads an older file as it was meant.",
        example=Example(
            {
                ORDERS: "kind: source\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Add `version` below `kind`, with the latest version this Nimblestax supports, such as"
        " `version: 1`.",
    ),
    "NSTX104": Rule(
        "unknown-version",
        checks="This Nimblestax doesn't support that `version`.",
        why="The file is written against a schema this Nimblestax doesn't have, usually because a"
        " newer Nimblestax wrote it. Checking it against another version's schema would give wrong"
        " answers.",
        example=Example(
            {
                ORDERS: "kind: source\nversion: 2\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Use a version this Nimblestax supports, which the diagnostic lists. If the file needs"
        " a newer Nimblestax, upgrade Nimblestax in the project so everyone runs the same one.",
    ),
    "NSTX105": Rule(
        "wrong-kind",
        checks="A file's `kind` doesn't belong in its location.",
        why="Where a file lives says what it is: Sources in `sources/`, Seeds in `seeds/` and"
        " Gold Models in `models/`. When a file's `kind` disagrees with its folder, Nimblestax"
        " can't"
        " tell which is right, so it doesn't guess.",
        example=Example(
            {
                ORDERS: "kind: model\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: json\n"
            }
        ),
        fix="Change `kind` to the Kind its folder holds, or move the file to the folder for its"
        " Kind.",
    ),
    "NSTX106": Rule(
        "invalid-field",
        checks="A field doesn't match its Kind's schema.",
        why="Each Kind's schema says which fields a file may have, their types, and which are"
        " required. Checking them with no workspace means a wrong field fails in review, not in"
        " a deploy. A field the schema doesn't have is a problem too, so a misspelt optional"
        " field isn't silently ignored.",
        example=Example(
            {
                ORDERS: "kind: source\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: 7\n"
            }
        ),
        fix="Correct the field the diagnostic names. `nstx schema <kind>` prints every field"
        " of a Kind, its type and whether it's required.",
    ),
    "NSTX107": Rule(
        "unreadable-config",
        checks="A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file"
        " isn't valid CSV.",
        why="Nimblestax reads a file before it checks anything in it. A file it can't read can't be"
        " checked at all.",
        example=Example(
            {
                ORDERS: "kind: source\nversion: 1\n"
                "path: /Volumes/{env}_sales/bronze/landing/orders\nformat: [json\n"
            }
        ),
        fix="Correct the YAML at the line the diagnostic gives, and make the file a mapping of"
        " fields that starts with `kind`. For a Seed's file, save it as UTF-8 and close every"
        " quoted value.",
    ),
    "NSTX108": Rule(
        "sql-without-config",
        checks="A SQL file has no config file beside it.",
        why="A Gold Model is a SQL file and a config file beside it, which says it's a model and"
        " names the SQL. Nimblestax reports a SQL file on its own rather than skipping it, so a"
        " model"
        " can't silently drop out of a deploy.",
        example=Example(
            {
                "domains/sales/models/gold/fct_returns.sql": (
                    "SELECT order_id\nFROM sales.silver.orders\n"
                )
            }
        ),
        fix="Add a config file with the same name beside it, with `kind: model`, `version: 1`"
        " and `sql` naming the SQL file.",
    ),
    "NSTX109": Rule(
        "missing-sql-file",
        checks="A model names a SQL file that doesn't exist.",
        why="A Gold Model's config names the SQL that builds its table. Without that file there"
        " is nothing to build.",
        example=Example(
            {
                "domains/sales/models/gold/fct_returns.yaml": "kind: model\nversion: 1\n"
                "sql: fct_returns.sql\nowner: sales-analytics\n"
            }
        ),
        fix="Correct `sql`, or add the SQL file to the same folder.",
    ),
    "NSTX110": Rule(
        "keys-without-sequence-by",
        checks="A Source's `silver` block has `keys` but no `sequence_by`.",
        why="With `keys`, silver keeps one row per key and applies each change to it. Changes can"
        " arrive out of order, so Nimblestax needs a column that says which change is newest."
        " Without one, an older change could overwrite a newer one.",
        example=Example({ORDERS: LANDED_AS_JSON + "silver:\n  keys: [order_id]\n"}),
        fix="Add `sequence_by` with the column that orders the changes, such as `updated_at`,"
        " or remove `keys` to append every row.",
        principle=SILVER_IS_TYPED,
    ),
    "NSTX111": Rule(
        "upsert-field-without-keys",
        checks="A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`.",
        why="These fields shape an upsert: which change is newest, whether history is kept, and"
        " which change is a delete. Each works on the rows of one key. Without `keys`, silver"
        " appends every row, so the field would do nothing while looking as if it did.",
        example=Example({ORDERS: LANDED_AS_JSON + "silver:\n  scd: 2\n"}),
        fix="Add `keys` with the columns that identify a row, or remove the field to append.",
        principle=SILVER_IS_TYPED,
    ),
    "NSTX112": Rule(
        "missing-seed-file",
        checks="A Seed's `file` doesn't exist beside it.",
        why="A Seed is a small table kept in the repo as a CSV file and a config file. Without"
        " the CSV file there is no data to load.",
        example=Example({COUNTRIES: COUNTRIES_CONFIG}),
        fix="Correct `file`, or add the CSV file to the same folder.",
    ),
    "NSTX113": Rule(
        "seed-header-mismatch",
        checks="The first line of a Seed's file doesn't name each declared column once.",
        why="Nimblestax matches a Seed's values to its columns by the names on the first line, then"
        " checks each value against its column's type. A first line that doesn't name each"
        " column once leaves values with no column, or a column with no values.",
        example=Example({COUNTRIES: COUNTRIES_CONFIG, COUNTRIES_CSV: "country\nAU\n"}),
        fix="Make the first line name each declared column once, or change `columns` in the"
        " Seed's config file.",
    ),
    "NSTX114": Rule(
        "seed-row-mismatch",
        checks="A row of a Seed's file has the wrong number of values, or a value that doesn't"
        " fit its column's type.",
        why="Nimblestax checks a Seed's values before deploying it, so a typo in the CSV file fails"
        " in review rather than when the table loads.",
        example=Example(
            {
                COUNTRIES: COUNTRIES_CONFIG + "  population: INT\n",
                COUNTRIES_CSV: "code,population\nAU,26 million\n",
            }
        ),
        fix="Give each row one value per column, quoting any value that contains a comma, and"
        " make each value fit its column's type, or change the type.",
    ),
    "NSTX115": Rule(
        "unsupported-seed-type",
        checks="A Seed's column has a type Nimblestax can't check values against.",
        why="Nimblestax checks every value in a Seed against its column's type. A type it can't"
        " check, often a misspelt one, would let any value through.",
        example=Example(
            {
                COUNTRIES: "kind: seed\nversion: 1\nfile: countries.csv\n"
                "columns:\n  code: VARCAHR\n",
                COUNTRIES_CSV: "code\nAU\n",
            }
        ),
        fix="Use a type Nimblestax checks, which the diagnostic lists, such as `STRING`, `INT`,"
        " `DATE` or `DECIMAL(10, 2)`.",
    ),
    "NSTX116": Rule(
        "invalid-expectation",
        checks="An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse,"
        " or it holds a query, an aggregate, a window function, a comment or an alias.",
        why="An Expectation is checked on each row as it's written to silver, so its condition"
        " can see only that row. A query, an aggregate or a window function reads other rows,"
        " and a rule across rows is a Test. Nimblestax places `expect` inside the code it"
        " generates,"
        " so it must parse on its own, and a comment would hide the code after it.",
        example=Example(
            {
                ORDERS: LANDED_AS_JSON
                + "silver:\n  expectations:\n    - name: amount_is_positive\n"
                "      expect: amount > (SELECT avg(amount) FROM sales.silver.orders)\n"
            }
        ),
        fix="Write `expect` as one condition on the row's own columns, such as `amount > 0`. A"
        " rule across rows is a Test.",
        principle=NO_ROW_DISAPPEARS_SILENTLY,
    ),
    "NSTX117": Rule(
        "invalid-name",
        checks="A config file's name isn't an identifier, so the table named after it can't be"
        " written in SQL: it must hold only letters, digits and underscores, and not start with"
        " a digit.",
        why="A Source, Seed or Gold Model takes its table's name from its config file's name, and"
        " SQL reads that table by name. A name with a hyphen or a space, or one that starts with"
        " a digit, would need quoting everywhere it's read.",
        example=Example(
            {
                "domains/sales/seeds/vat-rates.yaml": "kind: seed\nversion: 1\n"
                "file: vat-rates.csv\ncolumns:\n  code: STRING\n",
                "domains/sales/seeds/vat-rates.csv": "code\nAU\n",
            }
        ),
        fix="Rename the file to a name of letters, digits and underscores, such as"
        " `vat_rates.yaml`, which the diagnostic suggests.",
    ),
    "NSTX118": Rule(
        "invalid-delete-when",
        checks="A Source's `silver.delete_when` isn't one SQL condition on one row, for the same"
        " reasons as `NSTX116`.",
        why="`delete_when` decides, change by change, whether a change deletes its key's row,"
        " so it can see only that change. Nimblestax places it inside the code it generates, so it"
        " must parse on its own, and a comment would hide the code after it.",
        example=Example(
            {
                ORDERS: LANDED_AS_JSON + "silver:\n  keys: [order_id]\n  sequence_by: updated_at\n"
                "  delete_when: op = 'D' -- deletes from the source system\n"
            }
        ),
        fix="Write `delete_when` as one condition on the row's own columns, such as `op = 'D'`.",
        principle=SILVER_IS_TYPED,
    ),
    "NSTX119": Rule(
        "invalid-sequence-by",
        checks="A Source's `silver.sequence_by` isn't one SQL expression on one row, such as"
        " `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an"
        " aggregate, a window function, a comment or an alias.",
        why="`sequence_by` orders the changes to each key, so silver keeps the newest. Nimblestax"
        " places it inside the code it generates, so it must be one expression on the change's"
        " own columns. A sort direction such as `DESC` reads as an alias, and has no place"
        " there: the highest value is always the newest.",
        example=Example(
            {
                ORDERS: LANDED_AS_JSON
                + "silver:\n  keys: [order_id]\n  sequence_by: updated_at DESC\n"
            }
        ),
        fix="Write `sequence_by` as the column that orders the changes, such as `updated_at`, or"
        " one expression on the row's own columns, such as `struct(updated_at, seq)`.",
        principle=SILVER_IS_TYPED,
    ),
    "NSTX120": Rule(
        "duplicate-config-file",
        checks="Two config files share a name in one Domain's Layer: in one folder, such as"
        " `orders.yaml` and `orders.yml`, or in two folders, such as `sources/erp/orders.yaml`"
        " and `sources/crm/orders.yaml`. Nimblestax reads either ending, and writes `.yaml`.",
        why="A config file's name is its table's name, so two files with one name would declare"
        " one table twice, and Nimblestax can't tell which one is meant. Folders inside `sources/`,"
        " `seeds/` or a model Layer's folder only group files, so they don't make two tables."
        " The same name in two model Layers is two tables, such as `sales.gold.orders` and"
        " `sales.marts.orders`.",
        example=Example({"domains/sales/sources/orders.yml": LANDED_AS_JSON}),
        fix="Keep one of the files, and delete or rename the other.",
    ),
    "NSTX121": Rule(
        "unlisted-domain-folder",
        checks="A folder under `domains/` isn't listed in `domains` in `nimblestax.platform.yaml`,"
        " in the same case, so nothing in it is validated or deployed.",
        why="`domains` in `nimblestax.platform.yaml` lists the project's Domains, and Nimblestax"
        " reads only those folders. A folder it doesn't list would be silently left out of every"
        " check and every deploy. A folder that differs only in case is found on some file systems"
        " and not others, so it's reported too.",
        example=Example(
            {
                "domains/hr/sources/employees.yaml": "kind: source\nversion: 1\n"
                "path: /Volumes/{env}_hr/bronze/landing/employees\nformat: json\n"
            }
        ),
        fix="Add the folder to `domains` in `nimblestax.platform.yaml`, matching its case, or"
        " remove the folder.",
    ),
    "NSTX122": Rule(
        "dev-host-missing",
        checks="`nimblestax.platform.yaml` has no `host` on the Development Environment. In a"
        " version 1 file, which knows Environments by name, it has no `host` on `dev`.",
        why="The Development Environment is the one every project starts from, and its `host` is"
        " the workspace Nimblestax connects to. Every other Environment uses its `host` unless it"
        " sets its own, so without it no Environment has a workspace.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace(
                    "    host: https://your-workspace.cloud.databricks.com\n", ""
                )
                + "domains:\n  - sales\n"
            }
        ),
        fix="Add `host` under the Development Environment, such as `environments.dev`, set to"
        " its workspace URL.",
    ),
    "NSTX123": Rule(
        "two-default-environments",
        checks="More than one Environment in `nimblestax.platform.yaml` sets `default: true`.",
        why="Commands that read rather than deploy use the default Environment when `--env` is"
        " left out. With two defaults, Nimblestax can't tell which one you mean, so it"
        " doesn't guess.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace(
                    "    role: development\n",
                    "    role: development\n    default: true\n  prod:\n    default: true\n",
                )
                + "domains:\n  - sales\n"
            }
        ),
        fix="Keep `default: true` on one Environment and remove it from the others. With none,"
        " the Development Environment is the default.",
    ),
    "NSTX124": Rule(
        "naming-patterns-not-supported",
        checks="`nimblestax.platform.yaml` sets `catalog` and `schema` patterns that aren't a"
        " Naming Style, or sets any patterns at version 2, which takes only `naming.style`.",
        why="Each Naming Style is a layout Nimblestax tests end to end. A pattern of your own can"
        " go wrong in ways a style can't: dev and prod can write to one table, every Domain's"
        " silver can land in one schema, and two Domains joined with their Layers can give the"
        " same schema name. Nimblestax reads a version 1 file's patterns as the style they match,"
        " and has no way yet to check patterns that match none.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace(
                    "  style: domain-catalogs\n",
                    '  catalog: "{env}"\n  schema: "{layer}"\n',
                )
                + "domains:\n  - sales\n"
            }
        ),
        fix="Replace `catalog` and `schema` with `style`, set to `domain-catalogs`,"
        " `layer-catalogs` or `environment-catalogs`, and set `version: 2`. For a version 1"
        " file, the diagnostic names the closest style. If the project is deployed, check"
        " where the style puts each table first, because a new style moves them. If none of"
        " the styles fits, see [When none of these fit]"
        "(../../concepts/naming.md#when-none-of-these-fit).",
    ),
    "NSTX125": Rule(
        "source-layers-fixed",
        checks="A version 1 `nimblestax.platform.yaml` lists source Layers other than"
        " `[bronze, silver]`.",
        why="Every Source makes a bronze table and a silver table, and Nimblestax decides what each"
        " one does: Expectations, quarantine and exported silver. Another name would only"
        " relabel them, so the source Layers are always bronze and silver, and version 2 has no"
        " field for them.",
        example=Example(
            {
                "nimblestax.platform.yaml": "kind: platform\nversion: 1\nname: shop\n"
                "environments:\n  dev:\n    host: https://your-workspace.cloud.databricks.com\n"
                'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
                "  layers:\n    sources: [bronze, curated]\n    models: [gold]\n"
                "domains:\n  - sales\n"
            }
        ),
        fix="Remove `naming.layers.sources`, and set `version: 2` with `naming.style`. To add a"
        " Layer, add it to `naming.layers.models`.",
    ),
    "NSTX126": Rule(
        "model-layer-named-like-a-source-layer",
        checks="A model Layer in `naming.layers.models` is called `bronze` or `silver`, in any"
        " case.",
        why="Every Source fills bronze and silver, and only Gold Models fill model Layers. A model"
        " Layer with a source Layer's name would put Gold Models in the same schema as Sources,"
        " and a Logical Name such as `sales.silver.orders` could name either.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace(
                    "models: [gold]", "models: [gold, silver]"
                )
                + "domains:\n  - sales\n"
            }
        ),
        fix="Rename the model Layer, such as to `gold` or `marts`, and rename its folder under"
        " `models/` to match.",
    ),
    "NSTX127": Rule(
        "model-outside-a-layer",
        checks="A file sits directly in a Domain's `models/` folder, or in a first folder under"
        " it that isn't a model Layer in `naming.layers.models`.",
        why="A Gold Model's Layer is the first folder under `models/`, so"
        " `domains/sales/models/gold/fct_orders.yaml` is `sales.gold.fct_orders` and the path"
        " reads as the Logical Name. A file with no such folder has no Layer, and a misspelt"
        " folder would put a table in a schema nobody expects, so Nimblestax doesn't guess.",
        example=Example(
            {
                "domains/sales/models/fct_returns.yaml": "kind: model\nversion: 1\n"
                "sql: fct_returns.sql\nowner: sales-analytics\n",
                "domains/sales/models/fct_returns.sql": "SELECT order_id\n"
                "FROM sales.silver.orders\n",
            }
        ),
        fix="Move the file into a folder named after a model Layer, which the diagnostic lists."
        " To add a Layer, add it to `naming.layers.models` in `nimblestax.platform.yaml`.",
    ),
    # NSTX128 `production-shares-a-workspace` was removed before any release. Never reuse it.
    "NSTX129": Rule(
        "skill-version-drift",
        checks="A Nimblestax Skill in `.agents/skills/` or `.claude/skills/` was written by another"
        " version of Nimblestax than the one installed.",
        why="Nimblestax Skills guide a coding agent through Nimblestax's commands, and each one"
        " records the Nimblestax version that wrote it. A skill from another version can name"
        " commands, options or steps the installed Nimblestax doesn't have, so an agent follows"
        " stale steps. This is a warning: `nstx validate` still passes.",
        example=Example(
            {
                ".agents/skills/nimblestax-add-source/SKILL.md": "---\nname:"
                " nimblestax-add-source\n"
                "description: Add a Source to a Nimblestax project.\nmetadata:\n"
                '  nimblestax-version: "0.0.9"\n---\n\n# Add a Source\n'
            }
        ),
        fix="Run `nstx skills update`, which refreshes both copies of each skill, and commit"
        " them.",
        severity="warning",
    ),
    "NSTX130": Rule(
        "no-development-environment",
        checks="No Environment in `nimblestax.platform.yaml` sets `role: development`.",
        why="Nimblestax knows an Environment by its role, not its name. The Development Environment"
        " is where pull request Plans compare against, where Preview Environments live, and the"
        " workspace any Environment without a `host` uses. A project has exactly one, so Nimblestax"
        " doesn't guess it from a name.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace("    role: development\n", "")
                + "domains:\n  - sales\n"
            }
        ),
        fix="Add `role: development` to the Environment people develop in, such as `dev`.",
    ),
    "NSTX131": Rule(
        "two-environments-with-one-role",
        checks="More than one Environment in `nimblestax.platform.yaml` sets the same `role`.",
        why="A project has exactly one Development Environment and at most one Production"
        " Environment. Plans, Preview Environments and the approval gate each need to know which"
        " one Environment they mean.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace(
                    "naming:",
                    "  test:\n    role: production\n  prod:\n    role: production\n" "naming:",
                )
                + "domains:\n  - sales\n"
            }
        ),
        fix="Keep the role on one Environment and remove it from the others. Any Environment"
        " without a role is an ordinary stage.",
    ),
    "NSTX132": Rule(
        "environment-name-not-an-identifier",
        checks="An Environment's name in `nimblestax.platform.yaml` isn't an identifier: letters,"
        " digits and underscores, starting with a letter or underscore.",
        why="An Environment's name goes into each of its catalogs, so `prd` gives"
        " `prd_sales.silver.orders`. Nimblestax writes catalog names into SQL unquoted, so the name"
        " must be an identifier.",
        example=Example(
            {
                "nimblestax.platform.yaml": PLATFORM_HEAD.replace("naming:", "  prd-1: {}\nnaming:")
                + "domains:\n  - sales\n"
            }
        ),
        fix="Rename the Environment to letters, digits and underscores, such as `prd` or"
        " `test_2`.",
    ),
    "NSTX133": Rule(
        "reserved-environment-name",
        checks="An Environment is named `preview`.",
        why="`preview` is the bundle target every Preview Environment deploys through, so an"
        " Environment with that name would share its target.",
        example=Example(
            files={
                "nimblestax.platform.yaml": "kind: platform\nversion: 2\nname: shop\n"
                "environments:\n  dev:\n    host: https://shop.cloud.databricks.com\n"
                "    role: development\n  preview: {}\n"
                "naming:\n  style: domain-catalogs\n  layers:\n    models: [gold]\n"
                "domains:\n  - sales\n"
            },
            command="nstx validate",
        ),
        fix="Rename the Environment, such as to `staging`.",
    ),
    "NSTX134": Rule(
        "model-without-owner",
        checks="A Gold Model has no `owner`.",
        why="Every Gold Model has someone who answers for it: who to ask when a Test fails, or"
        " before changing what it means. `owner` names that team or person beside the SQL, so"
        " it's reviewed with the model and never goes stale in a separate list.",
        example=Example(
            {
                "domains/sales/models/gold/fct_returns.yaml": "kind: model\nversion: 1\n"
                "sql: fct_returns.sql\n",
                "domains/sales/models/gold/fct_returns.sql": "SELECT order_id\n"
                "FROM sales.silver.orders\n",
            }
        ),
        fix="Add `owner` naming the team or person who answers for the table, such as"
        " `owner: sales-analytics`.",
    ),
    "NSTX201": Rule(
        "unresolved-logical-name",
        checks="SQL reads a table that isn't in the project.",
        why="Nimblestax knows every table a project makes: each Source's bronze and silver tables,"
        " each Seed's table and each Gold Model's table. SQL reads them by Logical Name, such as"
        " `sales.silver.orders`, so Nimblestax can check every read before a deploy and point it at"
        " the right catalog in each Environment. A read it can't find is a typo, or a table"
        " nothing in the project makes. A table name without its Domain and Layer that isn't a"
        " CTE is reported too, because Nimblestax can't tell which table it means.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.silver.order\n"}),
        fix="Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
        principle=CODE_NAMES_TABLES_LOGICALLY,
    ),
    "NSTX202": Rule(
        "duplicate-table",
        checks="A Seed and a Source in one Domain share a name, so they would be one table.",
        why="A Seed's table is in silver, beside each Source's silver table. A Seed and a Source"
        " with one name in one Domain would write the same table, and one would overwrite the"
        " other.",
        example=Example(
            {
                "domains/sales/seeds/orders.yaml": "kind: seed\nversion: 1\nfile: orders.csv\n"
                "columns:\n  order_id: INT\n",
                "domains/sales/seeds/orders.csv": "order_id\n1\n",
            }
        ),
        fix="Rename the Seed or the Source, so each has its own table.",
    ),
    "NSTX203": Rule(
        "unparseable-sql",
        checks="A Gold Model's SQL doesn't parse as one Databricks SQL query.",
        why="Nimblestax reads a Gold Model's SQL to find every table it reads, so it can check"
        " them, build them first and point each at the right Environment. SQL it can't parse hides"
        " those reads. A file with more than one statement is reported too, because a Gold"
        " Model is one query.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.silver.orders\nWHERE\n"}),
        fix="Make the file one Databricks SQL query that runs on its own.",
    ),
    "NSTX204": Rule(
        "computed-table-name",
        checks="SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Nimblestax"
        " can't see what it reads.",
        why="Nimblestax checks every table a Gold Model reads, and shows those reads in review. A"
        " name built when the query runs can't be seen until then, so it could read any table in"
        " any Environment.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM IDENTIFIER(:orders_table)\n"}),
        fix="Write the table as a Logical Name, such as `sales.silver.orders`.",
        principle=EVERY_CHANGE_IS_REVIEWED,
    ),
    "NSTX205": Rule(
        "real-table-name",
        checks="SQL reads a real table name, which names one Environment, instead of its Logical"
        " Name.",
        why="A real table name such as `dev_sales.silver.orders` names one Environment's"
        " catalog, so the same SQL would read dev data in prod. A Logical Name such as"
        " `sales.silver.orders` names no Environment, and Nimblestax points it at the right catalog"
        " in each.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM dev_sales.silver.orders\n"}),
        fix="Use the table's Logical Name, which the diagnostic gives. If no table in the project"
        " has that name, declare a Source, Seed or Gold Model for it.",
        principle=CODE_NAMES_TABLES_LOGICALLY,
    ),
    "NSTX206": Rule(
        "file-read",
        checks="A Gold Model reads files or external data, such as `read_files(...)` or"
        " ``parquet.`/path` ``, instead of a table.",
        why="A Gold Model reads tables in the project. Data read straight from files skips"
        " bronze and silver, so it isn't landed, typed or checked, and Nimblestax can't point the"
        " path at each Environment.",
        example=Example(
            {
                FCT_ORDERS: "SELECT order_id, amount\n"
                "FROM read_files('/Volumes/prod_sales/bronze/landing/orders')\n"
            }
        ),
        fix="Declare a Source for these files, and read its silver table by Logical Name.",
        principle=DATA_FLOWS_ONE_WAY,
    ),
    "NSTX207": Rule(
        "raw-string-placeholder",
        checks="A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`.",
        why="The pipeline replaces `${name}` with a setting's value anywhere in its SQL, even"
        " inside a string. Nimblestax escapes `${` in ordinary strings and comments, so they keep"
        " the value you wrote, but a raw string can't hold the escape.",
        example=Example(
            {FCT_ORDERS: "SELECT order_id, r'${order_id}' AS template\nFROM sales.silver.orders\n"}
        ),
        fix="Write it as an ordinary string, doubling each backslash, and Nimblestax escapes the"
        " `${`.",
    ),
    "NSTX208": Rule(
        "model-cycle",
        checks="Gold Models read themselves, or each other in a loop, so none of them can run"
        " first.",
        why="Nimblestax builds each Gold Model after the tables it reads. When Gold Models read"
        " each other in a loop, every one of them waits for another, so there is no order to build"
        " them in.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.gold.fct_orders\n"}),
        fix="Remove one of the reads in the loop, which the diagnostic lists, so each Gold Model"
        " reads only tables built before it.",
    ),
    "NSTX209": Rule(
        "cross-domain-read",
        checks="A Gold Model reads another Domain's gold, or silver that Domain hasn't Exported.",
        why="Each Domain owns its tables, and only the tables it publishes are read by other"
        " Domains. A Domain publishes silver by Exporting it, with `export: true`, and its"
        " gold and the rest of its silver stay its own, free to change. The Shared Domain, the"
        " Domain called `shared`, holds what every Domain reads, so its gold is the one gold"
        " other Domains may read."
        " Reads that only point this way can't form a loop between Domains.",
        example=Example(
            {
                "nimblestax.platform.yaml": f"{PLATFORM_HEAD}domains:\n  - sales\n  - finance\n",
                INVOICES: INVOICES_AS_JSON,
                FCT_ORDERS: "SELECT order_id, amount\nFROM finance.silver.invoices\n",
            }
        ),
        fix="Read silver the other Domain has Exported, or ask its owner to Export it. To share"
        " a Gold Model, move it into the Shared Domain.",
        principle=DATA_FLOWS_ONE_WAY,
    ),
    "NSTX210": Rule(
        "read-against-build-order",
        checks="A Gold Model reads bronze.",
        why="Tables are built in a fixed order: bronze, then silver, then gold. Bronze keeps"
        " every row as it landed, untyped and with duplicates, and only its own silver reads"
        " it. A Gold Model reads silver, where rows are conformed and checked, so a change to"
        " bronze reaches gold only through silver.",
        example=Example({FCT_ORDERS: "SELECT order_id, amount\nFROM sales.bronze.orders\n"}),
        fix="Read the silver table of the same name, which the diagnostic gives.",
        principle=DATA_FLOWS_ONE_WAY,
    ),
    "NSTX211": Rule(
        "stream-of-upsert-silver",
        checks="A Gold Model reads silver that has `keys` with `STREAM(...)`.",
        why="A stream reads only rows added since its last update. Silver with `keys` is"
        " written by upserts, which change and delete rows in place, so a stream from it fails"
        " in the pipeline's first update after a change. Read without `STREAM(...)`, the Gold"
        " Model is a materialized view, which Databricks refreshes incrementally where it can."
        " See [How Nimblestax reads a gold model's SQL]"
        "(../../concepts/how-nimblestax-reads-a-gold-models-sql.md).",
        example=Example(
            {
                ORDERS: f"{LANDED_AS_JSON}silver:\n  keys: [order_id]\n  sequence_by: updated_at\n",
                FCT_ORDERS: "SELECT order_id, amount\nFROM STREAM(sales.silver.orders)\n",
            }
        ),
        fix="Read the table without `STREAM(...)`, as `FROM sales.silver.orders`.",
    ),
    "NSTX212": Rule(
        "stream-of-materialized-view",
        checks="A Gold Model reads a Seed, or a Gold Model that doesn't stream, with"
        " `STREAM(...)`.",
        why="A stream reads only rows added since its last update. A Seed, and a Gold Model"
        " whose SQL reads no `STREAM(...)`, are materialized views, which Databricks may"
        " recompute in full on any refresh, so it refuses a stream from one. A stream may read"
        " silver without `keys`, a Quarantine table, or a Gold Model that streams. See"
        " [How Nimblestax reads a gold model's SQL]"
        "(../../concepts/how-nimblestax-reads-a-gold-models-sql.md).",
        example=Example(
            {
                COUNTRIES: COUNTRIES_CONFIG,
                COUNTRIES_CSV: "code\nAU\n",
                FCT_ORDERS: "SELECT code\nFROM STREAM(sales.silver.countries)\n",
            }
        ),
        fix="Read the table without `STREAM(...)`, as `FROM sales.silver.countries`.",
    ),
    "NSTX213": Rule(
        "test-references-unknown-table",
        checks="A `references` Test names a table that isn't in the project.",
        why="A `references` Test checks that every value of a column is a key in another table,"
        " and reads that table in the same Preview Environment. So the other table must be one"
        " the project builds: a Source's bronze or silver, a Seed or a Gold Model.",
        example=Example(
            {
                "domains/sales/models/gold/fct_orders.yaml": "kind: model\nversion: 1\n"
                "sql: fct_orders.sql\nowner: sales-analytics\ntests:\n  - references:\n"
                "      column: customer_id\n"
                "      to: sales.gold.dim_customers\n"
            }
        ),
        fix="Correct `to` to the Logical Name of a table in the project, such as"
        " `shared.gold.dim_customers`.",
    ),
    "NSTX301": Rule(
        "missing-catalog",
        checks="With `--platform`, a catalog the project's tables need isn't in the"
        " Environment's workspace, or the identity Nimblestax signs in as can't see it.",
        why="Nimblestax makes tables, views and pipelines, and never catalogs or schemas: those"
        " belong to whoever runs the platform, so the same tool never both creates and grants"
        " them. `nstx init` lists every catalog and schema to create. A deploy into a catalog"
        " that isn't there fails halfway through, so `nstx validate --platform` checks first.",
        example=Example(
            command="nstx validate --platform",
            when="dev's workspace has no catalog `dev_sales`.",
        ),
        fix="Create the catalog with the schemas the diagnostic lists, or grant the identity"
        " `USE CATALOG` on it.",
    ),
    "NSTX302": Rule(
        "missing-schema",
        checks="With `--platform`, a schema the project's tables need isn't in its catalog in"
        " the Environment's workspace, or the identity Nimblestax signs in as can't see it.",
        why="Nimblestax makes tables in schemas that already exist, and never creates them, for the"
        " same reasons as `NSTX301`. A deploy into a schema that isn't there fails halfway"
        " through, so `nstx validate --platform` checks first.",
        example=Example(
            command="nstx validate --platform",
            when="dev's workspace has the catalog `dev_sales` but no schema `silver` in it.",
        ),
        fix="Create the schema in its catalog, or grant the identity `USE SCHEMA` on it.",
    ),
    "NSTX303": Rule(
        "developer-group-missing-grant",
        checks="With `--platform` on the Development Environment, the group `developers` names"
        " lacks `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` or `READ VOLUME` on one"
        " of its catalogs.",
        why="Each person deploys their own Preview Environment with their own login, into schemas"
        " they create in the Development Environment's catalogs, and its sources read the files"
        " that land in its Volumes. The group needs those four privileges there, and only"
        " there.",
        example=Example(
            files={
                "nimblestax.platform.yaml": "kind: platform\nversion: 2\nname: shop\n"
                "environments:\n  dev:\n    host: https://shop.cloud.databricks.com\n"
                "    role: development\ndevelopers: data-engineers\n"
                "naming:\n  style: domain-catalogs\n  layers:\n    models: [gold]\n"
                "domains:\n  - sales\n"
            },
            command="nstx validate --platform",
            when="`data-engineers` has no `CREATE SCHEMA` on `dev_sales`.",
        ),
        fix="Run the `GRANT` the diagnostic gives, as the catalog's owner.",
    ),
    "NSTX401": Rule(
        "test-failed",
        checks="A Gold Model's Test failed on its table in your Preview Environment.",
        why="A Test is a rule about a whole table, such as no two rows sharing an `order_id`."
        " `nstx test` runs each one on the table your preview built from all of dev's rows, so"
        " a Test that fails there would fail in dev too. It exits 1.",
        example=Example(
            {
                "domains/sales/models/gold/fct_orders.yaml": "kind: model\nversion: 1\n"
                "sql: fct_orders.sql\nowner: sales-analytics\ntests:\n  - unique: [order_id]\n"
            },
            command="nstx test",
            when="Two rows of the preview's `fct_orders` have the same `order_id`.",
        ),
        fix="Fix the model's SQL or the data it reads, or correct the Test. Then run"
        " `nstx preview` and `nstx test` again.",
    ),
    "NSTX402": Rule(
        "test-could-not-run",
        checks="The SQL warehouse refused a Test's query.",
        why="Each Test runs as one query on the model's table. The warehouse refuses it when the"
        " Test doesn't match the table, such as a column the table doesn't have. Nimblestax can't"
        " see a table's columns without a workspace, so `nstx validate` can't catch this. The"
        " other Tests still run, and `nstx test` exits 1.",
        example=Example(
            {
                "domains/sales/models/gold/fct_orders.yaml": "kind: model\nversion: 1\n"
                "sql: fct_orders.sql\nowner: sales-analytics\ntests:\n  - unique: [order_no]\n"
            },
            command="nstx test",
            when="`fct_orders` has no column `order_no`.",
        ),
        fix="Correct the Test so it matches the model's table, such as a column's name.",
    ),
    "NSTX901": Rule(
        "usage-error",
        checks="The command line is wrong.",
        why="A command, option or argument is unknown or missing. With `--json`, Nimblestax still"
        " prints one envelope, so a script or agent reads the problem instead of help text. It"
        " exits 2, because the command line needs a change, not the project.",
        example=Example(command="nstx validate --projct ."),
        fix="Correct the command line. `nstx <command> --help` lists a command's options.",
    ),
    "NSTX902": Rule(
        "unknown-environment",
        checks="`--env` isn't an Environment in the project.",
        why="Environments are declared in `nimblestax.platform.yaml`, each with its workspace. An"
        " Environment that isn't there has no workspace or catalogs to compile or deploy for.",
        example=Example(command="nstx compile --env staging"),
        fix="Use an Environment from `nimblestax.platform.yaml`, which the diagnostic lists, or add"
        " the Environment there.",
    ),
    "NSTX903": Rule(
        "databricks-cli-missing",
        checks="`NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI that Nimblestax can't run.",
        why="Nimblestax runs its own pinned Databricks CLI, which it downloads the first time it"
        " needs it. `NIMBLESTAX_DATABRICKS_CLI` points Nimblestax at a CLI you installed yourself"
        " instead, for a machine that can't download one. The file it names doesn't exist, or this"
        " machine can't run it.",
        example=Example(
            command="nstx deploy --env dev",
            when="`NIMBLESTAX_DATABRICKS_CLI` is set to `/opt/databricks/databricks`, which doesn't"
            " exist.",
        ),
        fix="Point `NIMBLESTAX_DATABRICKS_CLI` at the Databricks CLI's binary, or unset it so"
        " Nimblestax downloads its own.",
    ),
    "NSTX904": Rule(
        "databricks-command-failed",
        checks="A Databricks CLI command failed.",
        why="Nimblestax ran a Databricks CLI command, such as `databricks bundle deploy`, and it"
        " failed. Its log on stderr says why, often authentication, permissions or the"
        " workspace itself. A refresh that fails reports this Rule too when Nimblestax can't read"
        " the"
        " pipeline's own error.",
        example=Example(
            command="nstx deploy --env dev",
            when="The Databricks CLI isn't signed in to the dev workspace.",
        ),
        fix="Read the Databricks CLI's log on stderr, fix what it names, and run the command"
        " again. `nstx databricks auth describe` checks how the CLI signs in.",
    ),
    "NSTX905": Rule(
        "unexpected-error",
        checks="Nimblestax stopped on something it didn't expect, with a traceback on stderr.",
        why="Something went wrong that isn't a problem in the project or on the command line."
        " Nimblestax still reports it as a diagnostic, as an envelope with `--json`, and exits 2,"
        " so"
        " scripts keep working.",
        example=Example(command="nstx compile", when="The disk is full."),
        fix="Read the traceback on stderr. If your machine isn't the cause, report a bug at"
        " https://github.com/nimblestax/core/issues with the traceback.",
    ),
    "NSTX906": Rule(
        "pipeline-column-not-found",
        checks="The refresh failed because a pipeline names a column its table doesn't have,"
        " often an Expectation on a column bronze doesn't have yet.",
        why="`nstx deploy` refreshes an Environment's tables after it ships them, and reports a"
        " pipeline's own error when an update fails. When an Expectation checks a column that"
        " arrives in the same change, the silver flow fails on the unknown column before bronze"
        " runs, so bronze never picks the column up, and landing new data doesn't help.",
        example=Example(
            command="nstx deploy --env dev",
            when="A Source's files gained a `region` column, and an Expectation on `region` was"
            " added in the same change.",
        ),
        fix="Correct the column's name. If an Expectation names a column bronze doesn't have"
        " yet, deploy without the Expectation so bronze picks up the column, then add it back."
        f" See {RECOVERY_GUIDE}.",
    ),
    "NSTX907": Rule(
        "expectation-failed",
        checks="The refresh failed because a row broke an Expectation whose `action` is `fail`.",
        why="An Expectation with `action: fail` stops the update when a row breaks it. Bronze is"
        " append-only, so the row stays there, and every refresh fails on it until the rule"
        " changes. Landing a corrected row doesn't remove the bad one.",
        example=Example(
            command="nstx deploy --env dev",
            when="A row in bronze has a negative `amount`, and the Source has an Expectation"
            " `amount >= 0` with `action: fail`.",
        ),
        fix="Correct the rule if the row is fine, or change its `action` to `quarantine` or"
        f" `warn`, then deploy again. See {RECOVERY_GUIDE}.",
        principle=NO_ROW_DISAPPEARS_SILENTLY,
    ),
    "NSTX908": Rule(
        "pipeline-failed",
        checks="The refresh failed with another pipeline error. The message is the pipeline's"
        " own.",
        why="`nstx deploy` refreshes an Environment's tables after it ships them. When a"
        " pipeline update fails for a reason Nimblestax has no Rule for, it reports the pipeline's"
        " own error, read from its event log, rather than a generic failure.",
        example=Example(
            command="nstx deploy --env dev",
            when="The pipeline can't read the Volume a Source's files land in.",
        ),
        fix="Fix the cause, then deploy again. The pipeline's event log in the workspace has"
        " more.",
    ),
    "NSTX909": Rule(
        "project-already-exists",
        checks="`nstx init` was run in a folder that already holds `nimblestax.platform.yaml`.",
        why="`nstx init` writes a new project. Writing it over an existing one would replace"
        " the Platform Contract and every starter file you've edited, so it writes nothing"
        " instead. Other files in the folder are fine, so a new Git repo with a README works.",
        example=Example(command="nstx init"),
        fix="Run `nstx init` in another folder, or give it one, as `nstx init <folder>`.",
    ),
    "NSTX910": Rule(
        "databricks-cli-checksum-mismatch",
        checks="The Databricks CLI Nimblestax downloaded doesn't match the checksum its release"
        " names.",
        why="Each Nimblestax release names one Databricks CLI version and the checksum of each"
        " platform's archive. Nimblestax downloads that archive from Databricks' GitHub releases"
        " the"
        " first time it needs the CLI. An archive that doesn't match was changed or cut short on"
        " the way, so Nimblestax doesn't install it and runs nothing.",
        example=Example(
            command="nstx deploy --env dev",
            when="A proxy between you and GitHub changes the archive Nimblestax downloads.",
        ),
        fix="Run the command again. If it fails again, something between you and GitHub is"
        " changing the download: check your proxy, or point `NIMBLESTAX_DATABRICKS_CLI` at a"
        " Databricks CLI you installed yourself.",
    ),
    "NSTX911": Rule(
        "databricks-cli-unsupported",
        checks="`NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI older than this Nimblestax"
        " supports.",
        why="Each Nimblestax release is tested with one Databricks CLI version and names the oldest"
        " it supports. An older CLI can deploy the same project differently, so Nimblestax refuses"
        " it"
        " and runs nothing. A CLI that doesn't report its version is refused too.",
        example=Example(
            command="nstx deploy --env dev",
            when="`NIMBLESTAX_DATABRICKS_CLI` names a Databricks CLI at version 0.240.0.",
        ),
        fix="Point `NIMBLESTAX_DATABRICKS_CLI` at the Databricks CLI version the diagnostic names,"
        " or unset it so Nimblestax downloads its own.",
    ),
    "NSTX912": Rule(
        "databricks-cli-download-failed",
        checks="Nimblestax couldn't download its Databricks CLI.",
        why="Nimblestax downloads its pinned Databricks CLI from Databricks' GitHub releases the"
        " first time it needs it, then reuses it. This machine couldn't reach GitHub, or GitHub"
        " refused the download. Nimblestax honours `HTTPS_PROXY` and `NO_PROXY`.",
        example=Example(
            command="nstx deploy --env dev",
            when="This machine has no internet access and no proxy is set.",
        ),
        fix="Check the machine can reach github.com, setting `HTTPS_PROXY` if it needs a proxy."
        " On a machine that can't reach it at all, install the Databricks CLI yourself and point"
        " `NIMBLESTAX_DATABRICKS_CLI` at it.",
    ),
    "NSTX913": Rule(
        "no-databricks-cli-for-platform",
        checks="Databricks publishes no CLI for this operating system and architecture.",
        why="Nimblestax downloads the Databricks CLI archive for this machine. Databricks publishes"
        " one for Linux, macOS and Windows, each on x86-64 and ARM, and nothing else.",
        example=Example(command="nstx deploy --env dev", when="Nimblestax runs on 32-bit Linux."),
        fix="Build or install a Databricks CLI for this machine and point"
        " `NIMBLESTAX_DATABRICKS_CLI` at it.",
    ),
    "NSTX914": Rule(
        "skills-folder-ignored",
        checks="`nstx init` wrote Nimblestax Skills into a folder Git ignores, such as `.claude/`.",
        why="Nimblestax Skills are committed, so everyone on the team, and CI, gets the same"
        " version, and a change to a skill is reviewed in a pull request. In a folder Git ignores,"
        " the skills stay on one machine. This is a warning: `nstx init` still succeeds.",
        example=Example(command="nstx init", when="The repo's `.gitignore` lists `.claude/`."),
        fix="Stop ignoring the folder the diagnostic names, or only its `skills/nimblestax-*`"
        " folders, with a line such as `!.claude/skills/` in `.gitignore`, then commit them.",
        severity="warning",
    ),
    "NSTX915": Rule(
        "skill-edited",
        checks="`nstx skills update` found a Nimblestax Skill edited since Nimblestax wrote it.",
        why="Each Nimblestax Skill records a digest of the text Nimblestax wrote. A skill whose"
        " text no longer matches was edited, and updating it would lose the edit, so `nstx skills"
        " update` writes nothing and shows the difference instead. Exits 2.",
        example=Example(
            command="nstx skills update",
            when="A step was added to `.claude/skills/nimblestax-add-model/SKILL.md`.",
        ),
        fix="Move your edit into a skill of your own, outside the `nimblestax-*` folders, and run"
        " `nstx skills update` again. To replace the edit, run `nstx skills update --force`.",
    ),
    "NSTX916": Rule(
        "unknown-example",
        checks="`nstx init --example` names an example Nimblestax doesn't ship.",
        why="`nstx init --example` writes one of the example projects that ship inside Nimblestax,"
        " so the example always matches the Nimblestax you have installed. The diagnostic lists the"
        " examples there are. It exits 2, because the command line needs a change.",
        example=Example(command="nstx init --example teapot"),
        fix="Name an example the diagnostic lists, such as `nstx init --example kettle`.",
    ),
    "NSTX917": Rule(
        "not-a-build-package",
        checks="`nstx deploy --package` names a folder that isn't a Build Package.",
        why="A Build Package is what `nstx compile` writes: the generated code, every"
        " Environment's settings, and `nimblestax.package.json`, which records the commit it was"
        " built from and a checksum of every file. The folder has no `nimblestax.package.json`,"
        " so Nimblestax can't tell what it holds, and deploys nothing.",
        example=Example(command="nstx deploy --env dev --package src"),
        fix="Pass the folder `nstx compile` wrote, such as `build`, or the artifact CI downloaded"
        " from the run that built it.",
    ),
    "NSTX918": Rule(
        "build-package-changed",
        checks="A file in the Build Package `nstx deploy --package` was given differs from what"
        " was built.",
        why="Every Environment receives the same Build Package, so prod runs exactly what the"
        " stages before it ran. `nimblestax.package.json` holds a checksum of each file, and a"
        " file that was added, removed or edited since breaks that promise, so Nimblestax deploys"
        " nothing. The diagnostic names the files that differ.",
        example=Example(
            command="nstx deploy --env dev --package build",
            when="`build/src/sales/gold/fct_orders.sql` was edited after `nstx compile`.",
        ),
        fix="Deploy the package as `nstx compile` wrote it. To change what it holds, change the"
        " project and build a new one.",
    ),
    "NSTX919": Rule(
        "manifest-copies-not-removed",
        checks="A deploy succeeded, but old copies of the Deployment Manifest couldn't be"
        " removed.",
        why="Each deploy writes the Deployment Manifest next to the deployed bundle, plus a copy"
        " named for its commit, and keeps only the newest 100 copies. Removing older ones failed,"
        " so there are more than 100 for now. Nothing reads the copies to deploy or plan, so the"
        " deploy still succeeds.",
        example=Example(
            command="nstx deploy --env dev",
            when="The deploying identity can write files in the bundle's folder but not delete"
            " them.",
        ),
        fix="Nothing to do now: the next deploy tries again. If this repeats, check that the"
        " deploying identity can delete files in the bundle's `nimblestax/manifests` folder.",
    ),
    "NSTX920": Rule(
        "preview-schema-taken",
        checks="`nstx preview` would deploy into a schema that another project, another person, or"
        " someone by hand already created.",
        why="A Preview Environment creates its own schemas in the Development Environment's"
        " catalogs, each labelled with the project and the person in its properties, and `nstx"
        " preview down` removes them. A schema it didn't create isn't its to fill or to remove, so"
        " `nstx preview` stops before it changes anything. It exits 2.",
        example=Example(
            command="nstx preview",
            when="Another of your projects, `warehouse`, already has a preview with the schema"
            " `dev_sales.u_priya_sharma__silver`.",
        ),
        fix="Remove the other preview with `nstx preview down` from its project, or drop the"
        " schema if nobody needs it, then run `nstx preview` again.",
    ),
    "NSTX921": Rule(
        "example-has-no-preview",
        checks="`nstx preview`, or `nstx test`, was run in an example project, such as Kettle.",
        why="An example already runs in catalogs of its own, made for the person who ran it, so a"
        " Preview Environment would add nothing. It exits 2, and changes nothing in the"
        " workspace.",
        example=Example(command="nstx preview", when="The project is Kettle."),
        fix="Deploy the example directly, with `nstx deploy --env <env>`.",
    ),
    "NSTX923": Rule(
        "no-warehouse-for-tests",
        checks="`nstx test` can't tell which SQL warehouse to run Tests on.",
        why="Tests run as SQL on a warehouse in the Development Environment's workspace, where"
        " every Preview Environment lives. With no `warehouse` set, Nimblestax uses the only one"
        " you can see there, and with several, or none, it won't guess. It exits 2.",
        example=Example(
            command="nstx test",
            when="The workspace has two SQL warehouses, and `nimblestax.platform.yaml` names"
            " neither.",
        ),
        fix="Add `warehouse` under the Development Environment in `nimblestax.platform.yaml`,"
        " set to the ID of the warehouse your team runs Tests on.",
    ),
    "NSTX924": Rule(
        "no-preview-to-test",
        checks="`nstx test` found no Preview Environment of this project to run Tests on.",
        why="Tests run on the tables a Preview Environment built, so the preview must be"
        " deployed, and its refresh must have succeeded, first. Nimblestax knows it did when the"
        " preview's Deployment Manifest is in its bundle folder. It exits 2.",
        example=Example(command="nstx test", when="You haven't run `nstx preview` yet."),
        fix="Run `nstx preview`, or `nstx preview --pr <number>` for a pull request's preview,"
        " then `nstx test` again.",
    ),
    "NSTX925": Rule(
        "no-databricks-sql-access",
        checks="The identity `nstx test` runs as isn't allowed to use Databricks SQL.",
        why="Tests run as SQL on a warehouse, and a workspace only lets an identity use Databricks"
        " SQL once it has the `databricks-sql-access` entitlement. A service principal often"
        " lacks it, because deploying a bundle doesn't need it. It exits 2.",
        example=Example(
            command="nstx test --pr 42",
            when="The Development Environment's deploying identity has no `databricks-sql-access`"
            " entitlement.",
        ),
        fix="Ask a workspace admin to give the identity the `databricks-sql-access` entitlement,"
        " and `CAN USE` on the SQL warehouse Tests run on.",
    ),
    "NSTX926": Rule(
        "no-such-model",
        checks="`--model` names no Gold Model in the project, or a name that more than one Domain"
        " has.",
        why="`--model` picks a Gold Model by its name, such as `fct_orders`, or by its Logical"
        " Name, such as `sales.gold.fct_orders`. A name two Domains share could mean either, so"
        " Nimblestax doesn't guess. It exits 2, before reaching the workspace.",
        example=Example(command="nstx test --model fct_order"),
        fix="Give a Gold Model's name, or its Logical Name when two Domains share the name. The"
        " diagnostic lists the ones it could be.",
    ),
    "NSTX922": Rule(
        "preview-down-outside-fence",
        checks="`nstx preview down` found a schema in the preview's bundle state outside your"
        " `u_<user>__` schemas, or outside the Development Environment's catalogs.",
        why="`nstx preview down` destroys what the preview's bundle deployed, read from its"
        " bundle state. A Preview Environment only ever has your own `u_<user>__` schemas in the"
        " Development Environment's catalogs, so anything else in that state is a mistake, and"
        " `nstx preview down` refuses to remove anything rather than drop it. It exits 2.",
        example=Example(
            command="nstx preview down",
            when="The preview's bundle state holds the schema `prod_sales.silver`.",
        ),
        fix="Find out how that schema got into the preview's bundle state before removing"
        " anything. Drop the preview's own schemas by hand if you need to.",
    ),
}
