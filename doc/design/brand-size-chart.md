# Brand Size Chart Workflow

## Public Input

`WorkflowBrandSizeChartInput` is the only public workflow input. It has the complete `request` and `config` fields required by `input.schema.json`; the runtime never merges a prompt, a partial config, or defaults into a saved input.

`request` owns `brand_list`, `priority_country_code`, `product_type_request_list`, and `source_type_allow_list`. `brand_list` is a non-empty `list[str]` of final brand names: every value is non-empty, already trimmed, unique, convertible to `parsed_brand_key`, and produces a distinct key. `config` inherits `WorkflowBrowserConfigBase` and owns one workflow instruction, one `McpPlaywrightProfileWritebackPolicy`, and the closed typed `step_map` containing `source_discover`, `coverage_decide`, and `canonical_select` configs.

Every step config uses the browser-profile fields from `WorkflowStepCodexConfigBase`. `source_discover.mcp_playwright_profile` is `"source-discover"`; its source is `null`. The profile and source fields of `coverage_decide` and `canonical_select` are `null`. Concurrent source-discovery lanes therefore use `source-discover-1` through `source-discover-N` according to the common runtime contract. The workflow writeback policy is:

```json
{
  "mcp_playwright_profile_name_prefix": "",
  "workflow_run_status_list": ["done"]
}
```

An empty prefix permits every named profile and does not disable writeback. The policy publishes the last successfully verified named profile once when the workflow run becomes `done`; `working` writeback remains an explicit user choice.

## Public Input Migration

Version `0.5.0` is the single incompatible successor to `0.4.0`; `versions.yaml` declares the exact edge `0.4.0 -> 0.5.0` through `migration/input/0.4.0_to_0.5.0.py`, and `contracts.workflow` advances from `3` to `4`. Artifact and prompt contract versions do not change.

The migration removes `brand_list_text` instead of retaining a compatibility field. Its script applies the legacy line-parsing semantics once, writes the resulting canonical brand names to `brand_list`, and fails if it cannot produce a valid non-empty list with distinct parsed keys. It adds the exact profile fields and writeback policy above to the saved complete input, validates the complete migrated object against the new `input.schema.json`, and leaves no runtime fallback for the old shape. Legacy parsing code belongs only to this migration script after the cutover.

## Runtime Tree

The root workflow writes the complete input and starts one brand workflow for every value in `request.brand_list`, preserving list order. It derives `BrandInput` with only `parsed_brand_key` and `parsed_brand_name`; there is no runtime line parser, raw-name mirror, source-line field, parse-warning model, or parse-warning field in `RunResult`. Every brand workflow writes the same complete input into its own instance, then creates registry-ordered independent `SourceDiscoveryInputSource` invocations. `SourceDiscoveryStep.run_outcome_list(...)` receives the exact `WorkflowStepSourceDiscoverConfig`; its runtime scheduler uses `concurrency` and returns ordered outcomes in invocation order. Exhausted validation feedback becomes the matching failed `SourceTypeResult`, while Codex infrastructure errors propagate for DBOS recovery.

`BrandSizeChartSourceTypeWorkflow` is intentionally absent. It was a one-step proxy with a duplicate child-input contract.

The brand workflow turns source-discovery results into `SourceTypeResult` values, then runs coverage decision, canonical selection, and final output publication. Each configurable DBOS wrapper receives the exact typed config separately. The runtime verifies that config against the current workflow `input.json`.

## Persisted Step Inputs

`SourceDiscoveryInput` persists stable `brand_input`, `source_type`, its evidence target, and `workflow_input_path`. Coverage and canonical selection persist full `source_type_result_list` plus `workflow_input_path`. No step input copies workflow config, instructions, or a config subset.

Action and verification prompts follow `workflow_input_path` to the complete input. Runtime prompt partials apply the step instruction before the workflow instruction while preserving domain and runtime contracts.

## Source Discovery

Each source discovery keeps the committed SQLite current-state lifecycle: schemas are created before work, state is updated through the declared command surface, charts and evidence remain declared artifacts, and downstream readers consume only validated result handles. Product work uses `request.product_type_request_list`; market selection uses `request.priority_country_code`.

## Verification

Behavior tests cover strict `brand_list` validation, the exact `0.4.0 -> 0.5.0` migration, removal of runtime line-parsing state, complete explicit profile config, deterministic source-discovery lanes, and the `done` writeback policy. After automated verification, a real Defacto run with at least two allowed source types and `source_discover.concurrency >= 2` must confirm concurrent use of distinct run-local profiles, successful workflow output, and publication of the final writeback candidate without mocks or fixtures.
