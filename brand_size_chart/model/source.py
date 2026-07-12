"""Source-discovery current-state rows and read-only downstream handoffs."""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, ConfigDict, field_validator
from workflow_container_contract import WorkflowResult
from workflow_container_runtime.step import BrowserActionResult

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel, identifier_component_validate

SourceDiscoveryQueryState = Literal["searched", "failed"]
SourceDiscoveryProductSearchState = Literal["pending", "searched", "rejected"]
SourceDiscoveryUrlState = Literal["opened", "rejected"]
SourceDiscoveryTableState = Literal["candidate", "accepted", "market_filtered", "market_conflict"]
SourceDiscoveryOutcome = Literal["table_available", "no_table", "market_conflict"]


def browser_url_validate(value: str) -> str:
    """Validate one browser-openable HTTP or HTTPS URL.

    Args:
        value: Candidate browser URL.

    Returns:
        Validated unmodified browser URL.

    Raises:
        ValueError: If the URL is not an absolute HTTP or HTTPS URL with a host.
    """

    if not value or value.strip() != value or any(character.isspace() for character in value):
        raise ValueError("browser URL must not be empty or contain whitespace")
    try:
        parsed_url = urlsplit(value)
        _ = parsed_url.port
    except ValueError as exc:
        raise ValueError("browser URL must use a valid host and port") from exc
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or parsed_url.hostname is None:
        raise ValueError("browser URL must be an absolute http or https URL with a host")
    return value


BrowserUrl = Annotated[str, AfterValidator(browser_url_validate)]


def market_scope_key_validate(value: str) -> str:
    """Validate one deterministic source-table market scope identity.

    Args:
        value: Candidate lowercase market scope key.

    Returns:
        Validated source-table market scope key.

    Raises:
        ValueError: If the key is not one supported deterministic market scope.
    """

    value = identifier_component_validate(value)
    if "__" in value:
        raise ValueError("market_scope_key must not contain the reserved __ separator")
    if value in {"global", "eu"}:
        return value
    scope_component_list = value.split("_")
    if (
        not scope_component_list
        or any(
            len(country_code) != 2 or not country_code.isalpha() or country_code != country_code.lower()
            for country_code in scope_component_list
        )
        or scope_component_list != sorted(set(scope_component_list))
    ):
        raise ValueError("market_scope_key must be global, eu, or a sorted lowercase alpha-2 country group")
    return value


_MarketScopeKey = Annotated[str, AfterValidator(market_scope_key_validate)]


def size_group_key_validate(value: str) -> str:
    """Validate one source-derived physical chart identity component.

    Args:
        value: Candidate physical table identity.

    Returns:
        Validated physical table identity.

    Raises:
        ValueError: If the identifier uses the reserved component separator.
    """

    value = identifier_component_validate(value)
    if "__" in value:
        raise ValueError("size_group_key must not contain the reserved __ separator")
    return value


class SourceDiscoveryResult(BrowserActionResult):
    """Public source-discovery result and DBOS handoff."""

    outcome: SourceDiscoveryOutcome
    source_discovery_database_path: str


class SourceDiscoveryQuery(StrictBaseModel):
    """Current source-discovery query row stored by its natural key."""

    evidence_path_list: list[str]
    query: str
    reason: str
    state: SourceDiscoveryQueryState


class SourceDiscoveryMarketBoundary(StrictBaseModel):
    """Selected source market boundary persisted before table discovery."""

    evidence_path_list: list[str]
    market_scope_key: _MarketScopeKey
    reason: str
    source_url: BrowserUrl


class SourceDiscoveryProductSearch(StrictBaseModel):
    """Current product-type search-branch worklist row."""

    evidence_path_list: list[str]
    product_type: str
    reason: str
    search_sex: str
    state: SourceDiscoveryProductSearchState


class SourceDiscoveryUrl(StrictBaseModel):
    """Current opened or rejected source URL row."""

    evidence_path_list: list[str]
    reason: str
    state: SourceDiscoveryUrlState
    url: BrowserUrl


class SourceDiscoveryUrlProductSearch(StrictBaseModel):
    """Persist one source URL to one product search branch."""

    product_type: str
    search_sex: str
    url: BrowserUrl


class SourceDiscoveryTable(StrictBaseModel):
    """Current physical source-table row keyed by group and market scope."""

    evidence_path_list: list[str]
    market_scope_key: _MarketScopeKey
    reason: str
    size_group_key: IdentifierComponent
    source_title: str
    source_url: BrowserUrl
    state: SourceDiscoveryTableState

    @field_validator("size_group_key")
    @classmethod
    def size_group_key_validate(cls, value: str) -> str:
        """Reserve the double underscore for chart-path component separation.

        Args:
            value: Candidate validated physical table key.

        Returns:
            Validated physical table key.
        """

        return size_group_key_validate(value)


class SourceDiscoveryAcceptedTable(StrictBaseModel):
    """Transient accepted source-table query result for downstream decisions."""

    chart_path: str
    source_priority: int
    source_table: SourceDiscoveryTable
    source_type: IdentifierComponent


class SourceDiscoveryChartWriteResult(StrictBaseModel):
    """Outcome of one bounded source-discovery chart publication attempt."""

    status: Literal["created", "unchanged", "conflict"]


class SourceTypeResult(WorkflowResult):
    """Workflow result for one source type loop."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    source_type: str
    source_discovery_result: SourceDiscoveryResult | None = None


def source_type_result_list_validate(value: list[SourceTypeResult]) -> list[SourceTypeResult]:
    """Require unique source types and declared source-discovery database paths.

    Args:
        value: Complete source-type workflow results supplied to one downstream owner.

    Returns:
        The validated unmodified source-type result list.

    Raises:
        ValueError: If two results claim one source type or one declared database artifact.
    """

    source_type_set: set[str] = set()
    source_discovery_database_path_set: set[str] = set()
    for source_type_result in value:
        if source_type_result.source_type in source_type_set:
            raise ValueError(
                f"source_type_result_list contains duplicate source_type: {source_type_result.source_type}"
            )
        source_type_set.add(source_type_result.source_type)
        source_discovery_result = source_type_result.source_discovery_result
        if source_discovery_result is None:
            continue
        source_discovery_database_path = source_discovery_result.source_discovery_database_path
        if source_discovery_database_path in source_discovery_database_path_set:
            raise ValueError(
                "source_type_result_list contains duplicate source_discovery_database_path: "
                f"{source_discovery_database_path}"
            )
        source_discovery_database_path_set.add(source_discovery_database_path)
    return value


SourceTypeResultList = Annotated[list[SourceTypeResult], AfterValidator(source_type_result_list_validate)]


def source_discovery_accepted_table_list_validate(
    value: list[SourceDiscoveryAcceptedTable],
) -> list[SourceDiscoveryAcceptedTable]:
    """Require one transient accepted-table owner for every derived chart path.

    Args:
        value: Aggregated transient accepted-table query results.

    Returns:
        The validated unmodified accepted-table list.

    Raises:
        ValueError: If several accepted rows derive the same chart artifact identity.
    """

    chart_path_set: set[str] = set()
    for accepted_table in value:
        if accepted_table.chart_path in chart_path_set:
            raise ValueError(f"Accepted source tables derive duplicate chart_path: {accepted_table.chart_path}")
        chart_path_set.add(accepted_table.chart_path)
    return value
