"""Project rules. `nsx validate` runs these with no workspace."""

from nimblestax import names, sql
from nimblestax.diagnostics import Diagnostic, error
from nimblestax.kinds.model import Model, References
from nimblestax.kinds.platform import SHARED_DOMAIN
from nimblestax.kinds.seed import Seed
from nimblestax.kinds.source import Source
from nimblestax.load.project import Project
from nimblestax.names import Table


def check(project: Project) -> list[Diagnostic]:
    known = _tables(project)
    views = _materialized_views(project)
    diagnostics = []
    reads: dict[Table, set[Table]] = {}
    for model in project.models:
        file = model.sql_file.relative_to(project.root).as_posix()
        try:
            query = sql.parse(model.query)
        except sql.Unparseable as failure:
            diagnostics.append(_unparseable(file, failure))
            continue
        found = _resolved(project, query.reads)
        streams = _resolved(project, query.streams)
        # A loop across Domains needs a read of another Domain's gold, which is its own failure.
        reads[_gold(project, model)] = {
            read for read in found if read.domain == model.domain.lower()
        }
        diagnostics += _reads(project, known, file, query)
        diagnostics += _build_order(project, known, model, file, found, streams)
        diagnostics += [
            _stream_of_materialized_view(file, streams[read])
            for read in sorted(streams.keys() & views, key=str)
        ]
        diagnostics += [_unqualified(project, file, name) for name in query.unqualified]
        diagnostics += [_computed(project, file, computed) for computed in query.computed]
        diagnostics += [_file_read(file, found) for found in query.file_reads]
        diagnostics += [_raw_placeholder(file, found) for found in query.raw_placeholders]
    return (
        diagnostics
        + _referenced_tables(project, known)
        + _cycles(project, reads)
        + _seeds_named_like_sources(project)
        + _named_like_a_quarantine(project)
    )


def _resolved(project: Project, written: dict[sql.Written, sql.Found]) -> dict[Table, sql.Found]:
    """Each name written in the project's Naming Style, by the table it names."""
    found = {}
    for name, where in written.items():
        table = names.table_named(project.platform, name)
        if table:
            found.setdefault(table, where)
    return found


def _reads(project: Project, known: set[Table], file: str, query: sql.Query):
    """Every read must be a table in the project, by its Logical Name. A real table name, or a
    Logical Name in another Naming Style's shape, gets the Logical Name to write."""
    diagnostics = []
    for read, written in sorted(query.reads.items()):
        if names.table_named(project.platform, read) in known:
            continue
        real = names.table_for_real_name(project, read)
        if real in known:
            diagnostics.append(_real_name(project, file, written, real))
        elif real:
            diagnostics.append(_real_name_of_no_table(project, file, written, real))
        elif in_other_style := _in_other_style(project, known, read):
            diagnostics.append(_other_styles_shape(project, file, written, *in_other_style))
        elif len(read) != names.logical_name_parts(project.platform.naming.style):
            diagnostics.append(_unqualified(project, file, written))
        else:
            diagnostics.append(_unresolved(file, written))
    return diagnostics


def _in_other_style(
    project: Project, known: set[Table], read: sql.Written
) -> tuple[str, Table] | None:
    """The other Naming Style, and the table in the project, a name would be written for."""
    for style in names.other_styles(project.platform):
        table = names.table_named(project.platform, read, style)
        if table in known:
            return style, table
    return None


def _build_order(
    project: Project,
    known: set[Table],
    model: Model,
    file: str,
    reads: dict[Table, sql.Found],
    streams: dict[Table, sql.Found],
) -> list[Diagnostic]:
    """A Gold Model reads silver and gold, never bronze. Its own Domain's are all open to it, but
    from other Domains it reads only Exported silver and the Shared Domain's gold.

    So every read points to a step built earlier, and Domains can't read each other in a loop.
    """
    bronze, silver = (layer.lower() for layer in project.platform.source_layers)
    domain = model.domain.lower()
    published = _published(project, known, domain)
    upserts = {
        Table(source.domain, silver, source.name)
        for source in project.sources
        if source.silver.keys
    }
    diagnostics = []
    for read, written in sorted(reads.items(), key=lambda item: str(item[0])):
        if read not in known:
            continue  # Reported as a table that isn't in the project.
        if read.layer == bronze:
            silver_of = Table(read.domain, silver, read.entity)
            diagnostics.append(_bronze_read(file, written, _logical(project, silver_of)))
        elif read.domain != domain and read not in published:
            if read.layer == silver:
                diagnostics.append(_private_silver(file, written, read))
            else:
                diagnostics.append(_other_domains_gold(file, written, read))
        elif read in streams and read in upserts:
            diagnostics.append(_stream_of_upsert(file, streams[read]))
    return diagnostics


def _published(project: Project, known: set[Table], domain: str) -> set[Table]:
    """What a Gold Model in `domain` may read from other Domains."""
    silver = project.platform.source_layers[1]
    tables = (*project.sources, *project.seeds)
    published = {Table(table.domain, silver, table.name) for table in tables if _is_exported(table)}
    if domain != SHARED_DOMAIN:
        model_layers = {layer.lower() for layer in project.platform.model_layers}
        published |= {
            name for name in known if name.domain == SHARED_DOMAIN and name.layer in model_layers
        }
    return published


def _is_exported(table: Source | Seed) -> bool:
    return table.silver.export if isinstance(table, Source) else table.export


def _materialized_views(project: Project) -> set[Table]:
    """Every table no stream may read: each Seed, and each Gold Model that reads no stream.

    A Gold Model whose SQL can't be read is left out, because it's reported on its own.
    """
    silver = project.platform.source_layers[1]
    views = {Table(seed.domain, silver, seed.name) for seed in project.seeds}
    for model in project.models:
        try:
            streaming = sql.streams(model.query)
        except sql.Unparseable:
            continue
        if not streaming:
            views.add(_gold(project, model))
    return views


def _stream_of_materialized_view(file: str, written: sql.Found) -> Diagnostic:
    return error(
        "NSX212",
        file,
        f"{written.text} is a materialized view, which Databricks can recompute in full, and"
        " `STREAM(...)` reads only new rows. The pipeline would fail when it starts.",
        f"Read it without `STREAM(...)`, as `FROM {written.text}`, so this Gold Model refreshes"
        " from the whole table.",
        written.line,
    )


def _stream_of_upsert(file: str, written: sql.Found) -> Diagnostic:
    return error(
        "NSX211",
        file,
        f"{written.text} is upsert silver, which changes rows in place, and `STREAM(...)` reads"
        " only new rows. The pipeline would fail at runtime, after its first update.",
        f"Read it without `STREAM(...)`, as `FROM {written.text}`, so this Gold Model refreshes"
        " from the whole table.",
        written.line,
    )


def _bronze_read(file: str, written: sql.Found, silver: str) -> Diagnostic:
    return error(
        "NSX210",
        file,
        f"{written.text} is bronze, which only its silver reads. Bronze keeps rows as they"
        " landed, so a Gold Model reads silver, built after it.",
        f"Read {silver} instead.",
        written.line,
    )


def _private_silver(file: str, written: sql.Found, read: Table) -> Diagnostic:
    return error(
        "NSX209",
        file,
        f"{written.text} is silver the {read.domain} Domain hasn't Exported,"
        " so only that Domain reads it.",
        f"Ask the {read.domain} Domain's owner to Export it, with `export: true` under a"
        " Source's `silver:` or in a Seed, or read a table it has Exported.",
        written.line,
    )


def _other_domains_gold(file: str, written: sql.Found, read: Table) -> Diagnostic:
    return error(
        "NSX209",
        file,
        f"{written.text} is the {read.domain} Domain's gold. Nobody reads another Domain's gold,"
        " so each Domain can change its own.",
        f"Build it from silver the {read.domain} Domain has Exported, or move what's shared"
        " into the Shared Domain.",
        written.line,
    )


def _referenced_tables(project: Project, known: set[Table]) -> list[Diagnostic]:
    """A `references` Test reads its other table on the same preview, so the project builds it."""
    diagnostics = []
    for model in project.models:
        for test in model.tests:
            if not isinstance(test, References):
                continue
            to = tuple(test.references.to.split("."))
            if names.table_named(project.platform, to) in known:
                continue
            file = model.config_file.relative_to(project.root).as_posix()
            ours = project.platform.naming.style
            refers = f"`{test.name}` refers to `{test.references.to}`"
            if in_other_style := _in_other_style(project, known, to):
                style, table = in_other_style
                message = (
                    f"{refers}, a Logical Name under `{style}`, and this project's Naming Style"
                    f" is `{ours}`."
                )
                fix = (
                    f"Write `to` as `{_logical(project, table)}`, its Logical Name under `{ours}`."
                )
            else:
                message = f"{refers}, which isn't a table in this project."
                fix = (
                    "Correct `to` to the Logical Name of a Source, Seed or Gold Model, such as"
                    f" `{_logical(project, Table(SHARED_DOMAIN, 'gold', 'dim_customers'))}`."
                )
            diagnostics.append(error("NSX213", file, message, fix))
    return diagnostics


def _gold(project: Project, model: Model) -> Table:
    return Table(model.domain, model.layer, model.name)


def _cycles(project: Project, reads: dict[Table, set[Table]]) -> list[Diagnostic]:
    """Each loop of Gold Models reading each other, found once by a depth-first walk."""
    files = {
        _gold(project, model): model.sql_file.relative_to(project.root).as_posix()
        for model in project.models
    }
    finished: set[Table] = set()
    diagnostics = []

    def dotted(table: Table) -> str:
        return _logical(project, table)

    def walk(model: Table, path: list[Table]) -> None:
        path.append(model)
        for read in sorted(reads[model] & reads.keys(), key=dotted):
            if read in path:
                cycle = path[path.index(read) :]
                first = cycle.index(min(cycle, key=dotted))
                diagnostics.append(_cycle(project, files, cycle[first:] + cycle[:first]))
            elif read not in finished:
                walk(read, path)
        path.pop()
        finished.add(model)

    for model in sorted(reads, key=dotted):
        if model not in finished:
            walk(model, [])
    return sorted(diagnostics, key=lambda diagnostic: diagnostic.file)


def _cycle(project: Project, files: dict[Table, str], cycle: list[Table]) -> Diagnostic:
    loop = " → ".join(_logical(project, model) for model in [*cycle, cycle[0]])
    return error(
        "NSX208",
        files[cycle[0]],
        "A Gold Model can't read itself, directly or through other Gold Models,"
        f" because each must be built before it's read: {loop}.",
        "Remove one of these reads, so each Gold Model reads only tables built before it.",
    )


def _tables(project: Project) -> set[Table]:
    tables = set()
    for source in project.sources:
        for layer in project.platform.source_layers:
            tables.add(Table(source.domain, layer, source.name))
        if source.silver.quarantining:
            silver = project.platform.source_layers[1]
            tables.add(Table(source.domain, silver, source.quarantine))
    for seed in project.seeds:
        tables.add(Table(seed.domain, project.platform.source_layers[1], seed.name))
    for model in project.models:
        tables.add(_gold(project, model))
    return tables


def _seeds_named_like_sources(project: Project) -> list[Diagnostic]:
    silver = project.platform.source_layers[1]
    sources = {(source.domain, source.name) for source in project.sources}
    return [
        error(
            "NSX202",
            seed.config_file.relative_to(project.root).as_posix(),
            f"{_logical(project, Table(seed.domain, silver, seed.name))} is both a Seed and a"
            " Source.",
            "Rename the Seed or the Source, so each has its own table.",
        )
        for seed in project.seeds
        if (seed.domain, seed.name) in sources
    ]


def _named_like_a_quarantine(project: Project) -> list[Diagnostic]:
    """A Source's Quarantine table is in silver's schema, so no other table may take its name."""
    silver = project.platform.source_layers[1]
    quarantines = {
        (source.domain, source.quarantine): source.name
        for source in project.sources
        if source.silver.quarantining
    }
    return [
        error(
            "NSX202",
            table.config_file.relative_to(project.root).as_posix(),
            f"{_logical(project, Table(table.domain, silver, table.name))} is also the"
            " Quarantine table"
            f" of the Source {quarantines[(table.domain, table.name)]}.",
            "Rename this file, so each table has its own name.",
        )
        for table in (*project.sources, *project.seeds)
        if (table.domain, table.name) in quarantines
    ]


def _unresolved(file: str, read: sql.Found) -> Diagnostic:
    return error(
        "NSX201",
        file,
        f"{read.text} isn't a table in this project.",
        "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
        read.line,
    )


def _real_name(project: Project, file: str, real: sql.Found, table: Table) -> Diagnostic:
    logical = _logical(project, table)
    return error(
        "NSX205",
        file,
        f"{real.text} is a real table name, which names one Environment.",
        f"Use its Logical Name, {logical}, so the same SQL works in every Environment.",
        real.line,
    )


def _real_name_of_no_table(
    project: Project, file: str, real: sql.Found, table: Table
) -> Diagnostic:
    logical = _logical(project, table)
    return error(
        "NSX205",
        file,
        f"{real.text} is a real table name, and no table called {logical} is in this project.",
        f"Declare a Source, Seed or Gold Model called {logical}, or correct the name.",
        real.line,
    )


def _other_styles_shape(
    project: Project, file: str, written: sql.Found, style: str, table: Table
) -> Diagnostic:
    ours = project.platform.naming.style
    return error(
        "NSX214",
        file,
        f"{written.text} is a Logical Name under `{style}`, and this project's Naming Style is"
        f" `{ours}`.",
        f"Write it as {_logical(project, table)}, its Logical Name under `{ours}`.",
        written.line,
    )


def _file_read(file: str, found: sql.Found) -> Diagnostic:
    return error(
        "NSX206",
        file,
        f"{found.text} reads data that isn't a table in this project,"
        " so Nimblestax can't check it or point it at each Environment.",
        "A Gold Model reads tables. Declare a Source for these files"
        " and read its silver table by Logical Name.",
        found.line,
    )


def _raw_placeholder(file: str, found: sql.Found) -> Diagnostic:
    return error(
        "NSX207",
        file,
        f"{found.text} holds `${{`, so the pipeline could replace it with a setting's value,"
        " and a raw string can't hold the escape that stops it.",
        "Write it as an ordinary string, doubling each backslash, and Nimblestax escapes the `${`.",
        found.line,
    )


def _logical(project: Project, table: Table) -> str:
    """How the project writes a table's name, in its Naming Style."""
    return names.logical_name(project.platform.naming.style, table)


def _example(project: Project) -> str:
    """A Logical Name to show in a fix: the first Domain's silver `orders`."""
    domain = project.platform.domains[0] if project.platform.domains else "sales"
    return _logical(project, Table(domain, project.platform.source_layers[1], "orders"))


def _unqualified(project: Project, file: str, name: sql.Found) -> Diagnostic:
    return error(
        "NSX201",
        file,
        f"`{name.text}` isn't a CTE or a Logical Name, so Nimblestax can't tell which table it"
        " reads.",
        f"Write the table as a Logical Name, such as {_example(project)},"
        " or define a CTE with this name.",
        name.line,
    )


def _unparseable(file: str, failure: sql.Unparseable) -> Diagnostic:
    return error(
        "NSX203",
        file,
        f"Nimblestax can't read this SQL, so it can't tell what it reads. {failure.reason}",
        "Make the file one Databricks SQL query that runs on its own.",
        failure.line,
    )


def _computed(project: Project, file: str, computed: sql.Found) -> Diagnostic:
    return error(
        "NSX204",
        file,
        f"{computed.text} builds a table name as the query runs,"
        " so Nimblestax can't see what it reads.",
        f"Write the table as a Logical Name, such as {_example(project)},"
        " so every read shows in review.",
        computed.line,
    )
