"""Generic artifact reference materialization."""

from pathlib import Path


class ArtifactMaterializer:
    """Convert allowed filesystem references into run-relative artifact paths."""

    def __init__(self, result_dir: Path, allowed_root_list: list[Path]) -> None:
        """Store the result directory and allowed reference roots.

        Args:
            result_dir: Root result directory.
            allowed_root_list: Absolute or relative directories allowed to contain materialized references.
        """

        self.allowed_root_list = [allowed_root.resolve() for allowed_root in allowed_root_list]
        self.result_dir = result_dir.resolve()

    def reference_list_materialize(self, reference_list: list[str]) -> list[str]:
        """Return run-relative POSIX references for allowed filesystem paths.

        Args:
            reference_list: Filesystem paths to materialize.

        Returns:
            Result-dir-relative POSIX artifact references.

        Raises:
            RuntimeError: If one reference is outside all allowed roots or outside the result directory.
        """

        materialized_reference_list = []
        for reference in reference_list:
            reference_path = Path(reference).resolve()
            self._reference_path_validate(reference_path=reference_path, reference=reference)
            try:
                materialized_reference_list.append(reference_path.relative_to(self.result_dir).as_posix())
            except ValueError as exc:
                raise RuntimeError(f"Artifact reference is outside result_dir: {reference}") from exc
        return materialized_reference_list

    def _reference_path_validate(self, *, reference_path: Path, reference: str) -> None:
        """Validate one filesystem reference against allowed roots.

        Args:
            reference_path: Resolved filesystem reference path.
            reference: Original reference text for diagnostics.

        Raises:
            RuntimeError: If the resolved path is outside all allowed roots.
        """

        for allowed_root in self.allowed_root_list:
            try:
                reference_path.relative_to(allowed_root)
            except ValueError:
                continue
            return
        raise RuntimeError(f"Artifact reference is outside allowed roots: {reference}")
