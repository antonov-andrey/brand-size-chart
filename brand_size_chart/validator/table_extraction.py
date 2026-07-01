"""Table-extraction mechanical validation."""

from pathlib import Path

from brand_size_chart.model import SourceDiscovery, TableExtraction
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

    def error_list_get(self, table_extraction: TableExtraction, *, source_discovery: SourceDiscovery) -> list[str]:
        """Return table-extraction mechanical validation errors.

        Args:
            table_extraction: Table extraction result to validate.
            source_discovery: Source discovery that owns the table identity.

        Returns:
            Mechanical validation errors.
        """

        return self._error_list_get(
            lambda: self.validate(
                source_discovery=source_discovery,
                table_extraction=table_extraction,
            )
        )

    def validate(self, *, source_discovery: SourceDiscovery, table_extraction: TableExtraction) -> None:
        """Validate table-extraction structural consistency after semantic verification.

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
        if table_extraction.size_group_key != source_discovery.size_group_key:
            raise RuntimeError(
                f"table_extraction size_group_key mismatch: "
                f"{table_extraction.size_group_key} != {source_discovery.size_group_key}"
            )
        self._artifact_validator.evidence_path_list_validate(
            evidence_path_list=table_extraction.evidence_path_list,
            stage_key="table_extraction",
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
