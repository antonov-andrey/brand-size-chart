"""Concrete step inheritance and config-routing contracts."""

from workflow_container_runtime.step import WorkflowStepCodexConcurrentBase, WorkflowStepCodexBase

from brand_size_chart.step import CanonicalSelectionStep, CoverageDecisionStep, SourceDiscoveryStep


def test_configurable_steps_use_current_runtime_bases_and_exact_config_models() -> None:
    """Bind each concrete configurable step to its runtime config owner."""

    assert issubclass(SourceDiscoveryStep, WorkflowStepCodexConcurrentBase)
    assert issubclass(CoverageDecisionStep, WorkflowStepCodexBase)
    assert issubclass(CanonicalSelectionStep, WorkflowStepCodexBase)
    assert SourceDiscoveryStep.config_model.__name__ == "WorkflowStepSourceDiscoverConfig"
    assert CoverageDecisionStep.config_model.__name__ == "WorkflowStepCoverageDecideConfig"
    assert CanonicalSelectionStep.config_model.__name__ == "WorkflowStepCanonicalSelectConfig"
