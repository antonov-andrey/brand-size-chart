# Brand Size Chart Workflow

## Public Input

`WorkflowBrandSizeChartInput` is the only public workflow input. It has the complete `request` and `config` fields required by `input.schema.json`; the runtime never merges a prompt, a partial config, or defaults into a saved input.

`request` owns `brand_list`, `priority_country_code`, `product_type_request_list`, and `source_type_allow_list`. `brand_list` is a non-empty `list[str]` of final brand names: every value is non-empty, already trimmed, and unique. `config` inherits `WorkflowBrowserConfigBase` and owns one workflow instruction, one `McpPlaywrightProfileWritebackPolicy`, and the closed typed `step_map` containing `source_discover`, `coverage_decide`, and `canonical_select` configs.

Every step config uses the browser-profile fields from `WorkflowStepCodexConfigBase`. `source_discover.mcp_playwright_profile` is `"source-discover"`; its source is `null`. The profile and source fields of `coverage_decide` and `canonical_select` are `null`. Concurrent source-discovery lanes therefore use `source-discover-1` through `source-discover-N` according to the common runtime contract. The workflow writeback policy is:

```json
{
  "mcp_playwright_profile_name_prefix": "",
  "workflow_run_status_list": ["done"]
}
```

An empty prefix permits every named profile and does not disable writeback. The policy publishes the last successfully verified named profile once when the workflow run becomes `done`; `working` writeback remains an explicit user choice.

## Public Input Migration

The next incompatible input version removes `brand_list_text` instead of retaining a compatibility field. Its migration script applies the existing line parser once, writes the resulting canonical brand names to `brand_list`, and fails if it cannot produce a valid non-empty unique list. It adds the exact profile fields and writeback policy above to the saved complete input, validates the complete migrated object against the new `input.schema.json`, and leaves no runtime fallback for the old shape.

## Runtime Tree

The root workflow writes the complete input and starts one brand workflow per parsed brand. Every brand workflow writes the same complete input into its own instance, then creates registry-ordered independent `SourceDiscoveryInputSource` invocations. `SourceDiscoveryStep.run_outcome_list(...)` receives the exact `WorkflowStepSourceDiscoverConfig`; its runtime scheduler uses `concurrency` and returns ordered outcomes in invocation order. Exhausted validation feedback becomes the matching failed `SourceTypeResult`, while Codex infrastructure errors propagate for DBOS recovery.

`BrandSizeChartSourceTypeWorkflow` is intentionally absent. It was a one-step proxy with a duplicate child-input contract.

The brand workflow turns source-discovery results into `SourceTypeResult` values, then runs coverage decision, canonical selection, and final output publication. Each configurable DBOS wrapper receives the exact typed config separately. The runtime verifies that config against the current workflow `input.json`.

## Persisted Step Inputs

`SourceDiscoveryInput` persists stable `brand_input`, `source_type`, its evidence target, and `workflow_input_path`. Coverage and canonical selection persist full `source_type_result_list` plus `workflow_input_path`. No step input copies workflow config, instructions, or a config subset.

Action and verification prompts follow `workflow_input_path` to the complete input. Runtime prompt partials apply the step instruction before the workflow instruction while preserving domain and runtime contracts.

## Source Discovery

Each source discovery keeps the committed SQLite current-state lifecycle: schemas are created before work, state is updated through the declared command surface, charts and evidence remain declared artifacts, and downstream readers consume only validated result handles. Product work uses `request.product_type_request_list`; market selection uses `request.priority_country_code`.
