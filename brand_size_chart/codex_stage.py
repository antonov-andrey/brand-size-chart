"""Codex-backed semantic stage execution."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Literal
from typing import TypeVar

from pydantic import BaseModel

from brand_size_chart.io import json_artifact_write

CODEX_EXEC_TIMEOUT_SECONDS = 900
CODEX_STAGE_SYSTEM_PROMPT = (
    "You are a schema-bound workflow stage inside brand-size-chart. "
    "Return only a JSON object that matches the supplied output schema. "
    "Do not edit files. Read the referenced evidence files and preserve all source data."
)
CODEX_BROWSER_STAGE_SYSTEM_PROMPT = (
    "You are a Codex browser workflow stage inside brand-size-chart. "
    "Use the configured browser tools for every source-page and source-data load. "
    "All non-browser loading mechanisms are forbidden for source data; curl, requests, wget, and direct HTTP are "
    "examples, not an exhaustive list. "
    "You may write evidence files only under the stage artifact directory named in the prompt. "
    "Do not emit progress text. Return only the final JSON object that matches the supplied output schema."
)
PLAYWRIGHT_MCP_APPROVED_TOOL_LIST = [
    "browser_click",
    "browser_evaluate",
    "browser_navigate",
    "browser_resize",
    "browser_snapshot",
    "browser_tabs",
]
_ResultModelT = TypeVar("_ResultModelT", bound=BaseModel)


class CodexStageError(RuntimeError):
    """Raised when one Codex semantic stage fails."""


def codex_stage_run(
    *,
    allow_user_config: bool = False,
    browser_runtime_data_source_path: Path | None = None,
    model_class: type[_ResultModelT],
    prompt_text: str,
    result_dir: Path,
    sandbox_mode: Literal["read-only", "workspace-write"] = "read-only",
    stage_dir: Path,
    stage_name: str,
) -> _ResultModelT:
    """Run one Codex semantic stage and validate its JSON result.

    Args:
        allow_user_config: Whether to load the configured Codex profile and MCP tools.
        browser_runtime_data_source_path: Browser/VPN runtime DataSource path for browser stages.
        model_class: Pydantic model class for the stage result.
        prompt_text: Stage prompt text.
        result_dir: Root result directory used as Codex working directory.
        sandbox_mode: Codex filesystem sandbox for the stage.
        stage_dir: Stage artifact directory.
        stage_name: Stage name used for diagnostic artifact names.

    Returns:
        Validated stage result.

    Raises:
        CodexStageError: If Codex exits with an error or returns invalid JSON.
    """
    stage_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_dir = stage_dir / "diagnostics" / stage_name
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = diagnostic_dir / "prompt.md"
    output_path = diagnostic_dir / "codex_output.json"
    schema_path = diagnostic_dir / "schema.json"
    stderr_path = diagnostic_dir / "stderr.txt"
    event_path = diagnostic_dir / "event.jsonl"
    json_artifact_write(schema_path, _codex_output_schema_get(model_class))
    system_prompt = CODEX_BROWSER_STAGE_SYSTEM_PROMPT if allow_user_config else CODEX_STAGE_SYSTEM_PROMPT
    prompt_path.write_text(f"{system_prompt}\n\n{prompt_text}\n", encoding="utf-8")
    command = [
        "codex",
        "exec",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "--json",
        "--sandbox",
        sandbox_mode,
        "--ephemeral",
        "--ignore-user-config",
        "-c",
        'approval_policy="never"',
        "--ignore-rules",
        "--skip-git-repo-check",
        "--cd",
        str(result_dir),
        "-",
    ]
    if allow_user_config:
        if browser_runtime_data_source_path is None:
            raise CodexStageError(f"Codex browser stage {stage_name} has no browser/VPN runtime DataSource path.")
        browser_config_args = _playwright_mcp_config_arg_list_get(
            browser_runtime_data_source_path=browser_runtime_data_source_path,
            stage_dir=stage_dir,
        )
        for tool_name in PLAYWRIGHT_MCP_APPROVED_TOOL_LIST:
            browser_config_args.extend(
                [
                    "-c",
                    f'mcp_servers.playwright.tools.{tool_name}.approval_mode="approve"',
                ]
            )
        command[command.index("--ignore-rules") : command.index("--ignore-rules")] = browser_config_args
    process = subprocess.run(
        command,
        check=False,
        input=prompt_path.read_text(encoding="utf-8"),
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        timeout=CODEX_EXEC_TIMEOUT_SECONDS,
    )
    event_path.write_text(process.stdout, encoding="utf-8")
    stderr_path.write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise CodexStageError(f"Codex stage {stage_name} failed with exit code {process.returncode}.")
    try:
        return model_class.model_validate_json(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CodexStageError(f"Codex stage {stage_name} returned invalid JSON: {exc}") from exc


def _playwright_mcp_config_arg_list_get(*, browser_runtime_data_source_path: Path, stage_dir: Path) -> list[str]:
    """Return Codex config args for the browser/VPN runtime-owned Playwright MCP server.

    Args:
        browser_runtime_data_source_path: Browser/VPN runtime DataSource path.
        stage_dir: Stage artifact directory.

    Returns:
        Codex `-c` argument list.
    """

    browser_runtime_arg_list = [
        "-m",
        "browser_vpn_runtime.playwright_mcp",
        "--data-source-path",
        str(browser_runtime_data_source_path),
        "--persistent-profile-path",
        str(stage_dir / ".browser-vpn-runtime" / "playwright_profile"),
        "--output-dir",
        str(stage_dir / ".playwright-mcp"),
    ]
    return [
        "-c",
        f"mcp_servers.playwright.command={json.dumps(sys.executable)}",
        "-c",
        f"mcp_servers.playwright.args={json.dumps(browser_runtime_arg_list)}",
    ]


def _codex_output_schema_get(model_class: type[BaseModel]) -> dict[str, object]:
    """Return a strict JSON schema accepted by `codex exec --output-schema`.

    Args:
        model_class: Pydantic model class.

    Returns:
        Strict JSON schema.
    """
    schema = model_class.model_json_schema()
    _schema_strict_normalize(schema)
    return schema


def _schema_strict_normalize(schema: object) -> None:
    """Normalize one JSON schema tree in place for strict structured output.

    Args:
        schema: JSON schema node.
    """
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            schema["required"] = sorted(properties)
            schema["additionalProperties"] = False
        for value in schema.values():
            _schema_strict_normalize(value)
        return
    if isinstance(schema, list):
        for value in schema:
            _schema_strict_normalize(value)
