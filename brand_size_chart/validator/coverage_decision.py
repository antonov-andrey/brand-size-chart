"""Coverage-decision validation against read-only accepted source tables."""

from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext

from brand_size_chart.model import BrandSourceTypeResultStepInput, CoverageDecisionResult, WorkflowBrandSizeChartInput
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader


class CoverageDecisionValidator:
    """Validate coverage decisions against current accepted source charts."""

    def __init__(self, *, source_discovery_database_reader: SourceDiscoveryDatabaseReader) -> None:
        """Store the shared read-only accepted-table boundary.

        Args:
            source_discovery_database_reader: Shared validated source-discovery query boundary.
        """

        self._source_discovery_database_reader = source_discovery_database_reader

    def validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        result: CoverageDecisionResult,
    ) -> None:
        """Validate one complete covered and uncovered requested-product partition.

        Args:
            execution_context: Current step execution context.
            step_input: Persisted complete source results and workflow input.
            result: Candidate public coverage decision.

        Raises:
            StepResultValidationError: If coverage violates requested scope or accepted chart identity.
        """

        try:
            accepted_table_list = (
                self._source_discovery_database_reader.accepted_table_list_get_for_source_type_result_list(
                    result_dir=execution_context.result_dir,
                    source_type_result_list=step_input.source_type_result_list,
                )
            )
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise StepResultValidationError(
                feedback_list=[f"Read the declared accepted source tables without changing SQLite state: {exc}"]
            ) from exc
        accepted_chart_path_set = {accepted_table.chart_path for accepted_table in accepted_table_list}
        requested_product_type_set = set(
            WorkflowBrandSizeChartInput.model_validate_json(
                (execution_context.result_dir / step_input.workflow_input_path).read_text(encoding="utf-8")
            ).request.product_type_request_list
        )
        covered_product_type_set: set[str] = set()
        for covered_product_type in result.covered_product_type_list:
            if not covered_product_type.reason.strip():
                self._fail(f"Add a non-empty evidence-backed coverage reason for {covered_product_type.product_type}.")
            if covered_product_type.chart_path not in accepted_chart_path_set:
                self._fail(f"Use only accepted source chart paths; unknown path: {covered_product_type.chart_path}.")
            if covered_product_type.product_type not in requested_product_type_set:
                self._fail(f"Remove unrequested covered product type {covered_product_type.product_type}.")
            if covered_product_type.product_type in covered_product_type_set:
                self._fail(f"Return covered product type {covered_product_type.product_type} exactly once.")
            covered_product_type_set.add(covered_product_type.product_type)
        uncovered_product_type_list = [gap.product_type for gap in result.uncovered_product_type_gap_list]
        uncovered_product_type_set = set(uncovered_product_type_list)
        if len(uncovered_product_type_list) != len(uncovered_product_type_set):
            self._fail("Return each uncovered requested product type exactly once.")
        if unexpected_product_type_list := sorted(uncovered_product_type_set - requested_product_type_set):
            self._fail(f"Remove unrequested uncovered product types: {unexpected_product_type_list}.")
        if overlap_product_type_list := sorted(covered_product_type_set & uncovered_product_type_set):
            self._fail(f"Keep covered and uncovered product types disjoint: {overlap_product_type_list}.")
        if missing_product_type_list := sorted(
            requested_product_type_set - covered_product_type_set - uncovered_product_type_set
        ):
            self._fail(f"Classify every requested product type; missing: {missing_product_type_list}.")
        for product_type_gap in result.uncovered_product_type_gap_list:
            if not product_type_gap.reason.strip():
                self._fail(f"Add a non-empty gap reason for {product_type_gap.product_type}.")

    def _fail(self, feedback: str) -> None:
        """Raise one mechanical coverage validation failure.

        Args:
            feedback: Actionable correction text.

        Raises:
            StepResultValidationError: Always.
        """

        raise StepResultValidationError(feedback_list=[feedback])
