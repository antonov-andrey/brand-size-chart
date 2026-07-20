"""Deterministic final brand chart publication from accepted source tables."""

from pathlib import Path
from typing import ClassVar

from workflow_container_runtime.artifact import JsonArtifactWriter, JsonLinesArtifactWriter
from workflow_container_runtime.step import WorkflowStepDeterministicBase, WorkflowStepExecutionContext

from brand_size_chart.artifact import ArtifactLayout, BrandDataLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandOutputInput,
    BrandOutputInputSource,
    BrandOutputItem,
    BrandOutputResult,
    BrandSizeChart,
    BrandSizeChartDataset,
    BrandSizeChartDatasetRow,
)
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader
from brand_size_chart.validator import BrandOutputValidator


class BrandOutputStep(
    WorkflowStepDeterministicBase[
        BrandOutputInputSource,
        BrandOutputInput,
        BrandOutputResult,
    ]
):
    """Copy selected accepted charts into the final brand output tree."""

    result_model: ClassVar[type[BrandOutputResult]] = BrandOutputResult

    def __init__(
        self,
        *,
        artifact_writer: JsonArtifactWriter,
        json_lines_artifact_writer: JsonLinesArtifactWriter,
        source_discovery_database_reader: SourceDiscoveryDatabaseReader,
        validator: BrandOutputValidator,
    ) -> None:
        """Store publication, read-only lookup, and output-validation dependencies.

        Args:
            artifact_writer: Atomic JSON artifact writer.
            json_lines_artifact_writer: Atomic queryable-dataset writer.
            source_discovery_database_reader: Shared accepted-table query boundary.
            validator: Final brand-output mechanical validator.
        """

        super().__init__(artifact_writer=artifact_writer)
        self._json_lines_artifact_writer = json_lines_artifact_writer
        self._source_discovery_database_reader = source_discovery_database_reader
        self._validator = validator

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandOutputInputSource,
    ) -> BrandOutputInput:
        """Build exact output targets from selected accepted source charts.

        Args:
            execution_context: Current step context.
            input_source: Verified decisions and complete source-type results.

        Returns:
            Persisted final-output input.

        Raises:
            RuntimeError: If a canonical selection has no accepted source-table owner.
        """

        data_layout = BrandDataLayout(execution_context.data_path)
        accepted_table_list = (
            self._source_discovery_database_reader.accepted_table_list_get_for_source_type_result_list(
                result_dir=execution_context.result_dir,
                source_type_result_list=input_source.source_type_result_list,
            )
        )
        accepted_table_by_chart_path_map = {
            accepted_table.chart_path: accepted_table for accepted_table in accepted_table_list
        }
        output_item_list: list[BrandOutputItem] = []
        output_artifact_path_set: set[str] = set()
        for selection in input_source.canonical_selection_result.canonical_selection_list:
            accepted_table = accepted_table_by_chart_path_map.get(selection.selected_chart_path)
            if accepted_table is None:
                raise RuntimeError(
                    f"Canonical selection references unknown accepted chart: {selection.selected_chart_path}"
                )
            output_path = data_layout.size_chart_path(
                input_source.brand_input,
                accepted_table.source_table.size_group_key,
                accepted_table.source_table.market_scope_key,
            )
            output_artifact_path = data_layout.result_artifact_path(output_path)
            if output_artifact_path in output_artifact_path_set:
                raise RuntimeError(f"Canonical selections derive duplicate final chart target: {output_artifact_path}")
            output_artifact_path_set.add(output_artifact_path)
            output_item_list.append(
                BrandOutputItem(
                    market_scope_key=accepted_table.source_table.market_scope_key,
                    output_write_target=ArtifactWriteTarget(
                        artifact_path=output_artifact_path,
                        filesystem_path=output_path.resolve().as_posix(),
                    ),
                    size_group_key=accepted_table.source_table.size_group_key,
                    source_chart_path=accepted_table.chart_path,
                    source_type=accepted_table.source_type,
                    source_url=accepted_table.source_table.source_url,
                )
            )
        dataset_path = data_layout.dataset_path(input_source.brand_input)
        return BrandOutputInput(
            brand_input=input_source.brand_input,
            dataset_write_target=ArtifactWriteTarget(
                artifact_path=data_layout.result_artifact_path(dataset_path),
                filesystem_path=dataset_path.resolve().as_posix(),
            ),
            output_item_list=output_item_list,
        )

    def result_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandOutputInput,
    ) -> BrandOutputResult:
        """Publish selected source charts to their exact final targets.

        Args:
            execution_context: Current step context.
            step_input: Persisted final-output input.

        Returns:
            Final brand output references.
        """

        publication_list = self._publication_list_get(execution_context=execution_context, step_input=step_input)
        dataset_row_list: list[BrandSizeChartDatasetRow] = []
        for output_item, output_path, source_chart in publication_list:
            self._artifact_writer.write(output_path, source_chart)
            dataset_row_list.extend(
                BrandSizeChartDataset.from_chart(
                    brand_input=step_input.brand_input,
                    chart=source_chart,
                    market_scope_key=output_item.market_scope_key,
                    run_context=execution_context.run_context,
                    size_group_key=output_item.size_group_key,
                    source_type=output_item.source_type,
                    source_url=output_item.source_url,
                ).row_list
            )
        dataset_path = self._output_path_get(
            data_layout=BrandDataLayout(execution_context.data_path),
            output_write_target=step_input.dataset_write_target,
        )
        self._json_lines_artifact_writer.write(dataset_path, dataset_row_list)
        return BrandOutputResult(
            dataset_path=step_input.dataset_write_target.artifact_path,
            size_chart_path_list=[item.output_write_target.artifact_path for item in step_input.output_item_list],
        )

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandOutputInput,
        result: BrandOutputResult,
    ) -> None:
        """Validate final output references and chart files.

        Args:
            execution_context: Current step context.
            step_input: Persisted final-output input.
            result: Candidate final-output result.
        """

        self._validator.validate(execution_context=execution_context, result=result, step_input=step_input)

    def _publication_list_get(
        self,
        *,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandOutputInput,
    ) -> list[tuple[BrandOutputItem, Path, BrandSizeChart]]:
        """Preflight every selected source and derived output target before publication.

        Args:
            execution_context: Current step context that owns the result root.
            step_input: Persisted final-output input.

        Returns:
            Resolved contained publication targets with validated source charts.

        Raises:
            RuntimeError: If a source or target escapes the result root or cannot be published safely.
        """

        layout = ArtifactLayout(execution_context.result_dir)
        data_layout = BrandDataLayout(execution_context.data_path)
        publication_list: list[tuple[BrandOutputItem, Path, BrandSizeChart]] = []
        output_path_set: set[Path] = set()
        for output_item in step_input.output_item_list:
            source_chart_path = self._source_chart_path_get(
                layout=layout, source_chart_path=output_item.source_chart_path
            )
            output_path = self._output_path_get(
                data_layout=data_layout,
                output_write_target=output_item.output_write_target,
            )
            if output_path in output_path_set:
                raise RuntimeError(f"Final chart target is duplicated: {output_path}")
            output_path_set.add(output_path)
            try:
                source_chart = BrandSizeChart.model_validate_json(source_chart_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"Selected source chart is missing or invalid: {output_item.source_chart_path}"
                ) from exc
            publication_list.append((output_item, output_path, source_chart))
        return publication_list

    def _output_path_get(
        self,
        *,
        data_layout: BrandDataLayout,
        output_write_target: ArtifactWriteTarget,
    ) -> Path:
        """Resolve one canonical final output target before any write.

        Args:
            data_layout: Current standard Data layout.
            output_write_target: Persisted target declaration.

        Returns:
            Resolved final output path contained by the result root.

        Raises:
            RuntimeError: If the target is non-canonical or resolves outside the result root.
        """

        output_path = Path(output_write_target.filesystem_path)
        if not output_path.is_absolute():
            raise RuntimeError("Final chart filesystem_path must be absolute.")
        output_path = output_path.resolve()
        try:
            output_artifact_path = data_layout.result_artifact_path(output_path)
        except ValueError as exc:
            raise RuntimeError("Final output target escapes the standard result path.") from exc
        if output_artifact_path != output_write_target.artifact_path:
            raise RuntimeError("Final output target does not match its canonical image-relative artifact_path.")
        return output_path

    def _source_chart_path_get(self, *, layout: ArtifactLayout, source_chart_path: str) -> Path:
        """Resolve one canonical selected source chart before any read.

        Args:
            layout: Current result-root artifact layout.
            source_chart_path: Result-relative selected source chart handle.

        Returns:
            Resolved source chart path contained by the result root.

        Raises:
            RuntimeError: If the source handle is non-canonical or resolves outside the result root.
        """

        source_chart_relative_path = Path(source_chart_path)
        if (
            not source_chart_path
            or source_chart_path != source_chart_path.strip()
            or source_chart_relative_path.is_absolute()
            or ".." in source_chart_relative_path.parts
            or source_chart_relative_path.as_posix() != source_chart_path
        ):
            raise RuntimeError(f"Source chart path must be normalized and result-relative: {source_chart_path}")
        source_chart = (layout.result_dir / source_chart_relative_path).resolve()
        try:
            source_chart_artifact_path = layout.artifact_path(source_chart)
        except ValueError as exc:
            raise RuntimeError(f"Selected source chart escapes result_dir: {source_chart_path}") from exc
        if source_chart_artifact_path != source_chart_path:
            raise RuntimeError(f"Selected source chart is not a canonical artifact handle: {source_chart_path}")
        return source_chart
