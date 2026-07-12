"""Static SQLite state descriptors and read-only accepted-table access."""

from pathlib import Path

from workflow_container_runtime.state import SqliteStateReader, SqliteStateTable

from brand_size_chart.artifact.layout import ArtifactLayout
from brand_size_chart.model.chart import BrandSizeChart
from brand_size_chart.model.source import (
    SourceDiscoveryAcceptedTable,
    SourceDiscoveryMarketBoundary,
    SourceDiscoveryProductSearch,
    SourceDiscoveryQuery,
    SourceDiscoveryTable,
    SourceDiscoveryUrl,
    SourceDiscoveryUrlProductSearch,
    SourceTypeResult,
    SourceTypeResultList,
    source_discovery_accepted_table_list_validate,
)
from brand_size_chart.source.source_type_registry import SOURCE_TYPE_REGISTRY

SOURCE_DISCOVERY_QUERY_TABLE = SqliteStateTable(
    name="discovery_query",
    record_model=SourceDiscoveryQuery,
    primary_key_field_name_tuple=("query",),
)
SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE = SqliteStateTable(
    name="market_boundary",
    record_model=SourceDiscoveryMarketBoundary,
    primary_key_field_name_tuple=("market_scope_key",),
)
SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE = SqliteStateTable(
    name="product_search_worklist",
    record_model=SourceDiscoveryProductSearch,
    primary_key_field_name_tuple=("product_type", "search_sex"),
)
SOURCE_DISCOVERY_URL_TABLE = SqliteStateTable(
    name="source_url",
    record_model=SourceDiscoveryUrl,
    primary_key_field_name_tuple=("url",),
)
SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE = SqliteStateTable(
    name="source_url_product_search",
    record_model=SourceDiscoveryUrlProductSearch,
    primary_key_field_name_tuple=("url", "product_type", "search_sex"),
)
SOURCE_DISCOVERY_TABLE = SqliteStateTable(
    name="source_table",
    record_model=SourceDiscoveryTable,
    primary_key_field_name_tuple=("size_group_key", "market_scope_key"),
)
SOURCE_DISCOVERY_TABLE_BY_NAME_MAP = {
    table.name: table
    for table in (
        SOURCE_DISCOVERY_QUERY_TABLE,
        SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
        SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
        SOURCE_DISCOVERY_URL_TABLE,
        SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
        SOURCE_DISCOVERY_TABLE,
    )
}


class SourceDiscoveryDatabaseReader:
    """Read accepted source tables through one declared source-discovery database."""

    def __init__(self) -> None:
        """Store the runtime-owned SQLite URI read-only access boundary."""

        self._sqlite_state_reader = SqliteStateReader()

    def accepted_table_list_get_for_source_type_result_list(
        self,
        *,
        result_dir: Path,
        source_type_result_list: SourceTypeResultList,
    ) -> list[SourceDiscoveryAcceptedTable]:
        """Return uniquely derived accepted rows for readable successful source results.

        Args:
            result_dir: Exact absolute root that owns every source result artifact.
            source_type_result_list: Complete source-type workflow results.

        Returns:
            Unique accepted source tables from successful table-available results.
        """

        return source_discovery_accepted_table_list_validate(
            [
                accepted_table
                for source_type_result in source_type_result_list
                if source_type_result.status == "success"
                and source_type_result.source_discovery_result is not None
                and source_type_result.source_discovery_result.outcome == "table_available"
                for accepted_table in self.accepted_table_list_get(
                    result_dir=result_dir,
                    source_type_result=source_type_result,
                )
            ]
        )

    def accepted_table_list_get(
        self,
        *,
        result_dir: Path,
        source_type_result: SourceTypeResult,
    ) -> list[SourceDiscoveryAcceptedTable]:
        """Return accepted rows with validated deterministic chart handles.

        Args:
            result_dir: Exact absolute root that owns the source result artifacts.
            source_type_result: Complete source-type result that declares one readable database.

        Returns:
            Accepted source tables in source-table primary-key order.

        Raises:
            RuntimeError: If the handoff cannot safely identify valid accepted source rows and charts.
        """

        database_path = self._database_path_get(result_dir=result_dir, source_type_result=source_type_result)
        layout = ArtifactLayout(result_dir)
        source_priority = SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type_result.source_type)
        accepted_table_list: list[SourceDiscoveryAcceptedTable] = []
        for source_table in self._sqlite_state_reader.list(database_path, SOURCE_DISCOVERY_TABLE):
            if source_table.state != "accepted":
                continue
            chart_path = layout.source_discovery_chart_path(
                database_path.parent,
                source_table.size_group_key,
                source_table.market_scope_key,
            )
            chart_artifact_path = layout.artifact_path(chart_path)
            try:
                BrandSizeChart.model_validate_json(chart_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"Accepted source chart is missing or invalid: {chart_artifact_path}") from exc
            accepted_table_list.append(
                SourceDiscoveryAcceptedTable(
                    chart_path=chart_artifact_path,
                    source_priority=source_priority,
                    source_table=source_table,
                    source_type=source_type_result.source_type,
                )
            )
        if not accepted_table_list:
            raise RuntimeError("A table_available source-discovery handoff must contain accepted source tables.")
        return accepted_table_list

    def _database_path_get(self, *, result_dir: Path, source_type_result: SourceTypeResult) -> Path:
        """Resolve one declared source-discovery database artifact under an absolute result root.

        Args:
            result_dir: Exact absolute result root.
            source_type_result: Complete source result carrying the database handle.

        Returns:
            Existing resolved SQLite database path.

        Raises:
            RuntimeError: If the result does not declare one safe readable database artifact.
        """

        source_discovery_result = source_type_result.source_discovery_result
        if source_type_result.status != "success":
            raise RuntimeError("Accepted source tables require a successful complete SourceTypeResult.")
        if source_discovery_result is None:
            raise RuntimeError("Source type result does not declare source discovery.")
        if source_discovery_result.outcome != "table_available":
            raise RuntimeError("Accepted source tables require a table_available source-discovery outcome.")
        if not result_dir.is_absolute():
            raise RuntimeError("Source-discovery result_dir must be absolute.")
        database_handle = source_discovery_result.source_discovery_database_path
        database_relative_path = Path(database_handle)
        if (
            not database_handle
            or database_handle != database_handle.strip()
            or database_relative_path.is_absolute()
            or "\\" in database_handle
            or ".." in database_relative_path.parts
            or database_relative_path.as_posix() != database_handle
        ):
            raise RuntimeError("Source-discovery database handle must be normalized and result-relative.")
        result_dir = result_dir.resolve()
        database_path = (result_dir / database_relative_path).resolve()
        try:
            database_path.relative_to(result_dir)
        except ValueError as exc:
            raise RuntimeError("Source-discovery database handle escapes result_dir.") from exc
        if not database_path.is_file():
            raise RuntimeError("Declared source-discovery database artifact is missing.")
        if ArtifactLayout(result_dir).artifact_path(database_path) != database_handle:
            raise RuntimeError("Source-discovery database handle does not round-trip through ArtifactLayout.")
        return database_path
