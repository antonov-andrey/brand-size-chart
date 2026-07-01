"""Codex-backed semantic stage execution."""

import os
import signal
import subprocess
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from brand_size_chart.io import json_artifact_write

CODEX_EXEC_INACTIVITY_TIMEOUT_SECONDS = 900
CODEX_EXEC_POLL_SECONDS = 5
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
    browser_runtime_mcp_url: str = "",
    model_class: type[_ResultModelT],
    prompt_text: str,
    result_dir: Path,
    stage_dir: Path,
    stage_name: str,
) -> _ResultModelT:
    """Run one Codex semantic stage and validate its JSON result.

    Args:
        allow_user_config: Whether to load the configured Codex profile and MCP tools.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL for browser stages.
        model_class: Pydantic model class for the stage result.
        prompt_text: Stage prompt text.
        result_dir: Root result directory used as Codex working directory.
        stage_dir: Stage artifact directory.
        stage_name: Stage name used for diagnostic artifact names.

    Returns:
        Validated stage result.

    Raises:
        CodexStageError: If Codex exits with an error or returns invalid JSON.
    """
    result_dir = result_dir.resolve()
    stage_dir = stage_dir.resolve()
    stage_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_dir = stage_dir / "diagnostics" / stage_name
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = diagnostic_dir / "prompt.md"
    output_path = diagnostic_dir / "codex_output.json"
    schema_path = diagnostic_dir / "schema.json"
    stderr_path = diagnostic_dir / "stderr.txt"
    event_path = diagnostic_dir / "event.jsonl"
    for terminal_path in [output_path, stderr_path, event_path]:
        terminal_path.unlink(missing_ok=True)
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
        "--dangerously-bypass-approvals-and-sandbox",
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
        if not browser_runtime_mcp_url:
            raise CodexStageError(f"Codex browser stage {stage_name} has no browser/VPN runtime MCP URL.")
        browser_config_args = _playwright_mcp_config_arg_list_get(
            browser_runtime_mcp_url=browser_runtime_mcp_url,
        )
        for tool_name in PLAYWRIGHT_MCP_APPROVED_TOOL_LIST:
            browser_config_args.extend(
                [
                    "-c",
                    f'mcp_servers.playwright.tools.{tool_name}.approval_mode="approve"',
                ]
            )
        command[command.index("--ignore-rules") : command.index("--ignore-rules")] = browser_config_args
    process = _codex_subprocess_run(
        command,
        input=prompt_path.read_text(encoding="utf-8"),
        stage_dir=stage_dir,
    )
    event_path.write_text(process.stdout, encoding="utf-8")
    stderr_path.write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise CodexStageError(f"Codex stage {stage_name} failed with exit code {process.returncode}.")
    try:
        return model_class.model_validate_json(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CodexStageError(f"Codex stage {stage_name} returned invalid JSON: {exc}") from exc


def _playwright_mcp_config_arg_list_get(*, browser_runtime_mcp_url: str) -> list[str]:
    """Return Codex config args for the run-level browser/VPN MCP server.

    Args:
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.

    Returns:
        Codex `-c` argument list.
    """

    return [
        "-c",
        f"mcp_servers.playwright.url={browser_runtime_mcp_url!r}",
    ]


def _path_activity_marker_get(path: Path) -> int:
    """Return activity marker for one path tree.

    Args:
        path: Path to scan.

    Returns:
        Integer marker that changes when files under the path change.
    """
    try:
        path_stat = path.stat()
    except OSError:
        return 0
    activity_marker = path_stat.st_mtime_ns + path_stat.st_size
    for child_path in path.rglob("*"):
        try:
            child_stat = child_path.stat()
        except OSError:
            continue
        activity_marker += child_stat.st_mtime_ns + child_stat.st_size + 1
    return activity_marker


def _codex_subprocess_run(command: list[str], *, input: str, stage_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run `codex exec` with an artifact-activity inactivity timeout.

    Args:
        command: Codex command argv.
        input: Prompt text sent to Codex stdin.
        stage_dir: Stage artifact directory watched for progress.

    Returns:
        Completed process with captured stdout and stderr.
    """
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    communicate_input: str | None = input
    inactivity_seconds = 0
    output_path = _codex_output_path_get(command)
    stage_activity_marker = _path_activity_marker_get(stage_dir)
    while True:
        try:
            stdout, stderr = process.communicate(
                input=communicate_input,
                timeout=CODEX_EXEC_POLL_SECONDS,
            )
            if process.returncode is None:
                return subprocess.CompletedProcess(args=command, returncode=1, stdout=stdout, stderr=stderr)
            return subprocess.CompletedProcess(
                args=command, returncode=process.returncode, stdout=stdout, stderr=stderr
            )
        except subprocess.TimeoutExpired:
            communicate_input = None
            if _codex_completion_output_exist(output_path=output_path, stage_dir=stage_dir):
                stdout, stderr = _process_group_terminate(process)
                return subprocess.CompletedProcess(args=command, returncode=0, stdout=stdout, stderr=stderr)
            current_stage_activity_marker = _path_activity_marker_get(stage_dir)
            if current_stage_activity_marker != stage_activity_marker:
                stage_activity_marker = current_stage_activity_marker
                inactivity_seconds = 0
                continue
            inactivity_seconds += CODEX_EXEC_POLL_SECONDS
            if inactivity_seconds < CODEX_EXEC_INACTIVITY_TIMEOUT_SECONDS:
                continue
            _process_group_kill(process)
            stdout, stderr = process.communicate()
            timeout_stderr = (
                f"{stderr}\nCodex exec timed out after {CODEX_EXEC_INACTIVITY_TIMEOUT_SECONDS} seconds "
                "without stage artifact activity.\n"
            )
            return subprocess.CompletedProcess(args=command, returncode=124, stdout=stdout, stderr=timeout_stderr)


def _codex_completion_output_exist(*, output_path: Path | None, stage_dir: Path) -> bool:
    """Return whether Codex wrote final output and reported turn completion.

    Args:
        output_path: `codex exec --output-last-message` path.
        stage_dir: Stage artifact directory watched for diagnostics.

    Returns:
        Whether the stage has enough terminal artifacts to stop a stuck process tree.
    """
    if output_path is None or not output_path.is_file() or output_path.stat().st_size == 0:
        return False
    for event_path in stage_dir.glob("diagnostics/*/event.jsonl"):
        if _file_tail_contain(event_path=event_path, needle='"type":"turn.completed"'):
            return True
    return False


def _codex_output_path_get(command: list[str]) -> Path | None:
    """Return the `--output-last-message` path from one Codex command.

    Args:
        command: Codex command argv.

    Returns:
        Output path when the command declares one.
    """
    if "--output-last-message" not in command:
        return None
    index = command.index("--output-last-message") + 1
    if index >= len(command):
        return None
    return Path(command[index])


def _file_tail_contain(*, event_path: Path, needle: str) -> bool:
    """Return whether one file tail contains a marker string.

    Args:
        event_path: File path to inspect.
        needle: Marker string.

    Returns:
        Whether the marker exists in the recent file tail.
    """
    try:
        with event_path.open("rb") as file:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(max(0, size - 20000))
            return needle.encode() in file.read()
    except OSError:
        return False


def _process_group_kill(process: subprocess.Popen[str]) -> None:
    """Kill one subprocess process group.

    Args:
        process: Process whose group must be killed.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()


def _process_group_terminate(process: subprocess.Popen[str]) -> tuple[str, str]:
    """Terminate one subprocess process group and collect output.

    Args:
        process: Process whose group must be terminated.

    Returns:
        Captured stdout and stderr.
    """
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return process.communicate()
    except OSError:
        process.terminate()
    try:
        return process.communicate(timeout=CODEX_EXEC_POLL_SECONDS)
    except subprocess.TimeoutExpired:
        _process_group_kill(process)
        return process.communicate()


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
