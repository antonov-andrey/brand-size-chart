# Brand Size Chart Workflow

## Public Input

`WorkflowBrandSizeChartInput` is the only public workflow input. It has the complete `request` and `config` fields required by `input.schema.json`; the runtime never merges a prompt, a partial config, or defaults into a saved input.

`request` owns `brand_list_text`, `priority_country_code`, `product_type_request_list`, and `source_type_allow_list`. `config` owns one workflow instruction and the closed typed `step_map` containing `source_discover`, `coverage_decide`, and `canonical_select` configs.

## Runtime Tree

The root workflow writes the complete input and starts one brand workflow per parsed brand. Every brand workflow writes the same complete input into its own instance, then creates registry-ordered independent `SourceDiscoveryInputSource` invocations. `SourceDiscoveryStep.run_list(...)` receives the exact `WorkflowStepSourceDiscoverConfig`; its runtime scheduler uses `concurrency` and returns results in invocation order.

`BrandSizeChartSourceTypeWorkflow` is intentionally absent. It was a one-step proxy with a duplicate child-input contract.

The brand workflow turns source-discovery results into `SourceTypeResult` values, then runs coverage decision, canonical selection, and final output publication. Each configurable DBOS wrapper receives the exact typed config separately. The runtime verifies that config against the current workflow `input.json`.

## Persisted Step Inputs

`SourceDiscoveryInput` persists stable `brand_input`, `source_type`, its evidence target, and `workflow_input_path`. Coverage and canonical selection persist full `source_type_result_list` plus `workflow_input_path`. No step input copies workflow config, instructions, or a config subset.

Action and verification prompts follow `workflow_input_path` to the complete input. Runtime prompt partials apply the step instruction before the workflow instruction while preserving domain and runtime contracts.

## Source Discovery

Each source discovery keeps the committed SQLite current-state lifecycle: schemas are created before work, state is updated through the declared command surface, charts and evidence remain declared artifacts, and downstream readers consume only validated result handles. Product work uses `request.product_type_request_list`; market selection uses `request.priority_country_code`.
