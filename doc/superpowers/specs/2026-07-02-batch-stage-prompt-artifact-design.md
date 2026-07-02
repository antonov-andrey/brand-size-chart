# Batch `table_extract`, Prompt Templates, And Artifact References

## Цель

`brand-size-chart` должен ускорить загрузку таблиц размеров и сделать Codex-backed workflow прозрачнее. `source_discover` продолжает находить и верифицировать список таблиц по одному `source_type`, но следующий `table_extract` stage должен обрабатывать весь список таблиц за один Codex-запуск, а не запускать отдельный child workflow на каждую таблицу. Одновременно prompt-ы должны стать полными шаблонами в отдельных файлах, а работа с artifact references должна стать общей механикой, не привязанной к browser или Playwright `MCP`.

## Scope

В scope входит:

- заменить per-table `BrandSizeChartTableWorkflow` на batch `table_extract` step внутри `BrandSizeChartSourceTypeWorkflow`;
- ввести stage naming contract `{object}_{action}` и `{object}_{action}_verify`;
- переименовать semantic stages с существительных на действия: `source_discover`, `table_extract`, `coverage_decide`, `canonical_select`;
- ввести `TableExtractionBatchResult`, который содержит один `TableExtraction` на каждый verified `SourceDiscovery`;
- хранить batch audit в одном action stage directory на `source_type`;
- заменить prompt assembly из Python multiline strings на полные Jinja2 templates;
- оставить JSON-output validation на границе `CodexStageRunner`;
- ввести generic artifact materialization для references на внешние run-owned artifacts;
- обновить `doc/design/brand-size-chart.md`;
- обновить общий workflow-container contract в `marketplace-automation/doc/design/workflow-runtime.md`.

В scope не входит:

- изменение source type priority;
- изменение browser/VPN runtime;
- изменение marketplace source policy;
- изменение size-group semantics за пределами уже утвержденного `size_group_key` contract;
- подключение новых source types;
- production run на реальных брендах.

## Stage Naming Contract

Каждый Codex-backed action stage использует имя `{object}_{action}`. `{action}` должен быть глаголом. Verification stage использует имя action stage плюс `_verify`.

Canonical stage keys:

- `workflow_run_prompt_apply`;
- `workflow_run_prompt_apply_verify`;
- `source_discover`;
- `source_discover_verify`;
- `table_extract`;
- `table_extract_verify`;
- `coverage_decide`;
- `coverage_decide_verify`;
- `canonical_select`;
- `canonical_select_verify`.

`stage_key`, top-level prompt template name, diagnostics stage name and action stage directory segment must use the same action stage name. Verification does not get a separate artifact directory: verification writes `verification.json` inside the action stage directory.

## Batch Table Extraction

`source_discover` remains one bounded stage per `(brand, source_type)`. It returns verified `discovered_source_list`, where every item represents one concrete size chart table.

`BrandSizeChartSourceTypeWorkflow` must not enqueue one workflow per discovered table. It runs one `table_extract` DBOS step after successful discovery. That step receives:

- `BrandInput`;
- `PromptScope`;
- `source_type`;
- verified `SourceDiscoveryResult`;
- result root;
- run-level browser runtime `MCP` URL;
- secret path.

`table_extract` builds one ordered execplan from `discovered_source_list`. The plan contains one numbered item per discovered table with `size_group_key`, `source_type`, `source_url`, `source_title`, `country_code_list`, `product_type_hint_list`, and evidence references. The prompt instructs Codex to process those plan items sequentially in one stage and to preserve already-correct plan items on retry unless verification feedback names a concrete error.

The stage returns `TableExtractionBatchResult`:

- `status`;
- `message`;
- `source_type`;
- `table_extraction_list`;
- `error_list`.

`table_extraction_list` must contain exactly one `TableExtraction` per verified `SourceDiscovery` when `status="success"`. If one table cannot be extracted, the batch result is failed or verification fails, and feedback returns to the same `table_extract` action stage. Separate fix stages are forbidden.

## Batch Artifact Layout

Batch table extraction writes one stage directory per source type:

```text
brand_size_chart_audit/brand/<parsed_brand_key>/source_type/<source_type>/table_extract/
  result.json
  verification.json
  diagnostics/
  chart/
    <size_group_key>.json
```

`result.json` is the canonical batch result. `chart/<size_group_key>.json` files are deterministic generated artifacts materialized from validated `TableExtraction.chart` values. Final canonical brand output under `brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json` is still written by brand-level canonical selection.

The old per-table audit path `source_type/<source_type>/size_chart/<size_group_key>/table_extraction/` is removed. No compatibility layer is kept.

## Prompt Template Contract

Prompt rendering uses Jinja2 with strict undefined handling. A missing template variable must fail before Codex starts.

Every Codex-backed stage prompt is one complete template file under `brand_size_chart/prompt/template/`:

```text
brand_size_chart/prompt/template/
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
  partial/
    artifact_reference_contract.md.j2
    runtime_source_access.md.j2
    size_group_key_contract.md.j2
    stage_retry_context.md.j2
```

Each top-level template must include the whole prompt for that stage:

- stage role;
- stage inputs;
- schema/output contract;
- generated artifact paths;
- allowed external artifact reference roots;
- workflow prompt shared instruction;
- stage-specific user instruction;
- retry context;
- previous result;
- verification feedback.

Python stage classes must not own human-readable prompt prose in multiline strings. Python may build typed prompt context objects, select template names, and render templates. Short technical error messages are allowed in Python.

## Codex Output Validation

`CodexStageRunner` keeps the JSON-output boundary:

1. Generate JSON schema from the Pydantic result model.
2. Run `codex exec --output-schema ... --output-last-message ...`.
3. Validate the returned JSON into the expected Pydantic model.
4. Fail the stage if JSON is missing, invalid, or violates the schema.

Semantic stage code writes `result.json` only after this boundary validates. Mechanical validators run after semantic verification and check deterministic invariants that do not require source interpretation.

## Artifact Reference Materialization

Codex-backed stages distinguish generated artifacts from external artifact references.

Generated artifacts are owned by the current stage. They are created directly by the stage result or deterministically materialized from the validated stage result. Examples include `result.json`, `verification.json`, and `chart/<size_group_key>.json`.

External artifact references point to files created by another run-owned system or earlier stage. Codex must not copy those files. It returns references in the stage result.

The generic materialization layer:

1. receives external artifact references from a validated stage result;
2. checks that every source path is inside a declared allowed artifact root for this run;
3. normalizes references into the current result-root convention;
4. copies an external artifact only when the workflow's declarative policy requires a stage-owned copy;
5. otherwise preserves a normalized external reference;
6. feeds normalized references into mechanical validation and semantic verification.

The materialization layer must not contain browser-specific, Playwright-specific, or source-type-specific rules. Browser artifacts, downloaded files, previous-stage outputs, diagnostics, and future tool outputs use the same mechanism by adding allowed artifact roots and policy.

## Verification Contract

`table_extract_verify` validates the whole batch:

- every verified `SourceDiscovery` has exactly one matching `TableExtraction`;
- no extra `TableExtraction` exists;
- `source_type`, `source_url`, `source_title`, `size_group_key`, and applicability status match the source discovery contract;
- each chart is evidence-backed and complete;
- each generated `chart/<size_group_key>.json` exists and matches the corresponding `TableExtraction.chart`;
- normalized artifact references are valid;
- one table failure is reported as batch feedback for `table_extract`, not as a partial success.

`source_discover_verify`, `coverage_decide_verify`, and `canonical_select_verify` keep the same action/verification loop and use the new template and artifact reference contracts.

## General Workflow Container Contract

`marketplace-automation/doc/design/workflow-runtime.md` must own the reusable rules for future workflow containers:

- Codex-backed stage names use `{object}_{action}` and `{object}_{action}_verify`;
- prompt templates are complete Jinja2 files with typed context;
- Python code must not own human-readable stage instructions in multiline strings;
- Codex JSON output is validated at the runner boundary;
- Codex action stages do not copy external artifacts;
- generic artifact materialization handles references after the action result validates;
- DBOS steps are successful only after `result.json`, `verification.json`, and required generated artifacts are durable enough for restart recovery.

## Implementation Verification

Implementation must verify:

- prompt templates render with strict undefined handling;
- old stage names no longer appear in stage keys, prompt template names, or audit directories;
- one source type with multiple discovered tables calls Codex extraction once;
- batch verification fails when one discovered table is missing from `table_extraction_list`;
- batch verification fails on extra `TableExtraction`;
- chart files are materialized from validated result data;
- external artifact references are validated through generic artifact materialization without browser-specific code;
- existing `brand-size-chart` tests pass;
- a real Defacto run reaches `table_extract` with one batch extraction stage for `official_brand_size_guide`.
