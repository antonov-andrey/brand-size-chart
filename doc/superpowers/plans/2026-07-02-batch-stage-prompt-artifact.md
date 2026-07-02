# Batch Stage Prompt Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-table Codex extraction with one batch `table_extract` stage per source type, move stage prompts to full Jinja2 templates, and add generic artifact reference materialization.

**Architecture:** `source_discover` still returns one verified list of concrete table candidates. `table_extract` receives that whole list, runs one Codex action/verification loop, writes one batch `result.json` and deterministic `chart/<size_group_key>.json` files, then source-type summary consumes the verified batch list. Prompt rendering is centralized through strict Jinja2 templates, and artifact references are normalized through a generic materializer before mechanical validation.

**Tech Stack:** Python 3.14, DBOS, Pydantic v2, Jinja2, pytest, jsonschema.

---

### Task 1: Batch Result Models, Schemas, And Artifact Layout

**Files:**
- Modify: `pyproject.toml`
- Modify: `brand_size_chart/model/source.py`
- Modify: `brand_size_chart/model/__init__.py`
- Modify: `brand_size_chart/model/schema_registry.py`
- Modify: `brand_size_chart/artifact/layout.py`
- Modify: `brand_size_chart/artifact/__init__.py`
- Create: `brand_size_chart/artifact/materializer.py`
- Test: `test/test_models.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add failing tests for batch model, schema registration, and paths**

Add tests that assert:

```python
from pathlib import Path

from brand_size_chart.artifact import ArtifactLayout, ArtifactMaterializer
from brand_size_chart.model import (
    BrandInput,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    TableExtraction,
    TableExtractionBatchResult,
    schema_model_map_get,
)


def test_table_extraction_batch_result_is_public_schema_model() -> None:
    assert TableExtractionBatchResult.__module__ == "brand_size_chart.model.source"
    assert schema_model_map_get()["table_extraction_batch_result"] is TableExtractionBatchResult


def test_table_extract_layout_uses_one_source_type_batch_dir(tmp_path: Path) -> None:
    layout = ArtifactLayout(tmp_path)
    brand_input = BrandInput(parsed_brand_key="defacto", parsed_brand_name="Defacto", raw_brand_name="Defacto", source_line_number=1)
    stage_dir = layout.table_extract_dir(brand_input, "official_brand_size_guide")
    assert stage_dir.relative_to(tmp_path).as_posix() == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract"
    assert layout.table_extract_chart_path(brand_input, "official_brand_size_guide", "women_upper").relative_to(tmp_path).as_posix() == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/chart/women_upper.json"


def test_artifact_materializer_preserves_external_reference_inside_allowed_root(tmp_path: Path) -> None:
    result_dir = tmp_path / "result"
    external_root = result_dir / ".tool-output"
    external_file = external_root / "source.json"
    external_file.parent.mkdir(parents=True)
    external_file.write_text("{}\n", encoding="utf-8")
    materializer = ArtifactMaterializer(result_dir=result_dir, allowed_root_list=[external_root])
    assert materializer.reference_list_materialize(reference_list=[str(external_file)]) == [".tool-output/source.json"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest test/test_models.py::test_table_extraction_batch_result_is_public_schema_model test/test_workflow_contract.py::test_table_extract_layout_uses_one_source_type_batch_dir test/test_workflow_contract.py::test_artifact_materializer_preserves_external_reference_inside_allowed_root -q
```

Expected: fail because `TableExtractionBatchResult`, `table_extract_dir`, `table_extract_chart_path`, and `ArtifactMaterializer` do not exist.

- [ ] **Step 3: Implement minimal model and schema registration**

Add `TableExtractionBatchResult` to `brand_size_chart/model/source.py`:

```python
class TableExtractionBatchResult(StrictBaseModel):
    """Batch extraction result for one source type."""

    error_list: list[str] = Field(default_factory=list)
    message: str
    source_type: str
    status: StageStatus
    table_extraction_list: list[TableExtraction]
```

Export it from `brand_size_chart/model/__init__.py` and add it to `schema_model_map_get()` with key `table_extraction_batch_result`.

- [ ] **Step 4: Implement batch artifact layout**

In `ArtifactLayout`, add:

```python
def table_extract_dir(self, brand_input: BrandInput, source_type: str) -> Path:
    """Return batch table-extract audit directory for one source type."""
    return self.source_type_dir(brand_input, source_type) / "table_extract"


def table_extract_chart_path(self, brand_input: BrandInput, source_type: str, size_group_key: str) -> Path:
    """Return generated batch chart artifact path."""
    return self.table_extract_dir(brand_input, source_type) / "chart" / f"{size_group_key}.json"


def table_extract_result_path(self, brand_input: BrandInput, source_type: str) -> Path:
    """Return batch table-extract result path."""
    return self.stage_result_path(self.table_extract_dir(brand_input, source_type))
```

Remove old table-extraction layout methods after Task 3 migrates all call sites.

- [ ] **Step 5: Implement generic artifact materializer**

Create `brand_size_chart/artifact/materializer.py` with `ArtifactMaterializer`. It must accept `result_dir` and `allowed_root_list`, validate references are inside one allowed root, and return result-root-relative POSIX references. It must not mention browser, Playwright, source type, or brand-specific rules. Export it from `brand_size_chart/artifact/__init__.py`.

- [ ] **Step 6: Add Jinja2 dependency**

Add `"Jinja2>=3.1.0"` to `pyproject.toml`.

- [ ] **Step 7: Run GREEN checks**

Run:

```bash
uv run pytest test/test_models.py test/test_workflow_contract.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add pyproject.toml brand_size_chart/model brand_size_chart/artifact test/test_models.py test/test_workflow_contract.py
git commit -m "Add batch extraction model and artifact layout"
```

### Task 2: Prompt Renderer And Full Stage Templates

**Files:**
- Create: `brand_size_chart/prompt/renderer.py`
- Create: `brand_size_chart/prompt/template/*.md.j2`
- Create: `brand_size_chart/prompt/template/partial/*.md.j2`
- Modify: `brand_size_chart/stage/semantic.py`
- Modify: `brand_size_chart/stage/base.py`
- Test: `test/test_prompt_renderer.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add failing prompt renderer tests**

Create `test/test_prompt_renderer.py` with tests that assert strict undefined variables fail and that a rendered stage prompt includes `stage_key`, retry feedback, workflow shared instruction, stage-specific instruction, and the size group key partial for `source_discover`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest test/test_prompt_renderer.py -q
```

Expected: fail because `brand_size_chart.prompt.renderer` does not exist.

- [ ] **Step 3: Implement `PromptRenderer`**

Create `PromptRenderer` as a small class wrapping `jinja2.Environment(undefined=StrictUndefined, autoescape=False)` and loading templates from `brand_size_chart/prompt/template`. Its public method must be `render(template_name: str, context: Mapping[str, object]) -> str`.

- [ ] **Step 4: Move prompt assembly into templates**

Create full templates:

```text
workflow_run_prompt_apply.md.j2
workflow_run_prompt_apply_verify.md.j2
source_discover.md.j2
source_discover_verify.md.j2
table_extract.md.j2
table_extract_verify.md.j2
coverage_decide.md.j2
coverage_decide_verify.md.j2
canonical_select.md.j2
canonical_select_verify.md.j2
```

Each template must include one full prompt. Use partials for shared contracts:

```text
partial/artifact_reference_contract.md.j2
partial/runtime_source_access.md.j2
partial/size_group_key_contract.md.j2
partial/stage_retry_context.md.j2
```

- [ ] **Step 5: Update `SemanticStage` to use templates**

Replace `stage_prompt_text_get()` string concatenation with `PromptRenderer`. Keep the method as a compatibility test surface only if needed, but it must render templates rather than own human-readable prose.

- [ ] **Step 6: Add contract test against Python prompt prose drift**

In `test/test_workflow_contract.py`, add a code-shape test that checks stage modules do not contain long instruction fragments such as `"Do not use non-browser loading mechanisms"` or `"Extract only the table whose"`.

- [ ] **Step 7: Run GREEN checks**

Run:

```bash
uv run pytest test/test_prompt_renderer.py test/test_workflow_contract.py test/test_codex_browser_stage.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add brand_size_chart/prompt brand_size_chart/stage test/test_prompt_renderer.py test/test_workflow_contract.py test/test_codex_browser_stage.py
git commit -m "Render stage prompts from strict templates"
```

### Task 3: Batch `table_extract` Stage And Workflow Integration

**Files:**
- Modify: `brand_size_chart/stage/table_extraction.py`
- Modify: `brand_size_chart/validator/table_extraction.py`
- Modify: `brand_size_chart/workflow/base.py`
- Modify: `brand_size_chart/workflow/source_type.py`
- Modify: `brand_size_chart/workflow/__init__.py`
- Delete: `brand_size_chart/workflow/table.py`
- Test: `test/test_codex_browser_stage.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add failing batch extraction tests**

Add tests that assert:

- `workflow_base.table_stage_run` no longer exists;
- new `workflow_base.table_extract_result_get(...)` calls the fake Codex runner once with `TableExtractionBatchResult` for two discovered tables;
- the prompt contains a numbered execplan for both `women_upper` and `women_lower`;
- `table_extract` writes one batch `result.json`;
- `chart/women_upper.json` and `chart/women_lower.json` are written from validated chart data;
- missing one discovered table fails mechanical validation and is fed back into the same `table_extract` retry loop;
- extra table fails mechanical validation.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest test/test_codex_browser_stage.py::test_table_extract_batch_calls_codex_once_for_multiple_discoveries test/test_codex_browser_stage.py::test_table_extract_batch_rejects_missing_discovery test/test_workflow_contract.py::test_workflow_has_no_per_table_child_workflow -q
```

Expected: fail because batch stage and tests do not exist.

- [ ] **Step 3: Implement `TableExtractionStage` as batch owner**

Change `TableExtractionStage` so it accepts `source_discovery_list: list[SourceDiscovery]` and returns `TableExtractionBatchResult`. Its prompt context must build a clear execplan with one item per source discovery. It must use `stage_key="table_extract"` and `prompt_name="table_extract"`.

- [ ] **Step 4: Implement batch mechanical validator**

Change `TableExtractionValidator` to validate `TableExtractionBatchResult` against the verified `source_discovery_list`. It must check exact identity matching, missing discoveries, extra extractions, chart row/measurement invariants, and normalized artifact references.

- [ ] **Step 5: Materialize generated chart files**

After a verified successful batch result, write each `TableExtraction.chart` to `ArtifactLayout.table_extract_chart_path(...)`. Validate those files exist and match the result.

- [ ] **Step 6: Replace per-table workflow integration**

In `BrandSizeChartSourceTypeWorkflow.run`, remove the loop that enqueues `brand_size_chart_table`. Call one `table_extract_write_step` after successful discovery and extend `verified_table_extraction_payload_list` with the returned batch list. Remove `workflow/table.py` and its exports.

- [ ] **Step 7: Run GREEN checks**

Run:

```bash
uv run pytest test/test_codex_browser_stage.py test/test_workflow_contract.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add brand_size_chart/stage/table_extraction.py brand_size_chart/validator/table_extraction.py brand_size_chart/workflow test/test_codex_browser_stage.py test/test_workflow_contract.py
git rm brand_size_chart/workflow/table.py
git commit -m "Batch table extraction per source type"
```

### Task 4: Rename Stage Keys And Generated Schemas

**Files:**
- Modify: `brand_size_chart/stage/*.py`
- Modify: `brand_size_chart/workflow/*.py`
- Modify: `brand_size_chart/artifact/layout.py`
- Modify: `brand_size_chart/schema/*.schema.json`
- Modify: tests under `test/`

- [ ] **Step 1: Add failing tests for canonical stage names**

Add contract tests that scan code, generated schema artifacts, prompt template names, and test fixtures for forbidden target-stage names:

```python
FORBIDDEN_STAGE_NAME_LIST = [
    "source_discovery",
    "table_extraction",
    "coverage_decision",
    "canonical_selection",
]
```

The test may allow those strings only in migration/spec documentation or in field names like `table_extraction_list`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_stage_names_use_action_verbs -q
```

Expected: fail on current stage keys and directories.

- [ ] **Step 3: Rename stage keys and layout methods**

Update:

- `source_discovery_dir` to `source_discover_dir`;
- `source_discovery_evidence_dir` to `source_discover_evidence_dir`;
- `coverage_decision_dir` to `coverage_decide_dir`;
- `canonical_selection_dir` to `canonical_select_dir`;
- old stage keys to `source_discover`, `table_extract`, `coverage_decide`, `canonical_select`.

Do not rename domain model names such as `SourceDiscovery`, `SourceDiscoveryResult`, or `table_extraction_list`.

- [ ] **Step 4: Regenerate schemas**

Run the project schema generation path used by current tests. If no script exists, run the existing test-supported model schema writer from `brand_size_chart.model.schema_registry`.

- [ ] **Step 5: Run GREEN checks**

Run:

```bash
uv run pytest -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add brand_size_chart test
git commit -m "Use action verbs for workflow stages"
```

### Task 5: End-To-End Verification And Real Defacto Smoke

**Files:**
- Modify only files required by failures from real verification.

- [ ] **Step 1: Run formatting and unit verification**

Run:

```bash
uv run black --target-version py314 --line-length 120 brand_size_chart test
uv run pytest -q
uv run python -m compileall brand_size_chart
```

Expected: all pass.

- [ ] **Step 2: Run standalone Defacto smoke with real data**

Run the current standalone workflow command for one Defacto brand, using explicit SQLite `DBOS_SYSTEM_DATABASE_URL`, no fixtures, no dry-run, and source-type scope `official_brand_size_guide`. The run must reach one `table_extract` batch stage for the source type. The exact command must use the repository's current documented local run entrypoint and `.secret` layout.

- [ ] **Step 3: Inspect output artifacts**

Verify the output directory contains:

```text
brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/source_discover/result.json
brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/source_discover/verification.json
brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/result.json
brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/verification.json
brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/chart/*.json
```

Also verify there is no per-table `size_chart/<size_group_key>/table_extraction/` audit path.

- [ ] **Step 4: Fix real-run defects with TDD**

For each real-run defect, write or update a focused failing test first, verify RED, implement the fix, verify GREEN, then rerun the Defacto smoke.

- [ ] **Step 5: Final commit**

Run:

```bash
git status --short
git add -A
git commit -m "Verify batch table extraction workflow"
```

Skip the final commit only when Step 4 produces no changes after Task 4.
