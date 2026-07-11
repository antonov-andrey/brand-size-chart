"""Domain artifact paths inside one brand size-chart result root."""

from pathlib import Path

from brand_size_chart.model import BrandInput
from brand_size_chart.model.source import market_scope_key_validate, size_group_key_validate


class ArtifactLayout:
    """Build final output paths and current-step declared artifact targets."""

    def __init__(self, result_dir: Path) -> None:
        """Store one absolute result root.

        Args:
            result_dir: Root result directory.
        """

        self.result_dir = result_dir.resolve()

    def artifact_path(self, path: Path) -> str:
        """Return one result-relative public artifact reference.

        Args:
            path: Artifact path inside the result root.

        Returns:
            Relative POSIX artifact path.
        """

        return path.resolve().relative_to(self.result_dir).as_posix()

    def brand_output_dir(self, brand_input: BrandInput) -> Path:
        """Return the final output directory for one brand.

        Args:
            brand_input: Parsed brand identity.

        Returns:
            Brand output directory.
        """

        return self.result_dir / "brand_size_chart" / "brand" / brand_input.parsed_brand_key

    def brand_size_chart_path(self, brand_input: BrandInput, size_group_key: str, market_scope_key: str) -> Path:
        """Return one final canonical size-chart path.

        Args:
            brand_input: Parsed brand identity.
            size_group_key: Manufacturer-derived physical table key.
            market_scope_key: Deterministic market scope key.

        Returns:
            Final size-chart artifact path.
        """

        return (
            self.brand_output_dir(brand_input)
            / "size_chart"
            / (f"{size_group_key_validate(size_group_key)}__{market_scope_key_validate(market_scope_key)}.json")
        )

    def source_discovery_chart_path(
        self,
        step_instance_dir: Path,
        size_group_key: str,
        market_scope_key: str,
    ) -> Path:
        """Return one current-step chart path from its two-component identity.

        Args:
            step_instance_dir: Current source-discovery step directory.
            size_group_key: Manufacturer-derived physical table key.
            market_scope_key: Deterministic market scope key.

        Returns:
            Current step chart artifact path.
        """

        return self.step_artifact_path(
            step_instance_dir,
            Path("chart")
            / f"{size_group_key_validate(size_group_key)}__{market_scope_key_validate(market_scope_key)}.json",
        )

    def external_step_artifact_dir(self, step_instance_dir: Path, relative_dir: Path) -> Path:
        """Return one external write directory mirrored to the current step.

        Args:
            step_instance_dir: Current canonical step directory.
            relative_dir: Artifact directory relative to the step.

        Returns:
            External artifact write directory.

        Raises:
            ValueError: If the step or relative directory escapes its owner.
        """

        step_relative_path = step_instance_dir.resolve().relative_to(self.result_dir)
        if relative_dir.is_absolute() or ".." in relative_dir.parts:
            raise ValueError("relative_dir must stay inside the current step")
        return self.result_dir / ".playwright-mcp" / "current" / step_relative_path / relative_dir

    def filesystem_path_get(self, path: Path) -> str:
        """Return one absolute filesystem path for a declared write target.

        Args:
            path: Artifact path.

        Returns:
            Absolute POSIX path.
        """

        return path.resolve().as_posix()

    def step_artifact_path(self, step_instance_dir: Path, relative_path: Path) -> Path:
        """Return one canonical artifact path inside the current step.

        Args:
            step_instance_dir: Current canonical step directory.
            relative_path: Artifact path relative to the step.

        Returns:
            Canonical step artifact path.

        Raises:
            ValueError: If the step or relative path escapes its owner.
        """

        step_instance_dir = step_instance_dir.resolve()
        step_instance_dir.relative_to(self.result_dir)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("relative_path must stay inside the current step")
        return step_instance_dir / relative_path
