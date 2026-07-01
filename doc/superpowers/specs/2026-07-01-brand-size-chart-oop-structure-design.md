# OOP-структура `brand-size-chart`

## Цель

`brand-size-chart` должен сохранить текущее внешнее поведение `DBOS` workflow, но получить ясную объектную структуру: workflow, step, semantic stage, validator, artifact layout, Codex runner, prompt loader и schema registry должны быть отдельными владельцами с понятными обязанностями.

Рефакторинг должен быть behavior-preserving. Он не меняет смысл промтов, `DBOS` ids, `artifact` paths, `workflow.yaml`, `CLI`, source type priority/order, schema fields или browser/VPN runtime behavior.

## Текущая Проблема

Текущий `brand_size_chart/workflow.py` смешивает разные уровни ответственности:

- `DBOS` root/brand/source-type/table orchestration;
- `DBOS.step` write phases;
- semantic stage retry loop;
- prompt loading and prompt assembly;
- deterministic draft generation;
- Codex execution boundaries;
- mechanical validators;
- artifact path layout;
- result JSON writes.

`brand_size_chart/model.py` смешивает все result/data models и schema generation. `brand_size_chart/source_extractor.py` выглядит как временный draft-helper, а не как ясный extraction owner. Static prompts уже вынесены в `brand_size_chart/prompt/`, но prompt loading and assembly остаются внутри workflow implementation.

## Scope

В scope входит:

- разнести `brand_size_chart/workflow.py` на объектные владельцы;
- оформить `DBOS` workflows and steps как `@DBOS.dbos_class` instance-method classes;
- сделать базовые классы для workflow, step, semantic stage и validators;
- разнести Pydantic models по model-family модулям;
- оставить `brand_size_chart/schema/*.schema.json` generated artifacts from Pydantic models;
- выделить artifact path layout and reference validation;
- выделить Codex runner and output-schema support;
- обновить `marketplace-automation/doc/design/workflow-runtime.md`, чтобы новые workflow sources сразу следовали этому `DBOS` OOP contract.

В scope не входит:

- улучшение prompt text;
- изменение source discovery logic;
- изменение table extraction logic;
- изменение source type registry semantics;
- изменение browser/VPN runtime;
- изменение `workflow.yaml` or platform API contract.

## DBOS OOP Contract

Workflow source, который использует `DBOS`, должен оформлять workflow and step owners как `@DBOS.dbos_class` classes with instance methods.

`DBOS` instance methods должны следовать контракту:

- `self` не содержит run-specific mutable state;
- все durable input values передаются explicit method arguments;
- `self` может хранить только stateless dependencies: factories, registries, validators, artifact layout, prompt loader and Codex runner;
- decorated method является real owner boundary, а не thin wrapper around another workflow object;
- workflow method owns deterministic orchestration;
- step method owns one side-effect phase;
- external IO, filesystem writes, browser, network, Codex and secret access остаются только в `DBOS.step` methods or before root workflow start;
- method return values keep the current JSON-serializable payload contract.

Перед конвертацией основного workflow implementation нужен technical checkpoint: небольшой test/spike на текущем `DBOS` SDK должен доказать, что `@DBOS.dbos_class` instance workflow/step methods корректно регистрируются, запускаются через queue and preserve current call shape. Если текущая версия `DBOS` не поддержит этот вариант, это blocker для чистого OOP design, а не повод молча вернуть module-level wrapper functions.

## Package Structure

Целевая структура пакета:

```text
brand_size_chart/
  app/
    entrypoint.py
    runtime_config.py
  artifact/
    layout.py
    reference_validator.py
    writer.py
  codex/
    runner.py
    schema.py
  model/
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
    source_type_registry.py
  stage/
    base.py
    canonical_selection.py
    coverage_decision.py
    semantic.py
    source_discovery.py
    table_extraction.py
    workflow_run_prompt_apply.py
  validator/
    artifact.py
    base.py
    canonical_selection.py
    coverage_decision.py
    prompt_scope.py
    source_discovery.py
    table_extraction.py
  workflow/
    base.py
    brand.py
    root.py
    source_type.py
    table.py
```

`brand_size_chart/prompt/` remains static prompt storage. Prompt text improvements are intentionally deferred.

## Workflow Classes

`BaseDbosWorkflow` owns shared workflow mechanics:

- `workflow_run_id`;
- queue name;
- result root;
- browser runtime `MCP` URL;
- stable child workflow id creation;
- child workflow enqueue helpers;
- shared `ArtifactLayout`.

Concrete workflow owners:

- `BrandSizeChartRunWorkflow`: parse `brand_list`, run prompt-scope step, enqueue brand workflows, write run result.
- `BrandSizeChartBrandWorkflow`: execute source types in priority order, maintain remaining product-type coverage, run intermediate coverage decision, write brand selection.
- `BrandSizeChartSourceTypeWorkflow`: run source discovery, enqueue table workflows, write source-type summary.
- `BrandSizeChartTableWorkflow`: run table extraction for one discovered source.

Each concrete workflow class is a `@DBOS.dbos_class`. Its `run` method is a `@DBOS.workflow` instance method and receives every durable input as an explicit argument.

## Step And Stage Classes

`BaseDbosStep` owns one side-effect phase boundary. It may write artifacts, call Codex, read secrets, use browser `MCP` through Codex, and return one JSON-serializable result payload.

`SemanticStage` owns the common bounded lifecycle:

1. build deterministic draft result;
2. build prompt from static prompt, prompt scope, stage context, previous result and verification feedback;
3. run Codex;
4. write `<stage>/result.json`;
5. run semantic verification;
6. run mechanical validation;
7. write `<stage>/verification.json`;
8. retry by sending verification feedback to the same main stage until attempt limit;
9. fail after attempt limit.

Concrete semantic stages:

- `WorkflowRunPromptApplyStage`;
- `SourceDiscoveryStage`;
- `TableExtractionStage`;
- `CoverageDecisionStage`;
- `CanonicalSelectionStage`.

`SourceTypeSummaryWriteStep`, `BrandSelectionWriteStep`, and `RunResultWriteStep` are `BaseDbosStep` subclasses because they do not need the full semantic stage retry loop.

## Validators

Mechanical validators are separate from semantic verification. They must not use browser, Codex, network, filesystem discovery, or source interpretation. They only validate invariants that are already mechanically knowable.

Validator classes:

- `PromptScopeValidator`;
- `SourceDiscoveryValidator`;
- `TableExtractionValidator`;
- `CoverageDecisionValidator`;
- `CanonicalSelectionValidator`;
- `ArtifactReferenceValidator`.

Each validator exposes one public validation method and returns or raises concrete error messages suitable for stage feedback.

## Artifact Ownership

`ArtifactLayout` is the only owner of deterministic run paths:

- `brand_size_chart/brand/<parsed_brand_key>/manifest.json`;
- `brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json`;
- `brand_size_chart_audit/run/result.json`;
- `brand_size_chart_audit/brand/<parsed_brand_key>/...`;
- source-type stage directories;
- table stage directories.

`ArtifactReferenceValidator` validates relative references, missing files and outside-result-dir paths. Workflow and stage classes must call `ArtifactLayout` rather than manually concatenating audit/output paths.

## Model Ownership

Pydantic models move from one broad `model.py` into model-family modules:

- `model/base.py`: `StrictBaseModel` and shared literals/constants;
- `model/brand.py`: `BrandInput`, `BrandListParseWarning`, `BrandListParseResult`, `BrandResult`;
- `model/chart.py`: `BrandSizeChart`, rows and measurements;
- `model/prompt.py`: `PromptScope`, `PromptStageInstruction`;
- `model/run.py`: `RunResult`;
- `model/selection.py`: coverage and canonical-selection models;
- `model/source.py`: source discovery, source type summary and table extraction models;
- `model/stage.py`: `StageVerification`;
- `model/schema_registry.py`: generated schema registry and writer.

Public import compatibility must be preserved only through the package's intended public model surface. Refactor-only compatibility wrappers are forbidden.

## Codex Boundary

`CodexStageRunner` owns:

- `codex exec` command construction;
- output schema writing;
- browser `MCP` config args;
- approved tool list;
- diagnostics paths;
- inactivity timeout and process termination behavior;
- JSON output validation through Pydantic model class.

No workflow or stage class may build raw `codex exec` command arguments directly.

## Marketplace Automation Design Update

Implementation must update `marketplace-automation/doc/design/workflow-runtime.md` with the generic `DBOS` OOP workflow-source contract:

- workflow sources must use `@DBOS.dbos_class` instance-method classes for `DBOS` workflows and steps;
- instances must be stateless and receive durable run data through explicit method arguments;
- platform runtime, DBOS workflow layer, DBOS step layer, semantic stage layer, validator layer and artifact layer must stay separate;
- browser/VPN runtime remains a platform capability received as `MCP` URL;
- workflow source owns only stage meaning, prompts, result schemas, validators and artifact interpretation.

This update is part of the same implementation scope because it prevents future workflow projects from recreating the current procedural structure.

## Migration Plan

Implementation must be staged:

1. Add `DBOS.dbos_class` instance-method checkpoint test.
2. Move entrypoint runtime config into `app/` without behavior change.
3. Split model modules and schema registry.
4. Extract artifact layout, writer and reference validator.
5. Extract Codex runner.
6. Extract stage validators.
7. Implement `SemanticStage` and move concrete semantic stages.
8. Convert DBOS steps into `@DBOS.dbos_class` instance-method step classes.
9. Convert DBOS workflows into `@DBOS.dbos_class` instance-method workflow classes.
10. Update imports and tests.
11. Update `marketplace-automation/doc/design/workflow-runtime.md`.
12. Run full verification.

## Verification

Required verification after implementation:

- formatting for changed Python files;
- full project tests in `brand-size-chart`;
- direct `brand-size-chart-run --help`;
- real workflow run that loads `Defacto` size charts across every supported source type, without fixtures or dry-run mode, using explicit SQLite `DBOS_SYSTEM_DATABASE_URL` and the current browser runtime contract;
- focused check that current artifact paths and schema outputs are unchanged;
- semantic reread of `marketplace-automation/doc/design/workflow-runtime.md`.

## Success Criteria

Success means:

- `brand_size_chart/workflow.py` no longer owns all behavior;
- every DBOS workflow and step is represented by a class owner;
- common stage retry/verification lifecycle exists in one `SemanticStage` implementation;
- mechanical validation is separated from semantic verification;
- artifact layout is centralized;
- generated schema ownership remains Pydantic-based;
- existing behavior and external contracts remain compatible;
- `marketplace-automation` has the generic design contract for future workflow sources.
