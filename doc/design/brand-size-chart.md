# Brand Size Chart DBOS Workflow

## Scope

This repository owns a DBOS workflow container that parses one `brand_list`, uses one `secret` reference for external runtime credentials, and writes canonical `brand_size_chart` artifacts plus `brand_size_chart_audit` evidence.

## Determinism Boundary

The root DBOS workflow owns deterministic orchestration only. Browser access, filesystem writes, Codex prompt execution, and external IO belong to DBOS steps.

Real source discovery and table extraction are Codex-owned browser stages. Python code must not parse marketplace or brand pages into size-chart data and must not load source pages or source assets through non-browser request paths. The source discovery and table extraction stages must call Codex with configured browser access. Those stages must write browser-visible evidence artifacts and return schema-valid JSON that references those artifacts.

## Stage Workflow Contract

Each semantic stage is a bounded workflow with a main result and verification result. The main stage writes `<stage>/result.json`; verification writes `<stage>/verification.json` in the same directory. Verification failures are returned as feedback to the same main stage until the attempt limit is reached. Separate fix stages are forbidden.

`source_discovery` must build browser-visible source-surface inventory before it writes `discovered_source_list`. The inventory evidence must cover discovery queries, candidate URLs, opened URLs, accepted tables, duplicate or equivalent tables, rejected URLs, rejection reasons, and blocking browser errors for the requested source type. The result must contain every concrete unique table candidate found for that source type, not one aggregate page candidate. Inside one source type, one `size_group_key` may appear at most once in `discovered_source_list`; duplicate, equivalent, lower-priority-market, or rejected tables for the same `size_group_key` stay in the canonical inventory with exact reason codes and must not become separate source candidates.

`product_type_request_list` defines coverage targets and later-source-type continuation only. `official_brand_size_guide` and `official_seller_size_guide` must receive an empty product-type scope; they search all size-guide tables available on their non-product source surfaces. Product-type scope is passed only to source types that inspect concrete products. It must not filter `source_discovery` candidates, `accepted_tables`, or table extraction scope for an opened source surface. Concrete tables found inside the source-type boundary must be returned even when they do not cover any requested product type.

`priority_country_code` defines the market priority for source discovery. It is parsed from the workflow-run prompt by `workflow_run_prompt_apply` like `source_type_allow_list` and `product_type_request_list`; default value is `TR`. Every `SourceDiscovery` item must declare `country_code_list`. For each source type, `discovered_source_list` follows one strict ladder: if priority country tables exist, include only items whose `country_code_list` contains `priority_country_code`; otherwise, if global tables exist, include only items marked with `country_code_list=["GLOBAL"]`; otherwise include European consensus items marked with `country_code_list=["EU"]` only when evidence proves the relevant official European country tables do not differ. Conflicting European country tables make `source_discovery` fail with exact country codes, URLs, and `size_group_key` values.

`source_discovery` must not silently skip. An empty `discovered_source_list`, `status="skipped"`, missing inventory evidence, or incomplete browser loading is a critical incomplete stage result. The workflow retries it through the main-stage feedback loop and fails after the attempt limit instead of producing an empty successful source type.

`source_verification` is the verification half of `source_discovery`. It checks source-type completeness and source-type boundary, not only JSON shape or self-consistency. It may use the same browser runtime and may save its own evidence, but it must not repair the result.

Size-chart data may appear as an HTML table, page text, modal, rendered widget, PDF, image, embedded asset, product image, help section, FAQ section, Q&A section, seller answer, product details, or size recommendation block. These forms are universal across source types; source types differ only by authority, location, and applicability boundaries. A separate official asset source type is forbidden.

`official_brand_size_guide` covers official brand-owned non-product size-guide surfaces on the brand website. `official_seller_size_guide` covers official or authorized reseller or distributor non-product size-guide surfaces for the brand when the brand sells through an official seller in a relevant country; evidence must prove the seller is official or authorized.

`official_brand_product_page`, `official_marketplace_product_page`, and `official_marketplace_store` are product-type-scoped source types. When `product_type_request_list` is empty, the workflow must not run those source types. When `product_type_request_list` is present, each source discovery receives the current uncovered product-type list through `PromptScope`. After each source type, a semantic `coverage_decision` stage determines which requested product types are explicitly covered by verified tables; only still-uncovered product types are passed to later source types.

## Artifact Layout

Canonical brand output is written to `brand_size_chart/brand/<parsed_brand_key>/manifest.json`. Size chart data is written to `brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json`. Audit evidence is written under `brand_size_chart_audit/brand/<parsed_brand_key>/`.

Every main stage writes `<stage>/result.json`, and its verification writes `<stage>/verification.json` in the same stage directory. Verification stages do not own a separate artifact namespace.

The root run result is written to `brand_size_chart_audit/run/result.json`. The result model carries `status`, `message`, and `error_list` directly; separate terminal-result artifacts are forbidden.

## Size Group Key Contract

Real size-chart table keys use only `{sex}_{product_group_or_type}` or `{sex}_{sex_suffix}_{product_group_or_type}`. `sex` is limited to `women`, `men`, `girls`, `boys`, `unisex`, and `unisex_child`. A suffix is present only when source evidence shows a real chart-group qualifier; no default suffix exists.

Approved non-age suffix terms are `plus` and `baby`. Age-range suffixes use only the template `{min}_{max}_{month|year}` and only when source evidence names the whole chart group by an age range. Concrete age intervals are never pre-approved in the prompt or design; the numbers come only from source evidence during extraction. Current approved product group terms are `upper`, `lower`, `pants_skirts`, `belts`, `shoes`, `clothing`, `dresses`, `outerwear`, `underwear`, `swimwear`, `socks`, `hosiery`, `hats`, `gloves`, and `bras`.

The key must not include `size_chart`, `chart`, `product_measurement`, `product_measurements`, product ids, source-type names, brand names, coverage buckets, or diagnostic labels. Source row size values, including row-level age labels, bra sizes, or alpha sizes, are not chart-group suffixes. Semantic verification must reject alternative names for an already approved meaning and return feedback to the same main stage.

## Mechanical Guard Contract

Semantic verification owns source correctness and table accuracy, but Python code still owns mechanical invariants that do not require source interpretation.

`PromptScope` must fail when `source_type_allow_list` contains unknown source types or `stage_instruction_list` contains unknown stage keys.

`source_discovery` must fail after semantic verification when status is not `success`, no candidates were returned, the result source type differs from the current source type, one candidate has mismatched source type or source priority, one candidate has empty source URL or title, one evidence reference is missing or outside the result directory, two candidates in the same source type share one `size_group_key`, or the returned `country_code_list` values violate the `priority_country_code` market-selection ladder. If requested product types are present, `product_type_hint_list` may be empty but any non-empty value must belong to the requested product-type list.

`table_extraction` must fail after semantic verification when `source_type`, `source_url`, or `size_group_key` differs from the verified `SourceDiscovery`, one evidence reference is missing or outside the result directory, the chart has no rows, one row has empty `size_label`, one row has no measurements, or one measurement has empty `name`, `unit`, `min_value`, or `max_value`.

`coverage_decision` must fail when `uncovered_product_type_list` contains a value outside the current requested product-type list.

`canonical_selection` must fail when one selection points to no verified `TableExtraction`, repeats one `size_group_key`, has a source priority that differs from the source-type registry, or selects a source type different from the table extraction source type.

`source_type_summary` and final brand output must fail when their artifact paths point outside the result directory or to missing files.

## Production Runtime Boundary

Production runtime must not import or require subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state. Static prompts are repository artifacts consumed by future DBOS steps.

`DBOS_SYSTEM_DATABASE_URL` must be set before startup. It may use `postgresql://`, `postgres://`, or `sqlite://`. SQLite is allowed only when configured explicitly; DBOS defaults to local SQLite system storage when no system database URL is provided, and this workflow must reject that hidden fallback.

The default local private DataSource path is `.secret` under the project root. Container runtimes, including local Docker Compose and Kubernetes pods, must mount that DataSource read-only at `/input/.secret`, copy it at container startup into pod-local writable `/runtime/.secret`, and pass only `/runtime/.secret` to workflow code. `CODEX_HOME` must point to `/runtime/.secret/codex_profile` when that directory exists. Workflow code must not write to `/input/.secret`; mutable private DataSource prefixes are written back only by the platform after terminal workflow state. `openvpn/config.json` is required for production source loading, and the named `.ovpn` file must exist. `playwright_profile/**` and `codex_profile/**` are optional. When `playwright_profile/**` is absent, runtime starts from an empty browser profile. When `codex_profile/**` is absent, Codex authentication must come from the surrounding runtime environment.

The repository provides one standalone local compose profile independent of `marketplace-automation`: `vpn` starts an `openvpn` service, starts a `playwright-mcp` browser runtime service in the OpenVPN network namespace, and starts the workflow service in the normal compose network with an explicit SQLite DBOS system database under `/runtime`. The workflow image contains the installed project package; container runs must not bind-mount the repository checkout as writable runtime code.

The workflow process receives one `browser-vpn-runtime` Playwright MCP URL before the root DBOS workflow starts. DBOS stages receive only that run-level MCP URL. The workflow process must not run in the OpenVPN network namespace; dependency installation, DBOS, Codex, and non-browser network calls must use the normal network path. Stage prompts, stage code, and stage arguments must not customize profile paths, VPN paths, MCP commands, browser flags, locale, timezone, user agent, or stealth behavior. Those settings are owned by `browser-vpn-runtime`.

Codex subprocesses inside the workflow container run without Codex filesystem sandboxing. The workflow container and its mounted run directories are the execution boundary, and Codex must be able to write stage artifacts and evidence without `bubblewrap` or nested namespace support. The browser used by Codex remains the external Playwright MCP URL owned by `browser-vpn-runtime`; disabling Codex filesystem sandboxing must not move Codex itself into the VPN network path.
