"""Stable identifier helpers for DBOS workflow and artifact names."""

import re
from urllib.parse import urlparse

from unidecode import unidecode

DEFAULT_WORKFLOW_GIT_URL = "git@github.com:antonov-andrey/brand-size-chart.git"
_COMPONENT_INVALID_RE = re.compile(r"[^a-z0-9._-]+")
_COMPONENT_REPEAT_RE = re.compile(r"_+")


def dbos_identifier(*component_list: str) -> str:
    """Build a stable hierarchical DBOS identifier.

    Args:
        *component_list: Raw identifier components.

    Returns:
        A stable DBOS-safe identifier.
    """
    if not component_list:
        raise ValueError("DBOS identifier requires at least one component.")
    return "/".join(dbos_identifier_component(component) for component in component_list)


def dbos_identifier_component(raw_component: str) -> str:
    """Normalize one raw identifier component.

    Args:
        raw_component: Raw identifier component.

    Returns:
        A lowercase ASCII component safe for DBOS IDs and artifact path segments.

    Raises:
        ValueError: If the raw component contains a slash or normalizes to an empty value.
    """
    if "/" in raw_component:
        raise ValueError("Raw slash is forbidden in DBOS identifier components.")

    ascii_component = unidecode(raw_component).strip().lower()
    underscore_component = _COMPONENT_INVALID_RE.sub("_", ascii_component)
    component = _COMPONENT_REPEAT_RE.sub("_", underscore_component).strip("_")
    if not component or component in {".", ".."} or not any(character.isalnum() for character in component):
        raise ValueError("DBOS identifier component cannot be empty.")
    return component


def workflow_project_name(*, git_url: str = DEFAULT_WORKFLOW_GIT_URL) -> str:
    """Return the stable DBOS project name computed from a workflow git URL.

    Args:
        git_url: Workflow repository git URL.

    Returns:
        Workflow project name.
    """
    if git_url.startswith("git@") and ":" in git_url:
        path = git_url.split(":", maxsplit=1)[1]
    else:
        path = urlparse(git_url).path
    path = path.removeprefix("/").removesuffix(".git")
    project_name = "__".join(dbos_identifier_component(component) for component in path.split("/") if component)
    if not project_name:
        raise ValueError("Workflow git URL does not contain a project path.")
    return project_name
