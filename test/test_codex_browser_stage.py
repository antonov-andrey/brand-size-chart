"""Tests for Codex-owned browser stage contracts."""

import subprocess
from pathlib import Path

from pydantic import BaseModel

from brand_size_chart import codex_stage
from brand_size_chart import workflow
from brand_size_chart.model import (
    BrandInput,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    SourceDiscovery,
    SourceDiscoveryResult,
    StageVerification,
    TableExtraction,
)


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


def test_source_discovery_calls_codex_browser_stage_without_local_sources(monkeypatch: object, tmp_path: Path) -> None:
    """Run real discovery through Codex browser access even when the draft source list is empty."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_marketplace_product_page"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return schema-valid stage artifacts and record Codex execution settings.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        call_list.append(
            {
                "allow_user_config": allow_user_config,
                "browser_runtime_data_source_path": browser_runtime_data_source_path,
                "model_class": model_class,
                "prompt_text": prompt_text,
                "sandbox_mode": sandbox_mode,
                "stage_name": stage_name,
            }
        )
        evidence_path = stage_dir / "evidence" / "marketplace_product_page.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
        if model_class is SourceDiscoveryResult:
            return SourceDiscoveryResult(
                discovered_source_list=[
                    SourceDiscovery(
                        confidence=1.0,
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_size_chart",
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

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    result = workflow._source_discovery_result_get(
        brand_input=_brand_input_get(),
        prompt_scope=workflow.PromptScope(
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
    assert call_list[0]["browser_runtime_data_source_path"] == tmp_path / "secret"
    assert call_list[0]["sandbox_mode"] == "workspace-write"
    assert "Use the configured browser" in str(call_list[0]["prompt_text"])
    assert "women shoes" in str(call_list[0]["prompt_text"])
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
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one invalid page-level candidate and then one concrete table candidate.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        call_list.append(
            {
                "allow_user_config": allow_user_config,
                "browser_runtime_data_source_path": browser_runtime_data_source_path,
                "model_class": model_class,
                "prompt_text": prompt_text,
                "sandbox_mode": sandbox_mode,
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
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper_size_chart",
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

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    result = workflow._source_discovery_result_get(
        brand_input=_brand_input_get(),
        prompt_scope=workflow.PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_priority=600,
        source_type="official_brand_size_guide",
        source_type_dir=source_type_dir,
    )

    discovery_call_list = [call for call in call_list if call["model_class"] is SourceDiscoveryResult]
    assert result.discovered_source_list[0].size_group_key == "women_upper_size_chart"
    assert len(discovery_call_list) == 2


def test_source_discovery_prompt_has_no_hardcoded_size_guide_routes(monkeypatch: object, tmp_path: Path) -> None:
    """Keep official brand size-guide discovery generic without hardcoded route templates."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return valid source discovery while preserving the prompt for assertions.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        _ = allow_user_config
        _ = browser_runtime_data_source_path
        _ = sandbox_mode
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
                        evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                        size_group_key="women_upper_size_chart",
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

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    workflow._source_discovery_result_get(
        brand_input=_brand_input_get(),
        prompt_scope=workflow.PromptScope(),
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
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return the current bad empty skipped discovery response.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake empty discovery result or passing verification.
        """
        _ = allow_user_config
        _ = browser_runtime_data_source_path
        _ = result_dir
        _ = sandbox_mode
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

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    try:
        workflow._source_discovery_result_get(
            brand_input=_brand_input_get(),
            prompt_scope=workflow.PromptScope(),
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
    assert len(discovery_call_list) == workflow.MAX_STAGE_ATTEMPT_COUNT
    assert "Empty source discovery" in str(discovery_call_list[1]["prompt_text"])


def test_table_extraction_calls_codex_browser_stage_and_requires_evidence(monkeypatch: object, tmp_path: Path) -> None:
    """Run table extraction through Codex browser access and require a written evidence artifact."""
    call_list: list[dict[str, object]] = []
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_marketplace_product_page"
    )
    source_discovery = SourceDiscovery(
        confidence=1.0,
        evidence_path_list=[],
        size_group_key="women_size_chart",
        source_priority=300,
        source_title="Official marketplace product page size answer",
        source_type="official_marketplace_product_page",
        source_url="https://www.trendyol.com/defacto/example-p-1",
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return schema-valid extraction artifacts and record Codex execution settings.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake validated stage result.
        """
        call_list.append(
            {
                "allow_user_config": allow_user_config,
                "browser_runtime_data_source_path": browser_runtime_data_source_path,
                "model_class": model_class,
                "prompt_text": prompt_text,
                "sandbox_mode": sandbox_mode,
                "stage_name": stage_name,
            }
        )
        evidence_path = stage_dir / "evidence" / "women_size_chart.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"source": "browser"}\n', encoding="utf-8")
        if model_class is TableExtraction:
            return TableExtraction(
                applicability_status="turkey_official",
                chart=BrandSizeChart(
                    description="Defacto women size chart.",
                    row_list=[
                        BrandSizeChartRow(
                            measurement_list=[
                                BrandSizeChartMeasurement(
                                    max_value="90",
                                    min_value="88",
                                    name="chest",
                                    unit="cm",
                                )
                            ],
                            size_label="M",
                        )
                    ],
                ),
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_size_chart",
                source_title="Official marketplace product page size answer",
                source_type="official_marketplace_product_page",
                source_url="https://www.trendyol.com/defacto/example-p-1",
            )
        return StageVerification(
            artifact_path_list=[],
            stage_key="table_extraction",
            status="success",
            message="verified",
        )

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    result = workflow._table_stage_run(
        brand_input=_brand_input_get(),
        prompt_scope=workflow.PromptScope(),
        result_dir=tmp_path,
        secret_path=tmp_path / "secret",
        source_discovery=source_discovery,
        source_type="official_marketplace_product_page",
        source_type_dir=source_type_dir,
    )

    assert result.chart.row_list[0].size_label == "M"
    assert call_list[0]["allow_user_config"] is True
    assert call_list[0]["browser_runtime_data_source_path"] == tmp_path / "secret"
    assert call_list[0]["sandbox_mode"] == "workspace-write"
    assert "Use the configured browser" in str(call_list[0]["prompt_text"])


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
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return skipped discovery and an incorrectly passing verifier.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_data_source_path
        _ = prompt_text
        _ = result_dir
        _ = sandbox_mode
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

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    try:
        workflow._source_discovery_result_get(
            brand_input=_brand_input_get(),
            prompt_scope=workflow.PromptScope(),
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
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return duplicate discovered tables.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake discovery or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_data_source_path
        _ = prompt_text
        _ = sandbox_mode
        _ = stage_name
        evidence_path = stage_dir / "evidence" / "guide.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("browser evidence", encoding="utf-8")
        if model_class is SourceDiscoveryResult:
            discovery = SourceDiscovery(
                confidence=1.0,
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="women_upper_size_chart",
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

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    try:
        workflow._source_discovery_result_get(
            brand_input=_brand_input_get(),
            prompt_scope=workflow.PromptScope(),
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
    assert "women_upper_size_chart" in message


def test_table_extraction_rejects_identity_change(monkeypatch: object, tmp_path: Path) -> None:
    """Reject table extraction that changes the discovery-owned identity."""
    source_type_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )
    source_discovery = SourceDiscovery(
        confidence=1.0,
        evidence_path_list=[],
        size_group_key="women_upper_size_chart",
        source_priority=600,
        source_title="Women upper",
        source_type="official_brand_size_guide",
        source_url="https://defacto.example/size",
    )

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_data_source_path: Path | None,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        sandbox_mode: str,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return extraction with changed size group key.

        Args:
            allow_user_config: Whether Codex loads configured MCP tools.
            browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
            model_class: Expected stage result model.
            prompt_text: Prompt text passed to Codex.
            result_dir: Root result directory.
            sandbox_mode: Codex sandbox mode.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake extraction or verification result.
        """
        _ = allow_user_config
        _ = browser_runtime_data_source_path
        _ = prompt_text
        _ = sandbox_mode
        _ = stage_name
        evidence_path = stage_dir / "evidence" / "table.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("table evidence", encoding="utf-8")
        if model_class is TableExtraction:
            return TableExtraction(
                applicability_status="turkey_official",
                chart=BrandSizeChart(
                    description="Women upper",
                    row_list=[
                        BrandSizeChartRow(
                            measurement_list=[
                                BrandSizeChartMeasurement(max_value="90", min_value="88", name="chest", unit="cm")
                            ],
                            size_label="M",
                        )
                    ],
                ),
                evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                size_group_key="renamed_size_chart",
                source_title="Women upper",
                source_type="official_brand_size_guide",
                source_url="https://defacto.example/size",
            )
        return StageVerification(
            artifact_path_list=[],
            message="verified",
            stage_key="table_extraction",
            status="success",
        )

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    try:
        workflow._table_stage_run(
            brand_input=_brand_input_get(),
            prompt_scope=workflow.PromptScope(),
            result_dir=tmp_path,
            secret_path=tmp_path / "secret",
            source_discovery=source_discovery,
            source_type="official_brand_size_guide",
            source_type_dir=source_type_dir,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "size_group_key" in message
    assert "women_upper_size_chart" in message


def test_codex_browser_stage_uses_browser_vpn_runtime_mcp(monkeypatch: object, tmp_path: Path) -> None:
    """Configure Codex browser stages through browser-vpn-runtime instead of direct Playwright MCP."""
    captured_command: list[str] = []

    def fake_subprocess_run(
        command: list[str],
        *,
        check: bool,
        input: str,
        stderr: int,
        stdout: int,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        """Capture the Codex command and write a schema-valid output file.

        Args:
            command: Command argv passed to subprocess.
            check: Whether subprocess should raise on failure.
            input: Prompt text.
            stderr: Stderr capture mode.
            stdout: Stdout capture mode.
            text: Whether text mode is enabled.
            timeout: Command timeout in seconds.

        Returns:
            Successful completed process.
        """
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

    monkeypatch.setattr(codex_stage.subprocess, "run", fake_subprocess_run)

    codex_stage.codex_stage_run(
        allow_user_config=True,
        browser_runtime_data_source_path=tmp_path / "secret",
        model_class=StageVerification,
        prompt_text="verify",
        result_dir=tmp_path,
        sandbox_mode="workspace-write",
        stage_dir=tmp_path / "stage",
        stage_name="source_discovery",
    )

    command_text = "\n".join(captured_command)
    assert "browser_vpn_runtime.playwright_mcp" in command_text
    assert str(tmp_path / "secret") in command_text
    assert "@playwright/mcp" not in command_text
    assert "npx" not in command_text
