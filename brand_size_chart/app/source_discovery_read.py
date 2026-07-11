"""Read accepted source-discovery tables through one constrained console command."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from brand_size_chart.model import BrandSourceTypeResultStepInput, SourceTypeResult
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader


def _input_path_get(value: str) -> Path:
    """Load the exact current persisted brand downstream input.

    Args:
        value: Candidate filesystem input path.

    Returns:
        Resolved current input path.

    Raises:
        ValueError: If the path is not an exact readable current input artifact.
    """

    input_path = Path(value).resolve(strict=True)
    if input_path.name != "input.json":
        raise ValueError("input_path must name input.json")
    BrandSourceTypeResultStepInput.model_validate_json(input_path.read_text(encoding="utf-8"))
    return input_path


def _result_dir_get(input_path: Path, source_type_result: SourceTypeResult) -> Path:
    """Derive the unique result root that contains one declared database handle.

    Args:
        input_path: Exact persisted downstream input path.
        source_type_result: Selected complete source result.

    Returns:
        Unique absolute result root.

    Raises:
        ValueError: If no unique owning result root can be derived.
    """

    source_discovery_result = source_type_result.source_discovery_result
    if source_discovery_result is None:
        raise ValueError("selected source type has no source discovery result")
    database_handle = Path(source_discovery_result.source_discovery_database_path)
    if database_handle.is_absolute() or ".." in database_handle.parts:
        raise ValueError("selected source database handle is invalid")
    result_dir_list = [
        ancestor
        for ancestor in input_path.parents
        if (ancestor / database_handle).is_file()
        and (ancestor / database_handle).resolve().is_relative_to(ancestor.resolve())
    ]
    if len(result_dir_list) != 1:
        raise ValueError("selected source database must have exactly one containing result root ancestor")
    return result_dir_list[0]


def main(argument_list: Sequence[str] | None = None) -> int:
    """List accepted tables for one source type from the current persisted input.

    Args:
        argument_list: Optional command arguments without the executable name.

    Returns:
        Zero after emitting compact accepted-table JSON.
    """

    parser = argparse.ArgumentParser(description="List accepted source-discovery tables for one source type.")
    parser.add_argument("input_path")
    parser.add_argument("source_type")
    parser.add_argument("operation", choices=("list-accepted",))
    args = parser.parse_args(argument_list)
    try:
        input_path = _input_path_get(args.input_path)
        step_input = BrandSourceTypeResultStepInput.model_validate_json(input_path.read_text(encoding="utf-8"))
        matching_source_type_result_list = [
            source_type_result
            for source_type_result in step_input.source_type_result_list
            if source_type_result.source_type == args.source_type
        ]
        if len(matching_source_type_result_list) != 1:
            raise ValueError("source_type must select exactly one complete source result")
        source_type_result = matching_source_type_result_list[0]
        result_dir = _result_dir_get(input_path, source_type_result)
        accepted_table_list = SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=result_dir,
            source_type_result=source_type_result,
        )
    except (OSError, RuntimeError, ValidationError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    sys.stdout.write("[" + ",".join(item.model_dump_json() for item in accepted_table_list) + "]\n")
    return 0
