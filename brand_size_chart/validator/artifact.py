"""Artifact-path mechanical validation for explicit workflow artifacts."""

from pathlib import Path

from brand_size_chart.artifact import ArtifactReferenceValidator
from brand_size_chart.validator.base import MechanicalValidator


class ArtifactValidator(MechanicalValidator):
    """Validate explicit artifact references inside one result directory."""

    def __init__(self, result_dir: Path) -> None:
        """Store the explicit result directory.

        Args:
            result_dir: Root result directory.
        """

        self._artifact_reference_validator = ArtifactReferenceValidator(result_dir)

    def evidence_path_list_validate(self, *, evidence_path_list: list[str], stage_key: str) -> None:
        """Validate explicit evidence artifact references.

        Args:
            evidence_path_list: Result-dir-relative evidence artifact references.
            stage_key: Stable stage key for diagnostics.
        """

        self._artifact_reference_validator.evidence_path_list_validate(
            evidence_path_list=evidence_path_list,
            stage_key=stage_key,
        )

    def path_list_validate(self, *, path_list: list[str], stage_key: str) -> None:
        """Validate explicit artifact references.

        Args:
            path_list: Result-dir-relative artifact references.
            stage_key: Stable stage key for diagnostics.
        """

        self._artifact_reference_validator.path_list_validate(
            path_list=path_list,
            stage_key=stage_key,
        )
