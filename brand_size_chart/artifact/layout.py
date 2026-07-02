"""Deterministic artifact path layout for brand size-chart workflow runs."""

from pathlib import Path

from brand_size_chart.model import BrandInput


class ArtifactLayout:
    """Build deterministic output and audit artifact paths."""

    def __init__(self, result_dir: Path) -> None:
        """Store the result root directory.

        Args:
            result_dir: Root result directory.
        """

        self.result_dir = result_dir

    def artifact_path(self, path: Path) -> str:
        """Return one result-dir-relative artifact path.

        Args:
            path: Artifact path.

        Returns:
            Relative artifact path as POSIX text.
        """

        return path.relative_to(self.result_dir).as_posix()

    def filesystem_path_get(self, path: Path) -> str:
        """Return one absolute filesystem path for runtime file writes.

        Args:
            path: Artifact path.

        Returns:
            Absolute filesystem path as POSIX text.
        """

        return path.resolve().as_posix()

    def brand_audit_dir(self, brand_input: BrandInput) -> Path:
        """Return audit directory for one brand.

        Args:
            brand_input: Parsed brand input.

        Returns:
            Brand audit directory.
        """

        return self.result_dir / "brand_size_chart_audit" / "brand" / brand_input.parsed_brand_key

    def brand_coverage_decide_dir(self, brand_input: BrandInput) -> Path:
        """Return final brand coverage-decision audit directory.

        Args:
            brand_input: Parsed brand input.

        Returns:
            Final brand coverage-decision stage directory.
        """

        return self.brand_audit_dir(brand_input) / "coverage_decide"

    def brand_manifest_path(self, brand_input: BrandInput) -> Path:
        """Return final brand manifest path.

        Args:
            brand_input: Parsed brand input.

        Returns:
            Brand manifest artifact path.
        """

        return self.brand_output_dir(brand_input) / "manifest.json"

    def brand_output_dir(self, brand_input: BrandInput) -> Path:
        """Return canonical output directory for one brand.

        Args:
            brand_input: Parsed brand input.

        Returns:
            Brand output directory.
        """

        return self.result_dir / "brand_size_chart" / "brand" / brand_input.parsed_brand_key

    def brand_result_path(self, brand_input: BrandInput) -> Path:
        """Return final brand audit result path.

        Args:
            brand_input: Parsed brand input.

        Returns:
            Brand result artifact path.
        """

        return self.brand_audit_dir(brand_input) / "brand_result" / "result.json"

    def brand_size_chart_path(self, brand_input: BrandInput, size_group_key: str) -> Path:
        """Return final size-chart output path.

        Args:
            brand_input: Parsed brand input.
            size_group_key: Size group key.

        Returns:
            Size-chart artifact path.
        """

        return self.brand_output_dir(brand_input) / "size_chart" / f"{size_group_key}.json"

    def canonical_select_dir(self, brand_input: BrandInput) -> Path:
        """Return canonical-selection audit directory for one brand.

        Args:
            brand_input: Parsed brand input.

        Returns:
            Canonical-selection stage directory.
        """

        return self.brand_audit_dir(brand_input) / "canonical_select"

    def coverage_decide_dir(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return coverage-decision audit directory for one source type.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Coverage-decision stage directory.
        """

        return self.source_type_dir(brand_input, source_type) / "coverage_decide"

    def run_result_path(self) -> Path:
        """Return root run result audit path.

        Returns:
            Run result artifact path.
        """

        return self.result_dir / "brand_size_chart_audit" / "run" / "result.json"

    def source_discover_dir(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return source-discovery audit directory for one source type.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Source-discovery stage directory.
        """

        return self.source_type_dir(brand_input, source_type) / "source_discover"

    def source_discover_evidence_dir(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return source-discovery evidence directory for one source type.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Source-discovery evidence directory.
        """

        return (
            self.result_dir
            / ".playwright-mcp"
            / "current"
            / "brand_size_chart_audit"
            / "brand"
            / brand_input.parsed_brand_key
            / "source_type"
            / source_type
            / "source_discover"
            / "evidence"
        )

    def source_type_dir(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return audit directory for one brand source type.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Source-type audit directory.
        """

        return self.brand_audit_dir(brand_input) / "source_type" / source_type

    def source_type_summary_result_path(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return source-type summary result path.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Source-type summary result artifact path.
        """

        return self.source_type_dir(brand_input, source_type) / "source_type_summary" / "result.json"

    def stage_result_path(self, stage_dir: Path) -> Path:
        """Return generic stage result artifact path.

        Args:
            stage_dir: Stage artifact directory.

        Returns:
            Stage result artifact path.
        """

        return stage_dir / "result.json"

    def stage_verification_path(self, stage_dir: Path) -> Path:
        """Return generic stage verification artifact path.

        Args:
            stage_dir: Stage artifact directory.

        Returns:
            Stage verification artifact path.
        """

        return stage_dir / "verification.json"

    def table_extract_dir(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return batch table-extract audit directory for one source type.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Batch table-extract stage directory.
        """

        return self.source_type_dir(brand_input, source_type) / "table_extract"

    def table_extract_chart_path(self, brand_input: BrandInput, source_type: str, size_group_key: str) -> Path:
        """Return generated batch chart artifact path.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.
            size_group_key: Size group key.

        Returns:
            Batch chart artifact path.
        """

        return self.table_extract_dir(brand_input, source_type) / "chart" / f"{size_group_key}.json"

    def table_extract_result_path(self, brand_input: BrandInput, source_type: str) -> Path:
        """Return batch table-extract result path.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.

        Returns:
            Batch table-extract result artifact path.
        """

        return self.stage_result_path(self.table_extract_dir(brand_input, source_type))

    def table_extract_evidence_dir(self, brand_input: BrandInput, source_type: str, size_group_key: str) -> Path:
        """Return batch table-extract evidence directory for one size group.

        Args:
            brand_input: Parsed brand input.
            source_type: Source type key.
            size_group_key: Size group key.

        Returns:
            Batch table-extract evidence directory.
        """

        return (
            self.result_dir
            / ".playwright-mcp"
            / "current"
            / "brand_size_chart_audit"
            / "brand"
            / brand_input.parsed_brand_key
            / "source_type"
            / source_type
            / "table_extract"
            / "evidence"
            / size_group_key
        )

    def workflow_run_prompt_apply_dir(self) -> Path:
        """Return workflow-run prompt application audit directory.

        Returns:
            Workflow-run prompt application stage directory.
        """

        return self.result_dir / "brand_size_chart_audit" / "run" / "workflow_run_prompt_apply"
