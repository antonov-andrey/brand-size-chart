# Brand Size Chart DBOS Workflow

## Scope

This repository owns a DBOS workflow container that parses one `brand_list`, uses one `secret` reference for external runtime credentials, and writes canonical `brand_size_chart` artifacts plus `brand_size_chart_audit` evidence.

## Determinism Boundary
Shared `DBOS` workflow source, action/verification loop, prompt template, schema validation, artifact materialization, Codex sandbox, and browser runtime boundary rules belong to `workflow-container-developer/doc/design/workflow-container-authoring.md`. This document defines only `brand-size-chart` domain behavior: source types, source discovery semantics, table extraction semantics, `size_group_key`, mechanical domain guards, output paths, and local production runtime facts.

Real source discovery and table extraction are Codex-owned browser stages. Python code must not parse marketplace or brand pages into size-chart data and must not load source pages or source assets through non-browser request paths. The `source_discover` and `table_extract` stages must call Codex with configured browser access and return schema-valid domain results.

## Stage Workflow Contract

The shared action and verification stage shape belongs to `workflow-container-developer/doc/design/workflow-container-authoring.md`. The canonical action stage keys for this workflow are `workflow_run_prompt_apply`, `source_discover`, `table_extract`, `coverage_decide`, and `canonical_select`.

`source_discover` must build source-surface inventory before it writes `discovered_source_list`. The inventory evidence must cover discovery queries, candidate URLs, opened URLs, accepted tables, duplicate or equivalent tables, rejected URLs, rejection reasons, and blocking source-access errors for the requested source type. The result must contain every concrete unique table candidate found for that source type, not one aggregate page candidate. Inside one source type, one `size_group_key` may appear at most once in `discovered_source_list`; duplicate, equivalent, lower-priority-market, or rejected tables for the same `size_group_key` stay in the canonical inventory with exact reason codes and must not become separate source candidates.

For official hosts, `source_discover` must infer the browser-visible language and market from the opened page, derive localized size-chart search-term families for that language and market, and run separate browser-visible searches for each distinct localized family before concluding that no official size-guide table exists. These are search-term families, not URL templates.

`product_type_request_list` defines coverage targets and later-source-type continuation only. `official_brand_size_guide` and `official_seller_size_guide` must receive an empty product-type scope; they search all size-guide tables available on their non-product source surfaces. Product-type scope is passed only to source types that inspect concrete products. It must not filter `source_discover` candidates, accepted tables, or table extraction scope for an opened source surface. Concrete tables found inside the source-type boundary must be returned even when they do not cover any requested product type.

`priority_country_code` defines the market priority for source discovery. It is parsed from the workflow-run prompt by `workflow_run_prompt_apply` like `source_type_allow_list` and `product_type_request_list`; no default country exists in code, prompts, or design. Every `SourceDiscovery` item must declare `country_code_list`. For each source type, `discovered_source_list` follows one strict ladder: if priority country tables exist, include only items whose `country_code_list` contains `priority_country_code`; otherwise, if global tables exist, include only items marked with `country_code_list=["GLOBAL"]`; otherwise include European consensus items marked with `country_code_list=["EU"]` only when evidence proves the relevant official European country tables do not differ. Conflicting European country tables make `source_discover` fail with exact country codes, URLs, and `size_group_key` values.

`source_discover` must not silently skip. An empty `discovered_source_list`, `status="skipped"`, missing inventory evidence, or incomplete source loading is a critical incomplete stage result. The workflow retries it through the action-stage feedback loop and fails after the attempt limit instead of producing an empty successful source type. A semantically verified `status="failed"` with canonical inventory evidence and concrete no-table errors is a non-fatal no-table source result: the source-type summary state is `skipped`, and the errors are stored in `warning_list`. Runtime exceptions, Codex failures, and stage verification exhaustion remain fatal source-type failures.

`source_discover_verify` is the verification half of `source_discover`. It checks source-type completeness and source-type boundary, not only JSON shape or self-consistency. It may use the same external runtime capabilities as `source_discover` and may save its own evidence, but it must not repair the result.

`table_extract` is one batch stage per source type. It receives the complete verified `discovered_source_list`, builds an explicit execution plan from that list, extracts each table sequentially inside one Codex stage, and returns one `TableExtractionBatchResult` containing one `TableExtraction` per discovered source. The source-type workflow must not enqueue one child workflow per table. A failed table inside the batch fails the batch verification and sends feedback to the same `table_extract` action stage.

Size-chart data may appear as an HTML table, page text, modal, rendered widget, PDF, image, embedded asset, product image, help section, FAQ section, Q&A section, seller answer, product details, or size recommendation block. These forms are universal across source types; source types differ only by authority, location, and applicability boundaries. A separate official asset source type is forbidden.

`official_brand_size_guide` covers official brand-owned non-product size-guide surfaces on the brand website. `official_seller_size_guide` covers official or authorized reseller or distributor non-product size-guide surfaces for the brand when the brand sells through an official seller in a relevant country; evidence must prove the seller is official or authorized.

`official_brand_product_page`, `official_marketplace_product_page`, and `official_marketplace_store` are product-type-scoped source types. When `product_type_request_list` is empty, the workflow must not run those source types. When `product_type_request_list` is present, each source discovery receives the current uncovered product-type list through `PromptScope`. After each source type, a semantic `coverage_decide` stage determines which requested product types are explicitly covered by verified tables; only still-uncovered product types are passed to later source types.

## Artifact Layout

Canonical brand output is written to `brand_size_chart/brand/<parsed_brand_key>/manifest.json`. Size chart data is written to `brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json`. Stage result and verification artifacts are written under `brand_size_chart_audit/brand/<parsed_brand_key>/`. Runtime evidence artifacts may be written under any run-owned artifact root declared for the current workflow.

Batch table extraction uses `brand_size_chart_audit/brand/<parsed_brand_key>/source_type/<source_type>/table_extract/result.json`, `brand_size_chart_audit/brand/<parsed_brand_key>/source_type/<source_type>/table_extract/verification.json`, and generated table files under `brand_size_chart_audit/brand/<parsed_brand_key>/source_type/<source_type>/table_extract/chart/<size_group_key>.json`.

The root run result is written to `brand_size_chart_audit/run/result.json`. The result model carries `status`, `message`, and `error_list` directly; separate terminal-result artifacts are forbidden.

## Size Group Key Contract

Real size-chart table keys use only `{sex}_{product_group_or_type}` or `{sex}_{sex_suffix}_{product_group_or_type}`. `sex` is limited to `women`, `men`, `girls`, `boys`, `unisex`, and `unisex_child`. A suffix is present only when source evidence shows a real chart-group qualifier; no default suffix exists.

Approved non-age suffix terms are `plus` and `baby`. Age-range suffixes use only the template `{min}_{max}_{month|year}` and only when source evidence names the whole chart group by an age range. Concrete age intervals are never pre-approved in the prompt or design; the numbers come only from source evidence during extraction. Current approved product group terms are `upper`, `lower`, `belts`, `shoes`, `clothing`, `dresses`, `outerwear`, `underwear`, `swimwear`, `socks`, `hosiery`, `hats`, `gloves`, and `bras`. Lower-body clothing tables such as pants, skirts, shorts, trousers, jeans, and leggings use `lower` unless source evidence exposes a distinct standalone table whose meaning is not covered by `lower`.

The key must not include `size_chart`, `chart`, `product_measurement`, `product_measurements`, product ids, source-type names, brand names, coverage buckets, or diagnostic labels. Source row size values, including row-level age labels, bra sizes, or alpha sizes, are not chart-group suffixes. Semantic verification must reject alternative names for an already approved meaning and return feedback to the same action stage.

## Mechanical Guard Contract

Semantic verification owns source correctness and table accuracy, but Python code still owns mechanical invariants that do not require source interpretation.

`PromptScope` must fail when `source_type_allow_list` contains unknown source types or `stage_instruction_list` contains unknown stage keys.

`source_discover` must fail after semantic verification when status is neither `success` nor `failed`, when `status="success"` returns no candidates, when `status="failed"` returns candidates, when `status="failed"` has no concrete errors or canonical inventory evidence, when the result source type differs from the current source type, when one candidate has mismatched source type or source priority, when one candidate has empty source URL or title, when one artifact reference is missing or outside allowed run artifact roots, when two candidates in the same source type share one `size_group_key`, or when the returned `country_code_list` values violate the `priority_country_code` market-selection ladder. If requested product types are present, `product_type_hint_list` may be empty but any non-empty value must belong to the requested product-type list.

`table_extract` must fail after semantic verification when the result status is not `success`, one verified `SourceDiscovery` has no matching `TableExtraction`, one extra `TableExtraction` is returned, `source_type`, `source_url`, `source_title`, or `size_group_key` differs from the matching verified `SourceDiscovery`, one artifact reference is missing or outside allowed run artifact roots, the chart has no rows, one row has empty `size_label`, one row has no measurements, or one measurement has empty `name`, `unit`, `min_value`, or `max_value`.

`coverage_decide` must fail when `uncovered_product_type_list` contains a value outside the current requested product-type list.

`canonical_select` must fail when one selection points to no verified `TableExtraction`, repeats one `size_group_key`, has a source priority that differs from the source-type registry, or selects a source type different from the table extraction source type.

`source_type_summary` and final brand output must fail when their artifact paths point outside the result directory or to missing files.

## Production Runtime Boundary

Production runtime must not import or require subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state. Static prompts are repository artifacts consumed by future DBOS steps.

Every browser-backed stage must treat cookie banners, drawers, overlays, broad locators, and transient navigation errors as normal browser-interaction conditions. The stage must close or answer visible blockers before retrying one click, refine multi-match selectors through the current browser snapshot before retrying, and retry transient navigation failures such as `ERR_NETWORK_CHANGED` through the same configured browser before marking a source unavailable.

`DBOS_SYSTEM_DATABASE_URL` must be set before startup. It may use `postgresql://`, `postgres://`, or `sqlite://`. SQLite is allowed only when configured explicitly; DBOS defaults to local SQLite system storage when no system database URL is provided, and this workflow must reject that hidden fallback.

The default local private DataSource path is `.secret` under the project root. Container runtimes, including local Docker Compose and Kubernetes pods, must mount that DataSource read-only at `/input/.secret`, copy it at container startup into pod-local writable `/runtime/.secret`, and pass only `/runtime/.secret` to workflow code. `CODEX_HOME` must point to `/runtime/.secret/codex_profile` when that directory exists. Workflow code must not write to `/input/.secret`; mutable private DataSource prefixes are written back only by the platform after terminal workflow state. `openvpn/config.json` is required for production source loading, and the named `.ovpn` file must exist. `playwright_profile/**` and `codex_profile/**` are optional. When `playwright_profile/**` is absent, runtime starts from an empty browser profile. When `codex_profile/**` is absent, Codex authentication must come from the surrounding runtime environment.

The repository provides one standalone local compose profile independent of `marketplace-automation`: `vpn` starts an `openvpn` service, starts a `playwright-mcp` browser runtime service in the OpenVPN network namespace, and starts the workflow service in the normal compose network with an explicit SQLite DBOS system database under `/runtime`. The workflow image contains the installed project package; container runs must not bind-mount the repository checkout as writable runtime code. The Playwright MCP writable artifact namespace must be `/output/.playwright-mcp/current` so browser evidence can be written inside the shared workflow output root without allowing automatic Playwright MCP page or console artifacts beside root workflow outputs. Browser runtime mutable state, including persistent profile and generated MCP config, must stay under pod-local `/runtime` and must not be placed under `/output` only because browser evidence is written there.

The workflow process receives one `browser-vpn-runtime` Playwright MCP URL before the root DBOS workflow starts. DBOS stages receive only that run-level MCP URL. The workflow process must not run in the OpenVPN network namespace; dependency installation, DBOS, Codex, and non-browser network calls must use the normal network path. Stage prompts, stage code, and stage arguments must not customize profile paths, VPN paths, MCP commands, browser flags, locale, timezone, user agent, or stealth behavior. Those settings are owned by `browser-vpn-runtime`.

Static prompts for this project live under `brand_size_chart/prompt/template/`. Shared prompt fragments live under `brand_size_chart/prompt/template/partial/`. Root-level Markdown prompt copies under `brand_size_chart/prompt/*.md` are forbidden because they create a second prompt source of truth.

Browser evidence for this workflow is written under declared browser evidence write directories inside the current run output root. Chart artifacts, `result.json`, `verification.json`, audit JSON, and local evidence files derived from returned page data are written as declared by `Artifact Layout`. Stage owners must create declared chart and browser evidence directories before launching the Codex stage. Semantic verification for `brand-size-chart` reads current JSON artifacts as data and skips unrelated JSON artifact shapes after validating each parsed JSON value shape.
