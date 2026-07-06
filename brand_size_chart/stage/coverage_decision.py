"""Coverage-decision stage owner."""

from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import VerifiedCodexStageRunner

from brand_size_chart.model import BrandInput, CoverageDecision, CoverageDecisionResult, PromptScope, TableExtraction
from brand_size_chart.stage.base import CodexStageRun, verified_stage_config_get
from brand_size_chart.validator import CoverageDecisionValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class CoverageDecisionStage:
    """Decide requested product-type coverage from verified table extractions."""

    def __init__(
        self,
        *,
        brand_input: BrandInput,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        source_type: str,
        stage_dir: Path,
        table_extraction_list: list[TableExtraction],
    ) -> None:
        """Store coverage-decision stage dependencies.

        Args:
            brand_input: Parsed brand input.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            source_type: Source type that triggered this coverage check.
            stage_dir: Stage artifact directory.
            table_extraction_list: Verified table extractions.
        """

        self._brand_input = brand_input
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._source_type = source_type
        self._stage_dir = stage_dir
        self._table_extraction_list = table_extraction_list
        self._validator = CoverageDecisionValidator()

    def run(self) -> CoverageDecisionResult:
        """Return semantically verified coverage for requested product types.

        Returns:
            Verified coverage decision result.
        """

        coverage_decision_result = VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=verified_stage_config_get(
                prompt_context=self._prompt_context_get(),
                prompt_scope=self._prompt_scope,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="coverage_decide",
            ),
            draft_result=self.draft_result_get(
                prompt_scope=self._prompt_scope,
                table_extraction_list=self._table_extraction_list,
            ),
            model_class=CoverageDecisionResult,
            mechanical_error_list_get=lambda result: self._validator.error_list_get(
                result,
                prompt_scope=self._prompt_scope,
            ),
        )
        return coverage_decision_result

    @classmethod
    def draft_result_get(
        cls, *, prompt_scope: PromptScope, table_extraction_list: list[TableExtraction]
    ) -> CoverageDecisionResult:
        """Return coverage decisions for requested product types.

        Args:
            prompt_scope: Parsed prompt scope.
            table_extraction_list: Verified table extractions.

        Returns:
            Coverage decision result.
        """

        coverage_decision_list = [
            CoverageDecision(
                is_covered=False,
                reason="Deterministic draft does not infer product-type coverage without explicit table evidence.",
                size_group_key=table_extraction.size_group_key,
            )
            for table_extraction in table_extraction_list
        ]
        return CoverageDecisionResult(
            coverage_decision_list=coverage_decision_list,
            error_list=[
                f"{product_type}: no explicit table applicability evidence in deterministic draft"
                for product_type in prompt_scope.product_type_request_list
            ],
            message="Coverage decision completed." if table_extraction_list else "No verified tables for coverage.",
            status="success" if table_extraction_list else "skipped",
            uncovered_product_type_list=list(prompt_scope.product_type_request_list),
        )

    def _prompt_context_get(self) -> str:
        """Return coverage-decision prompt context.

        Returns:
            Prompt context text.
        """

        verified_table_summary_text = "\n".join(
            (
                f"- {table_extraction.size_group_key}: source_type={table_extraction.source_type}; "
                f"source_title={table_extraction.source_title}; "
                f"source_url={table_extraction.source_url}; "
                f"applicability_status={table_extraction.applicability_status}; "
                f"chart_path={table_extraction.chart_path}; "
                f"evidence_path_list={table_extraction.evidence_path_list}; "
                f"product_type_hint_list={table_extraction.product_type_hint_list}; "
                f"applicability_description={table_extraction.applicability_description}; "
                f"chart_description={table_extraction.chart.description}"
            )
            for table_extraction in self._table_extraction_list
        )
        return (
            f"Brand: {self._brand_input.parsed_brand_name}\n"
            f"Source type just completed: {self._source_type}\n"
            f"Requested product types: {self._prompt_scope.product_type_request_list}\n"
            f"Verified table summary:\n{verified_table_summary_text if verified_table_summary_text else '- none'}\n"
        )
