"""Table-extraction mechanical validation."""

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from brand_size_chart.artifact import ArtifactReferenceValidator
from brand_size_chart.model import (
    BrandSizeChart,
    SourceDiscovery,
    TableExtractExecplanItem,
    TableExtraction,
    TableExtractionArtifact,
    TableExtractionArtifactBatchResult,
    TableExtractionBatchResult,
)
from brand_size_chart.validator.base import MechanicalValidator


class TableExtractionValidator(MechanicalValidator):
    """Validate table-extraction structural consistency."""

    def __init__(self, result_dir: Path, *, stage_dir: Path | None = None) -> None:
        """Store the explicit result directory.

        Args:
            result_dir: Root result directory.
            stage_dir: Table-extraction stage directory.
        """

        self._artifact_reference_validator = ArtifactReferenceValidator(result_dir)
        self._result_dir = result_dir
        self._stage_dir = stage_dir

    def artifact_error_list_get(
        self,
        table_extraction_artifact_batch_result: TableExtractionArtifactBatchResult,
        *,
        source_discovery_list: list[SourceDiscovery],
    ) -> list[str]:
        """Return artifact-backed batch table-extraction mechanical validation errors.

        Args:
            table_extraction_artifact_batch_result: Artifact-backed extraction result to validate.
            source_discovery_list: Source discoveries that own table identities.

        Returns:
            Mechanical validation errors.
        """

        return self._error_list_get(
            lambda: self.artifact_validate(
                source_discovery_list=source_discovery_list,
                table_extraction_artifact_batch_result=table_extraction_artifact_batch_result,
            )
        )

    def artifact_validate(
        self,
        *,
        source_discovery_list: list[SourceDiscovery],
        table_extraction_artifact_batch_result: TableExtractionArtifactBatchResult,
    ) -> None:
        """Validate artifact-backed batch table-extraction structural consistency.

        Args:
            source_discovery_list: Source discoveries that own table identities.
            table_extraction_artifact_batch_result: Artifact-backed extraction result to validate.

        Raises:
            RuntimeError: If table extraction is structurally inconsistent.
        """

        if table_extraction_artifact_batch_result.status != "success":
            raise RuntimeError(f"table_extract status must be success: {table_extraction_artifact_batch_result.status}")
        source_type_set = {source_discovery.source_type for source_discovery in source_discovery_list}
        if source_type_set != {table_extraction_artifact_batch_result.source_type}:
            raise RuntimeError(
                f"table_extract source_type set mismatch: {sorted(source_type_set)} "
                f"!= {[table_extraction_artifact_batch_result.source_type]}"
            )
        source_discovery_by_size_group_key_map = self._source_discovery_by_size_group_key_map_get(source_discovery_list)
        table_extraction_artifact_by_size_group_key_map = self._table_extraction_artifact_by_size_group_key_map_get(
            table_extraction_artifact_batch_result.table_extraction_artifact_list
        )
        discovery_size_group_key_set = set(source_discovery_by_size_group_key_map)
        extraction_size_group_key_set = set(table_extraction_artifact_by_size_group_key_map)
        missing_size_group_key_list = sorted(discovery_size_group_key_set - extraction_size_group_key_set)
        extra_size_group_key_list = sorted(extraction_size_group_key_set - discovery_size_group_key_set)
        if missing_size_group_key_list or extra_size_group_key_list:
            message_part_list = []
            if missing_size_group_key_list:
                message_part_list.append(f"missing size_group_key list: {missing_size_group_key_list}")
            if extra_size_group_key_list:
                message_part_list.append(f"extra size_group_key list: {extra_size_group_key_list}")
            raise RuntimeError(f"table_extract size_group_key set mismatch; {'; '.join(message_part_list)}")
        for size_group_key, table_extraction_artifact in table_extraction_artifact_by_size_group_key_map.items():
            self._table_extraction_artifact_validate(
                source_discovery=source_discovery_by_size_group_key_map[size_group_key],
                table_extraction_artifact=table_extraction_artifact,
            )
        self._execplan_validate(
            source_discovery_by_size_group_key_map=source_discovery_by_size_group_key_map,
            table_extraction_artifact_by_size_group_key_map=table_extraction_artifact_by_size_group_key_map,
        )

    def error_list_get(
        self,
        table_extraction_batch_result: TableExtractionBatchResult,
        *,
        source_discovery_list: list[SourceDiscovery],
    ) -> list[str]:
        """Return batch table-extraction mechanical validation errors.

        Args:
            table_extraction_batch_result: Batch table extraction result to validate.
            source_discovery_list: Source discoveries that own table identities.

        Returns:
            Mechanical validation errors.
        """

        return self._error_list_get(
            lambda: self.validate(
                source_discovery_list=source_discovery_list,
                table_extraction_batch_result=table_extraction_batch_result,
            )
        )

    def table_extraction_batch_result_get(
        self,
        table_extraction_artifact_batch_result: TableExtractionArtifactBatchResult,
        *,
        source_discovery_list: list[SourceDiscovery],
    ) -> TableExtractionBatchResult:
        """Return final table extraction batch with chart artifacts loaded.

        Args:
            table_extraction_artifact_batch_result: Artifact-backed extraction result.
            source_discovery_list: Source discoveries that own table identities.

        Returns:
            Final table extraction batch with parsed charts.
        """

        self.artifact_validate(
            source_discovery_list=source_discovery_list,
            table_extraction_artifact_batch_result=table_extraction_artifact_batch_result,
        )
        return TableExtractionBatchResult(
            browsing_error_list=table_extraction_artifact_batch_result.browsing_error_list,
            error_list=table_extraction_artifact_batch_result.error_list,
            message=table_extraction_artifact_batch_result.message,
            source_type=table_extraction_artifact_batch_result.source_type,
            status=table_extraction_artifact_batch_result.status,
            table_extraction_list=[
                self.table_extraction_get(table_extraction_artifact)
                for table_extraction_artifact in table_extraction_artifact_batch_result.table_extraction_artifact_list
            ],
        )

    def table_extraction_get(self, table_extraction_artifact: TableExtractionArtifact) -> TableExtraction:
        """Return one final table extraction with parsed chart artifact.

        Args:
            table_extraction_artifact: Artifact-backed extraction result.

        Returns:
            Final table extraction with parsed chart.
        """

        return TableExtraction(
            applicability_description=table_extraction_artifact.applicability_description,
            applicability_status=table_extraction_artifact.applicability_status,
            chart=self._chart_get(table_extraction_artifact),
            chart_path=table_extraction_artifact.chart_path,
            evidence_path_list=table_extraction_artifact.evidence_path_list,
            product_type_hint_list=table_extraction_artifact.product_type_hint_list,
            size_group_key=table_extraction_artifact.size_group_key,
            source_title=table_extraction_artifact.source_title,
            source_type=table_extraction_artifact.source_type,
            source_url=table_extraction_artifact.source_url,
        )

    def validate(
        self,
        *,
        source_discovery_list: list[SourceDiscovery],
        table_extraction_batch_result: TableExtractionBatchResult,
    ) -> None:
        """Validate batch table-extraction structural consistency after semantic verification.

        Args:
            source_discovery_list: Source discoveries that own table identities.
            table_extraction_batch_result: Verified batch table extraction result.

        Raises:
            RuntimeError: If table extraction is structurally inconsistent.
        """

        if table_extraction_batch_result.status != "success":
            raise RuntimeError(f"table_extract status must be success: {table_extraction_batch_result.status}")
        source_type_set = {source_discovery.source_type for source_discovery in source_discovery_list}
        if source_type_set != {table_extraction_batch_result.source_type}:
            raise RuntimeError(
                f"table_extract source_type set mismatch: {sorted(source_type_set)} "
                f"!= {[table_extraction_batch_result.source_type]}"
            )
        source_discovery_by_size_group_key_map = self._source_discovery_by_size_group_key_map_get(source_discovery_list)
        table_extraction_by_size_group_key_map = self._table_extraction_by_size_group_key_map_get(
            table_extraction_batch_result.table_extraction_list
        )
        discovery_size_group_key_set = set(source_discovery_by_size_group_key_map)
        extraction_size_group_key_set = set(table_extraction_by_size_group_key_map)
        missing_size_group_key_list = sorted(discovery_size_group_key_set - extraction_size_group_key_set)
        extra_size_group_key_list = sorted(extraction_size_group_key_set - discovery_size_group_key_set)
        if missing_size_group_key_list or extra_size_group_key_list:
            message_part_list = []
            if missing_size_group_key_list:
                message_part_list.append(f"missing size_group_key list: {missing_size_group_key_list}")
            if extra_size_group_key_list:
                message_part_list.append(f"extra size_group_key list: {extra_size_group_key_list}")
            raise RuntimeError(f"table_extract size_group_key set mismatch; {'; '.join(message_part_list)}")
        for size_group_key, table_extraction in table_extraction_by_size_group_key_map.items():
            self._table_extraction_validate(
                source_discovery=source_discovery_by_size_group_key_map[size_group_key],
                table_extraction=table_extraction,
            )

    def _applicability_status_get(self, *, source_discovery: SourceDiscovery) -> str:
        """Return required applicability status for one verified source market.

        Args:
            source_discovery: Source discovery that owns the table identity.

        Returns:
            Required applicability status.
        """

        country_code_set = set(source_discovery.country_code_list)
        if country_code_set == {"GLOBAL"}:
            return "official_global"
        if country_code_set == {"EU"}:
            return "official_eu_consensus"
        if len(country_code_set) > 1:
            return "official_cross_locale_consensus"
        return "priority_country_official"

    def _chart_get(self, table_extraction_artifact: TableExtractionArtifact) -> BrandSizeChart:
        """Return the validated chart artifact for one extraction.

        Args:
            table_extraction_artifact: Artifact-backed table extraction.

        Returns:
            Parsed chart artifact.

        Raises:
            RuntimeError: If the chart artifact is missing or invalid.
        """

        self._artifact_reference_validator.path_list_validate(
            path_list=[table_extraction_artifact.chart_path],
            stage_key="table_extract",
        )
        chart_path = self._result_dir / table_extraction_artifact.chart_path
        expected_suffix = (
            f"source_type/{table_extraction_artifact.source_type}/table_extract/chart/"
            f"{table_extraction_artifact.size_group_key}.json"
        )
        if not table_extraction_artifact.chart_path.endswith(expected_suffix):
            raise RuntimeError(
                f"table_extraction chart_path mismatch for {table_extraction_artifact.size_group_key}: "
                f"{table_extraction_artifact.chart_path} must end with {expected_suffix}"
            )
        try:
            return BrandSizeChart.model_validate_json(chart_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"table_extraction chart artifact is invalid for {table_extraction_artifact.size_group_key}: {exc}"
            ) from exc

    def _execplan_item_list_get(self) -> list[TableExtractExecplanItem]:
        """Return validated durable table-extraction execplan items.

        Returns:
            Validated execplan item list.

        Raises:
            RuntimeError: If the stage directory is missing or the execplan artifact is invalid.
        """

        if self._stage_dir is None:
            return []
        execplan_path = self._stage_dir / "state.json"
        if not execplan_path.is_file():
            raise RuntimeError("table_extract must write state.json")
        try:
            execplan_payload = json.loads(execplan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("state.json is invalid JSON") from exc
        try:
            return TypeAdapter(list[TableExtractExecplanItem]).validate_python(execplan_payload)
        except ValidationError as exc:
            raise RuntimeError(f"state.json violates TableExtractExecplanItem contract: {exc}") from exc

    def _execplan_validate(
        self,
        *,
        source_discovery_by_size_group_key_map: dict[str, SourceDiscovery],
        table_extraction_artifact_by_size_group_key_map: dict[str, TableExtractionArtifact],
    ) -> None:
        """Validate durable table-extraction execplan against source and result identity.

        Args:
            source_discovery_by_size_group_key_map: Source discoveries keyed by size group key.
            table_extraction_artifact_by_size_group_key_map: Table extraction artifacts keyed by size group key.

        Raises:
            RuntimeError: If the execplan is missing, stale, or inconsistent.
        """

        execplan_item_list = self._execplan_item_list_get()
        if not execplan_item_list:
            return
        item_index_set: set[int] = set()
        for execplan_item in execplan_item_list:
            if execplan_item.item_index in item_index_set:
                raise RuntimeError(f"state.json duplicate item_index: {execplan_item.item_index}")
            item_index_set.add(execplan_item.item_index)
        execplan_item_by_size_group_key_map = {
            execplan_item.size_group_key: execplan_item for execplan_item in execplan_item_list
        }
        if len(execplan_item_by_size_group_key_map) != len(execplan_item_list):
            raise RuntimeError("state.json contains duplicate size_group_key values")
        discovery_size_group_key_set = set(source_discovery_by_size_group_key_map)
        execplan_size_group_key_set = set(execplan_item_by_size_group_key_map)
        if discovery_size_group_key_set != execplan_size_group_key_set:
            raise RuntimeError(
                "state.json size_group_key set mismatch: "
                f"execplan={sorted(execplan_size_group_key_set)}; discovery={sorted(discovery_size_group_key_set)}"
            )
        for size_group_key, execplan_item in execplan_item_by_size_group_key_map.items():
            source_discovery = source_discovery_by_size_group_key_map[size_group_key]
            table_extraction_artifact = table_extraction_artifact_by_size_group_key_map[size_group_key]
            self._execplan_item_validate(
                execplan_item=execplan_item,
                source_discovery=source_discovery,
                table_extraction_artifact=table_extraction_artifact,
            )

    def _execplan_item_validate(
        self,
        *,
        execplan_item: TableExtractExecplanItem,
        source_discovery: SourceDiscovery,
        table_extraction_artifact: TableExtractionArtifact,
    ) -> None:
        """Validate one execplan item against its source discovery and extraction artifact.

        Args:
            execplan_item: Durable execplan item.
            source_discovery: Matching source discovery.
            table_extraction_artifact: Matching extraction artifact.

        Raises:
            RuntimeError: If one execplan field is stale or inconsistent.
        """

        if execplan_item.state != "extracted":
            raise RuntimeError(
                f"state.json item for {execplan_item.size_group_key} must be extracted "
                f"when table_extract result is success"
            )
        if execplan_item.error:
            raise RuntimeError(f"state.json extracted item has error: {execplan_item.error}")
        if execplan_item.source_type != source_discovery.source_type:
            raise RuntimeError(f"state.json source_type mismatch for {execplan_item.size_group_key}")
        if execplan_item.source_url != source_discovery.source_url:
            raise RuntimeError(f"state.json source_url mismatch for {execplan_item.size_group_key}")
        if execplan_item.source_title != source_discovery.source_title:
            raise RuntimeError(f"state.json source_title mismatch for {execplan_item.size_group_key}")
        if execplan_item.chart_path != table_extraction_artifact.chart_path:
            raise RuntimeError(f"state.json chart_path mismatch for {execplan_item.size_group_key}")

    def _source_discovery_by_size_group_key_map_get(
        self, source_discovery_list: list[SourceDiscovery]
    ) -> dict[str, SourceDiscovery]:
        """Return source discoveries keyed by unique size group key.

        Args:
            source_discovery_list: Source discoveries to index.

        Returns:
            Source discovery map.

        Raises:
            RuntimeError: If source discoveries contain duplicate size group keys.
        """

        source_discovery_by_size_group_key_map = {
            source_discovery.size_group_key: source_discovery for source_discovery in source_discovery_list
        }
        if len(source_discovery_by_size_group_key_map) != len(source_discovery_list):
            raise RuntimeError("table_extract source_discovery_list contains duplicate size_group_key values")
        return source_discovery_by_size_group_key_map

    def _table_extraction_artifact_by_size_group_key_map_get(
        self, table_extraction_artifact_list: list[TableExtractionArtifact]
    ) -> dict[str, TableExtractionArtifact]:
        """Return table extraction artifacts keyed by unique size group key.

        Args:
            table_extraction_artifact_list: Table extraction artifacts to index.

        Returns:
            Table extraction artifact map.

        Raises:
            RuntimeError: If table extraction artifacts contain duplicate size group keys.
        """

        table_extraction_artifact_by_size_group_key_map = {
            table_extraction_artifact.size_group_key: table_extraction_artifact
            for table_extraction_artifact in table_extraction_artifact_list
        }
        if len(table_extraction_artifact_by_size_group_key_map) != len(table_extraction_artifact_list):
            raise RuntimeError("table_extract result contains duplicate size_group_key values")
        return table_extraction_artifact_by_size_group_key_map

    def _table_extraction_artifact_validate(
        self, *, source_discovery: SourceDiscovery, table_extraction_artifact: TableExtractionArtifact
    ) -> None:
        """Validate one table extraction artifact against its source discovery.

        Args:
            source_discovery: Source discovery that owns the table identity.
            table_extraction_artifact: Verified artifact-backed table extraction result.

        Raises:
            RuntimeError: If table extraction is structurally inconsistent.
        """

        self._table_extraction_validate(
            source_discovery=source_discovery,
            table_extraction=self.table_extraction_get(table_extraction_artifact),
        )

    def _table_extraction_by_size_group_key_map_get(
        self, table_extraction_list: list[TableExtraction]
    ) -> dict[str, TableExtraction]:
        """Return table extractions keyed by unique size group key.

        Args:
            table_extraction_list: Table extractions to index.

        Returns:
            Table extraction map.

        Raises:
            RuntimeError: If table extractions contain duplicate size group keys.
        """

        table_extraction_by_size_group_key_map = {
            table_extraction.size_group_key: table_extraction for table_extraction in table_extraction_list
        }
        if len(table_extraction_by_size_group_key_map) != len(table_extraction_list):
            raise RuntimeError("table_extract result contains duplicate size_group_key values")
        return table_extraction_by_size_group_key_map

    def _table_extraction_validate(
        self, *, source_discovery: SourceDiscovery, table_extraction: TableExtraction
    ) -> None:
        """Validate one table extraction against its source discovery.

        Args:
            source_discovery: Source discovery that owns the table identity.
            table_extraction: Verified table extraction result.

        Raises:
            RuntimeError: If table extraction is structurally inconsistent.
        """

        if table_extraction.source_type != source_discovery.source_type:
            raise RuntimeError(
                f"table_extraction source_type mismatch for {source_discovery.size_group_key}: "
                f"{table_extraction.source_type} != {source_discovery.source_type}"
            )
        if table_extraction.source_url != source_discovery.source_url:
            raise RuntimeError(
                f"table_extraction source_url mismatch for {source_discovery.size_group_key}: "
                f"{table_extraction.source_url} != {source_discovery.source_url}"
            )
        if table_extraction.source_title != source_discovery.source_title:
            raise RuntimeError(
                f"table_extraction source_title mismatch for {source_discovery.size_group_key}: "
                f"{table_extraction.source_title} != {source_discovery.source_title}"
            )
        if table_extraction.size_group_key != source_discovery.size_group_key:
            raise RuntimeError(
                f"table_extraction size_group_key mismatch: "
                f"{table_extraction.size_group_key} != {source_discovery.size_group_key}"
            )
        expected_applicability_status = self._applicability_status_get(source_discovery=source_discovery)
        if table_extraction.applicability_status != expected_applicability_status:
            raise RuntimeError(
                f"table_extraction applicability_status mismatch for {source_discovery.size_group_key}: "
                f"{table_extraction.applicability_status} != {expected_applicability_status}"
            )
        self._artifact_reference_validator.evidence_path_list_validate(
            evidence_path_list=table_extraction.evidence_path_list,
            stage_key="table_extract",
        )
        if not table_extraction.chart.row_list:
            raise RuntimeError(f"table_extraction returned an empty chart for {table_extraction.size_group_key}")
        for row_index, chart_row in enumerate(table_extraction.chart.row_list):
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
