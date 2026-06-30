# Brand Size Chart DBOS Workflow

## Scope

This repository owns a DBOS workflow container that parses one `brand_list`, uses one `secret` reference for external runtime credentials, and writes canonical `brand_size_chart` artifacts plus `brand_size_chart_audit` evidence.

## Determinism Boundary

The root DBOS workflow owns deterministic orchestration only. Browser access, filesystem writes, Codex prompt execution, and external IO belong to DBOS steps.

Real source discovery and table extraction are Codex-owned browser stages. Python code must not parse marketplace or brand pages into size-chart data and must not load source pages or source assets through non-browser request paths. The source discovery and table extraction stages must call Codex with configured browser access. Those stages must write browser-visible evidence artifacts and return schema-valid JSON that references those artifacts.

## Stage Workflow Contract

Each semantic stage is a bounded workflow with a main result and verification result. The main stage writes `<stage>/result.json`; verification writes `<stage>/verification.json` in the same directory. Verification failures are returned as feedback to the same main stage until the attempt limit is reached. Separate fix stages are forbidden.

`source_discovery` must build browser-visible source-surface inventory before it returns candidates. The inventory evidence must cover discovery queries, candidate URLs, opened URLs, accepted tables, rejected URLs, rejection reasons, and blocking browser errors for the requested source type. The result must contain every concrete table candidate found for that source type, not one aggregate page candidate.

`source_discovery` must not silently skip. An empty `discovered_source_list`, `status="skipped"`, missing inventory evidence, or incomplete browser loading is a critical incomplete stage result. The workflow retries it through the main-stage feedback loop and fails after the attempt limit instead of producing an empty successful source type.

`source_verification` is the verification half of `source_discovery`. It checks source-type completeness and source-type boundary, not only JSON shape or self-consistency. It may use the same browser runtime and may save its own evidence, but it must not repair the result.

Size-chart data may appear as an HTML table, page text, modal, rendered widget, PDF, image, embedded asset, product image, help section, FAQ section, Q&A section, seller answer, product details, or size recommendation block. These forms are universal across source types; source types differ only by authority, location, and applicability boundaries. A separate official asset source type is forbidden.

`official_brand_size_guide` covers official brand-owned non-product size-guide surfaces on the brand website. `official_seller_size_guide` covers official or authorized reseller or distributor non-product size-guide surfaces for the brand when the brand sells through an official seller in a relevant country; evidence must prove the seller is official or authorized.

`official_brand_product_page`, `official_marketplace_product_page`, and `official_marketplace_store` are product-type-scoped source types. When `product_type_request_list` is empty, the workflow must not run those source types. When `product_type_request_list` is present, each source discovery receives the current uncovered product-type list through `PromptScope`. After each source type, a semantic `coverage_decision` stage determines which requested product types are explicitly covered by verified tables; only still-uncovered product types are passed to later source types.

## Artifact Layout

Canonical brand output is written to `brand_size_chart/brand/<parsed_brand_key>/manifest.json`. Size chart data is written to `brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json`. Audit evidence is written under `brand_size_chart_audit/brand/<parsed_brand_key>/`.

Every main stage writes `<stage>/result.json`, and its verification writes `<stage>/verification.json` in the same stage directory. Verification stages do not own a separate artifact namespace.

The root run result is written to `brand_size_chart_audit/run/result.json`. The result model carries `status`, `message`, and `error_list` directly; separate terminal-result artifacts are forbidden.

## Production Runtime Boundary

Production runtime must not import or require subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state. Static prompts are repository artifacts consumed by future DBOS steps.

`DBOS_SYSTEM_DATABASE_URL` must be set before startup. It may use `postgresql://`, `postgres://`, or `sqlite://`. SQLite is allowed only when configured explicitly; DBOS defaults to local SQLite system storage when no system database URL is provided, and this workflow must reject that hidden fallback.
