"""Tests for DBOS class-method workflow and step ownership."""

import inspect

from dbos import DBOS


def test_dbos_class_method_workflow_and_step_are_registered() -> None:
    """Verify the current DBOS SDK supports class-owned workflow and step methods."""

    @DBOS.dbos_class("ExampleWorkflowOwner")
    class ExampleWorkflowOwner:
        """Minimal DBOS class owner used only for registration verification."""

        @DBOS.workflow(name="example_oop_workflow")
        def run(self, value: str) -> str:
            """Return a deterministic workflow value.

            Args:
                value: Durable workflow input.

            Returns:
                Deterministic output.
            """
            return f"workflow:{value}"

        @DBOS.step(name="example_oop_step")
        def step_run(self, value: str) -> str:
            """Return a deterministic step value.

            Args:
                value: Durable step input.

            Returns:
                Deterministic output.
            """
            return f"step:{value}"

    owner = ExampleWorkflowOwner()

    assert inspect.ismethod(owner.run)
    assert inspect.ismethod(owner.step_run)
    assert getattr(owner.run, "dbos_function_name") == "example_oop_workflow"
    assert getattr(owner.step_run, "dbos_function_name") == "example_oop_step"
    assert owner.run.dbos_func_decorator_info.func_type.name == "Instance"
    assert owner.step_run.dbos_func_decorator_info.func_type.name == "Instance"
    assert owner.run.dbos_func_decorator_info.class_info.registered_name == "ExampleWorkflowOwner"
    assert owner.step_run.dbos_func_decorator_info.class_info.registered_name == "ExampleWorkflowOwner"
