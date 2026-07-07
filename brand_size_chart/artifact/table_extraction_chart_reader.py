"""Table-extraction chart artifact reader."""

from pathlib import Path

from brand_size_chart.artifact.reference_validator import ArtifactReferenceValidator
from brand_size_chart.model import BrandSizeChart, TableExtractionArtifact


class TableExtractionChartReader:
    """Load validated chart artifacts referenced by table extraction results."""

    def __init__(self, result_dir: Path) -> None:
        """Store chart artifact dependencies.

        Args:
            result_dir: Root result directory.
        """

        self._artifact_reference_validator = ArtifactReferenceValidator(result_dir)
        self._result_dir = result_dir

    def chart_get(self, table_extraction_artifact: TableExtractionArtifact) -> BrandSizeChart:
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
        try:
            return BrandSizeChart.model_validate_json(chart_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"table_extraction chart artifact is invalid for {table_extraction_artifact.size_group_key}: {exc}"
            ) from exc
