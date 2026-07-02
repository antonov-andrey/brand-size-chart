"""Tests for Codex-owned browser stage contracts."""

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel

from brand_size_chart import codex_stage
from brand_size_chart.codex import runner as codex_runner
from brand_size_chart.model import (
    BrandInput,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    PromptScope,
    SourceDiscovery,
    SourceDiscoveryResult,
    StageVerification,
    TableExtraction,
    TableExtractionBatchResult,
)
from brand_size_chart.stage.base import MAX_STAGE_ATTEMPT_COUNT
from brand_size_chart.workflow import base as workflow_base


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
            / "source_discovery"
            / "evidence"
            / "marketplace_product_page.json"
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
        if model_class is SourceDiscoveryResult:
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper",
                        source_priority=300,
                        source_title="Official marketplace product page size answer",
                        source_type="official_marketplace_product_page",
                        source_url="https://www.trendyol.com/defacto/example-p-1",
                    )
                ],
                source_type="official_marketplace_product_page",
                status="success",
                message="browser discovery completed",
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="source_discovery",
            status="success",
            message="verified",
        )

    result = workflow_base.source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(
            product_type_request_list=["women shoes"],
            shared_instruction="Only search official marketplace product page evidence for requested product types.",
        ),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=300,
        source_type="official_marketplace_product_page",
        source_type_dir=source_type_dir,
    )

    assert result.discovered_source_list[0].source_type == "official_marketplace_product_page"
    assert call_list[0]["allow_user_config"] is True
    assert call_list[0]["browser_runtime_mcp_url"] == "http://127.0.0.1:12000/mcp"
    assert "Use the configured browser" in str(call_list[0]["prompt_text"])
    assert (
        f"Browser evidence write directory: "
        f"{tmp_path / '.playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/official_marketplace_product_page/source_discovery/evidence'}"
        in str(call_list[0]["prompt_text"])
    )
    assert (
        "Evidence reference directory: "
        ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_marketplace_product_page/source_discovery/evidence" in str(call_list[0]["prompt_text"])
    )
    assert "women shoes" in str(call_list[0]["prompt_text"])
    assert "run separate browser-visible searches for both `beden rehberi` and `beden tablosu`" in str(
        call_list[0]["prompt_text"]
    )
    assert (
        "Do not create one source candidate from product category, product title, variant labels, or option labels "
        "alone." in str(call_list[0]["prompt_text"])
    )
    assert "The candidate size_group_key must match one concrete browser-visible chart group or table heading" in str(
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
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="defacto_tr_beden_rehberi_all",
                        source_priority=600,
                        source_title="Beden Rehberi",
                        source_type="official_brand_size_guide",
                        source_url="https://www.defacto.com.tr/brand-size-guide",
                    )
                ],
                source_type="official_brand_size_guide",
                status="success",
                message="browser discovery completed",
            )
        if model_class is SourceDiscoveryResult:
            assert "aggregate token" in prompt_text
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper",
                        source_priority=600,
                        source_title="Kadın Üst Beden Tablosu",
                        source_type="official_brand_size_guide",
                        source_url="https://www.defacto.com.tr/brand-size-guide",
                    )
                ],
                source_type="official_brand_size_guide",
                status="success",
                message="browser discovery completed",
            )
        if len([call for call in call_list if call["model_class"] is SourceDiscoveryResult]) == 1:
            return StageVerification(
                artifact_path_list=[],
                error_list=["SourceDiscovery.size_group_key contains aggregate token."],
                feedback_list=["SourceDiscovery.size_group_key contains aggregate token."],
                stage_key="source_discovery",
                status="failed",
                message="Aggregate source discovery must be fixed by the main stage.",
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="source_discovery",
            status="success",
            message="verified",
        )

    result = workflow_base.source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=600,
        source_type="official_brand_size_guide",
        source_type_dir=source_type_dir,
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
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper",
                        source_priority=600,
                        source_title="Tableau Des Tailles Femmes",
                        source_type="official_brand_size_guide",
                        source_url="https://www.defacto.com/fr-ma/static/size-charts",
                    )
                ],
                source_type="official_brand_size_guide",
                status="success",
                message="partial browser discovery completed",
            )
        if model_class is SourceDiscoveryResult:
            assert "Previous stage result JSON" in prompt_text
            assert "women_upper" in prompt_text
            assert "https://www.defacto.com/fr-ma/static/size-charts" in prompt_text
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper",
                        source_priority=600,
                        source_title="Tableau Des Tailles Femmes",
                        source_type="official_brand_size_guide",
                        source_url="https://www.defacto.com/fr-ma/static/size-charts",
                    )
                ],
                source_type="official_brand_size_guide",
                status="success",
                message="completed browser discovery preserved previous candidates",
            )
        if discovery_call_count == 1:
            return StageVerification(
                artifact_path_list=[],
                error_list=["Inventory is incomplete."],
                feedback_list=["Inventory is incomplete."],
                stage_key="source_discovery",
                status="failed",
                message="Discovery inventory must be completed.",
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="source_discovery",
            status="success",
            message="verified",
        )

    result = workflow_base.source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=600,
        source_type="official_brand_size_guide",
        source_type_dir=source_type_dir,
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
            return SourceDiscoveryResult(
                discovered_source_list=[],
                source_type="official_brand_size_guide",
                status="failed",
                message="No concrete tables found.",
            )
        if model_class is SourceDiscoveryResult:
            assert "failed source_discovery must include concrete error_list blockers" in prompt_text
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper",
                        source_priority=600,
                        source_title="Kadın Üst Beden Tablosu",
                        source_type="official_brand_size_guide",
                        source_url="https://www.defacto.com.tr/brand-size-guide",
                    )
                ],
                source_type="official_brand_size_guide",
                status="success",
                message="browser discovery completed",
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="source_discovery",
            status="success",
            message="verified",
        )

    result = workflow_base.source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=600,
        source_type="official_brand_size_guide",
        source_type_dir=source_type_dir,
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
            inventory_path = stage_dir / "evidence" / "source_surface_inventory.json"
            inventory_path.parent.mkdir(parents=True, exist_ok=True)
            inventory_path.write_text('{"opened_url_list": [], "rejected_url_list": []}\n', encoding="utf-8")
            return SourceDiscoveryResult(
                discovered_source_list=[],
                error_list=["No official seller size-guide table was visible in browser evidence."],
                source_type="official_seller_size_guide",
                status="failed",
                message="No concrete official seller size guide found.",
            )
        return StageVerification(
            artifact_path_list=[],
            message="verified",
            stage_key="source_discovery",
            status="success",
        )

    result = workflow_base.source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=550,
        source_type="official_seller_size_guide",
        source_type_dir=source_type_dir,
    )

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert result.status == "failed"
    assert result.error_list == ["No official seller size-guide table was visible in browser evidence."]
    assert discovery_call_list == [{"model_class": SourceDiscoveryResult}]


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
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        country_code_list=["TR"],
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper",
                        source_priority=600,
                        source_title="Kadın Üst Beden Tablosu",
                        source_type="official_brand_size_guide",
                        source_url="https://www.defacto.com.tr/brand-size-guide",
                    )
                ],
                source_type="official_brand_size_guide",
                status="success",
                message="browser discovery completed",
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="source_discovery",
            status="success",
            message="verified",
        )

    workflow_base.source_discovery_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=600,
        source_type="official_brand_size_guide",
        source_type_dir=source_type_dir,
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
                discovered_source_list=[],
                source_type="official_brand_size_guide",
                status="skipped",
                message="No official brand-owned standalone size-guide page was found.",
            )
        return StageVerification(
            artifact_path_list=[],
            error_list=["Empty source discovery is forbidden."],
            feedback_list=["Empty source discovery is forbidden."],
            stage_key="source_discovery",
            status="failed",
            message="Empty source discovery must be fixed by the main stage.",
        )

    try:
        workflow_base.source_discovery_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(),
            result_dir=tmp_path,
            secret_path=tmp_path / "secret",
            source_priority=600,
            source_type="official_brand_size_guide",
            source_type_dir=source_type_dir,
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
        if model_class is TableExtractionBatchResult:
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
            return TableExtractionBatchResult(
                message="browser extraction completed",
                source_type="official_marketplace_product_page",
                status="success",
                table_extraction_list=[
                    _table_extraction_get(
                        evidence_path=evidence_path_by_size_group_key_map[source_discovery.size_group_key],
                        result_dir=result_dir,
                        size_group_key=source_discovery.size_group_key,
                        source_title=source_discovery.source_title,
                        source_type=source_discovery.source_type,
                        source_url=source_discovery.source_url,
                    )
                    for source_discovery in source_discovery_list
                ],
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="table_extract",
            status="success",
            message="verified",
        )

    result = workflow_base.table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_discovery_list=source_discovery_list,
        source_type="official_marketplace_product_page",
        source_type_dir=source_type_dir,
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionBatchResult]
    assert [table_extraction.size_group_key for table_extraction in result.table_extraction_list] == [
        "women_upper",
        "women_lower",
    ]
    assert len(table_extract_call_list) == 1
    assert table_extract_call_list[0]["allow_user_config"] is True
    assert table_extract_call_list[0]["browser_runtime_mcp_url"] == "http://127.0.0.1:12000/mcp"
    assert table_extract_call_list[0]["stage_name"] == "table_extract"
    assert "Use the configured browser" in str(table_extract_call_list[0]["prompt_text"])
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
    assert batch_result_payload["table_extraction_list"][0]["size_group_key"] == "women_upper"
    assert women_upper_chart_payload == result.table_extraction_list[0].chart.model_dump(mode="json")
    assert women_lower_chart_payload == result.table_extraction_list[1].chart.model_dump(mode="json")


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
        _ = stage_dir
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerification:
            return StageVerification(
                artifact_path_list=[],
                message="verified",
                stage_key="table_extract",
                status="success",
            )

        batch_call_count = len([call for call in call_list if call["model_class"] is TableExtractionBatchResult])
        if batch_call_count == 2:
            assert "missing" in prompt_text.lower()
            assert "women_lower" in prompt_text
        extraction_list = []
        selected_discovery_list = source_discovery_list if batch_call_count == 2 else source_discovery_list[:1]
        for source_discovery in selected_discovery_list:
            evidence_path = _table_evidence_path_get(
                result_dir=result_dir,
                source_type=source_discovery.source_type,
                size_group_key=source_discovery.size_group_key,
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            extraction_list.append(
                _table_extraction_get(
                    evidence_path=evidence_path,
                    result_dir=result_dir,
                    size_group_key=source_discovery.size_group_key,
                    source_title=source_discovery.source_title,
                    source_type=source_discovery.source_type,
                    source_url=source_discovery.source_url,
                )
            )
        return TableExtractionBatchResult(
            message="browser extraction completed",
            source_type="official_brand_size_guide",
            status="success",
            table_extraction_list=extraction_list,
        )

    result = workflow_base.table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_discovery_list=source_discovery_list,
        source_type="official_brand_size_guide",
        source_type_dir=tmp_path / "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide",
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionBatchResult]
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
        _ = stage_dir
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerification:
            return StageVerification(
                artifact_path_list=[],
                message="verified",
                stage_key="table_extract",
                status="success",
            )

        batch_call_count = len([call for call in call_list if call["model_class"] is TableExtractionBatchResult])
        if batch_call_count == 2:
            assert "extra" in prompt_text.lower()
            assert "women_extra" in prompt_text
        selected_size_group_key_list = ["women_upper"] if batch_call_count == 2 else ["women_upper", "women_extra"]
        extraction_list = []
        for size_group_key in selected_size_group_key_list:
            evidence_path = _table_evidence_path_get(
                result_dir=result_dir,
                source_type="official_brand_size_guide",
                size_group_key=size_group_key,
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
            extraction_list.append(
                _table_extraction_get(
                    evidence_path=evidence_path,
                    result_dir=result_dir,
                    size_group_key=size_group_key,
                    source_title="Women upper" if size_group_key == "women_upper" else "Women extra",
                )
            )
        return TableExtractionBatchResult(
            message="browser extraction completed",
            source_type="official_brand_size_guide",
            status="success",
            table_extraction_list=extraction_list,
        )

    result = workflow_base.table_extract_result_get(
        brand_input=_brand_input_get(),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_discovery_list=source_discovery_list,
        source_type="official_brand_size_guide",
        source_type_dir=tmp_path / "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide",
    )

    table_extract_call_list = [call for call in call_list if call["model_class"] is TableExtractionBatchResult]
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
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        if model_class is SourceDiscoveryResult:
            return SourceDiscoveryResult(
                discovered_source_list=[],
                message="No tables found.",
                source_type="official_brand_size_guide",
                status="skipped",
            )
        return StageVerification(
            artifact_path_list=[],
            message="verified",
            stage_key="source_discovery",
            status="success",
        )

    try:
        workflow_base.source_discovery_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(),
            result_dir=tmp_path,
            secret_path=tmp_path / "secret",
            source_priority=600,
            source_type="official_brand_size_guide",
            source_type_dir=source_type_dir,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "source_discovery" in message
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
            return SourceDiscoveryResult(
                discovered_source_list=[discovery, discovery],
                message="browser discovery completed",
                source_type="official_brand_size_guide",
                status="success",
            )
        return StageVerification(
            artifact_path_list=[],
            message="verified",
            stage_key="source_discovery",
            status="success",
        )

    try:
        workflow_base.source_discovery_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(),
            result_dir=tmp_path,
            secret_path=tmp_path / "secret",
            source_priority=600,
            source_type="official_brand_size_guide",
            source_type_dir=source_type_dir,
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
        _ = stage_dir
        evidence_path = _table_evidence_path_get(
            result_dir=result_dir,
            source_type="official_brand_size_guide",
            size_group_key="renamed_upper",
            suffix="md",
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("table evidence", encoding="utf-8")
        if model_class is TableExtractionBatchResult:
            return TableExtractionBatchResult(
                message="browser extraction completed",
                source_type="official_brand_size_guide",
                status="success",
                table_extraction_list=[
                    _table_extraction_get(
                        evidence_path=evidence_path,
                        result_dir=result_dir,
                        size_group_key="renamed_upper",
                        source_title="Women upper",
                    )
                ],
            )
        return StageVerification(
            artifact_path_list=[],
            message="verified",
            stage_key="table_extract",
            status="success",
        )

    try:
        workflow_base.table_extract_result_get(
            brand_input=_brand_input_get(),
            browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
            codex_stage_run_callable=fake_codex_stage_run,
            prompt_scope=PromptScope(),
            result_dir=tmp_path,
            secret_path=tmp_path / "secret",
            source_discovery_list=source_discovery_list,
            source_type="official_brand_size_guide",
            source_type_dir=source_type_dir,
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
        input: str,
        stage_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Capture the Codex command and write a schema-valid output file.

        Args:
            runner: Codex stage runner instance.
            command: Command argv passed to subprocess.
            input: Prompt text.
            stage_dir: Stage artifact directory.

        Returns:
            Successful completed process.
        """
        _ = runner
        _ = input
        _ = stage_dir
        captured_command.extend(command)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            StageVerification(
                artifact_path_list=[],
                stage_key="source_discovery",
                status="success",
                message="verified",
            ).model_dump_json(),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(codex_runner.CodexStageRunner, "_subprocess_run", fake_codex_subprocess_run)

    monkeypatch.chdir(tmp_path)
    result_dir = Path("result")
    result_dir.mkdir()
    stage_dir = Path("relative-stage")
    codex_stage.codex_stage_run(
        allow_user_config=True,
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        model_class=StageVerification,
        prompt_text="verify",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_name="source_discovery",
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


def test_codex_stage_run_removes_stale_diagnostics_before_subprocess(monkeypatch: object, tmp_path: Path) -> None:
    """Prevent retry attempts from reusing stale output and turn-completed diagnostics."""
    result_dir = tmp_path / "result"
    stage_dir = tmp_path / "stage"
    diagnostic_dir = stage_dir / "diagnostics" / "source_discovery_verification"
    output_path = diagnostic_dir / "codex_output.json"
    event_path = diagnostic_dir / "event.jsonl"
    stderr_path = diagnostic_dir / "stderr.txt"
    result_dir.mkdir()
    diagnostic_dir.mkdir(parents=True)
    output_path.write_text(
        StageVerification(
            artifact_path_list=[],
            error_list=["old error"],
            stage_key="source_discovery",
            status="failed",
            message="old verification",
        ).model_dump_json(),
        encoding="utf-8",
    )
    event_path.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    stderr_path.write_text("old stderr\n", encoding="utf-8")

    def fake_codex_subprocess_run(
        runner: object,
        command: list[str],
        *,
        input: str,
        stage_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Require stale terminal diagnostics to be gone before subprocess launch.

        Args:
            runner: Codex stage runner instance.
            command: Command argv passed to subprocess.
            input: Prompt text.
            stage_dir: Stage artifact directory.

        Returns:
            Successful completed process with fresh diagnostics.
        """
        _ = runner
        _ = input
        _ = stage_dir
        assert not output_path.exists()
        assert not event_path.exists()
        assert not stderr_path.exists()
        fresh_output_path = Path(command[command.index("--output-last-message") + 1])
        fresh_output_path.write_text(
            StageVerification(
                artifact_path_list=[],
                stage_key="source_discovery",
                status="success",
                message="fresh verification",
            ).model_dump_json(),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

    monkeypatch.setattr(codex_runner.CodexStageRunner, "_subprocess_run", fake_codex_subprocess_run)

    result = codex_stage.codex_stage_run(
        model_class=StageVerification,
        prompt_text="verify current result",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_name="source_discovery_verification",
    )

    assert result.status == "success"
    assert result.message == "fresh verification"
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

    process = codex_runner.CodexStageRunner()._subprocess_run(["codex", "exec"], input="prompt", stage_dir=tmp_path)

    assert communicate_call_count == 2
    assert process.returncode == 0
    assert process.stdout == '{"event": "done"}\n'


def test_codex_subprocess_terminates_completed_stuck_process_group(monkeypatch: object, tmp_path: Path) -> None:
    """Stop waiting when Codex wrote final output but its MCP child keeps the process alive."""
    output_path = tmp_path / "diagnostics" / "source_discovery" / "codex_output.json"
    event_path = tmp_path / "diagnostics" / "source_discovery" / "event.jsonl"
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
        input="prompt",
        stage_dir=tmp_path,
    )

    assert terminate_signal_list == [codex_runner.signal.SIGTERM]
    assert process.returncode == 0
    assert process.stdout == '{"type":"turn.completed"}\n'
