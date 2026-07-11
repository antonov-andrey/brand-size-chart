"""Run the runtime-owned SQLite state protocol for source discovery."""

import sys
from collections.abc import Sequence

from workflow_container_runtime.state import SqliteStateCommand

from brand_size_chart.model import SourceDiscoveryInput
from brand_size_chart.source.discovery_database import SOURCE_DISCOVERY_TABLE_BY_NAME_MAP


def main(argument_list: Sequence[str] | None = None) -> int:
    """Delegate one source-discovery state operation to the runtime protocol.

    Args:
        argument_list: Optional command arguments without the executable name.

    Returns:
        Runtime command process exit code.
    """

    return SqliteStateCommand().run(
        list(sys.argv[1:] if argument_list is None else argument_list),
        SourceDiscoveryInput,
        SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    )
