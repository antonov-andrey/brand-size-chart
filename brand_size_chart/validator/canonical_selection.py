"""Canonical-selection mechanical validation."""

from brand_size_chart.model import (
    APPLICABILITY_STATUS_CANONICAL_SET,
    CanonicalSelectionCandidate,
    CanonicalSelectionPromptContext,
    CanonicalSelectionResult,
)


class CanonicalSelectionValidator:
    """Validate canonical-selection structural consistency."""

    def __init__(self, *, prompt_context: CanonicalSelectionPromptContext) -> None:
        """Store canonical-selection prompt context.

        Args:
            prompt_context: Canonical-selection prompt context used by the action.
        """

        self._prompt_context = prompt_context

    def validate(self, canonical_selection_result: CanonicalSelectionResult) -> None:
        """Validate canonical-selection structural consistency.

        Args:
            canonical_selection_result: Verified canonical-selection result.

        Raises:
            RuntimeError: If selection points to missing or inconsistent table data.
        """

        eligible_candidate_list = self._eligible_candidate_list_get(
            self._prompt_context.canonical_selection_candidate_list
        )
        eligible_candidate_by_chart_path_map = self._candidate_by_chart_path_map_get(eligible_candidate_list)
        selected_size_group_key_set = self._selection_list_validate(
            canonical_selection_result=canonical_selection_result,
            eligible_candidate_by_chart_path_map=eligible_candidate_by_chart_path_map,
            eligible_candidate_list=eligible_candidate_list,
        )
        self._missing_selection_validate(
            eligible_candidate_list=eligible_candidate_list,
            selected_size_group_key_set=selected_size_group_key_set,
        )

    def _candidate_by_chart_path_map_get(
        self, candidate_list: list[CanonicalSelectionCandidate]
    ) -> dict[str, CanonicalSelectionCandidate]:
        """Return candidates keyed by unique chart path.

        Args:
            candidate_list: Verified candidates available for selection.

        Returns:
            Candidate map keyed by chart path.

        Raises:
            RuntimeError: If chart paths are duplicated.
        """

        candidate_by_chart_path_map = {
            candidate.table_extraction_artifact.chart_path: candidate for candidate in candidate_list
        }
        if len(candidate_by_chart_path_map) != len(candidate_list):
            raise RuntimeError("canonical_select candidate list contains duplicate chart_path values")
        return candidate_by_chart_path_map

    def _eligible_candidate_list_get(
        self, candidate_list: list[CanonicalSelectionCandidate]
    ) -> list[CanonicalSelectionCandidate]:
        """Return candidates eligible for canonical selection.

        Args:
            candidate_list: Verified candidates available for selection.

        Returns:
            Eligible candidate list.
        """

        return [
            candidate
            for candidate in candidate_list
            if candidate.applicability_status in APPLICABILITY_STATUS_CANONICAL_SET
        ]

    def _missing_selection_validate(
        self,
        *,
        eligible_candidate_list: list[CanonicalSelectionCandidate],
        selected_size_group_key_set: set[str],
    ) -> None:
        """Validate that missing selections are only unresolved same-priority groups.

        Args:
            eligible_candidate_list: Eligible candidates available for selection.
            selected_size_group_key_set: Size groups represented by canonical selections.

        Raises:
            RuntimeError: If one eligible size group is missing without same-priority ambiguity.
        """

        eligible_size_group_key_set = {
            candidate.table_extraction_artifact.size_group_key for candidate in eligible_candidate_list
        }
        missing_size_group_key_list: list[str] = []
        for size_group_key in sorted(eligible_size_group_key_set - selected_size_group_key_set):
            same_size_group_candidate_list = [
                candidate
                for candidate in eligible_candidate_list
                if candidate.table_extraction_artifact.size_group_key == size_group_key
            ]
            max_priority = max(candidate.source_priority for candidate in same_size_group_candidate_list)
            max_priority_candidate_list = [
                candidate for candidate in same_size_group_candidate_list if candidate.source_priority == max_priority
            ]
            if len(max_priority_candidate_list) < 2:
                missing_size_group_key_list.append(size_group_key)
        if missing_size_group_key_list:
            raise RuntimeError(
                "canonical_select missing eligible size_group_key values: " + ", ".join(missing_size_group_key_list)
            )

    def _selection_list_validate(
        self,
        *,
        canonical_selection_result: CanonicalSelectionResult,
        eligible_candidate_by_chart_path_map: dict[str, CanonicalSelectionCandidate],
        eligible_candidate_list: list[CanonicalSelectionCandidate],
    ) -> set[str]:
        """Validate selected rows against eligible candidates.

        Args:
            canonical_selection_result: Candidate canonical-selection result.
            eligible_candidate_by_chart_path_map: Eligible candidates keyed by chart path.
            eligible_candidate_list: Eligible candidates available for selection.

        Raises:
            RuntimeError: If one selection is duplicated, missing, or lower priority than another candidate.

        Returns:
            Size groups represented by canonical selections.
        """

        seen_chart_path_set: set[str] = set()
        seen_size_group_key_set: set[str] = set()
        for selection in canonical_selection_result.canonical_selection_list:
            if selection.selected_chart_path in seen_chart_path_set:
                raise RuntimeError(f"canonical_select duplicate selected_chart_path: {selection.selected_chart_path}")
            seen_chart_path_set.add(selection.selected_chart_path)

            selected_candidate = eligible_candidate_by_chart_path_map.get(selection.selected_chart_path)
            if selected_candidate is None:
                raise RuntimeError(
                    "canonical_select missing table extraction for selected_chart_path: "
                    f"{selection.selected_chart_path}"
                )
            selected_table_extraction = selected_candidate.table_extraction_artifact
            if selected_table_extraction.size_group_key in seen_size_group_key_set:
                raise RuntimeError(
                    f"canonical_select duplicate size_group_key: {selected_table_extraction.size_group_key}"
                )
            seen_size_group_key_set.add(selected_table_extraction.size_group_key)
            same_size_group_candidate_list = [
                candidate
                for candidate in eligible_candidate_list
                if candidate.table_extraction_artifact.size_group_key == selected_table_extraction.size_group_key
            ]
            max_priority = max(candidate.source_priority for candidate in same_size_group_candidate_list)
            if selected_candidate.source_priority < max_priority:
                raise RuntimeError(
                    f"canonical_select selected lower priority for {selected_table_extraction.size_group_key}: "
                    f"{selected_table_extraction.source_type} priority {selected_candidate.source_priority} "
                    f"< {max_priority}"
                )
            max_priority_candidate_list = [
                candidate for candidate in same_size_group_candidate_list if candidate.source_priority == max_priority
            ]
            if len(max_priority_candidate_list) > 1:
                representative_candidate = sorted(
                    max_priority_candidate_list,
                    key=lambda candidate: (
                        candidate.table_extraction_artifact.chart_path,
                        candidate.table_extraction_artifact.source_url,
                        candidate.table_extraction_artifact.source_title,
                    ),
                )[0]
                if selection.selected_chart_path != representative_candidate.table_extraction_artifact.chart_path:
                    raise RuntimeError(
                        "canonical_select selected non-deterministic representative for "
                        f"{selected_table_extraction.size_group_key}: expected "
                        f"{representative_candidate.table_extraction_artifact.chart_path}, "
                        f"got {selection.selected_chart_path}"
                    )
        return seen_size_group_key_set
