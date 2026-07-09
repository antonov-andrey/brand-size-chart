"""Shared contracts for semantic workflow stages."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from workflow_container_runtime.artifact import ArtifactMaterializationPolicy, ArtifactMaterializer, JsonArtifactWriter
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import (
    CodexStageRun,
    MAX_STAGE_ATTEMPT_COUNT,
    StageVerificationResult,
    stage_input_path_get,
    stage_result_path_get,
    stage_verification_path_get,
)

from brand_size_chart.model import PromptScope

STAGE_KEY_SET = frozenset(
    {
        "canonical_select",
        "coverage_decide",
        "source_discover",
        "table_extract",
        "workflow_run_prompt_apply",
    }
)


@dataclass(frozen=True)
class VerifiedCodexStageConfig:
    """Run-local configuration for one verified Codex stage."""

    prompt_context: BaseModel
    result_dir: Path
    stage_dir: Path
    stage_key: str
    browser_runtime_mcp_url: str = ""


class VerifiedCodexStageRunner:
    """Minimal brand-local verified stage runner compatible with current tests."""

    def __init__(
        self,
        *,
        codex_stage_run_callable: CodexStageRun,
        prompt_renderer: PromptRenderer | None = None,
    ) -> None:
        """Store the Codex runner and prompt renderer.

        Args:
            codex_stage_run_callable: Stage action and verification execution boundary.
            prompt_renderer: Optional shared prompt renderer.
        """

        self._artifact_writer = JsonArtifactWriter()
        self._artifact_materialization_policy = ArtifactMaterializationPolicy()
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_renderer = prompt_renderer or PromptRenderer()

    def run(
        self,
        *,
        config: VerifiedCodexStageConfig,
        mechanical_validate: Callable[[BaseModel], None],
        model_class: type[BaseModel],
    ) -> BaseModel:
        """Run one verified brand-local Codex stage.

        Args:
            config: Stage runtime config.
            mechanical_validate: Mechanical validator for the stage result.
            model_class: Expected action-stage result model.

        Returns:
            Verified stage result.

        Raises:
            RuntimeError: If verification does not pass within the retry budget.
        """

        self._artifact_write(
            path=stage_input_path_get(config.stage_dir),
            payload=config.prompt_context,
            stage_dir=config.stage_dir,
        )
        feedback_list: list[str] = []
        for attempt_index in range(1, MAX_STAGE_ATTEMPT_COUNT + 1):
            result = self._action_result_get(
                attempt_index=attempt_index,
                config=config,
                feedback_list=feedback_list,
                model_class=model_class,
            )
            ArtifactMaterializer(config.result_dir).stage_artifact_materialize(
                config.stage_dir,
                self._artifact_materialization_policy,
            )
            try:
                mechanical_validate(result)
            except RuntimeError as exc:
                verification = StageVerificationResult(feedback_list=[str(exc)], status="failed")
            else:
                self._artifact_write(
                    path=stage_result_path_get(config.stage_dir),
                    payload=result,
                    stage_dir=config.stage_dir,
                )
                verification = self._verification_get(config=config)
            if verification.status == "failed":
                self._artifact_write(
                    path=stage_result_path_get(config.stage_dir),
                    payload=result,
                    stage_dir=config.stage_dir,
                )
            self._artifact_write(
                path=stage_verification_path_get(config.stage_dir),
                payload=verification,
                stage_dir=config.stage_dir,
            )
            if verification.status == "success":
                return result
            feedback_list = verification.feedback_list
        feedback = "; ".join(feedback_list)
        if feedback:
            raise RuntimeError(
                f"Stage {config.stage_key} did not pass verification after {MAX_STAGE_ATTEMPT_COUNT} attempts: "
                f"{feedback}"
            )
        raise RuntimeError(
            f"Stage {config.stage_key} did not pass verification after {MAX_STAGE_ATTEMPT_COUNT} attempts."
        )

    def _action_result_get(
        self,
        *,
        attempt_index: int,
        config: VerifiedCodexStageConfig,
        feedback_list: list[str],
        model_class: type[BaseModel],
    ) -> BaseModel:
        """Run the action-stage prompt once."""

        return self._codex_stage_run(
            browser_runtime_mcp_url=config.browser_runtime_mcp_url,
            model_class=model_class,
            prompt_text=self._prompt_renderer.render(
                f"{config.stage_key}.md.j2",
                {
                    "attempt_index": attempt_index,
                    "feedback_list": feedback_list,
                    "input_path": _stage_relative_path_get(
                        path=stage_input_path_get(config.stage_dir),
                        result_dir=config.result_dir,
                    ),
                    "previous_stage_result_path": (
                        _stage_relative_path_get(
                            path=stage_result_path_get(config.stage_dir),
                            result_dir=config.result_dir,
                        )
                        if attempt_index > 1
                        else ""
                    ),
                    "stage_key": config.stage_key,
                },
            ),
            result_dir=config.result_dir,
            stage_dir=config.stage_dir,
            stage_name=config.stage_key,
        )

    def _artifact_write(self, *, path: Path, payload: BaseModel, stage_dir: Path) -> None:
        """Write one stage artifact under the stage directory."""

        stage_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_writer.write(path, payload)

    def _verification_get(self, *, config: VerifiedCodexStageConfig) -> StageVerificationResult:
        """Run the verification-stage prompt once."""

        return self._codex_stage_run(
            browser_runtime_mcp_url=config.browser_runtime_mcp_url,
            model_class=StageVerificationResult,
            prompt_text=self._prompt_renderer.render(
                f"{config.stage_key}_verify.md.j2",
                {
                    "input_path": _stage_relative_path_get(
                        path=stage_input_path_get(config.stage_dir),
                        result_dir=config.result_dir,
                    ),
                    "stage_key": config.stage_key,
                    "stage_result_path": _stage_relative_path_get(
                        path=stage_result_path_get(config.stage_dir),
                        result_dir=config.result_dir,
                    ),
                },
            ),
            result_dir=config.result_dir,
            stage_dir=config.stage_dir,
            stage_name=f"{config.stage_key}_verify",
        )


def _stage_relative_path_get(*, path: Path, result_dir: Path) -> str:
    """Return one stage artifact path relative to the result directory."""

    return path.relative_to(result_dir).as_posix()


def verified_stage_artifact_write(*, config: VerifiedCodexStageConfig, result: BaseModel) -> None:
    """Write deterministic stage input, result, and success verification artifacts."""

    artifact_writer = JsonArtifactWriter()
    config.stage_dir.mkdir(parents=True, exist_ok=True)
    artifact_writer.write(stage_input_path_get(config.stage_dir), config.prompt_context)
    artifact_writer.write(stage_result_path_get(config.stage_dir), result)
    artifact_writer.write(
        stage_verification_path_get(config.stage_dir),
        StageVerificationResult(feedback_list=[], status="success"),
    )


def stage_instruction_list_get(*, prompt_scope: PromptScope, stage_key: str) -> list[str]:
    """Return stage instructions from the prompt scope.

    Args:
        prompt_scope: Parsed workflow-run prompt scope.
        stage_key: Current stage key.

    Returns:
        Stage-specific instruction list.
    """

    return [
        stage_instruction.instruction
        for stage_instruction in prompt_scope.stage_instruction_list
        if stage_instruction.stage_key == stage_key
    ]
