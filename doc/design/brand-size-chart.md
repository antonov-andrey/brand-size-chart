# Brand Size Chart Workflow

## Scope

This repository owns the domain implementation of a workflow-container that discovers, verifies, selects, and publishes brand size charts. Generic workflow and step lifecycles belong to `workflow-container-runtime`; source contract models belong to `workflow-container-contract`; browser and VPN processes belong to `browser-vpn-runtime`.

The workflow uses Codex for source interpretation. Python owns deterministic orchestration, stable identities, artifact paths, strict models, mechanical validation, and public handoff construction. Python does not parse source pages into size-chart data.

The application composition root creates one shared `CodexRunner` with model `gpt-5.6-terra` and reasoning effort `high`. Every Codex action and semantic verification call in this container uses that runner; no step selects a model independently.

The canonical runtime and class contract is `references/workflow-container-authoring.md` from the `workflow-container-tools` plugin. This document defines only the `brand-size-chart` domain.

## Workflow Tree

The workflow tree has three public result types:

```text
RunInput -> RunResult
  BrandWorkflowInput -> BrandResult
    SourceTypeWorkflowInput -> SourceTypeResult
```

`BrandSizeChartRunWorkflow`, `BrandSizeChartBrandWorkflow`, and `BrandSizeChartSourceTypeWorkflow` directly inherit `WorkflowBase` and `DBOSConfiguredInstance`. Their instances store only reusable step and child-workflow dependencies. Invocation data is passed through typed arguments.

Every result follows one status rule: `status="failed"` exactly when that result's own `error_list` is non-empty. A failed child result remains nested and does not automatically fail its parent. No-table conclusions and uncovered requested product types are structured outcomes, not runtime errors.

`SourceTypeResult` always preserves its complete child boundary:

- `source_type` identifies the attempted source type;
- `source_discovery_result` is absent only when discovery failed before producing a verified result;
- `table_extraction_result` is absent when no table was discovered or extraction failed;
- nested `source_discovery_result.warning_list` contains verified no-table reasons without copying them into a second source-type field;
- `error_list` contains only failures of this source-type workflow.

`BrandResult` contains the complete `source_type_result_list`, `source_type_skip_list`, final `coverage_decision_result`, `canonical_selection_result`, and `brand_output_result`. `source_type_result_list` contains every source-type workflow that started, including failed children. `source_type_skip_list` contains only source types selected for this brand run but not started. Each skipped source type has one structured reason: `requested_product_type_coverage_complete` when earlier results cover the complete requested product scope, or `coverage_decision_failed` when a failed cumulative coverage decision prevents the workflow from deriving a valid scope for later product-scoped sources. Source types excluded before planning by prompt scope or source applicability are neither attempted nor skipped. The selected source-type plan is partitioned exactly between attempted results and skipped entries without duplicates or overlap.

A brand-owned coverage, selection, or output failure makes those not-yet-produced fields absent and makes that `BrandResult` failed. Child source failures and coverage gaps remain nested. A coverage-complete skip is not an error or warning. A `coverage_decision_failed` skip accompanies the brand-owned coverage error that already makes the brand result failed.

`RunResult` contains the complete `brand_result_list`, structured brand-list parse warnings, and the verified `prompt_scope`. A failed brand remains nested. Root errors are limited to failures that prevent the root from producing its own usable result, such as an invalid empty brand list or exhausted prompt parsing.

## Ordered Workflow

The root workflow performs this deterministic sequence:

1. Publish `RunInput`.
2. Parse and deduplicate the brand list.
3. Run `workflow_run_prompt_apply`, or its deterministic empty-prompt variant.
4. Run one child brand workflow per parsed brand.
5. Publish `RunResult` with all child results unchanged.

One brand workflow performs this sequence:

1. Select source types in registry priority order.
2. Run one child source-type workflow per selected source type, or append one structured skip entry when that selected source type must not start.
3. After each source type that adds verified tables, run cumulative `coverage_decide` for all tables collected so far.
4. Pass only currently uncovered requested product types to later product-scoped source types.
5. Run deterministic coverage when no semantic table comparison is needed.
6. Run `canonical_select`, or its deterministic empty-candidate variant.
7. Run deterministic `brand_output` and publish selected charts.
8. Publish one `BrandResult` containing the complete child tree and the exact selected-source partition.

General size-guide source types run before product-scoped source types. A completed coverage result may stop later product-scoped source types when every requested product type is covered; it does not suppress earlier general source types.

One source-type workflow performs this sequence:

1. Run `source_discover`.
2. If discovery returns accepted tables, run one batch `table_extract` step.
3. If discovery returns no accepted table with verified terminal reasons, return a successful no-table result.
4. If discovery or extraction exhausts correction, return a failed `SourceTypeResult` while preserving any previously verified child result.

## Prompt Scope

`workflow_run_prompt_apply` converts the user prompt into `PromptScope`. The priority country, requested product types, source allow-list, shared instruction, and step-specific instructions originate only from that user prompt. No country is hardcoded in Python, prompts, or source registry defaults.

An empty workflow prompt produces an empty `PromptScope` deterministically without a Codex call. A non-empty prompt must produce a mechanically and semantically verified scope.

## Source Discovery

`source_discover` is a browser-backed Codex step. Its public input is `SourceDiscoveryInput`; its Codex action output is `BrowserActionResult`; its public output is `SourceDiscoveryResult`.

`SourceDiscoveryInput.workflow_input.source_type` selects exactly one source authority rule from the shared domain prompt partial used by both action and verification. The source registry owns only deterministic priority and product-scope mechanics; it does not store Codex instruction prose. Product-scoped discovery reads its only product list from `workflow_input.prompt_scope.product_type_request_list`.

The step keeps its detailed inventory private and incremental. `state.json` is `SourceDiscoveryState` and contains the common Codex FSM fields plus relative paths to four JSONL files:

- `discovery_query.jsonl` contains `SourceSurfaceDiscoveryQuery` records;
- `product_type_sex_worklist.jsonl` contains `SourceSurfaceProductTypeSex` records;
- `table.jsonl` contains `SourceSurfaceTable` records;
- `url.jsonl` contains `SourceSurfaceUrl` records.

Codex appends one validated record immediately after that record becomes complete by calling `brand-size-chart-source-discovery-jsonl-append`. A next internal search, browser operation, or item decision cannot begin until the current record's evidence is saved and its append succeeds. It does not rewrite `state.json`, write JSONL directly, or buffer a completed inventory in memory until the end. `entity_id` is the stable semantic identity; `record_id` identifies one immutable revision. Corrections append the next revision with `supersedes_record_id` pointing to the current revision. Recovery validates the chain and folds it to the latest revision per entity while preserving the full append-only history.

The four generated sibling schemas come directly from the exact Pydantic record models. Evidence is saved before its reference is appended.

`SourceSurfaceTable` wraps one stable `SourceDiscovery` identity plus its inventory `state` and `reason`. Accepted handoff tables reuse that exact nested `SourceDiscovery`; Python does not copy its fields into a second identity object.

### Product-Scoped Discovery

`workflow_input.prompt_scope.product_type_request_list` is the single public product worklist. No second public search-task list may duplicate it. Codex processes that list in its stored order and creates private `product_type_sex_worklist.jsonl` records only as durable execution progress.

Codex processes one requested product type completely before moving to the next. An explicitly sexed product type has one search sex. An explicitly unisex or unsexed adult product type has the ordered search-sex list `[men, women]`; an explicitly unisex or unsexed child or baby product type has `[boys, girls]`. Every list member is processed; the order is not fallback behavior. Codex appends one worklist row immediately before processing that row, closes it before appending the next row, and never creates all initial rows in advance.

For each worklist row, Codex records one bounded query, opens a concrete matching product when the pair is applicable, inspects every product-local size surface, and saves each completed query, URL, and table decision before continuing. An impossible product and sex pair is terminal only as a rejected worklist row with its own evidence-backed reason. Active worklist rows are closed through URL records whose `worklist_key_list` references them. Table inventory rows do not close worklist rows.

The worklist describes how Codex searches; it does not define table identity or filter table inventory. Every physical table reached inside an opened source boundary is recorded exactly as the source presents it, including tables for a different sex or age segment from the search row. `source_discovery.source_title`, source evidence, and the manufacturer's physical table identity own the table's `size_group_key`. Equivalent physical tables found through multiple search rows remain one accepted table plus evidence-backed equivalent inventory rows.

Before returning, Codex rereads `product_type_request_list` and the current folded JSONL records and confirms that every requested product type and every required search-sex row is terminal. Mechanical validation rejects a requested product type with no worklist representation, unclosed active rows, incomplete source boundaries, or a table identity derived from the search request instead of source evidence. Semantic verification rejects an incorrect adult versus child/baby classification or an incomplete applicable-sex expansion.

### Source Boundary And Market Selection

Discovery must close every selected authority boundary and enumerate every concrete table reachable in that boundary. Requested product types guide product-page search but do not filter unrelated tables found inside an opened source boundary.

Accepted tables follow one market ladder:

1. Use priority-country official tables when present.
2. Otherwise use official global tables marked `GLOBAL`.
3. Otherwise use equivalent European consensus tables marked `EU`.

Conflicting European tables are recorded as `market_conflict` table rows and fail mechanical validation. Human-readable `reason` text is evidence for people; it is not a machine-state channel.

No accepted table is a valid non-fatal result only when the private inventory contains evidence-backed terminal reasons. Python derives `SourceDiscoveryResult.warning_list` from that inventory during the same step lifecycle. Downstream workflows consume only the public result and never read the private JSONL files.

## Table Extraction

`table_extract` is one browser-backed batch step per source type. `TableExtractionInput.execplan_item_list` is the ordered execution plan. Each item contains the same `SourceDiscovery` object produced by discovery, one exact chart filesystem path, and one evidence write target.

Codex processes items sequentially. For each item it sends one complete `BrandSizeChart` JSON object through `stdin` to `brand-size-chart-table-extraction-chart-write`, which resolves the target from the persisted `TableExtractionInput`, validates the exact Pydantic model, and atomically publishes one chart before Codex moves to the next item. Direct chart writes and multi-chart command payloads are forbidden. Existing valid chart files are durable progress on retry; no duplicate progress ledger is created.

The action returns `TableExtractionDeltaBatchResult`: one ordered delta per execplan item plus `browsing_error_list`. A delta owns only extracted evidence references and applicability description. Python builds one `TableExtractionArtifact` that retains the exact nested `SourceDiscovery` object and adds only extraction-owned applicability, chart, evidence, and source-type fields. `TableExtractionResult` is the public handoff and preserves browser errors.

`chart.schema.json` is generated from `BrandSizeChart`. Mechanical validation requires exact result cardinality, unique targets, valid chart content, and existing evidence references. It does not compare mirrored source identity fields because no mirrored identity exists.

## Coverage And Canonical Selection

`coverage_decide` reads verified chart artifacts and decides requested product-type coverage. Positive entries use `CoveredProductType(product_type, chart_path, reason)`. Missing coverage uses `CoverageDecisionProductTypeGap(product_type, reason)`. Gaps are not errors.

The validator owns complete partitioning of requested product types, unique membership, valid chart handles, and non-empty reasons. Semantic verification owns whether chart and evidence content actually supports each decision.

Before `canonical_select`, Python computes source priority and applicability status and filters candidates that cannot participate. Codex receives `CanonicalSelectionCandidate` objects and returns only selected physical `chart_path` handles.

For each physical `size_group_key`, the highest-priority candidate wins. Equal-priority candidates may share one deterministic representative only after semantic verification proves equivalent chart content and applicability. Otherwise the action omits selection for that group and Python adds one `CanonicalSelectionGap` with the physical key and maximum-priority candidate chart paths to the public result. The validator owns candidate membership, priority, one selection per group, exact derived gaps, and deterministic representative ordering.

## Size Group Key

`size_group_key` is the manufacturer's physical table identity normalized from the browser-visible table heading and evidence. It is created only by `source_discover` and is preserved unchanged afterward. It is not a coverage bucket and is never generated from a predefined list of business intervals.

Allowed age suffixes use the template `{min}_{max}_{month|year}` only when the manufacturer names the whole table group by that range. Concrete intervals come only from source evidence.

## Artifacts

The runtime-owned workflow tree lives under `<result_dir>/workflow/run/**`. Every workflow and step instance owns its own `input.json`, `result.json`, and `verification.json`; Codex steps also own private `state.json`.

Step-local charts and evidence live in their exact step instance directories. Browser evidence is first written under the mirrored external root `<result_dir>/.playwright-mcp/current/**` and materialized into the current step before result validation.

Final selected charts are written to:

```text
brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json
```

`BrandOutputResult.size_chart_path_list` contains result-relative handles to those files. No separate manifest duplicates `BrandResult`.

## Container Boundary

The workflow image installs sibling `workflow-container-contract` and `workflow-container-runtime` packages through explicit Docker build contexts. It does not copy their code into this package and does not clone them during the build.

The workflow receives `.secret` read-only at `/input/.secret`, copies it to pod-local writable `/runtime/.secret`, and points `CODEX_HOME` to the copied profile when present. Only browser/VPN runtime owns OpenVPN, Playwright process startup, browser profile mechanics, locale, stealth, and network namespace behavior. Local Compose keeps the mutable Playwright profile in the named `browser-profile-runtime` volume. After browser shutdown, the explicit `playwright-profile-writeback` service is the only service that mounts `.secret` writable; it invokes the browser-runtime atomic snapshot command with host UID/GID applied before publication. Kubernetes uses the corresponding stopped-runtime profile Job owned by `browser-vpn-runtime`.

Search queries use Codex internal web search. Playwright MCP opens selected target sites and writes declared browser evidence. Every browser-backed public result preserves `browsing_error_list` entries with exact `url` and `error` fields.
