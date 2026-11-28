"""Picks Gold Models by name, as `--model` gives them: a Model's name, such as `fct_orders`, or
its Logical Name, such as `sales.gold.fct_orders`, when more than one Model has that name."""

from collections.abc import Sequence

from nimblestax.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error
from nimblestax.kinds.model import Model
from nimblestax.load.project import Project


def logical_name(model: Model) -> str:
    return f"{model.domain}.{model.layer}.{model.name}".lower()


def one(project: Project, name: str) -> Model:
    """The one Gold Model `name` picks."""
    wanted = name.strip().lower()
    found = [m for m in project.models if wanted in (logical_name(m), m.name.lower())]
    if len(found) != 1:
        raise Failure([_unpicked(name, found or list(project.models))], USAGE_OR_ENVIRONMENT)
    return found[0]


def several(project: Project, names: Sequence[str]) -> list[Model]:
    """The Gold Models `names` pick, in the project's order. One value may list several,
    separated by commas. No names picks every Model."""
    # A name is made of identifiers, so it never holds a comma.
    names = [part.strip() for given in names for part in given.split(",") if part.strip()]
    if not names:
        return list(project.models)
    picked = {logical_name(one(project, name)) for name in names}
    return [model for model in project.models if logical_name(model) in picked]


def _unpicked(name: str, candidates: list[Model]) -> Diagnostic:
    listed = ", ".join(f"`{logical_name(model)}`" for model in candidates)
    if len(candidates) > 1 and all(model.name.lower() == name.lower() for model in candidates):
        # Two Domains, or two model Layers of one Domain, can each have a Model of one name.
        message = f"`{name}` names more than one Gold Model."
        fix = f"Give its Logical Name instead, one of: {listed}."
    else:
        message = f"`{name}` isn't a Gold Model in this project."
        fix = f"Give a Gold Model's name or its Logical Name, one of: {listed}."
    return error("NSX926", "", message, fix)
