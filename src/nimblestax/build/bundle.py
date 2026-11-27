"""Writes `databricks.yaml`: the resources, plus the placeholder values for each target."""

from dataclasses import dataclass

import yaml

from nimblestax import names, sql
from nimblestax.kinds.platform import PREVIEW
from nimblestax.load.project import Project

REFRESH_JOB = "refresh"
PREVIEW_TARGET = PREVIEW

# The labels on every schema a preview creates, naming the project and whose preview it is.
PROJECT_LABEL = "nimblestax.project"
USER_LABEL = "nimblestax.user"
PULL_REQUEST_LABEL = "nimblestax.pull_request"


@dataclass(frozen=True)
class Preview:
    """Whose Preview Environment the bundle's `preview` target deploys.

    `labels` mark its schemas as its own, beside the project's, and `folder` is where its bundle
    state sits, under `~/.bundle/<project>/` of whoever deploys it.
    """

    prefix: str
    owner: str
    labels: dict[str, str]
    folder: str
    remove: str


def personal(user: str) -> Preview:
    """A person's own preview, deployed from their laptop as themselves."""
    return Preview(
        names.personal_prefix(user),
        user,
        {USER_LABEL: user},
        PREVIEW_TARGET,
        "nsx preview down",
    )


def pull_request(number: int) -> Preview:
    """A pull request's preview, deployed by CI as the Development Environment's identity.

    Its folder name isn't an identifier, so no Environment's bundle state can share it.
    """
    return Preview(
        names.pull_request_prefix(number),
        f"pull request {number}",
        {PULL_REQUEST_LABEL: str(number)},
        f"pull-requests/{number}",
        f"nsx preview down --pr {number}",
    )

# One retry survives a one-off blip. An error a retry can't fix, such as a bad row in append-only
# bronze, then fails in about a minute instead of waiting through the default five retries.
UPDATE_RETRIES = {"pipelines.numUpdateRetryAttempts": "1"}


def render(project: Project, preview: Preview | None = None) -> str:
    """The bundle, with a target per Environment, and with `preview` a Preview Environment's."""
    platform = project.platform
    variables = list(names.settings(project, next(iter(platform.hosts))))
    pipelines = {}
    for domain in platform.domains:
        if any(item.domain == domain for item in (*project.sources, *project.seeds)):
            pipelines[f"{domain}_ingest"] = _pipeline(project, domain, "ingest")
        if any(model.domain == domain for model in project.models):
            pipelines[f"{domain}_gold"] = _pipeline(project, domain, "gold")
    upstream = _upstream(project, set(pipelines))
    tasks = [_task(pipeline, upstream.get(pipeline, [])) for pipeline in pipelines]
    targets = {env: _target(project, env) for env in platform.hosts}
    if preview:
        targets[PREVIEW_TARGET] = _preview_target(project, preview, pipelines)
    return yaml.safe_dump(
        {
            "bundle": {"name": platform.name},
            # Bundle sync skips gitignored files, and `nsx init` gitignores the package.
            "sync": {"include": ["src/**"]},
            "variables": {name: {"description": name} for name in variables},
            "targets": targets,
            "resources": {
                "pipelines": pipelines,
                "jobs": {REFRESH_JOB: {"name": _name(project, "refresh"), "tasks": tasks}},
            },
        },
        sort_keys=False,
    )


def _name(project: Project, *parts: str) -> str:
    """A pipeline or Job name, with the Environment in it, so Environments can share a workspace.

    Databricks refuses a second pipeline with the same name.
    """
    return "_".join((project.platform.name, "${bundle.target}", *parts))


def _target(project: Project, env: str) -> dict:
    """One Environment's workspace and placeholder values, and its Job's schedule if it has one."""
    target: dict = {
        "workspace": {"host": project.platform.hosts[env]},
        "variables": names.settings(project, env),
    }
    schedule = project.platform.environments[env].schedule
    if schedule:
        paused = schedule.paused
        if paused is None:
            paused = env != project.platform.production_environment
        target["resources"] = {
            "jobs": {
                REFRESH_JOB: {
                    "schedule": {
                        "quartz_cron_expression": schedule.cron,
                        "timezone_id": schedule.timezone,
                        "pause_status": "PAUSED" if paused else "UNPAUSED",
                    }
                }
            }
        }
    return target


def _preview_target(project: Project, preview: Preview, pipelines: dict) -> dict:
    """A Preview Environment in the Development Environment's workspace and catalogs.

    It creates its own schemas, labelled with the project, so destroying its bundle removes
    them and nothing else. Its pipelines and Job carry the prefix, and it has no schedule.
    """
    platform = project.platform
    prefix = preview.prefix
    schemas = {
        key: {
            "catalog_name": catalog,
            "name": schema,
            "comment": f"A Preview Environment of {platform.name}, for {preview.owner}. Nimblestax"
            f" created it, and `{preview.remove}` removes it.",
            "properties": {PROJECT_LABEL: platform.name, **preview.labels},
        }
        for key, (catalog, schema) in names.preview_schemas(platform, prefix).items()
    }
    overrides = {
        key: {
            "name": f"{prefix}{platform.name}_{key}",
            # Its default schema comes from the resource, so the schema is created first and
            # destroyed last.
            "schema": f"${{resources.schemas.{_default_schema(project, key)}.name}}",
        }
        for key in pipelines
    }
    return {
        "workspace": {
            "host": platform.hosts[platform.development_environment],
            "root_path": f"~/.bundle/{platform.name}/{preview.folder}",
        },
        # A failed update isn't retried, and compute is kept for the next push. The bundle's own
        # development mode isn't used, because it renames everything its own way.
        "presets": {"pipelines_development": True},
        "variables": names.preview_settings(project, prefix),
        "resources": {
            "schemas": schemas,
            "pipelines": overrides,
            "jobs": {REFRESH_JOB: {"name": f"{prefix}{platform.name}_refresh"}},
        },
    }


def _default_schema(project: Project, pipeline: str) -> str:
    """The key of a pipeline's default schema among the preview's schema resources."""
    domain, group = pipeline.rsplit("_", 1)
    return f"{domain}_{_default_layer(project, group)}".lower()


def _default_layer(project: Project, group: str) -> str:
    """A pipeline's default Layer. Every table is written by its full name, so it is only the
    pipeline's default. Model Layers have no order, so the first by name keeps it the same
    however the list is ordered."""
    platform = project.platform
    return platform.source_layers[0] if group == "ingest" else min(platform.model_layers)


def _pipeline(project: Project, domain: str, group: str) -> dict:
    platform = project.platform
    layer = _default_layer(project, group)
    keys = names.settings(project, next(iter(platform.hosts)))
    return {
        "name": _name(project, domain, group),
        "catalog": f"${{var.{names.catalog_setting(domain, layer)}}}",
        "schema": f"${{var.{names.schema_setting(domain, layer)}}}",
        "serverless": True,
        "channel": "CURRENT",
        "libraries": [{"glob": {"include": f"src/{domain}/{group}/**"}}],
        "configuration": {**{key: f"${{var.{key}}}" for key in keys}, **UPDATE_RETRIES},
    }


def _upstream(project: Project, pipelines: set[str]) -> dict[str, list[str]]:
    """The pipelines each gold pipeline reads from, so its task waits only for those.

    Ingest pipelines read only files, so they wait for nothing. Silver comes from its Domain's
    ingest pipeline, and gold of another Domain, which can only be the Shared Domain's, from its
    gold pipeline.
    """
    source_layers = {layer.lower() for layer in project.platform.source_layers}
    # Logical Names are lowercase, and pipelines are keyed by the Domain as the contract writes it.
    domains = {domain.lower(): domain for domain in project.platform.domains}
    upstream: dict[str, list[str]] = {}
    for model in project.models:
        try:
            reads = sql.reads(model.query)
        except sql.Unparseable:
            continue  # `nsx validate` reports it, and `nsx deploy` refuses it.
        reader = f"{model.domain}_gold"
        needed = upstream.setdefault(reader, [])
        for read in sorted(reads, key=str):
            group = "ingest" if read.layer in source_layers else "gold"
            pipeline = f"{domains.get(read.domain, read.domain)}_{group}"
            if pipeline in pipelines and pipeline != reader and pipeline not in needed:
                needed.append(pipeline)
    return upstream


def _task(pipeline: str, needs: list[str]) -> dict:
    task: dict = {
        "task_key": pipeline,
        "max_retries": 0,
        "pipeline_task": {"pipeline_id": f"${{resources.pipelines.{pipeline}.id}}"},
    }
    if needs:
        task["depends_on"] = [{"task_key": needed} for needed in needs]
    return task
