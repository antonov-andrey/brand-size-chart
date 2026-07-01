"""Artifact reference validation for run-relative paths."""

from pathlib import Path


class ArtifactReferenceValidator:
    """Validate artifact references returned by workflow stages."""

    def __init__(self, result_dir: Path) -> None:
        """Store the result root directory.

        Args:
            result_dir: Root result directory.
        """

        self.result_dir = result_dir.resolve()

    def evidence_path_list_validate(self, *, evidence_path_list: list[str], stage_key: str) -> None:
        """Validate that evidence references point to existing run artifacts.

        Args:
            evidence_path_list: Result-dir-relative artifact references.
            stage_key: Stable stage key for diagnostics.

        Raises:
            RuntimeError: If one evidence reference is absent or points outside the run directory.
        """

        if not evidence_path_list:
            raise RuntimeError(f"Stage {stage_key} returned no evidence_path_list.")
        for evidence_path_text in evidence_path_list:
            self._artifact_path_validate(
                missing_message=f"Stage {stage_key} returned missing evidence artifact: {evidence_path_text}",
                outside_message=f"Stage {stage_key} returned evidence outside result_dir: {evidence_path_text}",
                path_text=evidence_path_text,
            )

    def path_list_validate(self, *, path_list: list[str], stage_key: str) -> None:
        """Validate that artifact references point to existing run artifacts.

        Args:
            path_list: Result-dir-relative artifact references.
            stage_key: Stable stage key for diagnostics.

        Raises:
            RuntimeError: If one artifact reference is absent or points outside the run directory.
        """

        for path_text in path_list:
            self._artifact_path_validate(
                missing_message=f"Stage {stage_key} returned missing artifact: {path_text}",
                outside_message=f"Stage {stage_key} returned artifact outside result_dir: {path_text}",
                path_text=path_text,
            )

    def _artifact_path_validate(self, *, missing_message: str, outside_message: str, path_text: str) -> None:
        """Validate one result-dir-relative artifact path.

        Args:
            missing_message: Error message for missing artifacts.
            outside_message: Error message for outside artifacts.
            path_text: Result-dir-relative artifact reference.

        Raises:
            RuntimeError: If the artifact reference is invalid.
        """

        artifact_path = (self.result_dir / path_text).resolve()
        try:
            artifact_path.relative_to(self.result_dir)
        except ValueError as exc:
            raise RuntimeError(outside_message) from exc
        if not artifact_path.exists():
            raise RuntimeError(missing_message)
