# Repository Guidelines

## Scope
- This project owns the `brand-size-chart` workflow-container domain logic.
- Shared workflow-container authoring rules belong to `workflow-container-developer/doc/design/workflow-container-authoring.md`.
- Browser/VPN runtime behavior belongs to `browser-vpn-runtime`.
- This project must not depend on `workflow-container-developer` at runtime.

## DBOS Runtime
- Configure DBOS only inside `brand_size_chart.entrypoint.main`.
- Launch order must stay: build config, call `DBOS.listen_queues(...)`, call `DBOS.launch()`, register the queue, then start the root workflow.
- The browser/VPN runtime is an external runtime capability for this workflow process; `brand_size_chart.entrypoint.main` must receive its MCP URL and pass only that URL into DBOS stages.
- Production runtime must not depend on subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state.
- The workflow process must not run in the OpenVPN network namespace; only the browser runtime process may use the VPN network path.
- Stage code, stage prompts, and stage arguments must not customize browser/VPN runtime internals such as profile path, VPN path, MCP command, browser flags, locale, timezone, user agent, or stealth behavior.

## Artifacts
- Generated JSON schemas must come from Pydantic v2 models in `brand_size_chart.model`.
- Runtime chart output lives under `brand_size_chart/brand/<parsed_brand_key>/`.
- Audit output lives under `brand_size_chart_audit/brand/<parsed_brand_key>/`.
- Static prompts live under `brand_size_chart/prompt/template/` with shared partials under `brand_size_chart/prompt/template/partial/`.
- Root-level Markdown prompt copies under `brand_size_chart/prompt/*.md` are forbidden.
- Static prompts must not contain runtime tracker protocol.
