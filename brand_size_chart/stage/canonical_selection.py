"""Canonical-selection stage owner."""

from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import VerifiedCodexStageRunner

from brand_size_chart.model import (
    APPLICABILITY_STATUS_CANONICAL_SET,
    CanonicalSelection,
    CanonicalSelectionConflict,
    CanonicalSelectionResult,
    PromptScope,
    TableExtraction,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage.base import CodexStageRun, verified_stage_config_get
from brand_size_chart.validator import CanonicalSelectionValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class CanonicalSelectionStage:
    """Select canonical tables from verified table extractions."""

    def __init__(
        self,
        *,
        brand_name: str,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        stage_dir: Path,
        table_extraction_list: list[TableExtraction],
    ) -> None:
        """Store canonical-selection stage dependencies.

        Args:
            brand_name: Parsed brand display name.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            table_extraction_list: Verified table extractions.
        """

        self._brand_name = brand_name
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._stage_dir = stage_dir
        self._table_extraction_list = table_extraction_list
        self._validator = CanonicalSelectionValidator()

    def run(self) -> CanonicalSelectionResult:
        """Return semantically verified canonical selection.

        Returns:
            Verified canonical selection result.
        """

        canonical_selection_result = VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=verified_stage_config_get(
                prompt_context=self._prompt_context_get(),
                prompt_scope=self._prompt_scope,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="canonical_select",
            ),
            draft_result=self.draft_result_get(self._table_extraction_list),
            model_class=CanonicalSelectionResult,
            mechanical_error_list_get=lambda result: self._validator.error_list_get(
                canonical_selection_result=result,
                table_extraction_list=self._table_extraction_list,
            ),
        )
        self._validator.validate(
            canonical_selection_result=canonical_selection_result,
            table_extraction_list=self._table_extraction_list,
        )
        return canonical_selection_result

    def _prompt_context_get(self) -> str:
        """Return canonical-selection prompt context with verified candidate tables.

        Returns:
            Prompt context text.
        """

        table_context_text = "\n".join(
            (
                f"- size_group_key={table_extraction.size_group_key}; "
                f"source_type={table_extraction.source_type}; "
                f"source_priority={SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type)}; "
                f"source_url={table_extraction.source_url}; "
                f"source_title={table_extraction.source_title}; "
                f"applicability_status={table_extraction.applicability_status}; "
                f"applicability_description={table_extraction.applicability_description}; "
                f"product_type_hint_list={table_extraction.product_type_hint_list}; "
                f"evidence_path_list={table_extraction.evidence_path_list}; "
                f"chart_path={table_extraction.chart_path}"
            )
            for table_extraction in self._table_extraction_list
        )
        return (
            f"Brand: {self._brand_name}\n"
            f"Verified table context:\n{table_context_text if table_context_text else '- none'}\n"
        )

    @classmethod
    def draft_result_get(cls, table_extraction_list: list[TableExtraction]) -> CanonicalSelectionResult:
        """Return canonical selections from verified tables.

        Args:
            table_extraction_list: Verified table extractions.

        Returns:
            Canonical selection result.
        """

        conflict_list: list[CanonicalSelectionConflict] = []
        error_list: list[str] = []
        selected_extraction_by_size_group_key_map: dict[str, TableExtraction] = {}
        table_extraction_list_by_size_group_key_map: dict[str, list[TableExtraction]] = {}
        for table_extraction in table_extraction_list:
            if table_extraction.applicability_status not in APPLICABILITY_STATUS_CANONICAL_SET:
                conflict_list.append(
                    cls._conflict_get(
                        reason=f"applicability_status={table_extraction.applicability_status} is not canonical",
                        table_extraction=table_extraction,
                    )
                )
                continue
            table_extraction_list_by_size_group_key_map.setdefault(table_extraction.size_group_key, []).append(
                table_extraction
            )

        for size_group_key, grouped_table_extraction_list in sorted(
            table_extraction_list_by_size_group_key_map.items()
        ):
            max_priority = max(
                SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type)
                for table_extraction in grouped_table_extraction_list
            )
            max_priority_table_extraction_list = sorted(
                [
                    table_extraction
                    for table_extraction in grouped_table_extraction_list
                    if SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type) == max_priority
                ],
                key=cls._table_extraction_sort_key_get,
            )
            if len(max_priority_table_extraction_list) > 1:
                error_list.append(f"{size_group_key}: unresolved same-priority candidate equivalence")
                conflict_list.extend(
                    cls._conflict_get(
                        reason="same priority unresolved equivalence",
                        table_extraction=table_extraction,
                    )
                    for table_extraction in max_priority_table_extraction_list
                )
                continue

            selected_extraction = max_priority_table_extraction_list[0]
            selected_extraction_by_size_group_key_map[size_group_key] = selected_extraction
            for table_extraction in sorted(grouped_table_extraction_list, key=cls._table_extraction_sort_key_get):
                if table_extraction is selected_extraction:
                    continue
                conflict_list.append(
                    cls._conflict_get(
                        reason=(
                            f"lower priority candidate omitted because {selected_extraction.source_type} "
                            f"priority={max_priority} was selected"
                        ),
                        table_extraction=table_extraction,
                    )
                )

        canonical_selection_list = [
            CanonicalSelection(
                conflict_list=[conflict for conflict in conflict_list if conflict.size_group_key == size_group_key],
                selected_source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type),
                selected_source_type=table_extraction.source_type,
                selected_source_url=table_extraction.source_url,
                size_group_key=size_group_key,
            )
            for size_group_key, table_extraction in sorted(selected_extraction_by_size_group_key_map.items())
        ]
        return CanonicalSelectionResult(
            canonical_selection_list=canonical_selection_list,
            conflict_list=conflict_list,
            error_list=error_list,
            message=(
                "Canonical selection blocked by unresolved same-priority conflicts."
                if error_list
                else ("Canonical tables selected." if canonical_selection_list else "No verified source tables found.")
            ),
            status="failed" if error_list or not canonical_selection_list else "success",
        )

    @classmethod
    def _conflict_get(cls, *, reason: str, table_extraction: TableExtraction) -> CanonicalSelectionConflict:
        """Return structured conflict values for one compared table extraction.

        Args:
            reason: Conflict or selection reason.
            table_extraction: Compared table extraction.

        Returns:
            Structured canonical-selection conflict.
        """

        return CanonicalSelectionConflict(
            applicability_status=table_extraction.applicability_status,
            chart_path=table_extraction.chart_path,
            reason=reason,
            size_group_key=table_extraction.size_group_key,
            source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type),
            source_type=table_extraction.source_type,
            source_url=table_extraction.source_url,
        )

    @classmethod
    def _table_extraction_sort_key_get(cls, table_extraction: TableExtraction) -> tuple[str, int, str, str, str]:
        """Return deterministic canonical-selection candidate order.

        Args:
            table_extraction: Candidate table extraction.

        Returns:
            Sort key that groups by size group, prefers higher priority, and breaks equivalent ties deterministically.
        """

        return (
            table_extraction.size_group_key,
            -SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type),
            table_extraction.chart_path,
            table_extraction.source_url,
            table_extraction.source_title,
        )
