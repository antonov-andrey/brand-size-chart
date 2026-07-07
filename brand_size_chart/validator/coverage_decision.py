"""Coverage-decision mechanical validation."""

from brand_size_chart.model import CoverageDecisionPromptContext, CoverageDecisionResult


class CoverageDecisionValidator:
    """Validate coverage decisions against prompt scope."""

    def __init__(self, *, prompt_context: CoverageDecisionPromptContext) -> None:
        """Store coverage-decision validation context.

        Args:
            prompt_context: Coverage-decision prompt context used by the action.
        """

        self._prompt_context = prompt_context

    def validate(self, coverage_decision_result: CoverageDecisionResult) -> None:
        """Validate coverage decision against the requested product-type scope.

        Args:
            coverage_decision_result: Coverage decision result.

        Raises:
            RuntimeError: If coverage output mentions product types outside the requested scope.
        """

        requested_product_type_set = set(self._prompt_context.requested_product_type_list)
        covered_product_type_set: set[str] = set()
        verified_chart_path_set = {
            table_extraction.chart_path for table_extraction in self._prompt_context.verified_table_artifact_list
        }
        for covered_product_type in coverage_decision_result.covered_product_type_list:
            if not covered_product_type.reason.strip():
                raise RuntimeError(
                    f"coverage_decide returned empty coverage reason for {covered_product_type.product_type}"
                )
            if covered_product_type.chart_path not in verified_chart_path_set:
                raise RuntimeError(
                    "coverage_decide returned unknown chart_path for "
                    f"{covered_product_type.product_type}: {covered_product_type.chart_path}"
                )
            if covered_product_type.product_type not in requested_product_type_set:
                raise RuntimeError(
                    "coverage_decide returned unexpected covered product types for "
                    f"{covered_product_type.chart_path}: {[covered_product_type.product_type]}"
                )
            if covered_product_type.product_type in covered_product_type_set:
                raise RuntimeError(
                    f"coverage_decide duplicate covered product type: {covered_product_type.product_type}"
                )
            covered_product_type_set.add(covered_product_type.product_type)

        uncovered_gap_product_type_list = [
            product_type_gap.product_type
            for product_type_gap in coverage_decision_result.uncovered_product_type_gap_list
        ]
        uncovered_product_type_set = set(uncovered_gap_product_type_list)
        if len(uncovered_product_type_set) != len(uncovered_gap_product_type_list):
            raise RuntimeError("coverage_decide returned duplicate uncovered product types")
        if not uncovered_product_type_set.issubset(requested_product_type_set):
            unexpected_product_type_list = sorted(uncovered_product_type_set - requested_product_type_set)
            raise RuntimeError(f"coverage_decide returned unexpected product types: {unexpected_product_type_list}")
        overlapped_product_type_list = sorted(covered_product_type_set & uncovered_product_type_set)
        if overlapped_product_type_list:
            raise RuntimeError(
                "coverage_decide returned product types as both covered and uncovered: "
                f"{overlapped_product_type_list}"
            )
        missing_product_type_list = sorted(
            requested_product_type_set - covered_product_type_set - uncovered_product_type_set
        )
        if missing_product_type_list:
            raise RuntimeError(f"coverage_decide omitted requested product types: {missing_product_type_list}")
        for product_type_gap in coverage_decision_result.uncovered_product_type_gap_list:
            if not product_type_gap.reason.strip():
                raise RuntimeError(
                    "coverage_decide uncovered_product_type_gap_list contains empty reason for "
                    f"{product_type_gap.product_type}"
                )
