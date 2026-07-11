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
- `source_discovery_result.source_discovery_database_path` references the declared SQLite artifact that owns the current discovery inventory and extracted chart identities;
- `source_discovery_result.outcome` is the minimal public routing decision derived by the step owner from that database;
- `error_list` contains only failures of this source-type workflow.

`BrandResult` retains the exact `BrandInput` object as `brand_input` and contains the complete `source_type_result_list`, `source_type_skip_list`, final `coverage_decision_result`, `canonical_selection_result`, and `brand_output_result`. It does not mirror a subset of brand identity fields. `source_type_result_list` contains every source-type workflow that started, including failed children. `source_type_skip_list` contains only source types selected for this brand run but not started. Each skipped source type has one structured reason: `requested_product_type_coverage_complete` when earlier results cover the complete requested product scope, or `coverage_decision_failed` when a failed cumulative coverage decision prevents the workflow from deriving a valid scope for later product-scoped sources. Source types excluded before planning by prompt scope or source applicability are neither attempted nor skipped. The selected source-type plan is partitioned exactly between attempted results and skipped entries without duplicates or overlap.

A brand-owned coverage, selection, or output failure makes those not-yet-produced fields absent and makes that `BrandResult` failed. Child source failures and coverage gaps remain nested. A coverage-complete skip is not an error or warning. A `coverage_decision_failed` skip accompanies the brand-owned coverage error that already makes the brand result failed.

`RunResult` contains the complete `brand_result_list`, structured brand-list parse warnings, and the verified `prompt_scope`. A failed brand remains nested. Root errors are limited to failures that prevent the root from producing its own usable result, such as an invalid empty brand list or exhausted prompt parsing.

## Ordered Workflow

The root workflow performs this deterministic sequence:

1. Publish `RunInput`.
2. Parse and deduplicate the brand list.
3. Run `workflow_run_prompt_apply`, or its deterministic empty-prompt variant.
4. Require one user-selected priority country before child execution.
5. Run one child brand workflow per parsed brand.
6. Publish `RunResult` with all child results unchanged.

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
2. If `SourceDiscoveryResult.outcome` is `market_conflict`, return a failed `SourceTypeResult` without retrying a correctly represented domain blocker.
3. If the outcome is `no_table`, return a successful no-table result.
4. If discovery exhausts correction for an invalid or incomplete result, return a failed `SourceTypeResult` while preserving any previously verified child result.

## Prompt Scope

`workflow_run_prompt_apply` converts the user prompt into `PromptScope`. The priority country, requested product types, source allow-list, shared instruction, and step-specific instructions originate only from that user prompt. No country is hardcoded in Python, prompts, or source registry defaults. Prompt parsing preserves an absent country as an empty value; the root workflow then returns a root-owned error before starting any brand workflow instead of asking Codex or Python to invent a country.

An empty workflow prompt produces an empty `PromptScope` deterministically without a Codex call and therefore cannot start brand workflows until the caller supplies a priority country. A non-empty prompt produces a mechanically and semantically verified scope while preserving genuinely absent values.

## Source Discovery

`source_discover` is a browser-backed Codex step. Its public input is `SourceDiscoveryInput`; its Codex action output is `BrowserActionResult`; its public output is `SourceDiscoveryResult`. The public result contains only `browsing_error_list`, `outcome`, and `source_discovery_database_path`; it contains no table rows, table summaries, or copied no-table reasons.

`outcome` uses exactly `table_available`, `no_table`, or `market_conflict`. The step owner derives it while building the public result: any conflict row wins, otherwise any accepted row produces `table_available`, otherwise the outcome is `no_table`. This one routing decision is not a second inventory; it lets the DBOS workflow branch without filesystem IO. Mechanical validation requires exact agreement between `outcome` and the database.

`SourceDiscoveryInput.workflow_input.source_type` selects exactly one source authority rule from the shared domain prompt partial used by both action and verification. The source registry owns only deterministic priority and product-scope mechanics; it does not store Codex instruction prose. Product-scoped discovery reads its only product list from `workflow_input.prompt_scope.product_type_request_list`.

The step publishes one incremental SQLite database at the sibling path `state.sqlite3`. This database is a declared step artifact because later steps query it through the runtime SQLite URI `mode=ro` path; downstream reads validate schema and select rows without changing journaling, synchronous mode, or database state. It is not private merely because its standard filename contains `state`. `SourceDiscoveryResult.source_discovery_database_path` is its only public handle. Neither the result nor another artifact mirrors database rows.

`state.json` remains the private `SourceDiscoveryState` owned by the current Codex lifecycle. It contains only the common attempt FSM and scalar checkpoints. It contains no inventory rows, database snapshots, or paths that downstream code must read.

The SQLite database contains current rows in five statically registered tables:

| Table | Current-state owner |
| --- | --- |
| `discovery_query` | Completed and failed source queries with their evidence and reason. |
| `product_type_sex_worklist` | One current FSM row for each semantic product-type and search-sex pair. |
| `source_url` | One current decision for each inspected URL. |
| `source_url_worklist` | The many-to-many relation between one inspected URL and the product-type/search-sex rows it supports. |
| `source_table` | One current row for each potentially usable physical table identity. |

Each table is defined by one exact Pydantic row model and a domain primary key. `discovery_query` uses the exact `query`, `product_type_sex_worklist` uses `(product_type, sex)`, `source_url` uses `url`, `source_url_worklist` uses `(url, product_type, sex)`, and `source_table` uses `(size_group_key, market_scope_key)`. The relation table avoids an opaque concatenated worklist id and a JSON list of copied identities. There are no generic entity ids, record ids, revision indexes, predecessor links, or folded revision history. A correction upserts the same domain row. The shared `workflow-container-runtime` SQLite command accepts only the current public `input.json`, derives its sibling `state.sqlite3`, resolves one table from the project-owned static registry, validates one JSON object from `stdin`, and performs the requested short transaction. Codex never writes SQLite directly and never supplies raw SQL, a database path, a model, or a transaction boundary.

The `source_table` contract is intentionally minimal:

| Column | Meaning |
| --- | --- |
| `size_group_key` | Manufacturer-derived physical chart-group key. |
| `market_scope_key` | Canonical market scope visibly declared or proven for this concrete table. |
| `source_url` | Canonical source URL for the concrete table. |
| `source_title` | Browser-visible source title. |
| `evidence_path_list` | References to saved evidence supporting identity, scope, and content. |
| `state` | `candidate`, `accepted`, `market_filtered`, or `market_conflict`. |
| `reason` | Evidence-backed explanation of the current decision. |

The composite primary key is `(size_group_key, market_scope_key)`. This order is intentional: the leading-key index supports direct lookup of every market variant for one size group, while a full-key lookup addresses one physical table. The database does not store a concatenated source-table key, `country_code_list`, chart path, applicability description, or copied chart content. `market_scope_key` is the complete machine-readable scope; `BrandSizeChart.description` owns chart-level applicability prose. The chart path is derived from the composite key by `ArtifactLayout` and never parsed back into identity fields.

Every completed query, worklist transition, URL decision, and table decision is saved before the next dependent browser or reasoning action. Evidence files are saved before their references are written. JSONL is not used for current workflow state.

At the start of an action attempt, the step initializes or validates the static database schema and rereads current rows before doing external work. Recovery resumes the first incomplete worklist or candidate transition. It does not repeat a terminal query, URL, worklist row, or valid chart unless current verification feedback explicitly identifies that object.

### Product-Scoped Discovery

`workflow_input.prompt_scope.product_type_request_list` is the single public product worklist. No second public search-task list may duplicate it. Codex processes that list in its stored order and upserts `product_type_sex_worklist` rows only as durable execution progress. The single instruction owner for deriving each product's semantic search-sex branches is `brand_size_chart/prompt/template/partial/product_search_sex_contract.md.j2`; Python does not classify products, modifiers, age groups, or applicable sexes.

Codex processes one requested product type and all search-sex branches derived by the owned algorithm completely before moving to the next product. The worklist uses `(product_type, sex)` as its composite domain identity instead of a second concatenated key. Each worklist row has a local FSM: Codex writes `pending` immediately before searching, then updates the same row to terminal `searched` after inspecting an applicable concrete product boundary or terminal `rejected` only after its bounded exact candidate inventory proves no matching boundary exists under the current source authority. An opened boundary remains incomplete while any browser-visible child surface or control may contain size evidence; every such child is inspected and receives an evidence-backed terminal URL or table decision before the worklist row becomes terminal. Codex never creates all initial rows in advance and does not start another row before the current row is terminal.

For each worklist row, Codex first runs one exact internal query for the brand, current source authority, search sex, and requested product. When the first exact candidate is source-incompatible or no direct candidate exists, Codex refines or navigates to a source-compatible surface or result set already constrained to both the requested product type and search sex. Only such a constrained surface or captured result set is an exact bounded candidate inventory. A broad parent category, store, or site surface with unrelated products is authority or navigation evidence only and cannot prove exhaustion. Codex inspects matching candidates in visible deterministic order; `rejected` is allowed only after that exact inventory is exhausted. Codex then opens a concrete matching product when the pair is applicable, inspects every product-local size surface, and saves each completed query, URL, and table decision before continuing. A terminal `searched` row has current evidence and an evidence-backed outcome reason. A terminal `rejected` row has current evidence and an evidence-backed reason. A `searched` row also has one dedicated opened `source_url` row and one `source_url_worklist` relation to its `(product_type, sex)` identity; that relation validates evidence and source-boundary closure, not worklist state. Table inventory rows do not close worklist rows.

The worklist describes how Codex searches; it does not define table identity. A discovered table is classified before persistence. A table that cannot participate in the current or a permitted fallback market is recorded only through query, URL, and worklist evidence; it does not create a `source_table` row or chart file. A table that may participate is persisted immediately as one `candidate` row and one validated chart artifact, even if the final market decision later filters it out. Tables reached through a search row are classified from their own visible heading, scope, and content, not from that search request.

Before returning, Codex rereads `product_type_request_list` and the current SQLite rows and confirms that every requested product type and every required search-sex row is terminal. Mechanical validation rejects a requested product type with no worklist representation, every `pending` row, a terminal query, URL, or worklist row without evidence and reason, a `searched` product row without its dedicated opened URL, a candidate without a valid chart, or a table identity derived from the search request instead of source evidence. Semantic verification rejects an incorrect adult versus child/baby classification or an incomplete applicable-sex expansion.

### Source Boundary And Market Selection

Discovery must close every selected authority boundary and enumerate every concrete table reachable in that boundary. For `official_marketplace_store`, Codex selects exactly one actual seller-owned storefront root with a stable browser-visible seller identity and catalog before processing product worklist rows. It prefers a visible brand-owned official seller storefront and otherwise selects one evidence-backed authorized seller storefront. That selected seller-store identity remains fixed for the step; every worklist product URL and accepted table must be linked by evidence to it, and discovery cannot mix or switch stores. Exact candidate inventory and exhaustion stay inside the selected store or its exact stable seller identity. Public or global search and generic brand or category pages are navigation evidence only, and `rejected` requires exhaustion of the selected store's exact requested-product and search-sex inventory. This store-root contract does not apply to `official_marketplace_product_page`. Requested product types guide product-page search but do not filter unrelated tables found inside an opened source boundary.

The single instruction owner for country and fallback selection is `brand_size_chart/prompt/template/partial/market_selection_contract.md.j2`. Both source-discovery action and semantic verification include that same contract. Human-readable `reason` text explains a decision; it is not a machine-state channel.

Final market selection is applied independently for each `size_group_key`. The first available verified tier wins for that group:

1. an exact priority-country scope;
2. the narrowest explicit country group containing the priority country;
3. `global`;
4. `eu`;
5. a deterministic representative of equivalent European country-specific candidates.

Within tier 2, fewer countries is more specific, followed by lexical `market_scope_key`. Tier 5 is allowed only after semantic comparison proves all candidates equivalent; its representative is first by `(market_scope_key, source_url, source_title)`. Non-winning candidates remain stored as `market_filtered`. Differing tier-5 candidates become `market_conflict`; an arbitrary locale or inferred market is never selected.

Market handling has two ordered phases inside the same `source_discover` step:

1. The browser phase discovers source boundaries, classifies potentially useful tables, writes each validated chart, and upserts its `candidate` row before continuing.
2. The local finalization phase rereads only `state.sqlite3`, chart files, and saved evidence; it applies priority-country and fallback policy, verifies semantic equivalence where the policy requires it, and changes candidates to `accepted`, `market_filtered`, or `market_conflict`. It does not revisit the browser.

These phases are one action lifecycle with one owner. There is no `table_extract` step, no `source_table_select` step, and no second browser traversal of already discovered tables.

Equivalence is a market-selection decision, not table identity. Distinct composite keys remain distinct even when their chart content is equivalent. Repeated evidence for the same `(size_group_key, market_scope_key)` updates the same row and chart target. If a second observation claims the same composite identity but conflicts with the already validated chart, the existing chart is not overwritten and the row becomes `market_conflict`.

The step action writes one complete `BrandSizeChart` through the narrow chart producer command before moving to the next candidate. The command accepts the current public `input.json`, both validated identity components, and one chart object through `stdin`; it derives the sibling chart path itself, validates `chart.schema.json`, and atomically publishes one file. Codex never supplies a filesystem path, writes chart JSON directly, or submits several charts in one command.

The producer returns one structured outcome: `created` after a new atomic publication, `unchanged` when the existing validated chart is equal, or `conflict` when the same composite identity already has different validated content. `conflict` leaves the existing file unchanged and instructs the action to upsert `market_conflict`; it is not an infrastructure exception. A non-zero command exit is reserved for invalid input or a real publication failure. After `created` or `unchanged`, the action upserts the corresponding `candidate` row before continuing. Existing valid chart files are durable progress on retry and are reused unless current verification feedback names that table.

Image-backed extraction uses the browser-visible original image asset or a complete element capture at readable resolution. A scaled, cropped, or viewport-limited overlay is navigation context, not sufficient transcription evidence when the original asset is available.

Mechanical validation checks row identities, `source_url_worklist` references, terminal worklist state, evidence references, allowed state transitions, accepted-market invariants, exact public outcome parity, and the existence and schema of every persisted chart. Semantic verification checks source-boundary completeness, table transcription, market scope, equivalence, filtering, and conflicts. A complete evidence-backed `market_conflict` is a valid terminal discovery state and a domain blocker owned by `SourceTypeResult`; it is not a no-table warning or a reason to repeat an otherwise correct Codex action. An incomplete or unsupported conflict remains a verification failure.

A successful step handoff has no `candidate` rows and no non-terminal worklist rows. It may contain `market_conflict` only when that conflict is complete and verified. A valid chart without a corresponding database row is an unpublished orphan and is never visible downstream; recovery may reuse it when the same identity is rediscovered. A database candidate without its valid chart fails mechanical validation. Repeating the producer for the same identity and equal validated chart is idempotent.

No accepted table is a valid non-fatal result only when the database has no `market_conflict` and contains complete evidence-backed terminal query, URL, and worklist reasons. Those reasons remain in SQLite and are not copied into a warning summary. Downstream workflows read the declared SQLite artifact through `source_discovery_database_path`; they never read the previous step's private `state.json` and never receive copied source-table rows.

## Coverage And Canonical Selection

`coverage_decide` receives the complete `SourceTypeResult` objects produced by earlier child workflows. It does not receive a copied table list. The shared reader filters that complete list to successful `table_available` results, resolves every declared `source_discovery_database_path`, queries only `source_table` rows with `state="accepted"`, derives chart paths through `ArtifactLayout`, and rejects duplicate transient chart handles. The action reads those verified charts and decides requested product-type coverage. Positive entries use `CoveredProductType(product_type, chart_path, reason)`. Missing coverage uses `CoverageDecisionProductTypeGap(product_type, reason)`. Gaps are not errors.

The validator owns complete partitioning of requested product types, unique membership, valid chart handles, and non-empty reasons. Semantic verification owns whether chart and evidence content actually supports each decision.

`canonical_select` receives the same complete source-type results and no Python-built candidate collection. Its action and validator use the same read-only boundary to query accepted rows and charts. Source priority comes from the registry entry for the source type that owns each database; market applicability is derived from the row's `market_scope_key` and the priority-country/fallback policy in the current input. Query results are transient and are never written as a second candidate artifact or mirrored input model. The action returns only selected physical `chart_path` handles.

For each `size_group_key`, the highest-priority accepted source candidate wins. Each candidate remains a distinct physical `(size_group_key, market_scope_key)` identity, and the selected handle is its full derived chart path. Equal-priority candidates may share one deterministic representative only after semantic verification proves equivalent chart content and applicability, ordered by `(market_scope_key, source_url, source_title)`. Otherwise the action omits selection for that size group and one reusable domain operation derives one `CanonicalSelectionGap` with the size-group key and maximum-priority candidate chart paths to the sole public result. The validator compares the supplied gap list with that derivation and owns candidate membership, priority, one selection per size group, and deterministic representative ordering.

## Source Table Identity

`size_group_key` is the manufacturer's physical table identity normalized from the browser-visible table heading and evidence. It is created only by `source_discover` and is preserved unchanged afterward. It is not a coverage bucket and is never generated from a predefined list of business intervals.

Allowed age suffixes use the template `{min}_{max}_{month|year}` only when the manufacturer names the whole table group by that range in its heading or group label. Row values describe the table content and never redefine its physical group identity.

The exact semantic normalization algorithm is owned once by `brand_size_chart/prompt/template/partial/size_group_key_contract.md.j2` and is shared by the discovery action and verifier. Chart-content equality never creates, merges, or renames an identity; content is used only to validate repeated observations and market-equivalence decisions.

`market_scope_key` is created only after inspecting the concrete table's visible market applicability. It is independent of the user's priority-country request and uses exactly one canonical form:

- one country uses its lowercase ISO alpha-2 code, such as `tr`;
- a source-declared global table uses `global`;
- a table directly evidenced as one EU-wide scope uses `eu`;
- a table directly evidenced as one explicit multi-country scope uses unique lowercase country codes in ascending order joined by one underscore, such as `de_fr_nl`.

`brand_size_chart/prompt/template/partial/market_selection_contract.md.j2` owns both this normalization and the priority-country/fallback decision; action and verification use the same contract.

The stable table identity is the composite pair `(size_group_key, market_scope_key)`. Neither component is inferred from the search query. The pair is stored as two SQLite primary-key columns; no concatenated identity column is stored. Files use the deterministic stem `<size_group_key>__<market_scope_key>`, with `__` reserved only as the path separator and rejected inside either component. Code builds the path from the two fields and never parses the filename to recover them.

Because market scope is part of both database identity and artifact path, storage can represent several scopes for one size group without collision. A future or explicit all-tables selection policy can expose those existing physical identities without changing the database or filename contract.

## Artifacts

The runtime-owned workflow tree lives under `<result_dir>/workflow/run/**`. Every workflow and step instance owns its own `input.json`, `result.json`, and `verification.json`; Codex steps also own private `state.json`.

Each `source_discover` step also owns one declared `state.sqlite3` artifact and one generated `chart.schema.json`. Step-local charts use the deterministic relative path:

```text
chart/<size_group_key>__<market_scope_key>.json
```

The `source_table` row does not store this path. `ArtifactLayout` derives it from the composite key for the producer, validators, downstream readers, and final publication. Browser evidence is first written under the mirrored external root `<result_dir>/.playwright-mcp/current/**` and materialized into the current step before result validation.

Final selected charts are written to:

```text
brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>__<market_scope_key>.json
```

`BrandOutputResult.size_chart_path_list` contains result-relative handles to those files. No separate manifest duplicates `BrandResult`.

## Container Boundary

The workflow image installs sibling `workflow-container-contract` and `workflow-container-runtime` packages through explicit Docker build contexts. It does not copy their code into this package and does not clone them during the build.

The workflow receives `.secret` read-only at `/input/.secret`, copies it to pod-local writable `/runtime/.secret`, and points `CODEX_HOME` to the copied profile when present. Only browser/VPN runtime owns OpenVPN, the fail-closed SOCKS5 egress gateway, Playwright process startup, browser profile mechanics, locale, stealth, and network isolation. Local Compose runs `vpn-egress` and `playwright-mcp` in separate network namespaces. Playwright belongs only to the internal browser-control network and reaches target sites through the stable gateway endpoint, so OpenVPN may readdress or recreate its private tunnel without changing the browser network interface. Before Codex runs, each browser-backed step prepares only its exact declared external evidence directory for cross-process writes through the generic runtime artifact helper; private input and unrelated output paths keep their existing permissions. Local Compose keeps the mutable Playwright profile in the named `browser-profile-runtime` volume. After browser shutdown, the explicit `playwright-profile-writeback` service is the only service that mounts `.secret` writable; it invokes the browser-runtime atomic snapshot command with host UID/GID applied before publication. Kubernetes uses the corresponding separated gateway/browser capability and stopped-runtime profile Job owned by `browser-vpn-runtime`.

Search queries use Codex internal web search. Playwright MCP opens selected target sites and writes declared browser evidence. Every browser-backed public result preserves `browsing_error_list` entries with exact `url` and `error` fields.
