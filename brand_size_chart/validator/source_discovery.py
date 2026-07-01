"""Source-discovery mechanical validation."""

from pathlib import Path

from brand_size_chart.model import PromptScope, SourceDiscoveryResult
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
            source_discovery
            for source_discovery in discovery_result.discovered_source_list
            if priority_country_code in source_discovery.country_code_list
        ]
        if priority_country_source_list:
            non_priority_country_size_group_key_list = [
                source_discovery.size_group_key
                for source_discovery in discovery_result.discovered_source_list
                if priority_country_code not in source_discovery.country_code_list
            ]
            if non_priority_country_size_group_key_list:
                raise RuntimeError(
                    "source_discovery contains non-priority country candidates while priority country tables exist: "
                    f"priority_country_code={priority_country_code}; "
                    f"size_group_key_list={sorted(non_priority_country_size_group_key_list)}"
                )
            return

        global_source_list = [
            source_discovery
            for source_discovery in discovery_result.discovered_source_list
            if "GLOBAL" in source_discovery.country_code_list
        ]
        if global_source_list:
            non_global_size_group_key_list = [
                source_discovery.size_group_key
                for source_discovery in discovery_result.discovered_source_list
                if "GLOBAL" not in source_discovery.country_code_list
            ]
            if non_global_size_group_key_list:
                raise RuntimeError(
                    "source_discovery contains non-global candidates while global tables exist: "
                    f"priority_country_code={priority_country_code}; "
                    f"size_group_key_list={sorted(non_global_size_group_key_list)}"
                )
            return

        non_europe_size_group_key_list = [
            source_discovery.size_group_key
            for source_discovery in discovery_result.discovered_source_list
            if "EU" not in source_discovery.country_code_list
        ]
        if non_europe_size_group_key_list:
            raise RuntimeError(
                "source_discovery contains candidates that are neither priority-country, global, nor verified European "
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
                f"source_discovery source_type mismatch: {discovery_result.source_type} != {expected_source_type}"
            )
        if discovery_result.status == "failed":
            if discovery_result.discovered_source_list:
                raise RuntimeError("failed source_discovery must not return discovered_source_list items")
            if not discovery_result.error_list:
                raise RuntimeError("failed source_discovery must include concrete error_list blockers")
            inventory_path = self._stage_dir / "evidence" / "source_surface_inventory.json"
            if not inventory_path.is_file():
                raise RuntimeError(
                    "failed source_discovery must write canonical evidence/source_surface_inventory.json"
                )
            return
        if discovery_result.status != "success":
            raise RuntimeError(f"source_discovery status must be success or failed, got {discovery_result.status}")
        if not discovery_result.discovered_source_list:
            raise RuntimeError("source_discovery returned no discovered_source_list items")
        self.country_selection_validate(
            discovery_result=discovery_result,
            prompt_scope=prompt_scope,
        )
        size_group_key_set: set[str] = set()
        requested_product_type_set = set(prompt_scope.product_type_request_list)
        for source_discovery in discovery_result.discovered_source_list:
            if source_discovery.size_group_key in size_group_key_set:
                raise RuntimeError(f"source_discovery duplicate size_group_key: {source_discovery.size_group_key}")
            size_group_key_set.add(source_discovery.size_group_key)
            if source_discovery.source_type != expected_source_type:
                raise RuntimeError(
                    f"source_discovery item source_type mismatch for {source_discovery.size_group_key}: "
                    f"{source_discovery.source_type} != {expected_source_type}"
                )
            if source_discovery.source_priority != expected_source_priority:
                raise RuntimeError(
                    f"source_discovery source_priority mismatch for {source_discovery.size_group_key}: "
                    f"{source_discovery.source_priority} != {expected_source_priority}"
                )
            if not source_discovery.source_url.strip():
                raise RuntimeError(f"source_discovery returned empty source_url for {source_discovery.size_group_key}")
            if not source_discovery.source_title.strip():
                raise RuntimeError(
                    f"source_discovery returned empty source_title for {source_discovery.size_group_key}"
                )
            if requested_product_type_set:
                hint_product_type_set = set(source_discovery.product_type_hint_list)
                if not hint_product_type_set.issubset(requested_product_type_set):
                    unexpected_product_type_list = sorted(hint_product_type_set - requested_product_type_set)
                    raise RuntimeError(
                        f"source_discovery returned unexpected product_type_hint_list for "
                        f"{source_discovery.size_group_key}: {unexpected_product_type_list}"
                    )
            self._artifact_validator.evidence_path_list_validate(
                evidence_path_list=source_discovery.evidence_path_list,
                stage_key="source_discovery",
            )
