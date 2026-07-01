# Brand Size Chart OOP Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `brand-size-chart` into behavior-preserving classical OOP owners for DBOS workflows, DBOS steps, semantic stages, validators, artifacts, Codex execution, and schema models.

**Architecture:** The refactor keeps the public workflow behavior unchanged while replacing broad procedural modules with package-owned classes. DBOS workflow and step entrypoints become `@DBOS.dbos_class` instance-method classes with stateless instances and explicit durable arguments. Artifact paths, Codex execution, Pydantic schema generation, mechanical validation, semantic stage retry loops, and workflow orchestration each get one canonical owner.

**Tech Stack:** Python 3.14, DBOS Python SDK, Pydantic v2, pytest, Black, Codex CLI, Playwright MCP via external browser runtime.

---

## Рабочие Деревья

- Основная реализация: `/home/andrey/Projects/brand-size-chart/.worktrees/oop-workflow-structure`.
- Design update для platform runtime: `/home/andrey/Projects/marketplace-automation/.worktrees/workflow-runtime-oop-contract`.
- Не редактировать `/home/andrey/Projects/marketplace-automation/.worktrees/brand-size-chart-workflow-platform`: это отдельное dirty worktree.

## Важные Ограничения

- Рефакторинг не меняет смысл prompt text, `DBOS` identifiers, artifact paths, schema fields, CLI arguments, source type order, source type priority, browser/VPN runtime behavior, `workflow.yaml`, or platform API contract.
- `brand_size_chart/model.py` заменяется пакетом `brand_size_chart/model/`; одновременно файл и пакет с одним именем невозможны.
- `brand_size_chart/workflow.py` заменяется пакетом `brand_size_chart/workflow/`; одновременно файл и пакет с одним именем невозможны.
- Импорты вида `from brand_size_chart.model import BrandInput` и `from brand_size_chart.workflow import ...` должны остаться рабочими через package `__init__.py`.
- Compatibility files may remain only when their names do not conflict with target packages: `brand_size_chart/entrypoint.py`, `brand_size_chart/source_type.py`, `brand_size_chart/codex_stage.py`, and `brand_size_chart/io.py`.

## Итоговая Структура

```text
brand_size_chart/
  app/
    __init__.py
    entrypoint.py
    runtime_config.py
  artifact/
    __init__.py
    layout.py
    reference_validator.py
    writer.py
  codex/
    __init__.py
    runner.py
    schema.py
  model/
    __init__.py
    base.py
    brand.py
    chart.py
    prompt.py
    run.py
    schema_registry.py
    selection.py
    source.py
    stage.py
  prompt/
    apply.md
    discovery.md
    extraction.md
    selection.md
    size_group_key.md
    verification.md
  source/
    __init__.py
    source_type_registry.py
  stage/
    __init__.py
    base.py
    canonical_selection.py
    coverage_decision.py
    semantic.py
    source_discovery.py
    table_extraction.py
    workflow_run_prompt_apply.py
  validator/
    __init__.py
    artifact.py
    base.py
    canonical_selection.py
    coverage_decision.py
    prompt_scope.py
    source_discovery.py
    table_extraction.py
  workflow/
    __init__.py
    base.py
    brand.py
    root.py
    source_type.py
    table.py
```

## Task 1: DBOS Instance-Method Checkpoint

**Files:**
- Create: `test/test_dbos_class_method_contract.py`

- [ ] **Step 1: Add a minimal class-method DBOS registration test**

Create `test/test_dbos_class_method_contract.py`:

```python
"""Tests for DBOS class-method workflow and step ownership."""

import inspect

from dbos import DBOS


def test_dbos_class_method_workflow_and_step_are_registered() -> None:
    """Verify the current DBOS SDK supports class-owned workflow and step methods."""

    @DBOS.dbos_class("ExampleWorkflowOwner")
    class ExampleWorkflowOwner:
        """Minimal DBOS class owner used only for registration verification."""

        @DBOS.workflow(name="example_oop_workflow")
        def run(self, value: str) -> str:
            """Return a deterministic workflow value.

            Args:
                value: Durable workflow input.

            Returns:
                Deterministic output.
            """
            return f"workflow:{value}"

        @DBOS.step(name="example_oop_step")
        def step_run(self, value: str) -> str:
            """Return a deterministic step value.

            Args:
                value: Durable step input.

            Returns:
                Deterministic output.
            """
            return f"step:{value}"

    owner = ExampleWorkflowOwner()

    assert inspect.ismethod(owner.run)
    assert inspect.ismethod(owner.step_run)
    assert getattr(owner.run, "dbos_function_name") == "example_oop_workflow"
    assert getattr(owner.step_run, "dbos_function_name") == "example_oop_step"
    assert owner.run.dbos_func_decorator_info.func_type.name == "Instance"
    assert owner.step_run.dbos_func_decorator_info.func_type.name == "Instance"
    assert owner.run.dbos_func_decorator_info.class_info.registered_name == "ExampleWorkflowOwner"
    assert owner.step_run.dbos_func_decorator_info.class_info.registered_name == "ExampleWorkflowOwner"
```

- [ ] **Step 2: Run the checkpoint**

Run:

```bash
uv run pytest test/test_dbos_class_method_contract.py -q
```

Expected: PASS. The test must not directly invoke decorated workflow or step methods before `DBOS.launch()`, because DBOS correctly rejects workflow execution before initialization. If the decorator metadata does not show instance-method registration, stop and report the blocker; do not introduce module-level wrappers.

- [ ] **Step 3: Commit**

Run:

```bash
git add test/test_dbos_class_method_contract.py
git commit -m "Verify DBOS class method workflow support"
```

## Task 2: Split Pydantic Models Into `brand_size_chart/model/`

**Files:**
- Delete: `brand_size_chart/model.py`
- Create: `brand_size_chart/model/__init__.py`
- Create: `brand_size_chart/model/base.py`
- Create: `brand_size_chart/model/brand.py`
- Create: `brand_size_chart/model/chart.py`
- Create: `brand_size_chart/model/prompt.py`
- Create: `brand_size_chart/model/run.py`
- Create: `brand_size_chart/model/schema_registry.py`
- Create: `brand_size_chart/model/selection.py`
- Create: `brand_size_chart/model/source.py`
- Create: `brand_size_chart/model/stage.py`
- Modify: model import call sites only when needed
- Test: `test/test_models.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add model ownership tests**

Add to `test/test_models.py`:

```python
def test_model_package_exports_existing_public_models() -> None:
    """Keep public model imports stable while moving model owners into the package."""
    from brand_size_chart.model import BrandInput
    from brand_size_chart.model import BrandSizeChart
    from brand_size_chart.model import PromptScope
    from brand_size_chart.model import SourceDiscoveryResult
    from brand_size_chart.model import TableExtraction

    assert BrandInput.__module__ == "brand_size_chart.model.brand"
    assert BrandSizeChart.__module__ == "brand_size_chart.model.chart"
    assert PromptScope.__module__ == "brand_size_chart.model.prompt"
    assert SourceDiscoveryResult.__module__ == "brand_size_chart.model.source"
    assert TableExtraction.__module__ == "brand_size_chart.model.source"
```

Add to `test/test_workflow_contract.py`:

```python
def test_model_is_package_not_monolithic_module() -> None:
    """Replace the broad model module with focused model package modules."""
    assert Path("brand_size_chart/model.py").exists() is False
    assert Path("brand_size_chart/model/__init__.py").exists()
    assert Path("brand_size_chart/model/schema_registry.py").exists()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest test/test_models.py::test_model_package_exports_existing_public_models test/test_workflow_contract.py::test_model_is_package_not_monolithic_module -q
```

Expected: FAIL because models still live in `brand_size_chart/model.py`.

- [ ] **Step 3: Move definitions without changing fields**

Move existing definitions exactly by owner:

- `StrictBaseModel`, `ApplicabilityStatus`, `StageStatus`, `COUNTRY_CODE_PATTERN`, `SOURCE_COUNTRY_CODE_SPECIAL_SET`, `APPLICABILITY_STATUS_CANONICAL_SET` to `brand_size_chart/model/base.py`.
- `BrandInput`, `BrandListParseWarning`, `BrandListParseResult`, `BrandResult` to `brand_size_chart/model/brand.py`.
- `BrandSizeChartMeasurement`, `BrandSizeChartRow`, `BrandSizeChart` to `brand_size_chart/model/chart.py`.
- `PromptStageInstruction`, `PromptScope` to `brand_size_chart/model/prompt.py`.
- `RunResult` to `brand_size_chart/model/run.py`.
- `CoverageDecision`, `CoverageDecisionResult`, `CanonicalSelection`, `CanonicalSelectionResult` to `brand_size_chart/model/selection.py`.
- `SourceDiscovery`, `SourceDiscoveryResult`, `SourceTypeSummary`, `TableExtraction` to `brand_size_chart/model/source.py`.
- `StageVerification` to `brand_size_chart/model/stage.py`.
- `schema_file_write()` and `schema_model_map_get()` to `brand_size_chart/model/schema_registry.py`.

`brand_size_chart/model/__init__.py` must import and expose every public name previously imported from `brand_size_chart.model`.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest test/test_models.py test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add brand_size_chart/model test/test_models.py test/test_workflow_contract.py
git add -u brand_size_chart/model.py
git commit -m "Split workflow result models by owner"
```

## Task 3: Extract Artifact Layout, Writer, And Reference Validation

**Files:**
- Create: `brand_size_chart/artifact/__init__.py`
- Create: `brand_size_chart/artifact/layout.py`
- Create: `brand_size_chart/artifact/reference_validator.py`
- Create: `brand_size_chart/artifact/writer.py`
- Modify: `brand_size_chart/io.py`
- Modify: current workflow implementation
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add artifact ownership tests**

Add to `test/test_workflow_contract.py`:

```python
def test_artifact_layout_owns_current_paths(tmp_path: Path) -> None:
    """Centralize deterministic artifact paths in ArtifactLayout."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.model import BrandInput

    layout = ArtifactLayout(result_dir=tmp_path)
    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )

    assert layout.brand_output_dir(brand_input).relative_to(tmp_path).as_posix() == "brand_size_chart/brand/defacto"
    assert (
        layout.brand_audit_dir(brand_input).relative_to(tmp_path).as_posix()
        == "brand_size_chart_audit/brand/defacto"
    )
    assert (
        layout.table_extraction_dir(brand_input, "official_brand_size_guide", "women_upper")
        .relative_to(tmp_path)
        .as_posix()
        == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/size_chart/women_upper/table_extraction"
    )
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_artifact_layout_owns_current_paths -q
```

Expected: FAIL because `ArtifactLayout` does not exist.

- [ ] **Step 3: Implement artifact owners**

Create `ArtifactLayout` with methods for all existing output and audit paths. Move JSON writing from `brand_size_chart/io.py` into `brand_size_chart/artifact/writer.py`. Move artifact reference validation into `ArtifactReferenceValidator`.

- [ ] **Step 4: Replace inline artifact path construction**

Update workflow code to use `ArtifactLayout`, `JsonArtifactWriter`, and `ArtifactReferenceValidator`. Keep exact current paths.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add brand_size_chart/artifact brand_size_chart/io.py test/test_workflow_contract.py
git add -u brand_size_chart
git commit -m "Extract artifact layout ownership"
```

## Task 4: Extract Codex Runner And Schema Helpers

**Files:**
- Create: `brand_size_chart/codex/__init__.py`
- Create: `brand_size_chart/codex/runner.py`
- Create: `brand_size_chart/codex/schema.py`
- Modify: `brand_size_chart/codex_stage.py`
- Modify: current workflow implementation
- Test: `test/test_codex_browser_stage.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add Codex ownership test**

Add to `test/test_workflow_contract.py`:

```python
def test_codex_stage_py_is_compatibility_surface_only() -> None:
    """Move Codex subprocess mechanics into the codex package."""
    codex_stage_source = Path("brand_size_chart/codex_stage.py").read_text(encoding="utf-8")

    assert "subprocess.Popen" not in codex_stage_source
    assert "class CodexStageRunner" not in codex_stage_source
    assert "from brand_size_chart.codex.runner import" in codex_stage_source
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_codex_stage_py_is_compatibility_surface_only -q
```

Expected: FAIL because `codex_stage.py` still owns subprocess mechanics.

- [ ] **Step 3: Move Codex execution**

Create `CodexStageRunner` in `brand_size_chart/codex/runner.py`. Move process execution, browser MCP config generation, command construction, diagnostics, timeout handling, and JSON output parsing there. Keep a public `codex_stage_run(...)` function in `runner.py` for current call sites.

- [ ] **Step 4: Move schema helpers**

Move strict schema normalization helpers into `brand_size_chart/codex/schema.py` and import them from the runner.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest test/test_codex_browser_stage.py test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add brand_size_chart/codex brand_size_chart/codex_stage.py test/test_codex_browser_stage.py test/test_workflow_contract.py
git add -u brand_size_chart
git commit -m "Extract Codex stage runner"
```

## Task 5: Extract Mechanical Validators

**Files:**
- Create: `brand_size_chart/validator/__init__.py`
- Create: `brand_size_chart/validator/artifact.py`
- Create: `brand_size_chart/validator/base.py`
- Create: `brand_size_chart/validator/canonical_selection.py`
- Create: `brand_size_chart/validator/coverage_decision.py`
- Create: `brand_size_chart/validator/prompt_scope.py`
- Create: `brand_size_chart/validator/source_discovery.py`
- Create: `brand_size_chart/validator/table_extraction.py`
- Modify: current workflow implementation
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add validator ownership tests**

Add to `test/test_workflow_contract.py`:

```python
def test_stage_validators_live_under_validator_package() -> None:
    """Keep mechanical validation outside workflow orchestration."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator
    from brand_size_chart.validator.coverage_decision import CoverageDecisionValidator
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    assert PromptScopeValidator.__name__ == "PromptScopeValidator"
    assert SourceDiscoveryValidator.__name__ == "SourceDiscoveryValidator"
    assert TableExtractionValidator.__name__ == "TableExtractionValidator"
    assert CoverageDecisionValidator.__name__ == "CoverageDecisionValidator"
    assert CanonicalSelectionValidator.__name__ == "CanonicalSelectionValidator"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_stage_validators_live_under_validator_package -q
```

Expected: FAIL because validators do not exist.

- [ ] **Step 3: Move validators**

Move current mechanical validation functions into validator classes. Validators must not call Codex, browser, network, or discovery. They may read already-built objects and known artifact paths only when those paths are explicit inputs.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add brand_size_chart/validator test/test_workflow_contract.py
git add -u brand_size_chart
git commit -m "Extract mechanical stage validators"
```

## Task 6: Extract Source Registry

**Files:**
- Create: `brand_size_chart/source/__init__.py`
- Create: `brand_size_chart/source/source_type_registry.py`
- Modify: `brand_size_chart/source_type.py`
- Modify: current workflow implementation
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add source registry ownership test**

Add to `test/test_workflow_contract.py`:

```python
def test_source_type_py_is_compatibility_surface_only() -> None:
    """Move source type registry ownership into source package."""
    source_type_source = Path("brand_size_chart/source_type.py").read_text(encoding="utf-8")

    assert "SOURCE_TYPE_LIST" not in source_type_source
    assert "from brand_size_chart.source.source_type_registry import" in source_type_source
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_source_type_py_is_compatibility_surface_only -q
```

Expected: FAIL because `source_type.py` still owns registry data.

- [ ] **Step 3: Move registry**

Move source type constants, priority, and lookup behavior into `SourceTypeRegistry` in `brand_size_chart/source/source_type_registry.py`. Keep source type order and priority unchanged. `brand_size_chart/source_type.py` must import and re-export the public names only.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add brand_size_chart/source brand_size_chart/source_type.py test/test_workflow_contract.py
git add -u brand_size_chart
git commit -m "Extract source type registry"
```

## Task 7: Extract Semantic Stage Classes

**Files:**
- Create: `brand_size_chart/stage/__init__.py`
- Create: `brand_size_chart/stage/base.py`
- Create: `brand_size_chart/stage/canonical_selection.py`
- Create: `brand_size_chart/stage/coverage_decision.py`
- Create: `brand_size_chart/stage/semantic.py`
- Create: `brand_size_chart/stage/source_discovery.py`
- Create: `brand_size_chart/stage/table_extraction.py`
- Create: `brand_size_chart/stage/workflow_run_prompt_apply.py`
- Modify: current workflow implementation
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add stage ownership tests**

Add to `test/test_workflow_contract.py`:

```python
def test_semantic_stages_live_under_stage_package() -> None:
    """Keep semantic stage lifecycle outside DBOS workflow orchestration."""
    from brand_size_chart.stage.canonical_selection import CanonicalSelectionStage
    from brand_size_chart.stage.coverage_decision import CoverageDecisionStage
    from brand_size_chart.stage.source_discovery import SourceDiscoveryStage
    from brand_size_chart.stage.table_extraction import TableExtractionStage
    from brand_size_chart.stage.workflow_run_prompt_apply import WorkflowRunPromptApplyStage

    assert WorkflowRunPromptApplyStage.__name__ == "WorkflowRunPromptApplyStage"
    assert SourceDiscoveryStage.__name__ == "SourceDiscoveryStage"
    assert TableExtractionStage.__name__ == "TableExtractionStage"
    assert CoverageDecisionStage.__name__ == "CoverageDecisionStage"
    assert CanonicalSelectionStage.__name__ == "CanonicalSelectionStage"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_semantic_stages_live_under_stage_package -q
```

Expected: FAIL because stage classes do not exist.

- [ ] **Step 3: Implement `SemanticStage`**

Create `SemanticStage` to own the current common stage loop: deterministic draft, prompt assembly, Codex call, `result.json`, verification, mechanical validation, retry with verification feedback, and terminal failure after attempt limit.

- [ ] **Step 4: Move concrete stages**

Move current stage-specific prompt assembly, deterministic drafts, model classes, validators, and result writes into `WorkflowRunPromptApplyStage`, `SourceDiscoveryStage`, `TableExtractionStage`, `CoverageDecisionStage`, and `CanonicalSelectionStage`.

- [ ] **Step 5: Verify**

Run:

```bash
uv run pytest test/test_workflow_contract.py test/test_codex_browser_stage.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add brand_size_chart/stage test/test_workflow_contract.py
git add -u brand_size_chart
git commit -m "Extract semantic stage owners"
```

## Task 8: Replace `brand_size_chart/workflow.py` With DBOS Workflow Package

**Files:**
- Delete: `brand_size_chart/workflow.py`
- Create: `brand_size_chart/workflow/__init__.py`
- Create: `brand_size_chart/workflow/base.py`
- Create: `brand_size_chart/workflow/brand.py`
- Create: `brand_size_chart/workflow/root.py`
- Create: `brand_size_chart/workflow/source_type.py`
- Create: `brand_size_chart/workflow/table.py`
- Modify: `brand_size_chart/entrypoint.py`
- Test: `test/test_entrypoint.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add workflow ownership tests**

Add to `test/test_workflow_contract.py`:

```python
def test_workflow_is_package_not_monolithic_module() -> None:
    """Replace the broad workflow module with workflow owner package modules."""
    assert Path("brand_size_chart/workflow.py").exists() is False
    assert Path("brand_size_chart/workflow/__init__.py").exists()
    assert Path("brand_size_chart/workflow/root.py").exists()


def test_dbos_workflow_classes_are_class_owned() -> None:
    """Ensure DBOS workflows are owned by class instance methods."""
    from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow
    from brand_size_chart.workflow.root import BrandSizeChartRunWorkflow
    from brand_size_chart.workflow.source_type import BrandSizeChartSourceTypeWorkflow
    from brand_size_chart.workflow.table import BrandSizeChartTableWorkflow

    assert BrandSizeChartRunWorkflow.__name__ == "BrandSizeChartRunWorkflow"
    assert BrandSizeChartBrandWorkflow.__name__ == "BrandSizeChartBrandWorkflow"
    assert BrandSizeChartSourceTypeWorkflow.__name__ == "BrandSizeChartSourceTypeWorkflow"
    assert BrandSizeChartTableWorkflow.__name__ == "BrandSizeChartTableWorkflow"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_workflow_is_package_not_monolithic_module test/test_workflow_contract.py::test_dbos_workflow_classes_are_class_owned -q
```

Expected: FAIL because `workflow.py` still exists.

- [ ] **Step 3: Implement workflow classes**

Create these `@DBOS.dbos_class` owners:

- `BrandSizeChartRunWorkflow` in `workflow/root.py`.
- `BrandSizeChartBrandWorkflow` in `workflow/brand.py`.
- `BrandSizeChartSourceTypeWorkflow` in `workflow/source_type.py`.
- `BrandSizeChartTableWorkflow` in `workflow/table.py`.

Each `run` method is an instance method decorated by `@DBOS.workflow(...)`. `self` stores only stateless services. All run-specific values are explicit method arguments.

- [ ] **Step 4: Implement DBOS step class owners**

Move DBOS step functions into class-owned step methods in the workflow or stage owner that owns the side effect. The decorated method must own a real side-effect phase and must not be a thin wrapper around another DBOS function.

- [ ] **Step 5: Preserve public workflow imports**

`brand_size_chart/workflow/__init__.py` must expose the public names currently used by entrypoint and tests, including the root workflow start callable or class.

- [ ] **Step 6: Verify**

Run:

```bash
uv run pytest test/test_entrypoint.py test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add brand_size_chart/workflow test/test_entrypoint.py test/test_workflow_contract.py
git add -u brand_size_chart/workflow.py brand_size_chart/entrypoint.py brand_size_chart
git commit -m "Convert DBOS workflows to class owners"
```

## Task 9: Move Entrypoint Runtime Config Into `app/`

**Files:**
- Create: `brand_size_chart/app/__init__.py`
- Create: `brand_size_chart/app/entrypoint.py`
- Create: `brand_size_chart/app/runtime_config.py`
- Modify: `brand_size_chart/entrypoint.py`
- Test: `test/test_entrypoint.py`
- Test: `test/test_workflow_contract.py`

- [ ] **Step 1: Add app ownership test**

Add to `test/test_workflow_contract.py`:

```python
def test_entrypoint_py_is_compatibility_surface_only() -> None:
    """Move runtime config and launch ownership into app package."""
    entrypoint_source = Path("brand_size_chart/entrypoint.py").read_text(encoding="utf-8")

    assert "from brand_size_chart.app.entrypoint import main" in entrypoint_source
    assert "DBOS.launch" not in entrypoint_source
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest test/test_workflow_contract.py::test_entrypoint_py_is_compatibility_surface_only -q
```

Expected: FAIL because `entrypoint.py` still owns launch logic.

- [ ] **Step 3: Move entrypoint code**

Move CLI/runtime config objects and `main()` implementation into `brand_size_chart/app/entrypoint.py` and `brand_size_chart/app/runtime_config.py`. Keep `brand_size_chart/entrypoint.py` as import surface:

```python
"""Compatibility import surface for application entrypoint."""

from brand_size_chart.app.entrypoint import main

__all__ = ["main"]
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest test/test_entrypoint.py test/test_workflow_contract.py -q
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add brand_size_chart/app brand_size_chart/entrypoint.py test/test_entrypoint.py test/test_workflow_contract.py
git commit -m "Move runtime entrypoint ownership into app package"
```

## Task 10: Update `marketplace-automation` Workflow Runtime Design

**Files:**
- Modify: `/home/andrey/Projects/marketplace-automation/.worktrees/workflow-runtime-oop-contract/doc/design/workflow-runtime.md`

- [ ] **Step 1: Add the generic DBOS OOP workflow-source contract**

In `doc/design/workflow-runtime.md`, add a section named `## Структура DBOS Workflow Source` with these rules:

```md
## Структура DBOS Workflow Source
`Workflow Source`, который использует `DBOS`, должен оформлять `workflow` и `step` владельцев как `@DBOS.dbos_class` классы с instance-method методами.

Экземпляры таких классов должны быть stateless. Все durable данные запуска должны передаваться явными аргументами `DBOS` метода. `self` может хранить только stateless dependencies: factories, registries, validators, artifact layout, prompt loader, `Codex` runner и другие неизменяемые сервисы без run-specific mutable state.

`DBOS` workflow method владеет deterministic orchestration. `DBOS` step method владеет одной side-effect phase. Browser, network, filesystem writes, `Codex`, secret access и другие external IO должны выполняться только внутри `DBOS` steps или до старта root workflow.

`Workflow Source` должен разделять platform runtime contract, `DBOS` workflow layer, `DBOS` step layer, semantic stage layer, validator layer и artifact layer. Platform владеет запуском контейнера, `DataSource`, `DataContainer` и runtime capability. `Workflow Source` владеет смыслом своих шагов, prompts, result schemas, validators, artifact paths и интерпретацией данных.
```

- [ ] **Step 2: Verify design text**

Run:

```bash
rg -n "Структура DBOS Workflow Source|@DBOS.dbos_class|stateless dependencies|semantic stage layer" doc/design/workflow-runtime.md
```

Expected: all four patterns are present.

- [ ] **Step 3: Commit in `marketplace-automation` worktree**

Run in `/home/andrey/Projects/marketplace-automation/.worktrees/workflow-runtime-oop-contract`:

```bash
git add doc/design/workflow-runtime.md
git commit -m "Document DBOS workflow source OOP contract"
```

## Task 11: Full Mechanical Verification

**Files:**
- Modify only files needed to fix verification fallout.

- [ ] **Step 1: Format changed Python code**

Run:

```bash
uv run black --target-version py314 --line-length 120 brand_size_chart test
```

Expected: exits 0.

- [ ] **Step 2: Run compile and tests**

Run:

```bash
uv run python -m compileall brand_size_chart
uv run pytest -q
```

Expected: compile succeeds and all tests pass.

- [ ] **Step 3: Inspect compatibility surfaces**

Run:

```bash
rg -n "subprocess.Popen|DBOS.launch|class .*Workflow|def _.*validate|result_dir /" brand_size_chart/entrypoint.py brand_size_chart/codex_stage.py brand_size_chart/source_type.py brand_size_chart/io.py brand_size_chart/workflow brand_size_chart/stage brand_size_chart/validator
```

Expected: no forbidden ownership remains in compatibility files; matches inside owner packages are expected only for the owner that owns that behavior.

- [ ] **Step 4: Commit fallout fixes**

If Step 1 or Step 2 changed files, commit them:

```bash
git add brand_size_chart test
git commit -m "Verify OOP workflow structure"
```

If no files changed, do not create an empty commit.

## Task 12: Real Defacto Verification Across All Source Types

**Files:**
- Create or update transient files only under `tmp/` and output files only under `out/`.

- [ ] **Step 1: Prepare real verification inputs**

Create `tmp/brand_list_defacto_all_source_types.txt`:

```text
Defacto
```

Create `tmp/prompt_defacto_all_source_types.txt`:

```text
Use every supported source type. Load real Defacto size charts without fixtures or dry-run paths. Prefer Turkey official data when present; when Turkey data is absent, use the existing locale applicability rules from the workflow prompts. Include all product types found by each source type according to the current workflow contract.
```

- [ ] **Step 2: Start browser runtime if needed**

Run in `/home/andrey/Projects/brand-size-chart/.worktrees/oop-workflow-structure` through the project-local standalone compose profile:

```bash
HOST_UID="$(id -u)" \
HOST_GID="$(id -g)" \
BROWSER_VPN_RUNTIME_CONTEXT="/home/andrey/Projects/browser-vpn-runtime" \
WORKFLOW_RUN_ID="defacto-all-source-types-oop-verify" \
BRAND_LIST="./tmp/brand_list_defacto_all_source_types.txt" \
OUTPUT_DIR="./out/defacto-all-source-types-oop-verify" \
WORKFLOW_RUN_PROMPT="$(cat tmp/prompt_defacto_all_source_types.txt)" \
docker compose --profile vpn up --build --abort-on-container-exit --exit-code-from workflow
```

Expected: `openvpn`, `playwright-mcp`, and `workflow` run in the same compose project; `workflow` receives `BROWSER_RUNTIME_MCP_URL=http://openvpn:8931/mcp` from `compose.yaml`; command exits 0.

- [ ] **Step 3: Inspect real output**

Run in `/home/andrey/Projects/brand-size-chart/.worktrees/oop-workflow-structure`:

```bash
find out/defacto-all-source-types-oop-verify -path '*result.json' -o -path '*source_type_summary.json' | sort
rg -n '"state": "failed"|"state": "blocked"|"status": "failed"|"status": "blocked"' out/defacto-all-source-types-oop-verify
find out/defacto-all-source-types-oop-verify/brand_size_chart/brand -name '*.json' | sort
```

Expected: source type summaries and final brand outputs are present. Any failed or blocked source type is a real defect unless the artifact contains a verified external blocker that is consistent with the current specification.

- [ ] **Step 4: Commit verification-required code fixes**

If the real run exposes code defects, fix them, rerun Task 11 and Task 12, then commit:

```bash
git add brand_size_chart test
git commit -m "Fix real Defacto workflow verification"
```

Do not commit `tmp/` or `out/` artifacts.

## Task 13: Final Cross-Repository Review And Push

**Files:**
- No planned code files; review and repository state only.

- [ ] **Step 1: Review brand-size-chart branch**

Run:

```bash
git status --short --branch
git log --oneline --decorate -n 12
uv run pytest -q
```

Expected: branch is clean except ignored runtime artifacts; tests pass.

- [ ] **Step 2: Review marketplace-automation branch**

Run in `/home/andrey/Projects/marketplace-automation/.worktrees/workflow-runtime-oop-contract`:

```bash
git status --short --branch
git log --oneline --decorate -n 5
```

Expected: branch is clean after its design commit.

- [ ] **Step 3: Push both implementation branches**

Run:

```bash
git push origin oop-workflow-structure
```

Run in `/home/andrey/Projects/marketplace-automation/.worktrees/workflow-runtime-oop-contract`:

```bash
git push origin workflow-runtime-oop-contract
```

Expected: both pushes succeed.
