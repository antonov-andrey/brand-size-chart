"""Generated JSON-schema registry for workflow models."""

from __future__ import annotations

import json
from pathlib import Path

from brand_size_chart.model.base import StrictBaseModel
from brand_size_chart.model.brand import BrandInput, BrandListParseResult, BrandResult
from brand_size_chart.model.chart import BrandSizeChart
from brand_size_chart.model.prompt import PromptScope, PromptStageInstruction
from brand_size_chart.model.run import RunResult
from brand_size_chart.model.selection import (
    CanonicalSelection,
    CanonicalSelectionResult,
    CoverageDecision,
    CoverageDecisionResult,
)
from brand_size_chart.model.source import SourceDiscovery, SourceDiscoveryResult, SourceTypeSummary, TableExtraction
from brand_size_chart.model.stage import StageVerification


def schema_file_write(schema_dir: Path) -> None:
    """Write JSON Schema files generated from Pydantic models.

    Args:
        schema_dir: Directory where schema files are written.
    """
    schema_dir.mkdir(parents=True, exist_ok=True)
    for schema_name, model_class in schema_model_map_get().items():
        schema_path = schema_dir / f"{schema_name}.schema.json"
        schema_payload = model_class.model_json_schema()
        schema_path.write_text(json.dumps(schema_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def schema_model_map_get() -> dict[str, type[StrictBaseModel]]:
    """Return public artifact schema names and their Pydantic model owners.

    Returns:
        Mapping from schema file stem to model class.
    """
    return {
        "brand_input": BrandInput,
        "brand_list_parse_result": BrandListParseResult,
        "brand_result": BrandResult,
        "brand_size_chart": BrandSizeChart,
        "canonical_selection": CanonicalSelection,
        "canonical_selection_result": CanonicalSelectionResult,
        "coverage_decision": CoverageDecision,
        "coverage_decision_result": CoverageDecisionResult,
        "prompt_scope": PromptScope,
        "prompt_stage_instruction": PromptStageInstruction,
        "run_result": RunResult,
        "source_discovery": SourceDiscovery,
        "source_discovery_result": SourceDiscoveryResult,
        "source_type_summary": SourceTypeSummary,
        "stage_verification": StageVerification,
        "table_extraction": TableExtraction,
    }
