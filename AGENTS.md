# Repository Guidelines

## DBOS Runtime
- Configure DBOS only inside `brand_size_chart.entrypoint.main`.
- Launch order must stay: build config, call `DBOS.listen_queues(...)`, call `DBOS.launch()`, register the queue, then start the root workflow.
- Workflow functions must stay deterministic; filesystem, browser, network, Codex, and secret access must happen only in DBOS steps or outside DBOS before workflow start.
- Production runtime must not depend on subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state.

## Artifacts
- Generated JSON schemas must come from Pydantic v2 models in `brand_size_chart.model`.
- Runtime chart output lives under `brand_size_chart/brand/<parsed_brand_key>/`.
- Audit output lives under `brand_size_chart_audit/brand/<parsed_brand_key>/`.
- Static prompts live under `brand_size_chart/prompt/` and must not contain runtime tracker protocol.
