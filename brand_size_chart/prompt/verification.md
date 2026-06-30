# Brand Size Chart Verification

Verify the produced artifact against the stage schema, browser-visible source evidence, and canonical selection rules. Use the configured browser when the original source must be reopened to verify the artifact. Report conflicts explicitly and never repair the artifact inside verification.

For `source_discovery`, verify source-type completeness, not only internal consistency. A passed verification requires browser-visible evidence that the main stage checked the relevant source surface for the requested source type and returned all concrete matching size-chart table candidates. Empty discovery, skipped discovery, missing inventory evidence, untested plausible source URLs, or source-type boundary confusion must fail verification with actionable feedback for the same main stage.

For `table_extraction`, verify every source row, column, unit, size label, measurement, applicability description, source URL, source title, and `size_group_key` against the saved browser-visible evidence. Missing source columns or empty charts must fail verification.
