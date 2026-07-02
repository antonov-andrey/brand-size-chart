"""Table-extraction mechanical validation."""

from pathlib import Path

from brand_size_chart.model import (
    BrandSizeChart,
    SourceDiscovery,
    TableExtraction,
    TableExtractionArtifact,
    TableExtractionArtifactBatchResult,
    TableExtractionBatchResult,
)
from brand_size_chart.validator.artifact import ArtifactValidator
from brand_size_chart.validator.base import MechanicalValidator


class TableExtractionValidator(MechanicalValidator):
    """Validate table-extraction structural consistency."""

    def __init__(self, result_dir: Path) -> None:
        """Store the explicit result directory.

        Args:
            result_dir: Root result directory.
        """

        self._artifact_validator = ArtifactValidator(result_dir)
        self._result_dir = result_dir

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

        self._artifact_validator.path_list_validate(
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
        self._artifact_validator.evidence_path_list_validate(
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
