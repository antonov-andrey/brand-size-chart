"""Source-discovery mechanical validation."""

from pathlib import Path

from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext

from brand_size_chart.artifact import ArtifactReferenceValidator
from brand_size_chart.model import (
    SourceDiscoveryInput,
    SourceDiscoveryResult,
    SourceSurfaceInventory,
    SourceSurfaceTable,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY


def _accepted_table_list_validate(
    *,
    accepted_table_list: list[SourceSurfaceTable],
    priority_country_code: str,
) -> None:
    """Validate accepted table identity and market-selection invariants.

    Args:
        accepted_table_list: Accepted source-surface table rows.
        priority_country_code: Preferred market from the persisted workflow input.

    Raises:
        StepResultValidationError: If accepted rows duplicate identities or mix market levels.
    """

    size_group_key_list = [table.source_discovery.size_group_key for table in accepted_table_list]
    if len(set(size_group_key_list)) != len(size_group_key_list):
        raise StepResultValidationError(
            feedback_list=[
                "Keep exactly one accepted source table per size_group_key and move duplicate tables to equivalent, "
                "market_filtered, market_conflict, or rejected inventory rows."
            ]
        )

    priority_country_source_list = [
        table for table in accepted_table_list if priority_country_code in table.source_discovery.country_code_list
    ]
    if priority_country_source_list:
        non_priority_country_size_group_key_list = sorted(
            table.source_discovery.size_group_key
            for table in accepted_table_list
            if priority_country_code not in table.source_discovery.country_code_list
        )
        if non_priority_country_size_group_key_list:
            raise StepResultValidationError(
                feedback_list=[
                    f"Keep only {priority_country_code} accepted tables because that priority market has verified "
                    f"tables; move lower-market rows out of accepted: {non_priority_country_size_group_key_list}."
                ]
            )
        return

    global_source_list = [
        table for table in accepted_table_list if "GLOBAL" in table.source_discovery.country_code_list
    ]
    if global_source_list:
        non_global_size_group_key_list = sorted(
            table.source_discovery.size_group_key
            for table in accepted_table_list
            if "GLOBAL" not in table.source_discovery.country_code_list
        )
        if non_global_size_group_key_list:
            raise StepResultValidationError(
                feedback_list=[
                    "Keep only GLOBAL accepted tables because verified global tables exist; move lower-market rows "
                    f"out of accepted: {non_global_size_group_key_list}."
                ]
            )
        return

    non_europe_size_group_key_list = sorted(
        table.source_discovery.size_group_key
        for table in accepted_table_list
        if "EU" not in table.source_discovery.country_code_list
    )
    if non_europe_size_group_key_list:
        raise StepResultValidationError(
            feedback_list=[
                f"Accept only {priority_country_code}, GLOBAL, or verified EU-consensus tables; correct the market "
                f"classification for: {non_europe_size_group_key_list}."
            ]
        )


def _artifact_reference_list_validate(
    *,
    execution_context: WorkflowStepExecutionContext,
    evidence_path_list: list[str],
    evidence_target_path: str,
) -> None:
    """Validate explicit evidence references against the declared target.

    Args:
        execution_context: Current step execution context.
        evidence_path_list: Result-relative evidence references.
        evidence_target_path: Declared public evidence directory.

    Raises:
        StepResultValidationError: If a reference escapes the target or does not exist.
    """

    target_path = (execution_context.result_dir / evidence_target_path).resolve()
    outside_target_path_list: list[str] = []
    for evidence_path in evidence_path_list:
        evidence_relative_path = Path(evidence_path)
        if (
            evidence_relative_path.is_absolute()
            or "\\" in evidence_path
            or ".." in evidence_relative_path.parts
            or evidence_relative_path.as_posix() != evidence_path
        ):
            outside_target_path_list.append(evidence_path)
            continue
        try:
            (execution_context.result_dir / evidence_path).resolve().relative_to(target_path)
        except ValueError:
            outside_target_path_list.append(evidence_path)
    if outside_target_path_list:
        raise StepResultValidationError(
            feedback_list=[
                "Return source-discovery evidence only from the declared evidence_write_target.artifact_path "
                f"{evidence_target_path}; outside references: {sorted(outside_target_path_list)}."
            ]
        )

    try:
        ArtifactReferenceValidator(execution_context.result_dir).path_list_validate(
            path_list=evidence_path_list,
            step_key="source_discover inventory",
        )
    except RuntimeError as exc:
        raise StepResultValidationError(
            feedback_list=[
                "Create every referenced evidence artifact under the declared source-discovery evidence target and "
                f"return normalized result-relative paths; artifact validation failed: {exc}."
            ]
        ) from exc


def _equivalent_table_list_validate(
    *,
    accepted_size_group_key_set: set[str],
    inventory: SourceSurfaceInventory,
) -> None:
    """Require each equivalent table to share an accepted table identity.

    Args:
        accepted_size_group_key_set: Accepted size-group identities.
        inventory: Reconstructed source-surface inventory.

    Raises:
        StepResultValidationError: If one equivalent row has no accepted representative.
    """

    orphan_size_group_key_list = sorted(
        {
            table.source_discovery.size_group_key
            for table in inventory.table_list
            if table.state == "equivalent" and table.source_discovery.size_group_key not in accepted_size_group_key_set
        }
    )
    if orphan_size_group_key_list:
        raise StepResultValidationError(
            feedback_list=[
                "Add one accepted table with the same size_group_key for every equivalent inventory row, or change "
                f"the orphan row state; orphan size groups: {orphan_size_group_key_list}."
            ]
        )


def _inventory_evidence_path_list_get(inventory: SourceSurfaceInventory) -> list[str]:
    """Return every explicit inventory evidence reference.

    Args:
        inventory: Reconstructed source-surface inventory.

    Returns:
        Evidence references from query, worklist, table, and URL rows.
    """

    evidence_path_list: list[str] = []
    for discovery_query in inventory.discovery_query_list:
        evidence_path_list.extend(discovery_query.evidence_path_list)
    for worklist_item in inventory.product_type_sex_worklist:
        evidence_path_list.extend(worklist_item.evidence_path_list)
    for table in inventory.table_list:
        evidence_path_list.extend(table.source_discovery.evidence_path_list)
    for source_url in inventory.url_list:
        evidence_path_list.extend(source_url.evidence_path_list)
    return evidence_path_list


def _worklist_validate(
    *,
    inventory: SourceSurfaceInventory,
    require_dedicated_product_url: bool,
    requested_product_type_list: list[str],
) -> None:
    """Validate product-type worklist identity and URL closure.

    Args:
        inventory: Reconstructed source-surface inventory.
        require_dedicated_product_url: Whether each searched row requires its own product URL record.
        requested_product_type_list: Exact product scope from the persisted step input.

    Raises:
        StepResultValidationError: If worklist rows are duplicated, invalid, or unclosed.
    """

    worklist_key_list = [worklist_item.worklist_key for worklist_item in inventory.product_type_sex_worklist]
    worklist_key_set = set(worklist_key_list)
    if len(worklist_key_set) != len(worklist_key_list):
        raise StepResultValidationError(
            feedback_list=["Give every product_type_sex_worklist row one unique worklist_key."]
        )

    represented_product_type_set = {
        represented_product_type
        for worklist_item in inventory.product_type_sex_worklist
        for represented_product_type in {
            worklist_item.product_type,
            f"{worklist_item.sex} {worklist_item.product_type}",
        }
    }
    missing_product_type_list = [
        requested_product_type
        for requested_product_type in requested_product_type_list
        if requested_product_type not in represented_product_type_set
    ]
    if missing_product_type_list:
        raise StepResultValidationError(
            feedback_list=[
                "Add at least one product_type_sex_worklist row for every requested product type; "
                f"missing requested product types: {missing_product_type_list}."
            ]
        )

    pending_worklist_key_list = sorted(
        worklist_item.worklist_key
        for worklist_item in inventory.product_type_sex_worklist
        if worklist_item.state == "pending"
    )
    if pending_worklist_key_list:
        raise StepResultValidationError(
            feedback_list=[
                "Complete every pending product_type_sex_worklist row before returning the source-discovery result; "
                f"pending keys: {pending_worklist_key_list}."
            ]
        )

    searched_worklist_key_set: set[str] = set()
    for worklist_item in inventory.product_type_sex_worklist:
        if not worklist_item.reason.strip():
            raise StepResultValidationError(
                feedback_list=[
                    f"Add an evidence-backed terminal reason for product_type_sex_worklist row "
                    f"{worklist_item.worklist_key}."
                ]
            )
        if not worklist_item.evidence_path_list:
            raise StepResultValidationError(
                feedback_list=[
                    f"Add evidence_path_list for terminal product_type_sex_worklist row "
                    f"{worklist_item.worklist_key}."
                ]
            )
        if worklist_item.state == "searched":
            searched_worklist_key_set.add(worklist_item.worklist_key)

    linked_worklist_key_set = {
        worklist_key for source_url in inventory.url_list for worklist_key in source_url.worklist_key_list
    }
    unknown_worklist_key_list = sorted(linked_worklist_key_set - worklist_key_set)
    if unknown_worklist_key_list:
        raise StepResultValidationError(
            feedback_list=[
                "Remove unknown worklist_key_list references from URL inventory rows or add their worklist rows; "
                f"unknown keys: {unknown_worklist_key_list}."
            ]
        )

    if not require_dedicated_product_url:
        return

    closing_worklist_key_set = {
        source_url.worklist_key_list[0]
        for source_url in inventory.url_list
        if source_url.state == "opened" and len(source_url.worklist_key_list) == 1
    }
    unclosed_worklist_key_list = sorted(searched_worklist_key_set - closing_worklist_key_set)
    if unclosed_worklist_key_list:
        raise StepResultValidationError(
            feedback_list=[
                "Open and record at least one dedicated product URL for every searched product/sex worklist row; "
                "a rejected URL or URL linked to multiple rows cannot close them; "
                f"unclosed keys: {unclosed_worklist_key_list}."
            ]
        )


class SourceDiscoveryValidator:
    """Validate source discovery against its reconstructed private inventory."""

    def validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: SourceDiscoveryInput,
        result: SourceDiscoveryResult,
        inventory: SourceSurfaceInventory,
    ) -> None:
        """Validate one public source-discovery result mechanically.

        Args:
            execution_context: Current step execution context.
            step_input: Persisted source-discovery input used by the action.
            result: Candidate public source-discovery result.
            inventory: Inventory reconstructed by the step from private JSONL files.

        Raises:
            StepResultValidationError: If the public result or inventory violates its mechanical contract.
        """

        market_conflict_size_group_key_list = sorted(
            {
                table.source_discovery.size_group_key
                for table in inventory.table_list
                if table.state == "market_conflict"
            }
        )
        if market_conflict_size_group_key_list:
            raise StepResultValidationError(
                feedback_list=[
                    "Resolve the market conflict instead of returning it as a no-table outcome; reconcile the "
                    f"European country tables for: {market_conflict_size_group_key_list}."
                ]
            )

        accepted_table_list = [table for table in inventory.table_list if table.state == "accepted"]
        accepted_size_group_key_set = {table.source_discovery.size_group_key for table in accepted_table_list}
        _equivalent_table_list_validate(
            accepted_size_group_key_set=accepted_size_group_key_set,
            inventory=inventory,
        )
        _worklist_validate(
            inventory=inventory,
            require_dedicated_product_url=SOURCE_TYPE_REGISTRY.source_type_requires_product_type(
                step_input.workflow_input.source_type
            ),
            requested_product_type_list=step_input.workflow_input.prompt_scope.product_type_request_list,
        )
        _artifact_reference_list_validate(
            execution_context=execution_context,
            evidence_path_list=_inventory_evidence_path_list_get(inventory),
            evidence_target_path=step_input.evidence_write_target.artifact_path,
        )

        expected_source_discovery_list = [table.source_discovery for table in accepted_table_list]
        if result.source_discovery_list != expected_source_discovery_list:
            raise StepResultValidationError(
                feedback_list=[
                    "Return source_discovery_list exactly from accepted inventory table rows, preserving row order "
                    "and every SourceDiscovery field."
                ]
            )

        if not accepted_table_list:
            expected_warning_list = inventory.no_table_reason_list_get()
            if not expected_warning_list:
                raise StepResultValidationError(
                    feedback_list=[
                        "Add at least one evidence-backed terminal no-table reason to the source inventory before "
                        "returning an empty source_discovery_list."
                    ]
                )
            if result.warning_list != expected_warning_list:
                raise StepResultValidationError(
                    feedback_list=[
                        "Return warning_list exactly as the sorted evidence-backed no-table reasons from the source "
                        f"inventory; expected: {expected_warning_list}."
                    ]
                )
            return

        if result.warning_list:
            raise StepResultValidationError(
                feedback_list=[
                    "Return an empty warning_list when accepted source tables exist; no-table warnings apply only "
                    "to an empty accepted result."
                ]
            )

        _accepted_table_list_validate(
            accepted_table_list=accepted_table_list,
            priority_country_code=step_input.workflow_input.prompt_scope.priority_country_code,
        )
        for source_discovery in result.source_discovery_list:
            if not source_discovery.source_url.strip():
                raise StepResultValidationError(
                    feedback_list=[
                        f"Set a non-empty source_url for accepted size group {source_discovery.size_group_key}."
                    ]
                )
            if not source_discovery.source_title.strip():
                raise StepResultValidationError(
                    feedback_list=[
                        f"Set a non-empty source_title for accepted size group {source_discovery.size_group_key}."
                    ]
                )
            if not source_discovery.evidence_path_list:
                raise StepResultValidationError(
                    feedback_list=[f"Add evidence_path_list for accepted size group {source_discovery.size_group_key}."]
                )
