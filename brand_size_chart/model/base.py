"""Shared model base classes, literals, and validation constants."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

APPLICABILITY_STATUS_CANONICAL_SET = {
    "priority_country_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
}
ApplicabilityStatus = Literal[
    "priority_country_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
    "duplicate_exact",
    "duplicate_units_only",
    "market_conflict",
    "unknown_blocked",
]
StageStatus = Literal["success", "failed", "skipped"]
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
SOURCE_COUNTRY_CODE_SPECIAL_SET = {"EU", "GLOBAL"}


class StrictBaseModel(BaseModel):
    """Base model with strict validation for workflow artifacts."""

    model_config = ConfigDict(extra="forbid", strict=True)
