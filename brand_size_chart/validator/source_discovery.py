"""Source-discovery mechanical validation."""

import json
from pathlib import Path

from pydantic import ValidationError
from workflow_container_runtime.stage import BrowserActionResult

from brand_size_chart.artifact import ArtifactReferenceValidator
from brand_size_chart.model import (
    SourceDiscoveryInput,
    SourceSurfaceInventory,
    SourceSurfaceTable,
)


class SourceDiscoveryValidator:
    """Validate source-discovery structural consistency."""

    def __init__(
        self,
        *,
        stage_input: SourceDiscoveryInput,
        result_dir: Path,
        stage_dir: Path,
    ) -> None:
        """Store source-discovery validation input.

        Args:
            stage_input: Source-discovery input used by the action.
            result_dir: Root result directory.
            stage_dir: Source-discovery stage artifact directory.
        """

        self._artifact_reference_validator = ArtifactReferenceValidator(result_dir)
        self._stage_input = stage_input
        self._stage_dir = stage_dir

    def _country_selection_validate(self, *, accepted_table_list: list[SourceSurfaceTable]) -> None:
        """Validate the source-discovery market selection ladder.

        Args:
            accepted_table_list: Accepted source-surface table rows.

        Raises:
            RuntimeError: If lower-priority market scopes are mixed into a higher-priority result.
        """

        priority_country_code = self._stage_input.priority_country_code
        priority_country_source_list = [
            source_surface_table
            for source_surface_table in accepted_table_list
            if priority_country_code in source_surface_table.source_discovery.country_code_list
        ]
        if priority_country_source_list:
            non_priority_country_size_group_key_list = [
                source_surface_table.source_discovery.size_group_key
                for source_surface_table in accepted_table_list
                if priority_country_code not in source_surface_table.source_discovery.country_code_list
            ]
            if non_priority_country_size_group_key_list:
                raise RuntimeError(
                    "source_discover contains non-priority country candidates while priority country tables exist: "
                    f"priority_country_code={priority_country_code}; "
                    f"size_group_key_list={sorted(non_priority_country_size_group_key_list)}"
                )
            return

        global_source_list = [
            source_surface_table
            for source_surface_table in accepted_table_list
            if "GLOBAL" in source_surface_table.source_discovery.country_code_list
        ]
        if global_source_list:
            non_global_size_group_key_list = [
                source_surface_table.source_discovery.size_group_key
                for source_surface_table in accepted_table_list
                if "GLOBAL" not in source_surface_table.source_discovery.country_code_list
            ]
            if non_global_size_group_key_list:
                raise RuntimeError(
                    "source_discover contains non-global candidates while global tables exist: "
                    f"priority_country_code={priority_country_code}; "
                    f"size_group_key_list={sorted(non_global_size_group_key_list)}"
                )
            return

        non_europe_size_group_key_list = [
            source_surface_table.source_discovery.size_group_key
            for source_surface_table in accepted_table_list
            if "EU" not in source_surface_table.source_discovery.country_code_list
        ]
        if non_europe_size_group_key_list:
            raise RuntimeError(
                "source_discover contains candidates that are neither priority-country, global, nor verified European "
                f"consensus tables: priority_country_code={priority_country_code}; "
                f"size_group_key_list={sorted(non_europe_size_group_key_list)}"
            )

    def validate(self, browser_action_result: BrowserActionResult) -> None:
        """Validate source-discovery structural consistency before semantic verification.

        Args:
            browser_action_result: Generic browser-backed action result.

        Raises:
            RuntimeError: If discovery is structurally inconsistent.
        """

        _ = browser_action_result
        inventory = self._inventory_validate()
        market_conflict_table_list = [
            source_surface_table
            for source_surface_table in inventory.table_list
            if source_surface_table.state == "market_conflict"
        ]
        if market_conflict_table_list:
            raise RuntimeError(
                "source_discover found conflicting European country tables; this is a blocker, not a no-table "
                "source result: size_group_key_list="
                f"{sorted({table.source_discovery.size_group_key for table in market_conflict_table_list})}"
            )
        accepted_table_list = [
            source_surface_table
            for source_surface_table in inventory.table_list
            if source_surface_table.state == "accepted"
        ]
        self._equivalent_table_validate(
            accepted_size_group_key_set={table.source_discovery.size_group_key for table in accepted_table_list},
            inventory=inventory,
        )
        if not accepted_table_list:
            if not inventory.no_table_reason_list_get():
                raise RuntimeError(
                    "source_discover returned no accepted table rows and no evidence-backed no-table inventory reasons"
                )
            return
        self._country_selection_validate(accepted_table_list=accepted_table_list)
        size_group_key_set: set[str] = set()
        for source_surface_table in accepted_table_list:
            source_discovery = source_surface_table.source_discovery
            if source_discovery.size_group_key in size_group_key_set:
                raise RuntimeError(f"source_discover duplicate size_group_key: {source_discovery.size_group_key}")
            size_group_key_set.add(source_discovery.size_group_key)
            if not source_discovery.source_url.strip():
                raise RuntimeError(f"source_discover returned empty source_url for {source_discovery.size_group_key}")
            if not source_discovery.source_title.strip():
                raise RuntimeError(f"source_discover returned empty source_title for {source_discovery.size_group_key}")
            self._artifact_reference_validator.evidence_path_list_validate(
                evidence_path_list=source_discovery.evidence_path_list,
                stage_key="source_discover",
            )

    def _equivalent_table_validate(
        self, *, accepted_size_group_key_set: set[str], inventory: SourceSurfaceInventory
    ) -> None:
        """Validate equivalent table rows against accepted rows.

        Args:
            accepted_size_group_key_set: Accepted size-group keys in the current inventory.
            inventory: Parsed source-surface inventory.

        Raises:
            RuntimeError: If one equivalent row has no accepted row with the same size group.
        """

        orphan_table_list = [
            source_surface_table
            for source_surface_table in inventory.table_list
            if source_surface_table.state == "equivalent"
            and source_surface_table.source_discovery.size_group_key not in accepted_size_group_key_set
        ]
        if orphan_table_list:
            raise RuntimeError(
                "source_discover equivalent table rows must reference an accepted table with the same size_group_key: "
                f"{sorted({table.source_discovery.size_group_key for table in orphan_table_list})}"
            )

    def _inventory_evidence_path_list_get(self, inventory: SourceSurfaceInventory) -> list[str]:
        """Return explicit evidence path references from the source-surface inventory.

        Args:
            inventory: Parsed source-surface inventory.

        Returns:
            Evidence path list from explicit inventory evidence fields.
        """

        evidence_path_list: list[str] = []
        for discovery_query in inventory.discovery_query_list:
            evidence_path_list.extend(discovery_query.evidence_path_list)
        for product_type_sex_worklist_item in inventory.product_type_sex_worklist:
            evidence_path_list.extend(product_type_sex_worklist_item.evidence_path_list)
        for source_surface_table in inventory.table_list:
            evidence_path_list.extend(source_surface_table.source_discovery.evidence_path_list)
        for source_surface_url in inventory.url_list:
            evidence_path_list.extend(source_surface_url.evidence_path_list)
        return evidence_path_list

    def _inventory_payload_get(self) -> SourceSurfaceInventory:
        """Return parsed canonical source-surface inventory.

        Returns:
            Parsed source-surface inventory.

        Raises:
            RuntimeError: If the inventory is missing or invalid JSON.
        """

        inventory_path = self._stage_dir / "state.json"
        if not inventory_path.is_file():
            raise RuntimeError("source_discover must write state.json")
        try:
            inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("source_discover state.json is invalid JSON") from exc
        try:
            return SourceSurfaceInventory.model_validate(inventory_payload)
        except ValidationError as exc:
            raise RuntimeError(f"source_discover state.json violates SourceSurfaceInventory contract: {exc}") from exc

    def _inventory_validate(self) -> SourceSurfaceInventory:
        """Validate canonical source-surface inventory artifact references.

        Returns:
            Parsed source-surface inventory.
        """

        inventory = self._inventory_payload_get()
        self._inventory_product_type_worklist_validate(inventory=inventory)
        self._artifact_reference_validator.path_list_validate(
            path_list=self._inventory_evidence_path_list_get(inventory),
            stage_key="source_discover inventory",
        )
        return inventory

    def _inventory_product_type_worklist_validate(self, *, inventory: SourceSurfaceInventory) -> None:
        """Validate product-type worklist closure in the source-surface inventory.

        Args:
            inventory: Parsed source-surface inventory.

        Raises:
            RuntimeError: If one worklist row is not linked to concrete inventory evidence.
        """

        worklist_key_set = {worklist_item.worklist_key for worklist_item in inventory.product_type_sex_worklist}
        if len(worklist_key_set) != len(inventory.product_type_sex_worklist):
            raise RuntimeError("source_discover duplicate product_type_sex_worklist worklist_key values")
        active_worklist_key_set: set[str] = set()
        for worklist_item in inventory.product_type_sex_worklist:
            if worklist_item.state == "active":
                active_worklist_key_set.add(worklist_item.worklist_key)
                continue
            if not worklist_item.reason.strip():
                raise RuntimeError(
                    "source_discover rejected product_type_sex_worklist row has empty reason: "
                    f"{worklist_item.worklist_key}"
                )
            if not worklist_item.evidence_path_list:
                raise RuntimeError(
                    "source_discover rejected product_type_sex_worklist row has no evidence_path_list: "
                    f"{worklist_item.worklist_key}"
                )

        linked_worklist_key_set: set[str] = set()
        active_closing_worklist_key_set: set[str] = set()
        for source_surface_url in inventory.url_list:
            linked_worklist_key_set.update(source_surface_url.worklist_key_list)
            active_closing_worklist_key_set.update(source_surface_url.worklist_key_list)

        unknown_worklist_key_list = sorted(linked_worklist_key_set - worklist_key_set)
        if unknown_worklist_key_list:
            raise RuntimeError(
                "source_discover inventory references unknown product_type_sex_worklist keys: "
                f"{unknown_worklist_key_list}"
            )

        unlinked_worklist_key_list = sorted(active_worklist_key_set - active_closing_worklist_key_set)
        if unlinked_worklist_key_list:
            raise RuntimeError(
                "source_discover unlinked product_type_sex_worklist keys: " f"{unlinked_worklist_key_list}"
            )
