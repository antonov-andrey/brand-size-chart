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
        uncovered_product_type_set = set(coverage_decision_result.uncovered_product_type_list)
        if not uncovered_product_type_set.issubset(requested_product_type_set):
            unexpected_product_type_list = sorted(uncovered_product_type_set - requested_product_type_set)
            raise RuntimeError(f"coverage_decision returned unexpected product types: {unexpected_product_type_list}")
