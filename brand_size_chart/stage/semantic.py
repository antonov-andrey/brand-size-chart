"""Common semantic stage lifecycle owner."""

from pathlib import Path
from typing import cast

from pydantic import BaseModel

from brand_size_chart.artifact import ArtifactLayout, JsonArtifactWriter
from brand_size_chart.model import PromptScope, StageVerification
from brand_size_chart.stage.base import CodexStageRun, MAX_STAGE_ATTEMPT_COUNT, ResultErrorListGet, _ResultModelT
from brand_size_chart.stage.base import prompt_file_text_get


def stage_prompt_text_get(
    *,
    attempt_index: int,
    draft_result_json_text: str,
    feedback_list: list[str],
    prompt_context: str,
    prompt_name: str,
    prompt_scope: PromptScope | None,
    previous_result_json_text: str,
    stage_key: str,
) -> str:
    """Build one Codex stage prompt from a static prompt file.

    Args:
        attempt_index: Stage attempt index.
        draft_result_json_text: Deterministic draft result JSON.
        feedback_list: Verification feedback from previous attempts.
        prompt_context: Stage-specific context.
        prompt_name: Static prompt file name stem.
        prompt_scope: Parsed workflow-run prompt scope.
        previous_result_json_text: Previous attempt result JSON, when present.
        stage_key: Stable stage key.

    Returns:
        Complete prompt text.
    """

    feedback_text = "\n".join(f"- {feedback}" for feedback in feedback_list)
    shared_instruction = prompt_scope.shared_instruction if prompt_scope else ""
    stage_instruction_list = [
        stage_instruction.instruction
        for stage_instruction in (prompt_scope.stage_instruction_list if prompt_scope else [])
        if stage_instruction.stage_key == stage_key
    ]
    stage_instruction_text = "\n".join(f"- {stage_instruction}" for stage_instruction in stage_instruction_list)
    return (
        f"{prompt_file_text_get(prompt_name)}\n\n"
        f"Stage: {stage_key}\n"
        f"Attempt: {attempt_index}\n\n"
        f"Workflow run shared instruction:\n{shared_instruction if shared_instruction else '- none'}\n\n"
        f"Stage-specific instruction:\n{stage_instruction_text if stage_instruction_text else '- none'}\n\n"
        f"{prompt_context}\n\n"
        f"Draft stage result JSON:\n{draft_result_json_text}\n\n"
        f"Previous stage result JSON:\n{previous_result_json_text if previous_result_json_text else '- none'}\n\n"
        f"Verification feedback from previous attempt:\n{feedback_text if feedback_text else '- none'}\n"
    )


class SemanticStage:
    """Run one semantic stage with Codex verification and mechanical guards."""

    def __init__(
        self,
        *,
        browser_access: bool = False,
        browser_runtime_mcp_url: str = "",
        codex_stage_run_callable: CodexStageRun,
        prompt_name: str,
        prompt_scope: PromptScope | None,
        result_dir: Path,
        stage_dir: Path,
        stage_key: str,
    ) -> None:
        """Store stable stage runtime dependencies.

        Args:
            browser_access: Whether Codex may use browser/MCP tools and write evidence artifacts.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL for browser stages.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_name: Static prompt file name stem.
            prompt_scope: Parsed prompt scope relevant to this stage.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_key: Stable stage key.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._artifact_writer = JsonArtifactWriter()
        self._browser_access = browser_access
        self._browser_runtime_mcp_url = browser_runtime_mcp_url
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_name = prompt_name
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._stage_dir = stage_dir
        self._stage_key = stage_key

    def run(
        self,
        *,
        draft_result: _ResultModelT,
        model_class: type[_ResultModelT],
        prompt_context: str,
        result_error_list_get: ResultErrorListGet[_ResultModelT] | None = None,
    ) -> _ResultModelT:
        """Run one main stage plus its verification stage.

        Args:
            draft_result: Deterministic draft result used as initial stage input.
            model_class: Pydantic result model.
            prompt_context: Stage-specific prompt context.
            result_error_list_get: Optional mechanical validator for a semantically verified result.

        Returns:
            Verified stage result.

        Raises:
            RuntimeError: If verification does not pass within the retry limit.
        """

        feedback_list: list[str] = []
        draft_result_json_text = draft_result.model_dump_json(indent=2)
        previous_result_json_text = ""
        self._stage_dir.mkdir(parents=True, exist_ok=True)
        for attempt_index in range(1, MAX_STAGE_ATTEMPT_COUNT + 1):
            result = cast(
                _ResultModelT,
                self._codex_stage_run(
                    allow_user_config=self._browser_access,
                    browser_runtime_mcp_url=self._browser_runtime_mcp_url,
                    model_class=model_class,
                    prompt_text=stage_prompt_text_get(
                        attempt_index=attempt_index,
                        draft_result_json_text=draft_result_json_text,
                        feedback_list=feedback_list,
                        prompt_context=prompt_context,
                        prompt_name=self._prompt_name,
                        prompt_scope=self._prompt_scope,
                        previous_result_json_text=previous_result_json_text,
                        stage_key=self._stage_key,
                    ),
                    result_dir=self._result_dir,
                    stage_dir=self._stage_dir,
                    stage_name=self._stage_key,
                ),
            )
            result_path = self._artifact_layout.stage_result_path(self._stage_dir)
            self._artifact_writer.write(result_path, result)
            artifact_path_list = [self._artifact_layout.artifact_path(result_path)]
            previous_result_json_text = result.model_dump_json(indent=2)
            verification = self._verification_get(
                artifact_path_list=artifact_path_list,
                prompt_context=prompt_context,
                result=result,
            )
            if verification.status == "success" and result_error_list_get:
                result_error_list = result_error_list_get(result)
                if result_error_list:
                    verification = self._guard_verification_get(
                        artifact_path_list=artifact_path_list,
                        error_list=result_error_list,
                    )
            self._artifact_writer.write(self._artifact_layout.stage_verification_path(self._stage_dir), verification)
            if verification.status == "success":
                return result
            feedback_list = verification.feedback_list or verification.error_list

        feedback_text = "; ".join(feedback_list)
        if feedback_text:
            raise RuntimeError(
                f"Stage {self._stage_key} did not pass verification after "
                f"{MAX_STAGE_ATTEMPT_COUNT} attempts: {feedback_text}"
            )
        raise RuntimeError(
            f"Stage {self._stage_key} did not pass verification after {MAX_STAGE_ATTEMPT_COUNT} attempts."
        )

    def _guard_verification_get(self, *, artifact_path_list: list[str], error_list: list[str]) -> StageVerification:
        """Return failed verification for mechanical stage-result validation.

        Args:
            artifact_path_list: Artifact paths produced by the main stage.
            error_list: Mechanical validation errors.

        Returns:
            Failed stage verification.
        """

        return StageVerification(
            artifact_path_list=artifact_path_list,
            error_list=error_list,
            feedback_list=error_list,
            message="Stage mechanical validation failed.",
            stage_key=self._stage_key,
            status="failed",
        )

    def _verification_get(
        self, *, artifact_path_list: list[str], prompt_context: str, result: BaseModel
    ) -> StageVerification:
        """Return semantic verification for one stage result.

        Args:
            artifact_path_list: Artifact paths produced by the main stage.
            prompt_context: Stage prompt context.
            result: Main stage result.

        Returns:
            Stage verification.
        """

        draft_verification = StageVerification(
            artifact_path_list=artifact_path_list,
            message="Stage verification passed.",
            stage_key=self._stage_key,
            status="success",
        )
        verification_prompt = (
            f"{prompt_file_text_get('verification')}\n\n"
            f"Stage: {self._stage_key}\n\n"
            "You must return a StageVerification JSON object only. Do not fail because structured output prevents "
            "progress messages. Use browser tools silently only when source evidence must be re-opened; otherwise "
            "verify from the artifact files listed below. If the stage result is schema-valid, evidence-backed, and "
            "semantically consistent with the prompt context, return the supplied draft verification success.\n\n"
            f"{prompt_context}\n\n"
            f"Stage result JSON:\n{result.model_dump_json(indent=2)}\n\n"
            f"Draft verification JSON:\n{draft_verification.model_dump_json(indent=2)}\n"
        )
        return cast(
            StageVerification,
            self._codex_stage_run(
                allow_user_config=self._browser_access,
                browser_runtime_mcp_url=self._browser_runtime_mcp_url,
                model_class=StageVerification,
                prompt_text=verification_prompt,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_name=f"{self._stage_key}_verification",
            ),
        )
