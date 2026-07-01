# Repository Guidelines

## DBOS Runtime
- Configure DBOS only inside `brand_size_chart.entrypoint.main`.
- Launch order must stay: build config, call `DBOS.listen_queues(...)`, call `DBOS.launch()`, register the queue, then start the root workflow.
- The browser/VPN runtime is an external runtime capability for this workflow process; `brand_size_chart.entrypoint.main` must receive its MCP URL and pass only that URL into DBOS stages.
- Workflow functions must stay deterministic; filesystem, browser, network, Codex, and secret access must happen only in DBOS steps or outside DBOS before workflow start.
- Production runtime must not depend on subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state.
- The workflow process must not run in the OpenVPN network namespace; only the browser runtime process may use the VPN network path.
- Stage code, stage prompts, and stage arguments must not customize browser/VPN runtime internals such as profile path, VPN path, MCP command, browser flags, locale, timezone, user agent, or stealth behavior.

## Artifacts
- Generated JSON schemas must come from Pydantic v2 models in `brand_size_chart.model`.
- Runtime chart output lives under `brand_size_chart/brand/<parsed_brand_key>/`.
- Audit output lives under `brand_size_chart_audit/brand/<parsed_brand_key>/`.
- Static prompts live under `brand_size_chart/prompt/` and must not contain runtime tracker protocol.
