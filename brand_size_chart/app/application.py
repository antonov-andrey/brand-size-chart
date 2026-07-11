"""Composition root for reusable workflow, step, and runtime owners."""

from pathlib import Path

from workflow_container_runtime.artifact import (
    ArtifactMaterializationPolicy,
    ArtifactMaterializer,
    JsonArtifactWriter,
)
from workflow_container_runtime.codex import CodexRunner, CodexRunnerConfig
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.state import SqliteStateStore
from workflow_container_runtime.step import CodexExecutionRetryPolicy, WorkflowStepCodexConfig

from brand_size_chart.step import (
    BrandOutputStep,
    CanonicalSelectionDefaultStep,
    CanonicalSelectionStep,
    CoverageDecisionDefaultStep,
    CoverageDecisionStep,
    SourceDiscoveryStep,
    WorkflowRunPromptApplyDefaultStep,
    WorkflowRunPromptApplyStep,
)
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader
from brand_size_chart.validator import (
    BrandOutputValidator,
    CanonicalSelectionValidator,
    CoverageDecisionValidator,
    PromptScopeValidator,
    SourceDiscoveryValidator,
)
from brand_size_chart.workflow import (
    BrandSizeChartBrandWorkflow,
    BrandSizeChartRunWorkflow,
    BrandSizeChartSourceTypeWorkflow,
)


class BrandSizeChartApplication:
    """Construct the complete stateless workflow object graph once."""

    def __init__(self) -> None:
        """Build shared runtime services, concrete steps, and DBOS workflows."""

        artifact_materializer = ArtifactMaterializer()
        artifact_writer = JsonArtifactWriter()
        prompt_renderer = PromptRenderer(
            template_dir=Path(__file__).resolve().parents[1] / "prompt" / "template",
        )
        codex_runner = CodexRunner(
            artifact_writer=artifact_writer,
            config=CodexRunnerConfig(
                model="gpt-5.6-terra",
                model_reasoning_effort="high",
            ),
            prompt_renderer=prompt_renderer,
            workflow_container_name="brand-size-chart",
        )
        browser_step_config = WorkflowStepCodexConfig(
            artifact_materialization_policy=ArtifactMaterializationPolicy(
                artifact_root_tuple=(Path(".playwright-mcp/current"),),
            ),
            attempt_limit=3,
            execution_retry_policy=CodexExecutionRetryPolicy(attempt_limit=2),
        )
        local_step_config = WorkflowStepCodexConfig(
            artifact_materialization_policy=ArtifactMaterializationPolicy(artifact_root_tuple=()),
            attempt_limit=3,
            execution_retry_policy=CodexExecutionRetryPolicy(attempt_limit=2),
        )

        sqlite_state_store = SqliteStateStore()
        source_discovery_database_reader = SourceDiscoveryDatabaseReader()
        source_discovery_step = SourceDiscoveryStep(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            config=browser_step_config,
            prompt_renderer=prompt_renderer,
            sqlite_state_store=sqlite_state_store,
            validator=SourceDiscoveryValidator(sqlite_state_store=sqlite_state_store),
        )
        source_type_workflow = BrandSizeChartSourceTypeWorkflow(
            artifact_writer=artifact_writer,
            config_name="source_type",
            source_discovery_step=source_discovery_step,
        )

        canonical_selection_validator = CanonicalSelectionValidator(
            source_discovery_database_reader=source_discovery_database_reader,
        )
        coverage_decision_validator = CoverageDecisionValidator(
            source_discovery_database_reader=source_discovery_database_reader,
        )
        brand_workflow = BrandSizeChartBrandWorkflow(
            artifact_writer=artifact_writer,
            brand_output_step=BrandOutputStep(
                artifact_writer=artifact_writer,
                source_discovery_database_reader=source_discovery_database_reader,
                validator=BrandOutputValidator(),
            ),
            canonical_selection_default_step=CanonicalSelectionDefaultStep(
                artifact_writer=artifact_writer,
                validator=canonical_selection_validator,
            ),
            canonical_selection_step=CanonicalSelectionStep(
                artifact_materializer=artifact_materializer,
                artifact_writer=artifact_writer,
                codex_runner=codex_runner,
                config=local_step_config,
                prompt_renderer=prompt_renderer,
                source_discovery_database_reader=source_discovery_database_reader,
                validator=canonical_selection_validator,
            ),
            config_name="brand",
            coverage_decision_default_step=CoverageDecisionDefaultStep(
                artifact_writer=artifact_writer,
                validator=coverage_decision_validator,
            ),
            coverage_decision_step=CoverageDecisionStep(
                artifact_materializer=artifact_materializer,
                artifact_writer=artifact_writer,
                codex_runner=codex_runner,
                config=local_step_config,
                prompt_renderer=prompt_renderer,
                validator=coverage_decision_validator,
            ),
            source_type_workflow=source_type_workflow,
        )
        self.root_workflow = BrandSizeChartRunWorkflow(
            artifact_writer=artifact_writer,
            brand_workflow=brand_workflow,
            config_name="run",
            workflow_run_prompt_apply_default_step=WorkflowRunPromptApplyDefaultStep(
                artifact_writer=artifact_writer,
            ),
            workflow_run_prompt_apply_step=WorkflowRunPromptApplyStep(
                artifact_materializer=artifact_materializer,
                artifact_writer=artifact_writer,
                codex_runner=codex_runner,
                config=local_step_config,
                prompt_renderer=prompt_renderer,
                validator=PromptScopeValidator(),
            ),
        )
