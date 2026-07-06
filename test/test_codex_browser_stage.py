"""Tests for Codex-owned browser stage contracts."""

from collections.abc import Callable
import json
import subprocess
from pathlib import Path

from pydantic import BaseModel
import pytest

from brand_size_chart.model import (
    BrandInput,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    PromptScope,
    SourceDiscovery,
    SourceDiscoveryResult,
    TableExtraction,
    TableExtractionArtifact,
    TableExtractionArtifactBatchResult,
    TableExtractionBatchResult,
)
from brand_size_chart.stage.source_discovery import SourceDiscoveryStage
from brand_size_chart.stage.table_extraction import TableExtractionStage
from workflow_container_runtime.codex import CodexStageRunner
from workflow_container_runtime.codex import runner as codex_runner
from workflow_container_runtime.stage import MAX_STAGE_ATTEMPT_COUNT, StageVerificationResult


def _brand_input_get() -> BrandInput:
    """Return a representative brand input.

    Returns:
        Parsed brand input.
    """
    return BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )


def _brand_size_chart_get(*, description: str, size_label: str) -> BrandSizeChart:
    """Return one populated size chart for table-extraction tests.

    Args:
        description: Chart description.
        size_label: Source row size label.

    Returns:
        Size chart with the required unit=size row measurement.
    """

    return BrandSizeChart(
        description=description,
        row_list=[
            BrandSizeChartRow(
                measurement_list=[
                    BrandSizeChartMeasurement(
                        max_value=size_label,
                        min_value=size_label,
                        name="SIZE",
                        unit="size",
                    ),
                    BrandSizeChartMeasurement(
                        max_value="90",
                        min_value="88",
                        name="chest",
                        unit="cm",
                    ),
                ],
                size_label=size_label,
            )
        ],
    )


def _source_discovery_get(
    *,
    product_type_hint_list: list[str] | None = None,
    size_group_key: str,
    source_title: str,
    source_type: str = "official_brand_size_guide",
    source_url: str = "https://defacto.example/size",
) -> SourceDiscovery:
    """Return one verified source discovery for table-extraction tests.

    Args:
        product_type_hint_list: Product types that the discovered table can cover.
        size_group_key: Discovered size group key.
        source_title: Discovered source title.
        source_type: Source type key.
        source_url: Source URL.

    Returns:
        Source discovery matching the supplied identity.
    """

    return SourceDiscovery(
        confidence=1.0,
        country_code_list=["TR"],
        evidence_path_list=[],
        product_type_hint_list=product_type_hint_list or [],
        size_group_key=size_group_key,
        source_priority=600,
        source_title=source_title,
        source_type=source_type,
        source_url=source_url,
    )


def _source_discover_state_payload_get() -> dict[str, object]:
    """Return an empty source-surface inventory payload for test doubles.

    Returns:
        Empty canonical source-surface inventory payload.
    """

    return {
        "accepted_table_list": [],
        "browsing_error_list": [],
        "candidate_url_list": [],
        "discovery_query_list": [],
        "non_returned_table_list": [],
        "opened_url_list": [],
        "product_type_sex_worklist": [],
        "rejected_url_list": [],
    }


def _table_evidence_path_get(*, result_dir: Path, source_type: str, size_group_key: str, suffix: str = "json") -> Path:
    """Return one browser evidence artifact path for batch table extraction.

    Args:
        result_dir: Root result directory.
        source_type: Source type key.
        size_group_key: Size group key.
        suffix: Evidence file suffix.

    Returns:
        Browser evidence artifact path.
    """

    return (
        result_dir
        / ".playwright-mcp"
        / "current"
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / source_type
        / "table_extract"
        / "evidence"
        / f"{size_group_key}.{suffix}"
    )


def _source_discover_state_write(
    *, evidence_path: Path, result_dir: Path, source_discovery: SourceDiscovery | None = None, stage_dir: Path
) -> None:
    """Write one canonical source-surface inventory for source-discovery test doubles.

    Args:
        evidence_path: Evidence artifact path referenced by the fake discovery.
        result_dir: Root result directory.
        source_discovery: Optional discovered source matched by accepted table inventory.
        stage_dir: Source-discovery stage directory.
    """

    inventory_path = stage_dir / "state.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_artifact_path = evidence_path.relative_to(result_dir).as_posix()
    inventory_payload = _source_discover_state_payload_get()
    if source_discovery is not None:
        inventory_payload["accepted_table_list"] = [
            {
                "country_code_list": source_discovery.country_code_list,
                "covered_product_type_list": source_discovery.product_type_hint_list,
                "evidence_path_list": [evidence_artifact_path],
                "reason": "visible table",
                "size_group_key": source_discovery.size_group_key,
                "source_title": source_discovery.source_title,
                "source_url": source_discovery.source_url,
                "state": "accepted",
            }
        ]
        opened_url = source_discovery.source_url
        source_boundary_role = source_discovery.source_type
    else:
        opened_url = "https://defacto.example/size"
        source_boundary_role = "source"
    inventory_payload["opened_url_list"] = [
        {
            "evidence_path_list": [evidence_artifact_path],
            "reason": "browser evidence observed",
            "source_boundary_role": source_boundary_role,
            "state": "opened",
            "url": opened_url,
        }
    ]
    inventory_path.write_text(
        json.dumps(
            inventory_payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _table_extraction_get(
    *,
    evidence_path: Path,
    result_dir: Path,
    size_group_key: str,
    source_title: str,
    source_type: str = "official_brand_size_guide",
    source_url: str = "https://defacto.example/size",
) -> TableExtraction:
    """Return one valid table extraction for batch tests.

    Args:
        evidence_path: Browser evidence artifact path.
        result_dir: Root result directory.
        size_group_key: Extracted size group key.
        source_title: Extracted source title.
        source_type: Source type key.
        source_url: Source URL.

    Returns:
        Table extraction with valid chart rows and evidence.
    """

    return TableExtraction(
        applicability_status="priority_country_official",
        chart=_brand_size_chart_get(description=source_title, size_label="M"),
        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
        size_group_key=size_group_key,
        source_title=source_title,
        source_type=source_type,
        source_url=source_url,
    )


def _table_extraction_artifact_get(
    *,
    chart_path: Path,
    evidence_path: Path,
    result_dir: Path,
    size_group_key: str,
    source_title: str,
    source_type: str = "official_brand_size_guide",
    source_url: str = "https://defacto.example/size",
) -> TableExtractionArtifact:
    """Write one chart artifact and return its lightweight table extraction metadata.

    Args:
        chart_path: Chart artifact path to write.
        evidence_path: Browser evidence artifact path.
        result_dir: Root result directory.
        size_group_key: Extracted size group key.
        source_title: Extracted source title.
        source_type: Source type key.
        source_url: Source URL.

    Returns:
        Table extraction artifact result with a chart path reference.
    """

    chart = _brand_size_chart_get(description=source_title, size_label="M")
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text(json.dumps(chart.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return TableExtractionArtifact(
        applicability_status="priority_country_official",
        chart_path=chart_path.relative_to(result_dir).as_posix(),
        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
        size_group_key=size_group_key,
        source_title=source_title,
        source_type=source_type,
        source_url=source_url,
    )


def _table_extract_state_write(
    *, stage_dir: Path, table_extraction_artifact_list: list[TableExtractionArtifact]
) -> None:
    """Write the durable table-extraction execplan for fake Codex extraction results.

    Args:
        stage_dir: Table-extraction stage directory.
        table_extraction_artifact_list: Fake extraction artifacts returned by the stage.
    """

    execplan_payload = [
        {
            "chart_path": table_extraction_artifact.chart_path,
            "error": "",
            "item_index": item_index,
            "size_group_key": table_extraction_artifact.size_group_key,
            "source_title": table_extraction_artifact.source_title,
            "source_type": table_extraction_artifact.source_type,
            "source_url": table_extraction_artifact.source_url,
            "state": "extracted",
        }
        for item_index, table_extraction_artifact in enumerate(table_extraction_artifact_list, start=1)
    ]
    (stage_dir / "state.json").write_text(
        json.dumps(execplan_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_discovery_result_get(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    codex_stage_run_callable: Callable[..., BaseModel],
    prompt_scope: PromptScope,
    result_dir: Path,
    source_priority: int,
    source_type: str,
) -> SourceDiscoveryResult:
    """Run the real source discovery stage for tests.

    Args:
        brand_input: Parsed brand input.
        browser_runtime_mcp_url: Browser runtime MCP URL.
        codex_stage_run_callable: Test Codex stage callable.
        prompt_scope: Prompt scope.
        result_dir: Result root.
        source_priority: Source type priority.
        source_type: Source type key.

    Returns:
        Source discovery result.
    """

    return SourceDiscoveryStage(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run_callable,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        source_priority=source_priority,
        source_type=source_type,
    ).run()


def _table_extract_result_get(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    codex_stage_run_callable: Callable[..., BaseModel],
    prompt_scope: PromptScope,
    result_dir: Path,
    source_discovery_list: list[SourceDiscovery],
    source_type: str,
) -> TableExtractionBatchResult:
    """Run the real table extraction stage for tests.

    Args:
        brand_input: Parsed brand input.
        browser_runtime_mcp_url: Browser runtime MCP URL.
        codex_stage_run_callable: Test Codex stage callable.
        prompt_scope: Prompt scope.
        result_dir: Result root.
        source_discovery_list: Verified source discoveries.
        source_type: Source type key.

    Returns:
        Batch table extraction result.
    """

    return TableExtractionStage(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run_callable,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        source_discovery_list=source_discovery_list,
        source_type=source_type,
    ).run()


def test_source_discovery_calls_codex_browser_stage_without_local_sources(monkeypatch: object, tmp_path: Path) -> None:
    """Run real discovery through Codex browser access even when the draft source list is empty."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_marketplace_product_page"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return schema-valid stage artifacts and record Codex execution settings.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        call_list.append(
            {
                "allow_user_config": allow_user_config,
                "browser_runtime_mcp_url": browser_runtime_mcp_url,
                "model_class": model_class,
                "prompt_text": prompt_text,
                "stage_name": stage_name,
            }
        )
        evidence_path = (
            result_dir
            / ".playwright-mcp"
            / "current"
            / "brand_size_chart_audit"
            / "brand"
            / "defacto"
            / "source_type"
            / "official_marketplace_product_page"
            / "source_discover"
            / "evidence"
            / "marketplace_product_page.json"
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
        if model_class is SourceDiscoveryResult:
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=300,
                source_title="Official marketplace product page size answer",
                source_type="official_marketplace_product_page",
                source_url="https://www.trendyol.com/defacto/example-p-1",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_marketplace_product_page",
                status="success",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(
            priority_country_code="TR",
            product_type_request_list=["women shoes"],
            shared_instruction="Only search official marketplace product page evidence for requested product types.",
        ),
        result_dir=tmp_path,
        source_priority=300,
        source_type="official_marketplace_product_page",
    )

    assert result.discovered_source_list[0].source_type == "official_marketplace_product_page"
    assert call_list[0]["allow_user_config"] is True
    assert call_list[0]["browser_runtime_mcp_url"] == "http://127.0.0.1:12000/mcp"
    assert "Use the configured browser" in str(call_list[0]["prompt_text"])
    assert (
        f"Browser evidence write directory: "
        f"{tmp_path / '.playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/official_marketplace_product_page/source_discover/evidence'}"
        in str(call_list[0]["prompt_text"])
    )
    assert (
        "Evidence reference directory: "
        ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_marketplace_product_page/source_discover/evidence" in str(call_list[0]["prompt_text"])
    )
    assert "women shoes" in str(call_list[0]["prompt_text"])
    assert "derive localized size-chart search-term families" in str(call_list[0]["prompt_text"])
    assert (
        "Do not create one source candidate from product category, product title, variant labels, or option labels "
        "alone." in str(call_list[0]["prompt_text"])
    )
    assert "source_title is the browser-visible chart group or table heading" in str(call_list[0]["prompt_text"])
    assert "size_group_key is the normalized table key derived from source_title and evidence" in str(
        call_list[0]["prompt_text"]
    )
    assert "Only search official marketplace product page evidence for requested product types." in str(
        call_list[0]["prompt_text"]
    )


def test_source_discovery_retries_page_level_size_group_key(monkeypatch: object, tmp_path: Path) -> None:
    """Reject source discovery that returns one page-level candidate instead of concrete tables."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one invalid page-level candidate and then one concrete table candidate.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        call_list.append(
            {
                "allow_user_config": allow_user_config,
                "browser_runtime_mcp_url": browser_runtime_mcp_url,
                "model_class": model_class,
                "prompt_text": prompt_text,
                "stage_name": stage_name,
            }
        )
        evidence_path = stage_dir / "evidence" / "defacto_size_guide.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("browser-visible evidence\n", encoding="utf-8")
        if (
            model_class is SourceDiscoveryResult
            and len([call for call in call_list if call["model_class"] is SourceDiscoveryResult]) == 1
        ):
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="defacto_tr_beden_rehberi_all",
                source_priority=600,
                source_title="Beden Rehberi",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/brand-size-guide",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        if model_class is SourceDiscoveryResult:
            assert "aggregate token" in prompt_text
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Kadın Üst Beden Tablosu",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/brand-size-guide",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        if len([call for call in call_list if call["model_class"] is SourceDiscoveryResult]) == 1:
            return StageVerificationResult(
                error_list=["SourceDiscovery.size_group_key contains aggregate token."],
                feedback_list=["SourceDiscovery.size_group_key contains aggregate token."],
                status="failed",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=600,
        source_type="official_brand_size_guide",
    )

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert result.discovered_source_list[0].size_group_key == "women_upper"
    assert len(discovery_call_list) == 2


def test_source_discovery_retry_prompt_includes_previous_result(monkeypatch: object, tmp_path: Path) -> None:
    """Give retry attempts the previous discovery result so evidence-backed candidates are preserved."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one partial discovery and require the retry prompt to preserve it.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        evidence_path = stage_dir / "evidence" / "fr_ma_size_charts_dom_tables.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"table": "Tableau Des Tailles Femmes"}\n', encoding="utf-8")
        discovery_call_count = len([call for call in call_list if call["model_class"] is SourceDiscoveryResult])
        if model_class is SourceDiscoveryResult and discovery_call_count == 1:
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Tableau Des Tailles Femmes",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com/fr-ma/static/size-charts",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        if model_class is SourceDiscoveryResult:
            assert "Previous stage result JSON" in prompt_text
            assert "women_upper" in prompt_text
            assert "https://www.defacto.com/fr-ma/static/size-charts" in prompt_text
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Tableau Des Tailles Femmes",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com/fr-ma/static/size-charts",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        if discovery_call_count == 1:
            return StageVerificationResult(
                error_list=["Inventory is incomplete."],
                feedback_list=["Inventory is incomplete."],
                status="failed",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=600,
        source_type="official_brand_size_guide",
    )

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert result.discovered_source_list[0].size_group_key == "women_upper"
    assert len(discovery_call_list) == 2


def test_source_discovery_retries_after_mechanical_guard_failure(monkeypatch: object, tmp_path: Path) -> None:
    """Feed mechanical guard failures back into source discovery retry attempts."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return a mechanically invalid result first and a valid retry result second.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        evidence_path = stage_dir / "evidence" / "defacto_size_guide.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
        discovery_call_count = len([call for call in call_list if call["model_class"] is SourceDiscoveryResult])
        if model_class is SourceDiscoveryResult and discovery_call_count == 1:
            _source_discover_state_write(evidence_path=evidence_path, result_dir=result_dir, stage_dir=stage_dir)
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[],
                source_type="official_brand_size_guide",
                status="failed",
            )
        if model_class is SourceDiscoveryResult:
            assert "failed source_discover must include concrete error_list blockers" in prompt_text
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Kadın Üst Beden Tablosu",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/brand-size-guide",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=600,
        source_type="official_brand_size_guide",
    )

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert result.discovered_source_list[0].size_group_key == "women_upper"
    assert len(discovery_call_list) == 2


def test_source_discovery_accepts_failed_result_with_canonical_inventory(monkeypatch: object, tmp_path: Path) -> None:
    """Accept a real no-table discovery result when it has blockers and canonical browser evidence."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_seller_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return a terminal failed discovery with canonical source inventory.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = result_dir
        _ = stage_name
        call_list.append({"model_class": model_class})
        if model_class is SourceDiscoveryResult:
            inventory_path = stage_dir / "state.json"
            inventory_path.parent.mkdir(parents=True, exist_ok=True)
            inventory_path.write_text(
                json.dumps(_source_discover_state_payload_get(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[],
                error_list=["No official seller size-guide table was visible in browser evidence."],
                source_type="official_seller_size_guide",
                status="failed",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=550,
        source_type="official_seller_size_guide",
    )

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert result.status == "failed"
    assert result.error_list == ["No official seller size-guide table was visible in browser evidence."]
    assert discovery_call_list == [{"model_class": SourceDiscoveryResult}]


def test_source_discovery_materializes_browser_inventory_before_guard(monkeypatch: object, tmp_path: Path) -> None:
    """Accept failed discovery when browser inventory starts in the MCP artifact namespace."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_seller_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return a failed discovery with browser-owned inventory evidence.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = stage_name
        call_list.append({"model_class": model_class})
        if model_class is SourceDiscoveryResult:
            inventory_path = result_dir / ".playwright-mcp" / "current" / stage_dir.relative_to(result_dir)
            inventory_path = inventory_path / "state.json"
            inventory_path.parent.mkdir(parents=True, exist_ok=True)
            inventory_path.write_text(
                json.dumps(_source_discover_state_payload_get(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[],
                error_list=["No official seller size-guide table was visible in browser evidence."],
                source_type="official_seller_size_guide",
                status="failed",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=550,
        source_type="official_seller_size_guide",
    )

    canonical_inventory_path = source_type_dir / "source_discover" / "state.json"
    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]

    assert len(discovery_call_list) == 1
    assert result.status == "failed"
    assert canonical_inventory_path.is_file()


def test_source_discovery_prepares_browser_evidence_directory_before_codex(monkeypatch: object, tmp_path: Path) -> None:
    """Create the browser evidence directory before source-discovery Codex execution."""
    source_type = "official_seller_size_guide"
    source_type_dir = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / source_type

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Require the source-discovery browser evidence directory before fake Codex writes.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = stage_name
        evidence_dir = (
            result_dir
            / ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type"
            / source_type
            / "source_discover/evidence"
        )
        assert evidence_dir.is_dir()
        if model_class is SourceDiscoveryResult:
            evidence_path = evidence_dir / "seller_size_guide_absence.json"
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            inventory_path = stage_dir / "state.json"
            inventory_path.parent.mkdir(parents=True, exist_ok=True)
            inventory_payload = _source_discover_state_payload_get()
            inventory_payload["rejected_url_list"] = [
                {
                    "evidence_path_list": [evidence_path.relative_to(result_dir).as_posix()],
                    "reason": "No concrete seller size guide was visible.",
                    "source_boundary_role": source_type,
                    "state": "rejected",
                    "url": "https://www.defacto.com.tr",
                }
            ]
            inventory_path.write_text(
                json.dumps(
                    inventory_payload,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[],
                error_list=["No official seller size-guide table was visible in browser evidence."],
                source_type=source_type,
                status="failed",
            )
        return StageVerificationResult(
            status="success",
        )

    result = _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=550,
        source_type=source_type,
    )

    assert result.status == "failed"


def test_source_discovery_prompt_has_no_hardcoded_size_guide_routes(monkeypatch: object, tmp_path: Path) -> None:
    """Keep official brand size-guide discovery generic without hardcoded route templates."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return valid source discovery while preserving the prompt for assertions.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        evidence_path = stage_dir / "evidence" / "defacto_size_guide.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("browser-visible evidence\n", encoding="utf-8")
        if model_class is SourceDiscoveryResult:
            source_discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Kadın Üst Beden Tablosu",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/brand-size-guide",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=source_discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[source_discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        return StageVerificationResult(
            status="success",
        )

    _source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_priority=600,
        source_type="official_brand_size_guide",
    )

    discovery_prompt = str(
        next(call["prompt_text"] for call in call_list if call["model_class"] is SourceDiscoveryResult)
    )
    assert "/statik/beden-rehberi" not in discovery_prompt
    assert "/statik/size-guide" not in discovery_prompt
    assert "/beden-tablosu" not in discovery_prompt
    assert "search" in discovery_prompt.lower()


def test_source_discovery_retries_then_fails_empty_skipped_result(monkeypatch: object, tmp_path: Path) -> None:
    """Reject empty skipped source discovery as an incomplete critical stage result."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return the current bad empty skipped discovery response.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake empty discovery result or passing verification.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is SourceDiscoveryResult:
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[],
                source_type="official_brand_size_guide",
                status="skipped",
            )
        return StageVerificationResult(
            error_list=["Empty source discovery is forbidden."],
            feedback_list=["Empty source discovery is forbidden."],
            status="failed",
        )

    try:
        _source_discovery_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(priority_country_code="TR"),
            result_dir=tmp_path,
            source_priority=600,
            source_type="official_brand_size_guide",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert "did not pass verification" in message
    assert len(discovery_call_list) == MAX_STAGE_ATTEMPT_COUNT
    assert "Empty source discovery" in str(discovery_call_list[1]["prompt_text"])


def test_table_extract_batch_calls_codex_once_for_multiple_discoveries(monkeypatch: object, tmp_path: Path) -> None:
    """Run one batch table extract through Codex browser access and write chart artifacts."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_marketplace_product_page"
    )
    source_discovery_list = [
        _source_discovery_get(
            product_type_hint_list=["women blouses"],
            size_group_key="women_upper",
            source_title="Official marketplace product page upper size answer",
            source_type="official_marketplace_product_page",
            source_url="https://www.trendyol.com/defacto/example-p-1",
        ),
        _source_discovery_get(
            product_type_hint_list=["women trousers"],
            size_group_key="women_lower",
            source_title="Official marketplace product page lower size answer",
            source_type="official_marketplace_product_page",
            source_url="https://www.trendyol.com/defacto/example-p-1",
        ),
    ]

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return schema-valid extraction artifacts and record Codex execution settings.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        _ = stage_dir
        call_list.append(
            {
                "allow_user_config": allow_user_config,
                "browser_runtime_mcp_url": browser_runtime_mcp_url,
                "model_class": model_class,
                "prompt_text": prompt_text,
                "stage_name": stage_name,
            }
        )
        if model_class is TableExtractionArtifactBatchResult:
            evidence_path_by_size_group_key_map = {
                source_discovery.size_group_key: _table_evidence_path_get(
                    result_dir=result_dir,
                    source_type=source_discovery.source_type,
                    size_group_key=source_discovery.size_group_key,
                )
                for source_discovery in source_discovery_list
            }
            for evidence_path in evidence_path_by_size_group_key_map.values():
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            table_extraction_artifact_list = [
                _table_extraction_artifact_get(
                    chart_path=stage_dir / "chart" / f"{source_discovery.size_group_key}.json",
                    evidence_path=evidence_path_by_size_group_key_map[source_discovery.size_group_key],
                    result_dir=result_dir,
                    size_group_key=source_discovery.size_group_key,
                    source_title=source_discovery.source_title,
                    source_type=source_discovery.source_type,
                    source_url=source_discovery.source_url,
                )
                for source_discovery in source_discovery_list
            ]
            _table_extract_state_write(
                stage_dir=stage_dir,
                table_extraction_artifact_list=table_extraction_artifact_list,
            )
            return TableExtractionArtifactBatchResult(
                message="test result",
                source_type="official_marketplace_product_page",
                status="success",
                table_extraction_artifact_list=table_extraction_artifact_list,
            )
        return StageVerificationResult(
            status="success",
        )

    result = _table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=source_discovery_list,
        source_type="official_marketplace_product_page",
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionArtifactBatchResult]
    assert [table_extraction.size_group_key for table_extraction in result.table_extraction_list] == [
        "women_upper",
        "women_lower",
    ]
    assert len(table_extract_call_list) == 1
    assert table_extract_call_list[0]["allow_user_config"] is True
    assert table_extract_call_list[0]["browser_runtime_mcp_url"] == "http://127.0.0.1:12000/mcp"
    assert table_extract_call_list[0]["stage_name"] == "table_extract"
    assert "Use the configured browser" in str(table_extract_call_list[0]["prompt_text"])
    assert "Priority country code: TR" in str(table_extract_call_list[0]["prompt_text"])
    assert (
        f"Browser evidence write directory: "
        f"{tmp_path / '.playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/official_marketplace_product_page/table_extract/evidence/women_upper'}"
        in str(table_extract_call_list[0]["prompt_text"])
    )
    assert (
        "Evidence reference directory: "
        ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_marketplace_product_page/table_extract/evidence/women_lower"
        in str(table_extract_call_list[0]["prompt_text"])
    )
    assert "1. size_group_key=women_upper" in str(table_extract_call_list[0]["prompt_text"])
    assert "2. size_group_key=women_lower" in str(table_extract_call_list[0]["prompt_text"])
    assert "Source discovery source_type: official_marketplace_product_page" in str(
        table_extract_call_list[0]["prompt_text"]
    )
    assert "Source discovery product_type_hint_list: ['women blouses']" in str(
        table_extract_call_list[0]["prompt_text"]
    )
    assert "Source discovery product_type_hint_list: ['women trousers']" in str(
        table_extract_call_list[0]["prompt_text"]
    )
    assert "Target source title: Official marketplace product page upper size answer" in str(
        table_extract_call_list[0]["prompt_text"]
    )
    assert "Target source title: Official marketplace product page lower size answer" in str(
        table_extract_call_list[0]["prompt_text"]
    )
    assert "Do not extract a default, current, product-category, adjacent, or differently named table" in str(
        table_extract_call_list[0]["prompt_text"]
    )
    batch_result_payload = json.loads(
        (
            tmp_path
            / "brand_size_chart_audit/brand/defacto/source_type/official_marketplace_product_page/table_extract/result.json"
        ).read_text(encoding="utf-8")
    )
    women_upper_chart_payload = json.loads(
        (
            tmp_path
            / "brand_size_chart_audit/brand/defacto/source_type/official_marketplace_product_page/table_extract/chart/women_upper.json"
        ).read_text(encoding="utf-8")
    )
    women_lower_chart_payload = json.loads(
        (
            tmp_path
            / "brand_size_chart_audit/brand/defacto/source_type/official_marketplace_product_page/table_extract/chart/women_lower.json"
        ).read_text(encoding="utf-8")
    )
    assert batch_result_payload["table_extraction_artifact_list"][0]["size_group_key"] == "women_upper"
    assert "chart_path" in batch_result_payload["table_extraction_artifact_list"][0]
    assert "chart" not in batch_result_payload["table_extraction_artifact_list"][0]
    assert women_upper_chart_payload == result.table_extraction_list[0].chart.model_dump(mode="json")
    assert women_lower_chart_payload == result.table_extraction_list[1].chart.model_dump(mode="json")


def test_table_extract_batch_loads_chart_artifacts_from_lightweight_codex_result(
    monkeypatch: object, tmp_path: Path
) -> None:
    """Load generated chart files instead of requiring full charts in Codex structured output."""
    call_list: list[dict[str, object]] = []
    source_type = "official_brand_size_guide"
    source_type_dir = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / source_type
    source_discovery_list = [
        _source_discovery_get(size_group_key="women_upper", source_title="Women upper"),
        _source_discovery_get(size_group_key="women_lower", source_title="Women lower"),
    ]

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Write chart artifacts and return a lightweight extraction result.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake artifact extraction or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerificationResult:
            return StageVerificationResult(
                status="success",
            )
        assert model_class is TableExtractionArtifactBatchResult
        table_extraction_artifact_list = []
        for source_discovery in source_discovery_list:
            evidence_path = _table_evidence_path_get(
                result_dir=result_dir,
                source_type=source_discovery.source_type,
                size_group_key=source_discovery.size_group_key,
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            chart_path = stage_dir / "chart" / f"{source_discovery.size_group_key}.json"
            chart = _brand_size_chart_get(description=source_discovery.source_title, size_label="M")
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            chart_path.write_text(
                json.dumps(chart.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            table_extraction_artifact_list.append(
                TableExtractionArtifact(
                    applicability_status="priority_country_official",
                    chart_path=chart_path.relative_to(result_dir).as_posix(),
                    evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                    size_group_key=source_discovery.size_group_key,
                    source_title=source_discovery.source_title,
                    source_type=source_discovery.source_type,
                    source_url=source_discovery.source_url,
                )
            )
        _table_extract_state_write(
            stage_dir=stage_dir,
            table_extraction_artifact_list=table_extraction_artifact_list,
        )
        return TableExtractionArtifactBatchResult(
            message="test result",
            source_type=source_type,
            status="success",
            table_extraction_artifact_list=table_extraction_artifact_list,
        )

    result = _table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=source_discovery_list,
        source_type=source_type,
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionArtifactBatchResult]
    result_payload = json.loads((source_type_dir / "table_extract" / "result.json").read_text(encoding="utf-8"))
    assert len(table_extract_call_list) == 1
    assert "Chart artifact path:" in str(table_extract_call_list[0]["prompt_text"])
    assert "Stage chart artifact write directory:" in str(table_extract_call_list[0]["prompt_text"])
    assert "chart_path" in result_payload["table_extraction_artifact_list"][0]
    assert "chart" not in result_payload["table_extraction_artifact_list"][0]
    assert [table_extraction.size_group_key for table_extraction in result.table_extraction_list] == [
        "women_upper",
        "women_lower",
    ]
    assert result.table_extraction_list[0].chart.description == "Women upper"
    assert result.table_extraction_list[1].chart.description == "Women lower"


def test_table_extract_prepares_chart_and_browser_evidence_directories_before_codex(
    monkeypatch: object, tmp_path: Path
) -> None:
    """Create batch chart and browser evidence directories before table-extraction Codex execution."""
    source_type = "official_brand_size_guide"
    source_type_dir = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / source_type
    source_discovery_list = [
        _source_discovery_get(size_group_key="women_upper", source_title="Women upper"),
        _source_discovery_get(size_group_key="women_lower", source_title="Women lower"),
    ]

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Require prepared chart and evidence directories before fake Codex writes.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake extraction or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = stage_name
        assert (stage_dir / "chart").is_dir()
        if model_class is StageVerificationResult:
            return StageVerificationResult(
                status="success",
            )
        table_extraction_artifact_list = []
        for source_discovery in source_discovery_list:
            evidence_dir = _table_evidence_path_get(
                result_dir=result_dir,
                source_type=source_type,
                size_group_key=source_discovery.size_group_key,
            ).parent
            assert evidence_dir.is_dir()
            evidence_path = evidence_dir / "table.json"
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            table_extraction_artifact_list.append(
                _table_extraction_artifact_get(
                    chart_path=stage_dir / "chart" / f"{source_discovery.size_group_key}.json",
                    evidence_path=evidence_path,
                    result_dir=result_dir,
                    size_group_key=source_discovery.size_group_key,
                    source_title=source_discovery.source_title,
                    source_type=source_discovery.source_type,
                    source_url=source_discovery.source_url,
                )
            )
        _table_extract_state_write(
            stage_dir=stage_dir,
            table_extraction_artifact_list=table_extraction_artifact_list,
        )
        return TableExtractionArtifactBatchResult(
            message="test result",
            source_type=source_type,
            status="success",
            table_extraction_artifact_list=table_extraction_artifact_list,
        )

    result = _table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=source_discovery_list,
        source_type=source_type,
    )

    assert [table_extraction.size_group_key for table_extraction in result.table_extraction_list] == [
        "women_upper",
        "women_lower",
    ]


def test_table_extract_batch_rejects_missing_discovery(monkeypatch: object, tmp_path: Path) -> None:
    """Reject and retry a batch extraction missing one discovered table."""
    call_list: list[dict[str, object]] = []
    source_discovery_list = [
        _source_discovery_get(size_group_key="women_upper", source_title="Women upper"),
        _source_discovery_get(size_group_key="women_lower", source_title="Women lower"),
    ]

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one incomplete batch and then a complete batch.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake batch extraction or verification result.
        """

        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerificationResult:
            return StageVerificationResult(
                status="success",
            )

        batch_call_count = len(
            [call for call in call_list if call["model_class"] is TableExtractionArtifactBatchResult]
        )
        if batch_call_count == 2:
            assert "missing" in prompt_text.lower()
            assert "women_lower" in prompt_text
        table_extraction_artifact_list = []
        selected_discovery_list = source_discovery_list if batch_call_count == 2 else source_discovery_list[:1]
        for source_discovery in selected_discovery_list:
            evidence_path = _table_evidence_path_get(
                result_dir=result_dir,
                source_type=source_discovery.source_type,
                size_group_key=source_discovery.size_group_key,
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            table_extraction_artifact_list.append(
                _table_extraction_artifact_get(
                    chart_path=stage_dir / "chart" / f"{source_discovery.size_group_key}.json",
                    evidence_path=evidence_path,
                    result_dir=result_dir,
                    size_group_key=source_discovery.size_group_key,
                    source_title=source_discovery.source_title,
                    source_type=source_discovery.source_type,
                    source_url=source_discovery.source_url,
                )
            )
        _table_extract_state_write(
            stage_dir=stage_dir,
            table_extraction_artifact_list=table_extraction_artifact_list,
        )
        return TableExtractionArtifactBatchResult(
            message="test result",
            source_type="official_brand_size_guide",
            status="success",
            table_extraction_artifact_list=table_extraction_artifact_list,
        )

    result = _table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=source_discovery_list,
        source_type="official_brand_size_guide",
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionArtifactBatchResult]
    assert [table_extraction.size_group_key for table_extraction in result.table_extraction_list] == [
        "women_upper",
        "women_lower",
    ]
    assert len(table_extract_call_list) == 2


def test_table_extract_batch_rejects_extra_discovery(monkeypatch: object, tmp_path: Path) -> None:
    """Reject and retry a batch extraction that invents an undiscovered table."""
    call_list: list[dict[str, object]] = []
    source_discovery_list = [_source_discovery_get(size_group_key="women_upper", source_title="Women upper")]

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one batch with an extra table and then a valid batch.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake batch extraction or verification result.
        """

        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerificationResult:
            return StageVerificationResult(
                status="success",
            )

        batch_call_count = len(
            [call for call in call_list if call["model_class"] is TableExtractionArtifactBatchResult]
        )
        if batch_call_count == 2:
            assert "extra" in prompt_text.lower()
            assert "women_extra" in prompt_text
        selected_size_group_key_list = ["women_upper"] if batch_call_count == 2 else ["women_upper", "women_extra"]
        table_extraction_artifact_list = []
        for size_group_key in selected_size_group_key_list:
            evidence_path = _table_evidence_path_get(
                result_dir=result_dir,
                source_type="official_brand_size_guide",
                size_group_key=size_group_key,
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            table_extraction_artifact_list.append(
                _table_extraction_artifact_get(
                    chart_path=stage_dir / "chart" / f"{size_group_key}.json",
                    evidence_path=evidence_path,
                    result_dir=result_dir,
                    size_group_key=size_group_key,
                    source_title="Women upper" if size_group_key == "women_upper" else "Women extra",
                )
            )
        _table_extract_state_write(
            stage_dir=stage_dir,
            table_extraction_artifact_list=table_extraction_artifact_list,
        )
        return TableExtractionArtifactBatchResult(
            message="test result",
            source_type="official_brand_size_guide",
            status="success",
            table_extraction_artifact_list=table_extraction_artifact_list,
        )

    result = _table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=source_discovery_list,
        source_type="official_brand_size_guide",
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionArtifactBatchResult]
    assert [table_extraction.size_group_key for table_extraction in result.table_extraction_list] == ["women_upper"]
    assert len(table_extract_call_list) == 2


def test_source_discovery_rejects_skipped_result_even_when_verification_passes(
    monkeypatch: object, tmp_path: Path
) -> None:
    """Reject `skipped` discovery through a mechanical guard after semantic verification."""
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return skipped discovery and an incorrectly passing verifier.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = stage_name
        evidence_path = stage_dir / "evidence" / "empty_discovery.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("no table evidence\n", encoding="utf-8")
        _source_discover_state_write(evidence_path=evidence_path, result_dir=result_dir, stage_dir=stage_dir)
        if model_class is SourceDiscoveryResult:
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[],
                source_type="official_brand_size_guide",
                status="skipped",
            )
        return StageVerificationResult(
            status="success",
        )

    try:
        _source_discovery_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(priority_country_code="TR"),
            result_dir=tmp_path,
            source_priority=600,
            source_type="official_brand_size_guide",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "source_discover" in message
    assert "status" in message


def test_source_discovery_rejects_duplicate_size_group_key(monkeypatch: object, tmp_path: Path) -> None:
    """Reject duplicate size group keys before child workflow ids collide."""
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return duplicate discovered tables.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = stage_name
        evidence_path = stage_dir / "evidence" / "guide.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("browser evidence", encoding="utf-8")
        if model_class is SourceDiscoveryResult:
            discovery = SourceDiscovery(
                confidence=1.0,
                country_code_list=["TR"],
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Women upper",
                source_type="official_brand_size_guide",
                source_url="https://defacto.example/size",
            )
            _source_discover_state_write(
                evidence_path=evidence_path,
                result_dir=result_dir,
                source_discovery=discovery,
                stage_dir=stage_dir,
            )
            return SourceDiscoveryResult(
                message="test result",
                discovered_source_list=[discovery, discovery],
                source_type="official_brand_size_guide",
                status="success",
            )
        return StageVerificationResult(
            status="success",
        )

    try:
        _source_discovery_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(priority_country_code="TR"),
            result_dir=tmp_path,
            source_priority=600,
            source_type="official_brand_size_guide",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "duplicate" in message.lower()
    assert "women_upper" in message


def test_table_extract_batch_rejects_identity_change(monkeypatch: object, tmp_path: Path) -> None:
    """Reject batch table extraction that changes a discovery-owned identity."""
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )
    source_discovery_list = [_source_discovery_get(size_group_key="women_upper", source_title="Women upper")]

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return extraction with changed size group key.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake extraction or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = stage_name
        evidence_path = _table_evidence_path_get(
            result_dir=result_dir,
            source_type="official_brand_size_guide",
            size_group_key="renamed_upper",
            suffix="md",
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("table evidence", encoding="utf-8")
        if model_class is TableExtractionArtifactBatchResult:
            return TableExtractionArtifactBatchResult(
                message="test result",
                source_type="official_brand_size_guide",
                status="success",
                table_extraction_artifact_list=[
                    _table_extraction_artifact_get(
                        chart_path=stage_dir / "chart" / "renamed_upper.json",
                        evidence_path=evidence_path,
                        result_dir=result_dir,
                        size_group_key="renamed_upper",
                        source_title="Women upper",
                    )
                ],
            )
        return StageVerificationResult(
            status="success",
        )

    try:
        _table_extract_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(priority_country_code="TR"),
            result_dir=tmp_path,
            source_discovery_list=source_discovery_list,
            source_type="official_brand_size_guide",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "size_group_key" in message
    assert "women_upper" in message
    assert "renamed_upper" in message


def test_codex_browser_stage_uses_browser_vpn_runtime_mcp(monkeypatch: object, tmp_path: Path) -> None:
    """Configure Codex browser stages through browser-vpn-runtime instead of direct Playwright MCP."""
    captured_command: list[str] = []

    def fake_codex_subprocess_run(
        runner: object,
        command: list[str],
        *,
        browser_artifact_activity: bool,
        input: str,
        result_dir: Path,
        stage_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Capture the Codex command and write a schema-valid output file.

        Args:
            runner: Codex stage runner instance.
            command: Command argv passed to subprocess.
            browser_artifact_activity: Whether browser artifacts count as subprocess activity.
            input: Prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.

        Returns:
            Successful completed process.
        """
        _ = runner
        assert browser_artifact_activity is True
        _ = input
        _ = result_dir
        _ = stage_dir
        captured_command.extend(command)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            StageVerificationResult(
                status="success",
            ).model_dump_json(),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(codex_runner.CodexStageRunner, "_subprocess_run", fake_codex_subprocess_run)

    monkeypatch.chdir(tmp_path)
    result_dir = Path("result")
    result_dir.mkdir()
    stage_dir = Path("relative-stage")
    CodexStageRunner(workflow_container_name="brand-size-chart").run(
        allow_user_config=True,
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        model_class=StageVerificationResult,
        prompt_text="verify",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_name="source_discover",
    )

    command_text = "\n".join(captured_command)
    assert "--dangerously-bypass-approvals-and-sandbox" in captured_command
    assert "--sandbox" not in captured_command
    assert "mcp_servers.playwright.url='http://127.0.0.1:12000/mcp'" in command_text
    assert "browser_vpn_runtime.playwright_mcp" not in command_text
    assert str((stage_dir / ".browser-vpn-runtime" / "playwright_profile").resolve()) not in command_text
    assert str((stage_dir / ".playwright-mcp").resolve()) not in command_text
    assert "@playwright/mcp" not in command_text
    assert "npx" not in command_text


def test_codex_browser_stage_rejects_browser_run_code_unsafe(monkeypatch: object, tmp_path: Path) -> None:
    """Reject unsafe controller-code browser tools even when Codex returns valid JSON."""

    def fake_codex_subprocess_run(
        runner: object,
        command: list[str],
        *,
        browser_artifact_activity: bool,
        input: str,
        result_dir: Path,
        stage_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Write one valid output and one forbidden browser tool event.

        Args:
            runner: Codex stage runner instance.
            command: Command argv passed to subprocess.
            browser_artifact_activity: Whether browser artifacts count as subprocess activity.
            input: Prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.

        Returns:
            Successful completed process with a forbidden event stream.
        """

        _ = runner
        assert browser_artifact_activity is True
        _ = input
        _ = result_dir
        _ = stage_dir
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            StageVerificationResult(
                status="success",
            ).model_dump_json(),
            encoding="utf-8",
        )
        event_payload = {
            "type": "item.started",
            "item": {
                "arguments": {"code": "async (page) => { const fs = require('fs'); return page.url(); }"},
                "server": "playwright",
                "tool": "browser_run_code_unsafe",
                "type": "mcp_tool_call",
            },
        }
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(event_payload) + "\n",
            stderr="",
        )

    monkeypatch.setattr(codex_runner.CodexStageRunner, "_subprocess_run", fake_codex_subprocess_run)

    with pytest.raises(codex_runner.CodexStageError, match="browser_run_code_unsafe"):
        CodexStageRunner(workflow_container_name="brand-size-chart").run(
            allow_user_config=True,
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            model_class=StageVerificationResult,
            prompt_text="verify",
            result_dir=tmp_path,
            stage_dir=tmp_path / "stage",
            stage_name="source_discover",
        )


def test_codex_browser_stage_rejects_node_api_inside_browser_evaluate(monkeypatch: object, tmp_path: Path) -> None:
    """Reject Node.js API usage inside browser page JavaScript."""

    def fake_codex_subprocess_run(
        runner: object,
        command: list[str],
        *,
        browser_artifact_activity: bool,
        input: str,
        result_dir: Path,
        stage_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Write one valid output and one invalid browser-evaluate event.

        Args:
            runner: Codex stage runner instance.
            command: Command argv passed to subprocess.
            browser_artifact_activity: Whether browser artifacts count as subprocess activity.
            input: Prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.

        Returns:
            Successful completed process with a forbidden browser JavaScript payload.
        """

        _ = runner
        assert browser_artifact_activity is True
        _ = input
        _ = result_dir
        _ = stage_dir
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            StageVerificationResult(
                status="success",
            ).model_dump_json(),
            encoding="utf-8",
        )
        event_payload = {
            "type": "item.started",
            "item": {
                "arguments": {"function": "() => import('node:fs')"},
                "server": "playwright",
                "tool": "browser_evaluate",
                "type": "mcp_tool_call",
            },
        }
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(event_payload) + "\n",
            stderr="",
        )

    monkeypatch.setattr(codex_runner.CodexStageRunner, "_subprocess_run", fake_codex_subprocess_run)

    with pytest.raises(codex_runner.CodexStageError, match="Node.js"):
        CodexStageRunner(workflow_container_name="brand-size-chart").run(
            allow_user_config=True,
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            model_class=StageVerificationResult,
            prompt_text="verify",
            result_dir=tmp_path,
            stage_dir=tmp_path / "stage",
            stage_name="source_discover",
        )


def test_codex_stage_run_removes_stale_diagnostics_before_subprocess(monkeypatch: object, tmp_path: Path) -> None:
    """Prevent retry attempts from reusing stale output and turn-completed diagnostics."""
    result_dir = tmp_path / "result"
    stage_dir = tmp_path / "stage"
    diagnostic_dir = stage_dir / "diagnostics" / "source_discover_verification"
    output_path = diagnostic_dir / "codex_output.json"
    event_path = diagnostic_dir / "event.jsonl"
    stderr_path = diagnostic_dir / "stderr.txt"
    result_dir.mkdir()
    diagnostic_dir.mkdir(parents=True)
    output_path.write_text(
        StageVerificationResult(
            error_list=["old error"],
            status="failed",
        ).model_dump_json(),
        encoding="utf-8",
    )
    event_path.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    stderr_path.write_text("old stderr\n", encoding="utf-8")

    def fake_codex_subprocess_run(
        runner: object,
        command: list[str],
        *,
        browser_artifact_activity: bool,
        input: str,
        result_dir: Path,
        stage_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Require stale terminal diagnostics to be gone before subprocess launch.

        Args:
            runner: Codex stage runner instance.
            command: Command argv passed to subprocess.
            browser_artifact_activity: Whether browser artifacts count as subprocess activity.
            input: Prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.

        Returns:
            Successful completed process with fresh diagnostics.
        """
        _ = runner
        assert browser_artifact_activity is False
        _ = input
        _ = result_dir
        _ = stage_dir
        assert not output_path.exists()
        assert not event_path.exists()
        assert not stderr_path.exists()
        fresh_output_path = Path(command[command.index("--output-last-message") + 1])
        fresh_output_path.write_text(
            StageVerificationResult(
                status="success",
            ).model_dump_json(),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

    monkeypatch.setattr(codex_runner.CodexStageRunner, "_subprocess_run", fake_codex_subprocess_run)

    result = CodexStageRunner(workflow_container_name="brand-size-chart").run(
        model_class=StageVerificationResult,
        prompt_text="verify current result",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_name="source_discover_verification",
    )

    assert result.status == "success"
    assert event_path.read_text(encoding="utf-8") == '{"type":"turn.completed"}\n'


def test_codex_subprocess_waits_after_stage_activity(monkeypatch: object, tmp_path: Path) -> None:
    """Continue waiting for `codex exec` when a timed-out interval produced stage artifacts."""
    communicate_call_count = 0

    class FakeProcess:
        """Fake long-running Codex process with one active timeout interval."""

        returncode = 0

        def communicate(self, input: str | None = None, timeout: int | None = None) -> tuple[str, str]:
            """Raise one timeout after writing an artifact, then finish.

            Args:
                input: Prompt text passed to the subprocess.
                timeout: Inactivity timeout.

            Returns:
                Captured stdout and stderr.

            Raises:
                subprocess.TimeoutExpired: On the first communicate call.
            """
            nonlocal communicate_call_count
            _ = input
            communicate_call_count += 1
            if communicate_call_count == 1:
                (tmp_path / "browser_evidence.json").write_text('{"ok": true}\n', encoding="utf-8")
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout)
            return '{"event": "done"}\n', ""

        def kill(self) -> None:
            """Fail the test if the active process is killed."""
            raise AssertionError("active process must not be killed")

    def fake_popen(
        command: list[str],
        *,
        stdin: int,
        stdout: int,
        stderr: int,
        start_new_session: bool,
        text: bool,
    ) -> FakeProcess:
        """Return a fake process and preserve the expected subprocess boundary shape.

        Args:
            command: Command argv passed to subprocess.
            stdin: Stdin pipe mode.
            stdout: Stdout pipe mode.
            stderr: Stderr pipe mode.
            start_new_session: Whether the process starts a new process group.
            text: Whether text mode is enabled.

        Returns:
            Fake process.
        """
        _ = command
        _ = stdin
        _ = stdout
        _ = stderr
        assert start_new_session is True
        _ = text
        return FakeProcess()

    monkeypatch.setattr(codex_runner.subprocess, "Popen", fake_popen)

    process = codex_runner.CodexStageRunner()._subprocess_run(
        ["codex", "exec"],
        browser_artifact_activity=False,
        input="prompt",
        result_dir=tmp_path,
        stage_dir=tmp_path,
    )

    assert communicate_call_count == 2
    assert process.returncode == 0
    assert process.stdout == '{"event": "done"}\n'


def test_codex_subprocess_waits_after_browser_artifact_activity(monkeypatch: object, tmp_path: Path) -> None:
    """Continue waiting when a browser stage writes run-local Playwright artifacts."""
    communicate_call_count = 0
    result_dir = tmp_path / "result"
    stage_dir = result_dir / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "x" / "source_discover"
    browser_stage_dir = result_dir / ".playwright-mcp" / "current" / stage_dir.relative_to(result_dir)

    class FakeProcess:
        """Fake long-running browser Codex process with one active browser-artifact interval."""

        returncode = 0

        def communicate(self, input: str | None = None, timeout: int | None = None) -> tuple[str, str]:
            """Raise one timeout after writing a browser artifact, then finish.

            Args:
                input: Prompt text passed to the subprocess.
                timeout: Inactivity timeout.

            Returns:
                Captured stdout and stderr.

            Raises:
                subprocess.TimeoutExpired: On the first communicate call.
            """
            nonlocal communicate_call_count
            _ = input
            communicate_call_count += 1
            if communicate_call_count == 1:
                browser_stage_dir.mkdir(parents=True, exist_ok=True)
                (browser_stage_dir / "evidence.json").write_text('{"ok": true}\n', encoding="utf-8")
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout)
            return '{"event": "done"}\n', ""

        def kill(self) -> None:
            """Fail the test if the active browser process is killed."""
            raise AssertionError("active browser process must not be killed")

    def fake_popen(
        command: list[str],
        *,
        stdin: int,
        stdout: int,
        stderr: int,
        start_new_session: bool,
        text: bool,
    ) -> FakeProcess:
        """Return a fake process and preserve the expected subprocess boundary shape.

        Args:
            command: Command argv passed to subprocess.
            stdin: Stdin pipe mode.
            stdout: Stdout pipe mode.
            stderr: Stderr pipe mode.
            start_new_session: Whether the process starts a new process group.
            text: Whether text mode is enabled.

        Returns:
            Fake process.
        """
        _ = command
        _ = stdin
        _ = stdout
        _ = stderr
        assert start_new_session is True
        _ = text
        return FakeProcess()

    monkeypatch.setattr(codex_runner.subprocess, "Popen", fake_popen)

    process = codex_runner.CodexStageRunner()._subprocess_run(
        ["codex", "exec"],
        browser_artifact_activity=True,
        input="prompt",
        result_dir=result_dir,
        stage_dir=stage_dir,
    )

    assert communicate_call_count == 2
    assert process.returncode == 0
    assert process.stdout == '{"event": "done"}\n'


def test_codex_subprocess_terminates_completed_stuck_process_group(monkeypatch: object, tmp_path: Path) -> None:
    """Stop waiting when Codex wrote final output but its MCP child keeps the process alive."""
    output_path = tmp_path / "diagnostics" / "source_discover" / "codex_output.json"
    event_path = tmp_path / "diagnostics" / "source_discover" / "event.jsonl"
    terminate_signal_list: list[int] = []

    class FakeProcess:
        """Fake Codex process that hangs after writing terminal artifacts."""

        pid = 12345
        returncode = None

        def __init__(self) -> None:
            """Initialize fake process state."""
            self.is_terminated = False

        def communicate(self, input: str | None = None, timeout: int | None = None) -> tuple[str, str]:
            """Write terminal artifacts, then hang until terminated.

            Args:
                input: Prompt text passed to the subprocess.
                timeout: Poll timeout.

            Returns:
                Captured stdout and stderr.

            Raises:
                subprocess.TimeoutExpired: Until the process group is terminated.
            """
            _ = input
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"status": "success"}\n', encoding="utf-8")
            event_path.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
            if not self.is_terminated:
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout)
            self.returncode = -15
            return '{"type":"turn.completed"}\n', ""

        def kill(self) -> None:
            """Fail the test if hard kill is used for completed output."""
            raise AssertionError("completed Codex process should be terminated, not killed")

        def terminate(self) -> None:
            """Mark the fake process as terminated."""
            self.is_terminated = True

    fake_process = FakeProcess()

    def fake_killpg(pid: int, signal_number: int) -> None:
        """Record process-group termination and mark the fake process terminated.

        Args:
            pid: Process id.
            signal_number: Signal sent to the process group.
        """
        assert pid == fake_process.pid
        terminate_signal_list.append(signal_number)
        fake_process.is_terminated = True

    def fake_popen(
        command: list[str],
        *,
        stdin: int,
        stdout: int,
        stderr: int,
        start_new_session: bool,
        text: bool,
    ) -> FakeProcess:
        """Return a fake stuck process and preserve the expected subprocess boundary shape.

        Args:
            command: Command argv passed to subprocess.
            stdin: Stdin pipe mode.
            stdout: Stdout pipe mode.
            stderr: Stderr pipe mode.
            start_new_session: Whether the process starts a new process group.
            text: Whether text mode is enabled.

        Returns:
            Fake process.
        """
        _ = command
        _ = stdin
        _ = stdout
        _ = stderr
        assert start_new_session is True
        _ = text
        return fake_process

    monkeypatch.setattr(codex_runner.os, "killpg", fake_killpg)
    monkeypatch.setattr(codex_runner.subprocess, "Popen", fake_popen)

    process = codex_runner.CodexStageRunner()._subprocess_run(
        ["codex", "exec", "--output-last-message", str(output_path)],
        browser_artifact_activity=False,
        input="prompt",
        result_dir=tmp_path,
        stage_dir=tmp_path,
    )

    assert terminate_signal_list == [codex_runner.signal.SIGTERM]
    assert process.returncode == 0
    assert process.stdout == '{"type":"turn.completed"}\n'
