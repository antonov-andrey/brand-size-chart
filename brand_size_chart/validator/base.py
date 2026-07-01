"""Shared mechanical validator helpers."""

from collections.abc import Callable


class MechanicalValidator:
    """Base helper for validators that report `RuntimeError` messages."""

    def _error_list_get(self, validate_call: Callable[[], None]) -> list[str]:
        """Return one validation error list from a validation call.

        Args:
            validate_call: No-argument validation callable.

        Returns:
            Empty list on success, otherwise one captured error message.
        """

        try:
            validate_call()
        except RuntimeError as exc:
            return [str(exc)]
        return []
