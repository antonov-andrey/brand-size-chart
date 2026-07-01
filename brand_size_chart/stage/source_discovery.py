"""Source-discovery stage owner."""

from functools import partial
from pathlib import Path

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import BrandInput, PromptScope, SourceDiscoveryResult
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.source_extractor import source_discovery_result_get
from brand_size_chart.stage.base import CodexStageRun
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.validator import SourceDiscoveryValidator


class SourceDiscoveryStage:
    """Discover concrete size-chart source candidates with browser evidence."""

    def __init__(
        self,
        *,
        brand_input: BrandInput,
        browser_runtime_mcp_url: str,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        secret_path: Path,
        source_priority: int,
        source_type: str,
        source_type_dir: Path,
    ) -> None:
        """Store source-discovery stage dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope for source discovery.
            result_dir: Result root directory.
            secret_path: Secret DataSource path.
            source_priority: Source type priority.
            source_type: Source type key.
            source_type_dir: Source-type audit directory.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._brand_input = brand_input
        self._browser_runtime_mcp_url = browser_runtime_mcp_url
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._secret_path = secret_path
        self._source_priority = source_priority
        self._source_type = source_type
        self._source_type_dir = source_type_dir
        self._stage_dir = self._artifact_layout.source_discovery_dir(brand_input, source_type)
        self._validator = SourceDiscoveryValidator(result_dir=result_dir, stage_dir=self._stage_dir)

    def run(self) -> SourceDiscoveryResult:
        """Run source discovery from rendered evidence.

        Returns:
            Verified source discovery result.
        """

        draft_result = self._draft_result_get()
        return SemanticStage(
            browser_access=True,
            browser_runtime_mcp_url=self._browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_run,
            prompt_name="discovery",
            prompt_scope=self._prompt_scope,
            result_dir=self._result_dir,
            stage_dir=self._stage_dir,
            stage_key="source_discovery",
        ).run(
            draft_result=draft_result,
            model_class=SourceDiscoveryResult,
            prompt_context=self._prompt_context_get(draft_result),
            result_error_list_get=partial(
                self._validator.error_list_get,
                expected_source_priority=self._source_priority,
                expected_source_type=self._source_type,
                prompt_scope=self._prompt_scope,
            ),
        )

    def _draft_result_get(self) -> SourceDiscoveryResult:
        """Return draft source discovery for one source type.

        Returns:
            Draft source discovery result.
        """

        return source_discovery_result_get(
            brand_input=self._brand_input,
            result_dir=self._result_dir,
            secret_path=self._secret_path,
            source_type=self._source_type,
            source_type_dir=self._source_type_dir,
        )

    def _prompt_context_get(self, draft_result: SourceDiscoveryResult) -> str:
        """Return source-discovery prompt context.

        Args:
            draft_result: Deterministic draft source discovery.

        Returns:
            Prompt context text.
        """

        evidence_dir = self._artifact_layout.source_discovery_evidence_dir(self._brand_input, self._source_type)
        requested_product_type_text = (
            "\n".join(f"- {product_type}" for product_type in self._prompt_scope.product_type_request_list) or "- none"
        )
        return (
            f"Brand: {self._brand_input.parsed_brand_name}\n"
            f"Source type: {self._source_type}\n"
            f"Source priority: {self._source_priority}\n"
            f"Priority country code: {self._prompt_scope.priority_country_code}\n"
            f"Requested product types:\n{requested_product_type_text}\n"
            f"Source type instruction: {SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(self._source_type)}\n"
            f"Evidence directory: {self._artifact_layout.artifact_path(evidence_dir)}\n"
            "Use the configured browser to search, open, and interact with source pages. "
            "All source-page and source-data loading must go through the configured browser. "
            "Do not use non-browser loading mechanisms; direct HTTP, curl, requests, wget, and Python scraping are "
            "examples of forbidden replacements, not an exhaustive list. "
            "Treat source discovery as a bounded workflow, not a best-effort search. First build one canonical "
            "browser-backed source-surface inventory artifact named source_surface_inventory.json for this source type "
            "under the evidence directory. "
            "The canonical inventory must include discovery queries, candidate URLs, opened URLs, accepted tables, "
            "rejected URLs, rejection reasons, blocking browser errors, and evidence paths. Update that canonical "
            "inventory on every retry before handoff; attempt-only inventory artifacts are allowed only as extra "
            "diagnostics and must not replace the canonical inventory verified by the workflow. "
            "In the canonical inventory, candidate_urls must contain only concrete source candidates that may directly "
            "hold size-chart data for this source type. Search pages, navigation pages, home pages, sitemap pages, FAQ "
            "index pages, help index pages, and other helper surfaces are discovery surfaces, not candidate URLs. Record "
            "helper surfaces in opened or rejected inventory entries with evidence and reasons, but do not list them as "
            "candidate URLs unless that exact opened URL itself contains a concrete size-chart table candidate. Do not "
            "put broad search-result or category product URL inventories in candidate_urls; if you collect broad product "
            "URL lists for sampling or coverage, store them separately as evidence fields such as search_result_url_list, "
            "category_product_url_list, or another clearly named non-candidate list, and record the sampling or rejection "
            "rule that selected the concrete candidate URLs. "
            "When this source type uses official brand sources, identify browser-visible official host variants before "
            "concluding that the source type has no tables. Host variants include global brand domains, country-code "
            "brand domains, and locale paths that browser evidence shows as brand-owned. Open relevant official host "
            "roots and inspect visible navigation, footer, search, help, FAQ, sitemap, and static-page links. Do not "
            "stop after one official domain variant fails when another brand-owned host variant is visible or inferable "
            "from browser-visible evidence. "
            "For each discovered official host, infer the browser-visible language and market from the opened page "
            "itself, then search for size-chart concepts in that language and market. Use the site's own search, "
            "visible navigation, footer/help pages, sitemap pages, and browser-opened public search results when they "
            "are available. Localized terms such as Turkish `beden rehberi` and `beden tablosu` are search terms, not "
            "URL templates. Record the localized queries and the opened or rejected results in the canonical inventory. "
            "Do not conclude that an official host has no size guide until localized size-chart term searches for that "
            "host are represented in the canonical inventory. "
            "Apply one market-selection ladder for discovered_source_list. First search for the priority country code "
            "from PromptScope. If priority country tables exist for this source type, discovered_source_list must "
            "contain only items whose country_code_list contains that priority country code. If no priority "
            "country table exists, return global tables only when global tables exist and mark them with "
            "country_code_list=['GLOBAL']. If neither priority country nor global tables exist, return European country "
            "tables only after verifying that the relevant official European country tables do not differ; mark such "
            "verified consensus candidates with country_code_list=['EU']. If European country tables differ, return "
            "status='failed' with exact conflicting country codes, URLs, and size_group_key values instead of picking "
            "one locale. "
            "Write each relevant browser evidence artifact under the evidence directory and reference those paths in "
            "evidence_path_list. Return every unique size-chart source candidate backed by evidence files. "
            "One SourceDiscovery item represents one concrete size chart table, not one page. "
            "If one page contains multiple size chart tables with different size_group_key values, return one "
            "discovered_source_list item per table. Inside one source type, return at most one discovered_source_list "
            "item for one size_group_key; when another page, locale, or asset exposes an equivalent table for the same "
            "size_group_key, record that duplicate or equivalent table in inventory evidence and source notes, but do not "
            "return a second candidate with the same size_group_key. "
            "The size_group_key must follow the Size Group Key Contract from the static prompt. Page-level or aggregate "
            "keys such as all, guide, page, or brand-wide bundle keys are forbidden. "
            "Requested product types are coverage targets only; they must not filter or narrow discovered_source_list, "
            "accepted_tables, or table extraction scope. When an opened source page contains concrete tables that are "
            "outside the requested product types, still return those tables and leave product_type_hint_list empty unless "
            "the evidence explicitly covers one requested product type. "
            "If requested product types are present, search for every requested product type in this source type. "
            "If one discovered table clearly applies to multiple requested product types, return one candidate and set "
            "product_type_hint_list to exactly the requested product types that are explicitly covered by the evidence. "
            "Do not include weakly inferred product types in product_type_hint_list. "
            "If at least one concrete table candidate is evidence-backed, return status='success' even when some "
            "requested product types remain uncovered; record missing requested product types in error_list with "
            "browser-backed reasons and keep accepted candidates in discovered_source_list. "
            "Respect the source type boundary exactly; do not return product-page measurement sections for "
            "official_brand_size_guide. "
            "Do not return status='skipped'. Empty discovered_source_list is forbidden in real discovery. "
            "If no concrete table can be returned after browser-backed inventory, return status='failed' "
            "with detailed blocker errors and canonical inventory evidence so this source type is recorded as failed "
            "and the workflow can continue to the next source type. Do not invent candidates.\n\n"
            f"Draft source_discovery JSON:\n{draft_result.model_dump_json(indent=2)}\n"
        )
