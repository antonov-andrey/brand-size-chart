"""Source-discovery mechanical validation."""

import json
from pathlib import Path

from pydantic import ValidationError

from brand_size_chart.model import BrowsingError, PromptScope, SourceDiscoveryResult
from brand_size_chart.validator.artifact import ArtifactValidator
from brand_size_chart.validator.base import MechanicalValidator


class SourceDiscoveryValidator(MechanicalValidator):
    """Validate source-discovery structural consistency."""

    def __init__(self, *, result_dir: Path, stage_dir: Path) -> None:
        """Store explicit source-discovery artifact paths.

        Args:
            result_dir: Root result directory.
            stage_dir: Source-discovery stage artifact directory.
        """

        self._artifact_validator = ArtifactValidator(result_dir)
        self._stage_dir = stage_dir

    def country_selection_validate(self, *, discovery_result: SourceDiscoveryResult, prompt_scope: PromptScope) -> None:
        """Validate the source-discovery market selection ladder.

        Args:
            discovery_result: Verified source discovery result.
            prompt_scope: Current prompt scope.

        Raises:
            RuntimeError: If lower-priority market scopes are mixed into a higher-priority result.
        """

        priority_country_code = prompt_scope.priority_country_code
        priority_country_source_list = [
            source_discover
            for source_discover in discovery_result.discovered_source_list
            if priority_country_code in source_discover.country_code_list
        ]
        if priority_country_source_list:
            non_priority_country_size_group_key_list = [
                source_discover.size_group_key
                for source_discover in discovery_result.discovered_source_list
                if priority_country_code not in source_discover.country_code_list
            ]
            if non_priority_country_size_group_key_list:
                raise RuntimeError(
                    "source_discover contains non-priority country candidates while priority country tables exist: "
                    f"priority_country_code={priority_country_code}; "
                    f"size_group_key_list={sorted(non_priority_country_size_group_key_list)}"
                )
            return

        global_source_list = [
            source_discover
            for source_discover in discovery_result.discovered_source_list
            if "GLOBAL" in source_discover.country_code_list
        ]
        if global_source_list:
            non_global_size_group_key_list = [
                source_discover.size_group_key
                for source_discover in discovery_result.discovered_source_list
                if "GLOBAL" not in source_discover.country_code_list
            ]
            if non_global_size_group_key_list:
                raise RuntimeError(
                    "source_discover contains non-global candidates while global tables exist: "
                    f"priority_country_code={priority_country_code}; "
                    f"size_group_key_list={sorted(non_global_size_group_key_list)}"
                )
            return

        non_europe_size_group_key_list = [
            source_discover.size_group_key
            for source_discover in discovery_result.discovered_source_list
            if "EU" not in source_discover.country_code_list
        ]
        if non_europe_size_group_key_list:
            raise RuntimeError(
                "source_discover contains candidates that are neither priority-country, global, nor verified European "
                f"consensus tables: priority_country_code={priority_country_code}; "
                f"size_group_key_list={sorted(non_europe_size_group_key_list)}"
            )

    def error_list_get(
        self,
        discovery_result: SourceDiscoveryResult,
        *,
        expected_source_priority: int,
        expected_source_type: str,
        prompt_scope: PromptScope,
    ) -> list[str]:
        """Return source-discovery mechanical validation errors.

        Args:
            discovery_result: Source discovery result to validate.
            expected_source_priority: Registry priority for the source type being processed.
            expected_source_type: Source type being processed.
            prompt_scope: Current prompt scope.

        Returns:
            Mechanical validation errors.
        """

        return self._error_list_get(
            lambda: self.validate(
                discovery_result=discovery_result,
                expected_source_priority=expected_source_priority,
                expected_source_type=expected_source_type,
                prompt_scope=prompt_scope,
            )
        )

    def validate(
        self,
        *,
        discovery_result: SourceDiscoveryResult,
        expected_source_priority: int,
        expected_source_type: str,
        prompt_scope: PromptScope,
    ) -> None:
        """Validate source-discovery structural consistency after semantic verification.

        Args:
            discovery_result: Verified source discovery result.
            expected_source_priority: Registry priority for the source type being processed.
            expected_source_type: Source type being processed.
            prompt_scope: Current prompt scope.

        Raises:
            RuntimeError: If discovery is structurally inconsistent.
        """

        if discovery_result.source_type != expected_source_type:
            raise RuntimeError(
                f"source_discover source_type mismatch: {discovery_result.source_type} != {expected_source_type}"
            )
        self._inventory_validate(discovery_result)
        if discovery_result.status == "failed":
            if discovery_result.discovered_source_list:
                raise RuntimeError("failed source_discover must not return discovered_source_list items")
            if not discovery_result.error_list:
                raise RuntimeError("failed source_discover must include concrete error_list blockers")
            return
        if discovery_result.status != "success":
            raise RuntimeError(f"source_discover status must be success or failed, got {discovery_result.status}")
        if not discovery_result.discovered_source_list:
            raise RuntimeError("source_discover returned no discovered_source_list items")
        self.country_selection_validate(
            discovery_result=discovery_result,
            prompt_scope=prompt_scope,
        )
        size_group_key_set: set[str] = set()
        requested_product_type_set = set(prompt_scope.product_type_request_list)
        for source_discover in discovery_result.discovered_source_list:
            if source_discover.size_group_key in size_group_key_set:
                raise RuntimeError(f"source_discover duplicate size_group_key: {source_discover.size_group_key}")
            size_group_key_set.add(source_discover.size_group_key)
            if source_discover.source_type != expected_source_type:
                raise RuntimeError(
                    f"source_discover item source_type mismatch for {source_discover.size_group_key}: "
                    f"{source_discover.source_type} != {expected_source_type}"
                )
            if source_discover.source_priority != expected_source_priority:
                raise RuntimeError(
                    f"source_discover source_priority mismatch for {source_discover.size_group_key}: "
                    f"{source_discover.source_priority} != {expected_source_priority}"
                )
            if not source_discover.source_url.strip():
                raise RuntimeError(f"source_discover returned empty source_url for {source_discover.size_group_key}")
            if not source_discover.source_title.strip():
                raise RuntimeError(f"source_discover returned empty source_title for {source_discover.size_group_key}")
            if requested_product_type_set:
                hint_product_type_set = set(source_discover.product_type_hint_list)
                if not hint_product_type_set.issubset(requested_product_type_set):
                    unexpected_product_type_list = sorted(hint_product_type_set - requested_product_type_set)
                    raise RuntimeError(
                        f"source_discover returned unexpected product_type_hint_list for "
                        f"{source_discover.size_group_key}: {unexpected_product_type_list}"
                    )
            self._artifact_validator.evidence_path_list_validate(
                evidence_path_list=source_discover.evidence_path_list,
                stage_key="source_discover",
            )

    def _inventory_evidence_path_list_extend(
        self, *, evidence_path_list: list[str], field_name: str, value: object
    ) -> None:
        """Collect evidence path references from one inventory field value.

        Args:
            evidence_path_list: Mutable evidence path accumulator.
            field_name: Current inventory field name.
            value: Current inventory field value.
        """

        if field_name.endswith("evidence_path") and isinstance(value, str):
            evidence_path_list.append(value)
            return
        if field_name.endswith("evidence_path_list") and isinstance(value, list):
            evidence_path_list.extend(item for item in value if isinstance(item, str))
            return
        self._inventory_evidence_path_list_get(evidence_path_list=evidence_path_list, value=value)

    def _inventory_evidence_path_list_get(self, *, evidence_path_list: list[str], value: object) -> None:
        """Collect evidence path references from the source-surface inventory payload.

        Args:
            evidence_path_list: Mutable evidence path accumulator.
            value: Current inventory JSON value.
        """

        if isinstance(value, dict):
            for field_name, field_value in value.items():
                self._inventory_evidence_path_list_extend(
                    evidence_path_list=evidence_path_list,
                    field_name=field_name,
                    value=field_value,
                )
            return
        if isinstance(value, list):
            for item in value:
                self._inventory_evidence_path_list_get(evidence_path_list=evidence_path_list, value=item)

    def _inventory_payload_get(self) -> object:
        """Return parsed canonical source-surface inventory.

        Returns:
            Parsed inventory JSON payload.

        Raises:
            RuntimeError: If the inventory is missing or invalid JSON.
        """

        inventory_path = self._stage_dir / "evidence" / "source_surface_inventory.json"
        if not inventory_path.is_file():
            raise RuntimeError("source_discover must write canonical evidence/source_surface_inventory.json")
        try:
            return json.loads(inventory_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "source_discover canonical evidence/source_surface_inventory.json is invalid JSON"
            ) from exc

    def _inventory_validate(self, discovery_result: SourceDiscoveryResult) -> None:
        """Validate canonical source-surface inventory artifact references.

        Args:
            discovery_result: Source discovery result to compare with the inventory.
        """

        inventory_payload = self._inventory_payload_get()
        self._inventory_browsing_error_list_validate(
            discovery_result=discovery_result,
            inventory_payload=inventory_payload,
        )
        evidence_path_list: list[str] = []
        self._inventory_evidence_path_list_get(
            evidence_path_list=evidence_path_list,
            value=inventory_payload,
        )
        self._artifact_validator.path_list_validate(
            path_list=evidence_path_list,
            stage_key="source_discover inventory",
        )

    def _inventory_browsing_error_identity_list_get(self, inventory_payload: object) -> list[tuple[str, str]]:
        """Return canonical inventory browsing-error identities.

        Args:
            inventory_payload: Parsed inventory JSON payload.

        Returns:
            Inventory browsing-error identities.

        Raises:
            RuntimeError: If the inventory does not expose a valid browsing-error list.
        """

        if not isinstance(inventory_payload, dict):
            raise RuntimeError("source_discover inventory must be a JSON object")
        browsing_error_payload_list = inventory_payload.get("browsing_error_list")
        if not isinstance(browsing_error_payload_list, list):
            raise RuntimeError("source_discover inventory must include browsing_error_list as a list")
        try:
            browsing_error_list = [
                BrowsingError.model_validate(browsing_error_payload)
                for browsing_error_payload in browsing_error_payload_list
            ]
        except ValidationError as exc:
            raise RuntimeError("source_discover inventory contains invalid browsing_error_list items") from exc
        return [(browsing_error.url, browsing_error.error) for browsing_error in browsing_error_list]

    def _inventory_browsing_error_list_validate(
        self, *, discovery_result: SourceDiscoveryResult, inventory_payload: object
    ) -> None:
        """Validate result-level browsing errors against inventory-level browsing errors.

        Args:
            discovery_result: Source discovery result to compare with the inventory.
            inventory_payload: Parsed inventory JSON payload.

        Raises:
            RuntimeError: If inventory and result browsing-error lists differ.
        """

        inventory_browsing_error_identity_list = self._inventory_browsing_error_identity_list_get(inventory_payload)
        result_browsing_error_identity_list = [
            (browsing_error.url, browsing_error.error) for browsing_error in discovery_result.browsing_error_list
        ]
        if sorted(inventory_browsing_error_identity_list) != sorted(result_browsing_error_identity_list):
            raise RuntimeError(
                "source_discover browsing_error_list mismatch: "
                f"inventory={sorted(inventory_browsing_error_identity_list)}; "
                f"result={sorted(result_browsing_error_identity_list)}"
            )
