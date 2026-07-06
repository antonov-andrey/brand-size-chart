"""Coverage-decision mechanical validation."""

from brand_size_chart.model import CoverageDecisionResult, PromptScope
from brand_size_chart.validator.base import MechanicalValidator


class CoverageDecisionValidator(MechanicalValidator):
    """Validate coverage decisions against prompt scope."""

    def error_list_get(
        self, coverage_decision_result: CoverageDecisionResult, *, prompt_scope: PromptScope
    ) -> list[str]:
        """Return coverage-decision mechanical validation errors.

        Args:
            coverage_decision_result: Coverage decision result.
            prompt_scope: Current prompt scope.

        Returns:
            Mechanical validation errors.
        """

        return self._error_list_get(
            lambda: self.validate(
                coverage_decision_result=coverage_decision_result,
                prompt_scope=prompt_scope,
            )
        )

    def validate(self, *, coverage_decision_result: CoverageDecisionResult, prompt_scope: PromptScope) -> None:
        """Validate coverage decision against the requested product-type scope.

        Args:
            coverage_decision_result: Coverage decision result.
            prompt_scope: Current prompt scope.

        Raises:
            RuntimeError: If coverage output mentions product types outside the requested scope.
        """

        requested_product_type_set = set(prompt_scope.product_type_request_list)
        covered_product_type_set: set[str] = set()
        for coverage_decision in coverage_decision_result.coverage_decision_list:
            decision_covered_product_type_set = set(coverage_decision.covered_product_type_list)
            if len(decision_covered_product_type_set) != len(coverage_decision.covered_product_type_list):
                raise RuntimeError(
                    f"coverage_decide duplicate covered product types for {coverage_decision.size_group_key}"
                )
            unexpected_covered_product_type_list = sorted(
                decision_covered_product_type_set - requested_product_type_set
            )
            if unexpected_covered_product_type_list:
                raise RuntimeError(
                    "coverage_decide returned unexpected covered product types for "
                    f"{coverage_decision.size_group_key}: {unexpected_covered_product_type_list}"
                )
            if requested_product_type_set and coverage_decision.is_covered and not decision_covered_product_type_set:
                raise RuntimeError(
                    "coverage_decide positive decision must list covered_product_type_list for "
                    f"{coverage_decision.size_group_key}"
                )
            if not coverage_decision.is_covered and decision_covered_product_type_set:
                raise RuntimeError(
                    "coverage_decide negative decision must not list covered_product_type_list for "
                    f"{coverage_decision.size_group_key}"
                )
            covered_product_type_set.update(decision_covered_product_type_set)

        uncovered_product_type_set = set(coverage_decision_result.uncovered_product_type_list)
        if len(uncovered_product_type_set) != len(coverage_decision_result.uncovered_product_type_list):
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
        for product_type in coverage_decision_result.uncovered_product_type_list:
            error_prefix = f"{product_type}:"
            if not any(error.startswith(error_prefix) for error in coverage_decision_result.error_list):
                raise RuntimeError(
                    f"coverage_decide missing error_list reason for uncovered product type: {product_type}"
                )
