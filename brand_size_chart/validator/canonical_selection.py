"""Canonical-selection validation against read-only accepted source tables."""

from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext

from brand_size_chart.model import (
    BrandSourceTypeResultStepInput,
    CanonicalSelectionResult,
    canonical_selection_unresolved_size_group_gap_list_get,
)
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader


class CanonicalSelectionValidator:
    """Validate physical canonical selections from accepted source-table query results."""

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
        result: CanonicalSelectionResult,
    ) -> None:
        """Validate selection membership, priority, representative order, and derived gaps.

        Args:
            execution_context: Current step execution context.
            step_input: Persisted complete source results and workflow input.
            result: Candidate public canonical selection.

        Raises:
            StepResultValidationError: If selection violates accepted-row mechanics.
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
        accepted_by_chart_path_map = {item.chart_path: item for item in accepted_table_list}
        selected_chart_path_set: set[str] = set()
        selected_size_group_key_set: set[str] = set()
        for selection in result.canonical_selection_list:
            if selection.selected_chart_path in selected_chart_path_set:
                self._fail(f"Return selected_chart_path {selection.selected_chart_path} exactly once.")
            selected_chart_path_set.add(selection.selected_chart_path)
            accepted_table = accepted_by_chart_path_map.get(selection.selected_chart_path)
            if accepted_table is None:
                self._fail(f"Choose only accepted source chart paths; unknown path: {selection.selected_chart_path}.")
            size_group_key = accepted_table.source_table.size_group_key
            if size_group_key in selected_size_group_key_set:
                self._fail(f"Return exactly one canonical selection for size_group_key {size_group_key}.")
            selected_size_group_key_set.add(size_group_key)
            group_table_list = [
                item for item in accepted_table_list if item.source_table.size_group_key == size_group_key
            ]
            max_priority = max(item.source_priority for item in group_table_list)
            if accepted_table.source_priority != max_priority:
                self._fail(f"Select highest source priority for size_group_key {size_group_key}.")
            max_priority_table_list = [item for item in group_table_list if item.source_priority == max_priority]
            if len(max_priority_table_list) > 1:
                expected_chart_path = min(
                    max_priority_table_list,
                    key=lambda item: (
                        item.source_table.market_scope_key,
                        item.source_table.source_url,
                        item.source_table.source_title,
                    ),
                ).chart_path
                if selection.selected_chart_path != expected_chart_path:
                    self._fail(
                        f"Select deterministic equivalent representative for {size_group_key}: {expected_chart_path}."
                    )
        expected_unresolved_size_group_gap_list = canonical_selection_unresolved_size_group_gap_list_get(
            canonical_selection_list=result.canonical_selection_list,
            accepted_table_list=accepted_table_list,
        )
        if result.unresolved_size_group_gap_list != expected_unresolved_size_group_gap_list:
            self._fail("Return unresolved_size_group_gap_list exactly from omitted accepted highest-priority groups.")
        for size_group_key in {
            item.source_table.size_group_key for item in accepted_table_list
        } - selected_size_group_key_set:
            group_table_list = [
                item for item in accepted_table_list if item.source_table.size_group_key == size_group_key
            ]
            max_priority = max(item.source_priority for item in group_table_list)
            if sum(item.source_priority == max_priority for item in group_table_list) == 1:
                self._fail(f"Select the sole highest-priority accepted row for size_group_key {size_group_key}.")

    def _fail(self, feedback: str) -> None:
        """Raise one mechanical canonical-selection validation failure.

        Args:
            feedback: Actionable correction text.

        Raises:
            StepResultValidationError: Always.
        """

        raise StepResultValidationError(feedback_list=[feedback])
