"""Mechanical validation for SQLite-backed source discovery."""

from pathlib import Path

from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    BrandSizeChart,
    SourceDiscoveryInput,
    SourceDiscoveryMarketBoundary,
    SourceDiscoveryProductSearch,
    SourceDiscoveryQuery,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceDiscoveryUrl,
    SourceDiscoveryUrlProductSearch,
    WorkflowBrandSizeChartInput,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
    SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
    SOURCE_DISCOVERY_QUERY_TABLE,
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_URL_TABLE,
    SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
)


class SourceDiscoveryValidator:
    """Validate terminal source-discovery current state without domain reconstruction."""

    def __init__(self, *, sqlite_state_store: SqliteStateStore) -> None:
        """Store the shared current-state reader.

        Args:
            sqlite_state_store: Shared state store injected by the composition root.
        """

        self._sqlite_state_store = sqlite_state_store

    def validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: SourceDiscoveryInput,
        result: SourceDiscoveryResult,
    ) -> None:
        """Validate one source-discovery result against its sibling state database.

        Args:
            execution_context: Current step context.
            step_input: Persisted source-discovery input.
            result: Candidate public handoff.

        Raises:
            StepResultValidationError: If current rows, chart artifacts, or outcome violate the mechanical contract.
        """

        state_database_path = state_database_path_get(execution_context.step_instance_dir)
        expected_database_path = ArtifactLayout(execution_context.result_dir).artifact_path(state_database_path)
        if result.source_discovery_database_path != expected_database_path:
            self._fail("Return the exact sibling state.sqlite3 result-relative database handle.")

        try:
            query_list = self._sqlite_state_store.list(state_database_path, SOURCE_DISCOVERY_QUERY_TABLE)
            market_boundary_list = self._sqlite_state_store.list(
                state_database_path,
                SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
            )
            product_search_list = self._sqlite_state_store.list(
                state_database_path, SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE
            )
            url_list = self._sqlite_state_store.list(state_database_path, SOURCE_DISCOVERY_URL_TABLE)
            url_product_search_list = self._sqlite_state_store.list(
                state_database_path,
                SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
            )
            table_list = self._sqlite_state_store.list(state_database_path, SOURCE_DISCOVERY_TABLE)
        except (OSError, RuntimeError, ValueError) as exc:
            self._fail(f"Initialize every declared source-discovery table with its static schema: {exc}")

        self._evidence_list_validate(
            execution_context=execution_context,
            evidence_target_path=step_input.evidence_write_target.artifact_path,
            evidence_path_list=[
                evidence_path
                for record in [*query_list, *market_boundary_list, *product_search_list, *url_list, *table_list]
                for evidence_path in record.evidence_path_list
            ],
        )
        self._query_list_validate(query_list)
        self._url_list_validate(url_list)
        self._market_boundary_list_validate(market_boundary_list=market_boundary_list, url_list=url_list)
        self._product_search_list_validate(
            execution_context=execution_context,
            step_input=step_input,
            url_list=url_list,
            url_product_search_list=url_product_search_list,
            product_search_list=product_search_list,
        )
        self._table_list_validate(
            execution_context=execution_context,
            evidence_target_path=step_input.evidence_write_target.artifact_path,
            table_list=table_list,
            url_list=url_list,
        )

        if any(table.state == "candidate" for table in table_list):
            self._fail("Finalize every candidate source-table row before a source-discovery handoff.")
        expected_outcome = (
            "market_conflict"
            if any(table.state == "market_conflict" for table in table_list)
            else "table_available" if any(table.state == "accepted" for table in table_list) else "no_table"
        )
        if result.outcome != expected_outcome:
            self._fail(f"Derive outcome exactly from finalized source-table states: expected {expected_outcome}.")
        if result.outcome == "no_table":
            if table_list:
                self._fail("Do not persist source-table rows for a no_table handoff.")
            if not query_list:
                self._fail("Persist complete terminal discovery evidence before a no_table handoff.")

    def _evidence_list_validate(
        self,
        *,
        execution_context: WorkflowStepExecutionContext,
        evidence_target_path: str,
        evidence_path_list: list[str],
    ) -> None:
        """Validate evidence paths against the declared evidence artifact root.

        Args:
            execution_context: Current step context.
            evidence_target_path: Result-relative evidence root.
            evidence_path_list: Candidate result-relative evidence paths.
        """

        evidence_target = (execution_context.result_dir / evidence_target_path).resolve()
        for evidence_path in evidence_path_list:
            relative_path = Path(evidence_path)
            if (
                not evidence_path
                or relative_path.is_absolute()
                or "\\" in evidence_path
                or ".." in relative_path.parts
                or relative_path.as_posix() != evidence_path
            ):
                self._fail(f"Keep evidence paths normalized and result-relative: {evidence_path!r}.")
            resolved_path = (execution_context.result_dir / relative_path).resolve()
            if not resolved_path.is_relative_to(evidence_target) or not resolved_path.is_file():
                self._fail(f"Keep evidence paths inside the declared materialized evidence target: {evidence_path!r}.")

    def _fail(self, feedback: str) -> None:
        """Raise one stable mechanical-validation failure.

        Args:
            feedback: Actionable correction message.

        Raises:
            StepResultValidationError: Always.
        """

        raise StepResultValidationError(feedback_list=[feedback])

    def _table_list_validate(
        self,
        *,
        execution_context: WorkflowStepExecutionContext,
        evidence_target_path: str,
        table_list: list[SourceDiscoveryTable],
        url_list: list[SourceDiscoveryUrl],
    ) -> None:
        """Validate chart, evidence, source URL, and accepted-group closure for table rows.

        Args:
            execution_context: Current step context.
            evidence_target_path: Declared evidence root.
            table_list: Persisted source-table rows.
            url_list: Persisted source URL rows.
        """

        opened_url_set = {url.url for url in url_list if url.state == "opened"}
        accepted_size_group_key_list = [table.size_group_key for table in table_list if table.state == "accepted"]
        if len(accepted_size_group_key_list) != len(set(accepted_size_group_key_list)):
            self._fail("Keep no more than one accepted source-table row per size_group_key.")
        layout = ArtifactLayout(execution_context.result_dir)
        database_identity_set = {(table.size_group_key, table.market_scope_key) for table in table_list}
        expected_chart_path_set = {
            layout.source_discovery_chart_path(execution_context.step_instance_dir, size_group_key, market_scope_key)
            for size_group_key, market_scope_key in database_identity_set
        }
        chart_dir = execution_context.step_instance_dir / "chart"
        for table in table_list:
            if not table.reason.strip() or not table.source_title.strip() or table.source_url not in opened_url_set:
                self._fail("Every source-table row needs a reason, title, and opened source URL.")
            if not table.evidence_path_list:
                self._fail("Every source-table row needs materialized evidence.")
            chart_path = layout.source_discovery_chart_path(
                execution_context.step_instance_dir,
                table.size_group_key,
                table.market_scope_key,
            )
            try:
                BrandSizeChart.model_validate_json(chart_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                self._fail(f"Persist one valid chart at every exact source-table identity path: {exc}")
        if chart_dir.exists():
            for artifact_path in chart_dir.rglob("*"):
                if artifact_path.is_file() and artifact_path not in expected_chart_path_set:
                    self._fail(
                        f"Remove orphan source-discovery chart artifact: {artifact_path.relative_to(chart_dir)}."
                    )
        _ = evidence_target_path

    def _query_list_validate(self, query_list: list[SourceDiscoveryQuery]) -> None:
        """Validate evidence-backed terminal discovery-query rows.

        Args:
            query_list: Persisted terminal discovery-query rows.
        """

        for query in query_list:
            if not query.reason.strip() or not query.evidence_path_list:
                self._fail("Every terminal query row needs an evidence-backed reason.")

    def _market_boundary_list_validate(
        self,
        *,
        market_boundary_list: list[SourceDiscoveryMarketBoundary],
        url_list: list[SourceDiscoveryUrl],
    ) -> None:
        """Require one evidence-backed selected source market boundary.

        Args:
            market_boundary_list: Persisted selected market rows.
            url_list: Persisted source URL rows.
        """

        if len(market_boundary_list) != 1:
            self._fail("Persist exactly one selected market boundary before table discovery.")
        market_boundary = market_boundary_list[0]
        opened_url_set = {url.url for url in url_list if url.state == "opened"}
        if (
            not market_boundary.reason.strip()
            or not market_boundary.evidence_path_list
            or market_boundary.source_url not in opened_url_set
        ):
            self._fail("The selected market boundary needs an evidence-backed reason and opened source URL.")

    def _url_list_validate(self, url_list: list[SourceDiscoveryUrl]) -> None:
        """Validate evidence-backed terminal source URL rows.

        Args:
            url_list: Persisted source URL rows.
        """

        for url in url_list:
            if not url.reason.strip() or not url.evidence_path_list:
                self._fail("Every terminal source URL row needs an evidence-backed reason.")

    def _product_search_list_validate(
        self,
        *,
        execution_context: WorkflowStepExecutionContext,
        step_input: SourceDiscoveryInput,
        url_list: list[SourceDiscoveryUrl],
        url_product_search_list: list[SourceDiscoveryUrlProductSearch],
        product_search_list: list[SourceDiscoveryProductSearch],
    ) -> None:
        """Validate product search worklist and URL relation closure.

        Args:
            execution_context: Current step context that owns the public workflow input.
            step_input: Persisted discovery input.
            url_list: Persisted source URL rows.
            url_product_search_list: Persisted URL-to-product-search relation rows.
            product_search_list: Persisted product search worklist rows.
        """

        requires_product_type = SOURCE_TYPE_REGISTRY.source_type_requires_product_type(step_input.source_type)
        if not requires_product_type:
            if product_search_list or url_product_search_list:
                self._fail("Non-product-scoped source discovery must not persist product-search rows.")
            return
        for product_search in product_search_list:
            if not product_search.reason.strip() or not product_search.evidence_path_list:
                self._fail("Every terminal product search row needs an evidence-backed reason.")
        requested_product_type_set = set(
            WorkflowBrandSizeChartInput.model_validate_json(
                (execution_context.result_dir / step_input.workflow_input_path).read_text(encoding="utf-8")
            ).request.product_type_request_list
        )
        represented_product_type_set = {row.product_type for row in product_search_list}
        if requested_product_type_set != represented_product_type_set:
            self._fail("Persist search rows for exactly the requested product type set.")
        if any(row.state == "pending" for row in product_search_list):
            self._fail("Terminal source discovery must not retain pending product search rows.")
        product_search_key_set = {(row.product_type, row.search_sex) for row in product_search_list}
        url_by_key_map = {url.url: url for url in url_list}
        opened_url_product_search_key_set: set[tuple[str, str]] = set()
        for url_product_search in url_product_search_list:
            product_search_key = (url_product_search.product_type, url_product_search.search_sex)
            if product_search_key not in product_search_key_set or url_product_search.url not in url_by_key_map:
                self._fail("Every URL product-search relation must reference one persisted URL and search row.")
            if url_by_key_map[url_product_search.url].state == "opened":
                opened_url_product_search_key_set.add(product_search_key)
        for product_search in product_search_list:
            product_search_key = (product_search.product_type, product_search.search_sex)
            if product_search.state == "searched" and product_search_key not in opened_url_product_search_key_set:
                self._fail("Every searched product row needs at least one opened URL relation.")
