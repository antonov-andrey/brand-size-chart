"""Canonical-selection stage owner."""

from pathlib import Path

from brand_size_chart.model import (
    APPLICABILITY_STATUS_CANONICAL_SET,
    CanonicalSelection,
    CanonicalSelectionResult,
    PromptScope,
    TableExtraction,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage.base import CodexStageRun
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.validator import CanonicalSelectionValidator


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

        canonical_selection_result = SemanticStage(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_name="selection",
            prompt_scope=self._prompt_scope,
            result_dir=self._result_dir,
            stage_dir=self._stage_dir,
            stage_key="canonical_selection",
        ).run(
            draft_result=self.draft_result_get(self._table_extraction_list),
            model_class=CanonicalSelectionResult,
            prompt_context=(
                f"Brand: {self._brand_name}\n"
                "Select canonical tables by source_priority and record conflicts with all compared decision values.\n"
            ),
            result_error_list_get=lambda result: self._validator.error_list_get(
                canonical_selection_result=result,
                table_extraction_list=self._table_extraction_list,
            ),
        )
        self._validator.validate(
            canonical_selection_result=canonical_selection_result,
            table_extraction_list=self._table_extraction_list,
        )
        return canonical_selection_result

    @classmethod
    def draft_result_get(cls, table_extraction_list: list[TableExtraction]) -> CanonicalSelectionResult:
        """Return canonical selections from verified tables.

        Args:
            table_extraction_list: Verified table extractions.

        Returns:
            Canonical selection result.
        """

        conflict_list: list[str] = []
        selected_extraction_by_size_group_key_map: dict[str, TableExtraction] = {}
        for table_extraction in table_extraction_list:
            if table_extraction.applicability_status not in APPLICABILITY_STATUS_CANONICAL_SET:
                conflict_list.append(
                    f"Table {table_extraction.size_group_key} from {table_extraction.source_url} skipped because "
                    f"applicability_status={table_extraction.applicability_status} is not canonical."
                )
                continue
            existing_extraction = selected_extraction_by_size_group_key_map.get(table_extraction.size_group_key)
            if existing_extraction is None:
                selected_extraction_by_size_group_key_map[table_extraction.size_group_key] = table_extraction
                continue

            existing_priority = SOURCE_TYPE_REGISTRY.source_type_priority_get(existing_extraction.source_type)
            current_priority = SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type)
            if current_priority > existing_priority:
                conflict_list.append(
                    "Higher priority table selected for "
                    f"{table_extraction.size_group_key}: {table_extraction.source_type} "
                    f"priority={current_priority} replaced {existing_extraction.source_type} "
                    f"priority={existing_priority}."
                )
                selected_extraction_by_size_group_key_map[table_extraction.size_group_key] = table_extraction
                continue
            if current_priority == existing_priority:
                conflict_list.append(
                    "Duplicate verified table with same priority for "
                    f"{table_extraction.size_group_key}: {existing_extraction.source_url} and "
                    f"{table_extraction.source_url}."
                )

        canonical_selection_list = [
            CanonicalSelection(
                conflict_list=[conflict for conflict in conflict_list if f" {size_group_key}:" in conflict],
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
            message="Canonical tables selected." if canonical_selection_list else "No verified source tables found.",
            status="success" if canonical_selection_list else "failed",
        )
