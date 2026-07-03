"""Source-type DBOS workflow owner."""

from pathlib import Path

from dbos import DBOS, DBOSConfiguredInstance

from brand_size_chart.artifact import ArtifactLayout, ArtifactReferenceValidator
from brand_size_chart.codex.runner import codex_stage_run
from brand_size_chart.model import (
    BrandInput,
    PromptScope,
    SourceDiscovery,
    SourceDiscoveryResult,
    SourceTypeSummary,
    TableExtraction,
    TableExtractionBatchResult,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.workflow.base import ARTIFACT_WRITER, source_discovery_result_get, table_extract_result_get


@DBOS.dbos_class("BrandSizeChartSourceTypeWorkflow")
class BrandSizeChartSourceTypeWorkflow(DBOSConfiguredInstance):
    """DBOS owner for one source type and source-type side-effect steps."""

    def __init__(self) -> None:
        """Register the stable stateless DBOS instance."""

        super().__init__("default")

    @DBOS.workflow(name="brand_size_chart_source_type")
    def run(
        self,
        workflow_run_id: str,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        secret_ref: str,
        source_type: str,
    ) -> dict[str, object]:
        """Process one source type with one batch table-extraction step.

        Args:
            workflow_run_id: Stable workflow run identifier.
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            secret_ref: Secret DataSource path string.
            source_type: Source type key.

        Returns:
            Serialized source-type summary and verified table list.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        verified_table_extraction_payload_list: list[dict[str, object]] = []
        blocker_list: list[str] = []
        warning_list: list[str] = []
        try:
            discovery_result_payload = self.source_discover_write_step(
                brand_input.model_dump(mode="json"),
                browser_runtime_mcp_url,
                prompt_scope.model_dump(mode="json"),
                result_dir,
                secret_ref,
                source_type,
            )
            discovery_result = SourceDiscoveryResult.model_validate(discovery_result_payload)
            if discovery_result.status == "failed":
                warning_list.extend(discovery_result.error_list or [discovery_result.message])
            else:
                table_extraction_batch_result_payload = self.table_extract_write_step(
                    brand_input.model_dump(mode="json"),
                    browser_runtime_mcp_url,
                    prompt_scope.model_dump(mode="json"),
                    result_dir,
                    secret_ref,
                    source_type,
                    [
                        source_discovery.model_dump(mode="json")
                        for source_discovery in discovery_result.discovered_source_list
                    ],
                )
                table_extraction_batch_result = TableExtractionBatchResult.model_validate(
                    table_extraction_batch_result_payload
                )
                verified_table_extraction_payload_list.extend(
                    [
                        table_extraction.model_dump(mode="json")
                        for table_extraction in table_extraction_batch_result.table_extraction_list
                    ]
                )
        except RuntimeError as exc:
            blocker_list.append(f"{type(exc).__name__}: {exc}")
        source_type_summary_payload = self.summary_write_step(
            brand_input.model_dump(mode="json"),
            result_dir,
            source_type,
            verified_table_extraction_payload_list,
            blocker_list,
            warning_list,
        )
        return {
            "source_type_summary": source_type_summary_payload,
            "table_extraction_list": verified_table_extraction_payload_list,
        }

    @DBOS.step(name="source_discover_write_step")
    def source_discover_write_step(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        secret_ref: str,
        source_type: str,
    ) -> dict[str, object]:
        """Write source discovery result and verification.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            secret_ref: Secret DataSource path string.
            source_type: Source type key.

        Returns:
            Serialized source discovery result.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        source_type_dir = artifact_layout.source_type_dir(brand_input, source_type)
        discovery_result = source_discovery_result_get(
            brand_input=brand_input,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=codex_stage_run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            secret_path=Path(secret_ref),
            source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
            source_type=source_type,
            source_type_dir=source_type_dir,
        )
        return discovery_result.model_dump(mode="json")

    @DBOS.step(name="table_extract_write_step")
    def table_extract_write_step(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        secret_ref: str,
        source_type: str,
        source_discovery_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Write batch table extraction and chart artifacts.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            secret_ref: Secret DataSource path string.
            source_type: Source type key.
            source_discovery_payload_list: Serialized source discoveries.

        Returns:
            Serialized verified batch table extraction.
        """

        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        source_type_dir = artifact_layout.source_type_dir(brand_input, source_type)
        table_extraction_batch_result = table_extract_result_get(
            brand_input=brand_input,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=codex_stage_run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            secret_path=Path(secret_ref),
            source_discovery_list=[
                SourceDiscovery.model_validate(source_discovery_payload)
                for source_discovery_payload in source_discovery_payload_list
            ],
            source_type=source_type,
            source_type_dir=source_type_dir,
        )
        return table_extraction_batch_result.model_dump(mode="json")

    @DBOS.step(name="source_type_summary_write_step")
    def summary_write_step(
        self,
        brand_input_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        table_extraction_payload_list: list[dict[str, object]],
        blocker_list: list[str],
        warning_list: list[str],
    ) -> dict[str, object]:
        """Write source-type summary.

        Args:
            brand_input_payload: Serialized brand input.
            result_dir: Root result directory string.
            source_type: Source type key.
            table_extraction_payload_list: Serialized verified table extractions.
            blocker_list: Source-type blocker messages collected during discovery or extraction.
            warning_list: Non-fatal source-type warnings collected during discovery.

        Returns:
            Serialized source-type summary.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        artifact_reference_validator = ArtifactReferenceValidator(result_dir_path)
        table_extraction_list = [
            TableExtraction.model_validate(table_extraction_payload)
            for table_extraction_payload in table_extraction_payload_list
        ]
        table_result_path_by_size_group_key_map = {
            table_extraction.size_group_key: artifact_layout.artifact_path(
                artifact_layout.table_extract_chart_path(
                    brand_input,
                    source_type,
                    table_extraction.size_group_key,
                )
            )
            for table_extraction in table_extraction_list
        }
        evidence_manifest_path_list = [
            artifact_layout.artifact_path(artifact_path)
            for artifact_path in [
                artifact_layout.stage_result_path(artifact_layout.source_discover_dir(brand_input, source_type)),
                artifact_layout.stage_verification_path(artifact_layout.source_discover_dir(brand_input, source_type)),
            ]
            if artifact_path.is_file()
        ]
        summary = SourceTypeSummary(
            blocker_list=blocker_list,
            evidence_manifest_path_list=evidence_manifest_path_list,
            source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
            source_type=source_type,
            state="failed" if blocker_list else ("passed" if table_extraction_list else "skipped"),
            table_result_path_by_size_group_key_map=table_result_path_by_size_group_key_map,
            verified_size_group_key_list=list(table_result_path_by_size_group_key_map),
            warning_list=warning_list,
        )
        if sorted(summary.verified_size_group_key_list) != sorted(summary.table_result_path_by_size_group_key_map):
            raise RuntimeError(f"source_type_summary key mismatch for {source_type}")
        artifact_reference_validator.path_list_validate(
            path_list=list(summary.table_result_path_by_size_group_key_map.values()),
            stage_key="source_type_summary",
        )
        artifact_reference_validator.path_list_validate(
            path_list=summary.evidence_manifest_path_list,
            stage_key="source_type_summary",
        )
        ARTIFACT_WRITER.write(artifact_layout.source_type_summary_result_path(brand_input, source_type), summary)
        return summary.model_dump(mode="json")


BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW = BrandSizeChartSourceTypeWorkflow()
brand_size_chart_source_type = BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.run
source_discover_write_step = BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.source_discover_write_step
table_extract_write_step = BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.table_extract_write_step
source_type_summary_write_step = BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.summary_write_step

__all__ = [
    "BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW",
    "BrandSizeChartSourceTypeWorkflow",
    "brand_size_chart_source_type",
    "source_discover_write_step",
    "table_extract_write_step",
    "source_type_summary_write_step",
]
