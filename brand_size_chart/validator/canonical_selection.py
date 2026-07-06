"""Canonical-selection mechanical validation."""

from collections.abc import Collection, Mapping

from brand_size_chart.model import APPLICABILITY_STATUS_CANONICAL_SET, CanonicalSelectionResult, TableExtraction
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.validator.base import MechanicalValidator


class CanonicalSelectionValidator(MechanicalValidator):
    """Validate canonical-selection structural consistency."""

    def __init__(
        self,
        *,
        canonical_applicability_status_set: Collection[str] = frozenset(APPLICABILITY_STATUS_CANONICAL_SET),
        source_priority_by_key_map: Mapping[str, int] = SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map,
    ) -> None:
        """Store canonical table and source-priority contracts.

        Args:
            canonical_applicability_status_set: Applicability statuses eligible for canonical selection.
            source_priority_by_key_map: Source priority by source type key.
        """

        self._canonical_applicability_status_set = set(canonical_applicability_status_set)
        self._source_priority_by_key_map = dict(source_priority_by_key_map)

    def error_list_get(
        self, *, canonical_selection_result: CanonicalSelectionResult, table_extraction_list: list[TableExtraction]
    ) -> list[str]:
        """Return canonical-selection structural errors.

        Args:
            canonical_selection_result: Candidate canonical-selection result.
            table_extraction_list: Verified table extractions available for selection.

        Returns:
            Canonical-selection error list.
        """

        error_list: list[str] = []
        eligible_table_extraction_list = [
            table_extraction
            for table_extraction in table_extraction_list
            if table_extraction.applicability_status in self._canonical_applicability_status_set
        ]
        selected_size_group_key_set = {
            selection.size_group_key for selection in canonical_selection_result.canonical_selection_list
        }
        eligible_size_group_key_set = {
            table_extraction.size_group_key for table_extraction in eligible_table_extraction_list
        }
        missing_size_group_key_list = [
            size_group_key
            for size_group_key in sorted(eligible_size_group_key_set - selected_size_group_key_set)
            if not self._is_unresolved_same_priority_conflict(
                canonical_selection_result=canonical_selection_result,
                size_group_key=size_group_key,
                table_extraction_list=eligible_table_extraction_list,
            )
        ]
        if missing_size_group_key_list:
            error_list.append(
                "canonical_select missing eligible size_group_key values: " + ", ".join(missing_size_group_key_list)
            )

        extra_size_group_key_list = sorted(selected_size_group_key_set - eligible_size_group_key_set)
        if extra_size_group_key_list:
            error_list.append(
                "canonical_select selected non-eligible size_group_key values: " + ", ".join(extra_size_group_key_list)
            )

        seen_size_group_key_set: set[str] = set()
        for selection in canonical_selection_result.canonical_selection_list:
            if selection.size_group_key in seen_size_group_key_set:
                error_list.append(f"canonical_select duplicate size_group_key: {selection.size_group_key}")
                continue
            seen_size_group_key_set.add(selection.size_group_key)

            expected_priority = self._source_priority_by_key_map.get(selection.selected_source_type)
            if expected_priority is None:
                error_list.append(
                    f"canonical_select unknown source_type for {selection.size_group_key}: "
                    f"{selection.selected_source_type}"
                )
                continue
            if selection.selected_source_priority != expected_priority:
                error_list.append(
                    f"canonical_select priority mismatch for {selection.size_group_key}: "
                    f"{selection.selected_source_priority} != {expected_priority}"
                )

            matching_table_extraction_list = [
                table_extraction
                for table_extraction in eligible_table_extraction_list
                if table_extraction.size_group_key == selection.size_group_key
                and table_extraction.source_type == selection.selected_source_type
                and table_extraction.source_url == selection.selected_source_url
            ]
            if not matching_table_extraction_list:
                error_list.append(
                    "canonical_select missing table extraction: "
                    f"{selection.size_group_key} {selection.selected_source_type} {selection.selected_source_url}"
                )
                continue

            eligible_priority_list = [
                self._source_priority_by_key_map[table_extraction.source_type]
                for table_extraction in eligible_table_extraction_list
                if table_extraction.size_group_key == selection.size_group_key
            ]
            max_priority = max(eligible_priority_list)
            if selection.selected_source_priority < max_priority:
                error_list.append(
                    f"canonical_select selected lower priority for {selection.size_group_key}: "
                    f"{selection.selected_source_type} priority {selection.selected_source_priority} < {max_priority}"
                )
        return error_list

    def _is_unresolved_same_priority_conflict(
        self,
        *,
        canonical_selection_result: CanonicalSelectionResult,
        size_group_key: str,
        table_extraction_list: list[TableExtraction],
    ) -> bool:
        """Return whether one missing selection is an explicit unresolved same-priority conflict.

        Args:
            canonical_selection_result: Candidate canonical-selection result.
            size_group_key: Missing size group key to inspect.
            table_extraction_list: Eligible table extractions available for selection.

        Returns:
            Whether the missing selection is intentionally represented by structured conflict objects.
        """

        if canonical_selection_result.status != "failed":
            return False
        same_size_group_table_extraction_list = [
            table_extraction
            for table_extraction in table_extraction_list
            if table_extraction.size_group_key == size_group_key
        ]
        if not same_size_group_table_extraction_list:
            return False
        max_priority = max(
            self._source_priority_by_key_map[table_extraction.source_type]
            for table_extraction in same_size_group_table_extraction_list
        )
        max_priority_table_extraction_list = [
            table_extraction
            for table_extraction in same_size_group_table_extraction_list
            if self._source_priority_by_key_map[table_extraction.source_type] == max_priority
        ]
        if len(max_priority_table_extraction_list) < 2:
            return False
        conflict_identity_set = {
            (
                conflict.size_group_key,
                conflict.source_type,
                conflict.source_url,
                conflict.source_priority,
                conflict.applicability_status,
                conflict.chart_path,
            )
            for conflict in canonical_selection_result.conflict_list
            if conflict.size_group_key == size_group_key
        }
        expected_identity_set = {
            (
                table_extraction.size_group_key,
                table_extraction.source_type,
                table_extraction.source_url,
                max_priority,
                table_extraction.applicability_status,
                table_extraction.chart_path,
            )
            for table_extraction in max_priority_table_extraction_list
        }
        if not expected_identity_set.issubset(conflict_identity_set):
            return False
        error_prefix = f"{size_group_key}:"
        return any(error.startswith(error_prefix) for error in canonical_selection_result.error_list)

    def validate(
        self, *, canonical_selection_result: CanonicalSelectionResult, table_extraction_list: list[TableExtraction]
    ) -> None:
        """Validate canonical-selection structural consistency.

        Args:
            canonical_selection_result: Verified canonical-selection result.
            table_extraction_list: Verified table extractions available for selection.

        Raises:
            RuntimeError: If selection points to missing or inconsistent table data.
        """

        error_list = self.error_list_get(
            canonical_selection_result=canonical_selection_result,
            table_extraction_list=table_extraction_list,
        )
        if error_list:
            raise RuntimeError("; ".join(error_list))
