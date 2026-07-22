# Brand Size Chart Workflow

## Platform Source Contract

`brand-size-chart` is the first acceptance workflow for `WorkflowSourceInterface` major 2, but its name and domain behavior do not appear in the generic platform implementation. Its `WorkflowSource` fixes interface major `2`; every version of that source must keep the same external process, filesystem, and control contract.

The target `workflow.yaml` declares:

- `build.dockerfile_path: docker/workflow/Dockerfile`;
- the complete runtime `command: [brand-size-chart-run]`;
- the publisher-owned `test.command: [python, -m, pytest, -q]`;
- exact run Data templates `result: result/{brand_key}` and `workspace: workspace/{brand_key}`;
- the Athena-visible `brand_size_chart` JSON Lines dataset below the result manifest;
- source-owned `brand_complete`, `canonical_select`, `coverage_decide`, and `source_discover` step policy keys;
- separate `codex_profile` and `playwright_profile` secret declarations;
- `browser_runtime` with only the `playwright_profile` capability role, while `codex_profile` remains a workflow-only Codex credential. VPN config is never a source secret declaration.

The source Dockerfile uses the pinned platform-owned base image as the optional shared implementation of `workflow-container-runtime`, DBOS, Codex, and their common dependencies. The exported exact `brand-size-chart` Git tree is the only build context: no `.git` metadata, Git submodule entry, sibling repository, additional Docker context, or host path participates in the build. Use of this base image is a decision of this first-party workflow and is not a requirement imposed on other `WorkflowSource` images.

The platform runs `brand-size-chart-run` without appended CLI arguments and supplies `WORKFLOW_RUN_ID`, `WORKFLOW_INPUT_PATH=/input/input.json`, `WORKFLOW_RUN_CONTEXT_PATH=/input/run-context.json`, `WORKFLOW_RUNTIME_PATH=/runtime`, `WORKFLOW_CONTROL_URL`, and `WORKFLOW_CAPABILITY_CONFIG_PATH=/input/capability.json`. `/input` is immutable, `/runtime` is private run-local checkpoint state, `/tmp` is attempt-local writable storage, and `/workspace` and `/result` are the two writable Data roots. The image may expose only source-declared run subtrees through accepted manifest requests. The writable Codex profile is recreated from the exact read-only `codex_profile` snapshot under `/tmp` for every execution and never enters accepted Data. DBOS SQLite configuration, Codex setup, recovery files, and the adapter from these platform values to the application entrypoint are internal details of the selected shared runtime implementation.

Immediately after the version image is built, the platform injects its own test bundle and test data into a clean container created from the exact candidate digest and verifies the interface from inside that image. A second clean container executes the declared publisher tests already present in the image. The version is not available to its owner, cannot be published, and cannot be selected by a `Workflow` until both required checks succeed.

## Public Input

`WorkflowBrandSizeChartInput` is the only public workflow input. It has the complete `request` and `config` fields required by `input.schema.json`; the runtime never merges a prompt, a partial config, or defaults into a saved input.

`request` owns `brand_list`, `priority_country_code`, `product_type_request_list`, and `source_type_allow_list`. `brand_list` is a non-empty `list[str]` of final brand names: every value is non-empty, already trimmed, unique, convertible to `parsed_brand_key`, and produces a distinct key. `source_type_allow_list` accepts canonical registry keys plus the public selectors `brand` for `official_brand_size_guide` and `product` for `official_brand_product_page`. `config` inherits `WorkflowBrowserConfigBase` and owns one workflow instruction, one `McpPlaywrightProfileWritebackPolicy`, and the closed typed `step_map` containing `source_discover`, `coverage_decide`, and `canonical_select` configs. It has no global proxy list or routing policy.

Every step config uses the browser fields from `WorkflowStepCodexConfigBase`, including one explicit nullable `mcp_playwright_network_proxy_name` marked by `format: network-proxy-name`. `source_discover.mcp_playwright_profile` is `"source-discover"`; its source is `null`. The profile and source fields of `coverage_decide` and `canonical_select` are `null`. Concurrent source-discovery lanes therefore use `source-discover-1` through `source-discover-N` according to the common runtime contract. The workflow writeback policy is:

```json
{
  "mcp_playwright_profile_name_prefix": "",
  "workflow_run_status_list": ["done"]
}
```

An empty prefix permits every named profile and does not disable writeback. After every successfully verified named invocation, the runtime atomically replaces the single run-local writeback candidate with that profile. The platform accepts the current candidate into the exact secret path selected for `browser_runtime` once when the workflow run becomes `done`; this trusted capability writeback uses a payload-independent transition identity and compare-and-swap against the expected `DataRevision`. `working` writeback remains an explicit user choice.

Each of `source_discover`, `coverage_decide`, and `canonical_select` independently takes its browser proxy from its own exact `mcp_playwright_network_proxy_name` in the complete immutable input. The shared runtime resolves only that name through `network_proxy.proxy_by_name_map` and passes it to the browser route; `null` means direct egress. All concurrent invocations of `source_discover` use the same exact source-discover setting. Action, verification, correction and recovery use the same immutable step config. No typed step input stores a proxy name, routing index, config copy, or automatically selected value.

## Public Input Migration

Version `0.5.0` is the single incompatible input successor to `0.4.0`; `versions.yaml` retains the exact edge `0.4.0 -> 0.5.0` through `migration/input/0.4.0_to_0.5.0.py`. Version `0.6.0` performs the destructive platform-interface cutover to major 2 and advances `contracts.artifact_schema` to `4` for the public Data and dataset contract. Version `0.7.0` completes the browser/VPN runtime split, declares only `browser_runtime`, and adds the inherited explicit nullable `mcp_playwright_network_proxy_name` to each Codex step config so the platform can provision the union of exact named proxies without selecting one for the workflow. The pre-production platform cutover recreates Workflows on this schema, so no `0.6.x -> 0.7.0` input migration or compatibility field exists.

The migration removes `brand_list_text` instead of retaining a compatibility field. Its script applies the legacy line-parsing semantics once, writes the resulting canonical brand names to `brand_list`, and fails if it cannot produce a valid non-empty list with distinct parsed keys. It adds the exact profile fields and writeback policy above to the saved complete input, validates the complete migrated object against the new `input.schema.json`, and leaves no runtime fallback for the old shape. Legacy parsing code belongs only to this migration script after the cutover.

This script transforms an exported complete input before form import. It does not create a platform `WorkflowRun`, migrate old platform storage, or preserve removed `DataSource` or `DataContainer` state; the destructive platform cutover recreates the workflow on the new source version.

## Runtime Tree

The root workflow writes the complete input below `/runtime/result` and starts one brand workflow for every value in `request.brand_list`, preserving list order. It derives `BrandInput` with only `parsed_brand_key` and `parsed_brand_name`; there is no runtime line parser, raw-name mirror, source-line field, parse-warning model, or parse-warning field in `RunResult`. Every brand workflow writes the same complete input into its own runtime-owned instance, then creates registry-ordered independent `SourceDiscoveryInputSource` invocations. Each browser-backed `InputT` contains the complete `workflow_input_path` and no proxy field or routing index. `SourceDiscoveryStep.run_outcome_list(...)` receives the exact `WorkflowStepSourceDiscoverConfig`; its runtime scheduler uses `concurrency` and returns ordered outcomes in invocation order. Exhausted validation feedback becomes the matching failed `SourceTypeResult`, while Codex infrastructure errors propagate for DBOS recovery.

Each accepted canonical chart is copied to `/result/{brand_key}/size_chart/`, and its flat Athena-visible measurement rows are written atomically to `/result/{brand_key}/dataset/brand_size_chart/part-00000.jsonl`. Every row contains the exact immutable `workflow_run_id`, `workflow_run_timestamp`, and `workflow_source_version_id` provenance from `WorkflowRunContext`. The brand safepoint writes `/workspace/{brand_key}/safepoint.json` and requests both declared manifests with stable `step_key: brand_complete`; the final request carries only the open `RunResult` because each brand manifest was already accepted.

`BrandSizeChartSourceTypeWorkflow` is intentionally absent. It was a one-step proxy with a duplicate child-input contract.

The brand workflow turns source-discovery results into `SourceTypeResult` values, then runs coverage decision, canonical selection, and final output publication. Each configurable DBOS wrapper receives the exact typed config separately. The runtime verifies that config against the current workflow `input.json`.

## Persisted Step Inputs

`SourceDiscoveryInput` persists stable `brand_input`, `source_type`, its evidence target, and `workflow_input_path`. Coverage and canonical selection persist full `source_type_result_list` plus `workflow_input_path`. No step input copies workflow config, instructions, or a config subset.

Action and verification prompts follow `workflow_input_path` to the complete input. Runtime prompt partials apply the step instruction before the workflow instruction while preserving domain and runtime contracts.

## Source Discovery

Each source discovery keeps the committed SQLite current-state lifecycle: schemas are created before work, state is updated through the declared command surface, charts and evidence remain declared artifacts, and downstream readers consume only validated result handles. Product work uses `request.product_type_request_list`; market selection uses `request.priority_country_code`.

## Verification

Behavior tests cover strict `brand_list` validation, the exact `0.4.0 -> 0.5.0` migration, removal of runtime line-parsing state, complete explicit profile and nullable browser-proxy config, exact per-step proxy propagation, null/direct behavior, absence of routing indices or automatic distribution, deterministic source-discovery lanes, queryable dataset provenance, and the `done` writeback policy. Source verification additionally covers the target `workflow.yaml`, reproducible single-source Docker build, the platform interface suite, the separate publisher suite, startup through the standard environment and control service, durable final-request receipt, and process exit without further business work before platform acceptance.

The full platform acceptance path creates the source and version through `workflow-control-center`, observes the version remain unavailable until both test suites pass, publishes it through the admin-only action, assigns the declared secret paths, creates two ready VPN roots with distinguishable exit IPs, assigns their exact stable names to two different browser step settings, and starts a `WorkflowRun` from the UI. A forced recoverable failure of the first execution Job after durable state exists must persist a pending replacement while stop is unproven and then automatically produce a sequential replacement Job for the same working run immediately after proof, without a user retry: the first Job and its Pods are confirmed stopped and fenced before replacement, no executions overlap, and the replacement resumes from the last accepted safepoint with the same accepted `/runtime`, control staging, capability state, proxy root set, and transition identities. A real Defacto run with at least two allowed source types and `source_discover.concurrency >= 2` must confirm that the capability map contains both explicitly configured names, each browser-backed step uses only its own exact setting, all concurrent source-discovery lanes retain the one source-discover setting, proxied exit IPs match those settings, workflow output succeeds, result and workspace Data are accepted, dataset rows are queryable, and the final profile candidate is accepted through compare-and-swap against the expected `DataRevision` without mocks or fixtures.
