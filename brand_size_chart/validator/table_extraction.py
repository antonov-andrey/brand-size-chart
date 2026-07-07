"""Table-extraction mechanical validation."""

from pathlib import Path

from brand_size_chart.artifact import ArtifactReferenceValidator
from brand_size_chart.model import (
    BrandSizeChart,
    TableExtractionDelta,
    TableExtractionDeltaBatchResult,
    TableExtractionExecplanItem,
    TableExtractionPromptContext,
)


class TableExtractionValidator:
    """Validate table-extraction structural consistency."""

    def __init__(
        self,
        *,
        prompt_context: TableExtractionPromptContext,
        result_dir: Path,
    ) -> None:
        """Store table-extraction validation context.

        Args:
            prompt_context: Table-extraction prompt context used by the action.
            result_dir: Root result directory.
        """

        self._artifact_reference_validator = ArtifactReferenceValidator(result_dir)
        self._prompt_context = prompt_context

    def validate(self, table_extraction_delta_batch_result: TableExtractionDeltaBatchResult) -> None:
        """Validate artifact-backed batch table-extraction structural consistency.

        Args:
            table_extraction_delta_batch_result: Codex-owned extraction deltas to validate.

        Raises:
            RuntimeError: If table extraction is structurally inconsistent.
        """

        self._execplan_validate()
        delta_count = len(table_extraction_delta_batch_result.table_extraction_delta_list)
        execplan_count = len(self._prompt_context.execplan_item_list)
        if delta_count != execplan_count:
            mismatch_kind = "missing delta" if delta_count < execplan_count else "extra delta"
            raise RuntimeError(
                f"table_extract result length mismatch ({mismatch_kind}); "
                f"execplan_count={execplan_count}; "
                f"delta_count={delta_count}; "
                "expected_size_group_key_list="
                f"{[execplan_item.size_group_key for execplan_item in self._prompt_context.execplan_item_list]}"
            )
        for execplan_item, table_extraction_delta in zip(
            self._prompt_context.execplan_item_list,
            table_extraction_delta_batch_result.table_extraction_delta_list,
            strict=True,
        ):
            self._table_extraction_delta_validate(
                execplan_item=execplan_item,
                table_extraction_delta=table_extraction_delta,
            )

    def _chart_get(self, *, execplan_item: TableExtractionExecplanItem) -> BrandSizeChart:
        """Return the validated chart artifact for one execplan item.

        Args:
            execplan_item: Table-extraction execplan item with the chart target.

        Returns:
            Parsed chart artifact.

        Raises:
            RuntimeError: If the chart artifact is missing or invalid.
        """

        self._artifact_reference_validator.path_list_validate(
            path_list=[execplan_item.chart_write_target.artifact_path],
            stage_key="table_extract",
        )
        chart_path = Path(execplan_item.chart_write_target.filesystem_path)
        try:
            return BrandSizeChart.model_validate_json(chart_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"table_extraction chart artifact is invalid for {execplan_item.size_group_key}: {exc}"
            ) from exc

    def _chart_validate(self, *, chart: BrandSizeChart, size_group_key: str) -> None:
        """Validate one parsed chart payload.

        Args:
            chart: Parsed chart artifact.
            size_group_key: Size group key used for diagnostics.

        Raises:
            RuntimeError: If chart content is structurally invalid.
        """

        if not chart.row_list:
            raise RuntimeError(f"table_extraction returned an empty chart for {size_group_key}")
        for row_index, chart_row in enumerate(chart.row_list):
            if not chart_row.size_label.strip():
                raise RuntimeError(f"table_extraction returned empty size_label at row {row_index}")
            if not chart_row.measurement_list:
                raise RuntimeError(f"table_extraction returned empty measurement_list at row {row_index}")
            for measurement_index, measurement in enumerate(chart_row.measurement_list):
                if not measurement.name.strip():
                    raise RuntimeError(
                        f"table_extraction returned empty measurement name at row {row_index}, "
                        f"measurement {measurement_index}"
                    )
                if not measurement.unit.strip():
                    raise RuntimeError(
                        f"table_extraction returned empty measurement unit at row {row_index}, "
                        f"measurement {measurement_index}"
                    )
                if not measurement.min_value.strip():
                    raise RuntimeError(
                        f"table_extraction returned empty min_value at row {row_index}, measurement {measurement_index}"
                    )
                if not measurement.max_value.strip():
                    raise RuntimeError(
                        f"table_extraction returned empty max_value at row {row_index}, measurement {measurement_index}"
                    )
            if not any(
                measurement.unit == "size"
                and measurement.min_value == chart_row.size_label
                and measurement.max_value == chart_row.size_label
                for measurement in chart_row.measurement_list
            ):
                raise RuntimeError(
                    f"table_extraction must preserve size_label as a unit=size measurement at row {row_index}"
                )

    def _execplan_validate(self) -> None:
        """Validate table-extraction execplan target uniqueness.

        Raises:
            RuntimeError: If execplan contains duplicate size group keys or chart targets.
        """

        execplan_item_by_size_group_key_map = {
            execplan_item.size_group_key: execplan_item for execplan_item in self._prompt_context.execplan_item_list
        }
        if len(execplan_item_by_size_group_key_map) != len(self._prompt_context.execplan_item_list):
            raise RuntimeError("table_extract execplan_item_list contains duplicate size_group_key values")
        chart_artifact_path_list = [
            execplan_item.chart_write_target.artifact_path for execplan_item in self._prompt_context.execplan_item_list
        ]
        if len(set(chart_artifact_path_list)) != len(chart_artifact_path_list):
            raise RuntimeError("table_extract execplan_item_list contains duplicate chart artifact targets")

    def _table_extraction_delta_validate(
        self, *, execplan_item: TableExtractionExecplanItem, table_extraction_delta: TableExtractionDelta
    ) -> None:
        """Validate one table extraction delta against its source discovery.

        Args:
            execplan_item: Execplan item that owns the table identity and paths.
            table_extraction_delta: Codex-owned extraction delta.

        Raises:
            RuntimeError: If table extraction is structurally inconsistent.
        """

        self._chart_validate(
            chart=self._chart_get(execplan_item=execplan_item),
            size_group_key=execplan_item.size_group_key,
        )
        self._artifact_reference_validator.evidence_path_list_validate(
            evidence_path_list=table_extraction_delta.evidence_path_list,
            stage_key="table_extract",
        )
