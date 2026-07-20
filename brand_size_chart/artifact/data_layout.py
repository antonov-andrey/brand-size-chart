"""User-visible Data paths for one brand size-chart run."""

from pathlib import Path

from workflow_container_runtime.data import WorkflowDataPath

from brand_size_chart.model import BrandInput
from brand_size_chart.model.source import market_scope_key_validate, size_group_key_validate


class BrandDataLayout:
    """Resolve exact result and workspace paths below the standard Data roots."""

    def __init__(self, data_path: WorkflowDataPath) -> None:
        """Store one immutable pair of standard run Data roots.

        Args:
            data_path: Exact image-visible result and workspace roots.
        """

        self._data_path = data_path

    def dataset_path(self, brand_input: BrandInput) -> Path:
        """Return the single JSON Lines dataset file for one brand.

        Args:
            brand_input: Parsed brand identity.

        Returns:
            Dataset file below the declared brand result manifest.
        """

        return self.result_brand_dir(brand_input) / "dataset" / "brand_size_chart" / "part-00000.jsonl"

    def result_artifact_path(self, path: Path) -> str:
        """Return one canonical image-relative result artifact path.

        Args:
            path: Exact path below the standard result root.

        Returns:
            POSIX path beginning with `result/`.
        """

        return (Path("result") / path.resolve().relative_to(self._data_path.result_path.resolve())).as_posix()

    def result_brand_dir(self, brand_input: BrandInput) -> Path:
        """Return the declared result manifest root for one brand.

        Args:
            brand_input: Parsed brand identity.

        Returns:
            Exact brand result directory.
        """

        return self._data_path.result_path / brand_input.parsed_brand_key

    def size_chart_path(self, brand_input: BrandInput, size_group_key: str, market_scope_key: str) -> Path:
        """Return one canonical user-visible size-chart path.

        Args:
            brand_input: Parsed brand identity.
            size_group_key: Manufacturer-derived physical table key.
            market_scope_key: Deterministic market scope key.

        Returns:
            Final chart path below the declared brand result manifest.
        """

        return (
            self.result_brand_dir(brand_input)
            / "size_chart"
            / (f"{size_group_key_validate(size_group_key)}__{market_scope_key_validate(market_scope_key)}.json")
        )

    def workspace_brand_dir(self, brand_input: BrandInput) -> Path:
        """Return the declared workspace manifest root for one brand.

        Args:
            brand_input: Parsed brand identity.

        Returns:
            Exact brand workspace directory.
        """

        return self._data_path.workspace_path / brand_input.parsed_brand_key
