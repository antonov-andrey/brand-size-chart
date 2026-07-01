"""Source type registry for brand size-chart discovery."""


class SourceTypeRegistry:
    """Own source type priority, prompt instructions, and execution order."""

    def __init__(self) -> None:
        """Store source type lookup contracts."""

        self.source_type_priority_by_key_map = {
            "official_brand_size_guide": 600,
            "official_seller_size_guide": 550,
            "official_brand_product_page": 500,
            "official_marketplace_product_page": 300,
            "official_marketplace_store": 200,
        }
        self.product_type_required_source_type_set = {
            "official_brand_product_page",
            "official_marketplace_product_page",
            "official_marketplace_store",
        }
        self.source_type_discovery_instruction_by_key_map = {
            "official_brand_size_guide": (
                "Find official brand size-guide or size-chart surfaces on the brand-owned website. Apply the "
                "prompt-supplied priority country before fallback markets. Search official site navigation, "
                "size-guide surfaces, help sections, FAQ sections, and other official brand-owned non-product "
                "surfaces. Do not return ordinary product pages from this source type; product-page measurement "
                "sections belong only to official_brand_product_page. Build an inventory of official host "
                "candidates, accepted tables, rejected URLs, and rejection reasons before returning candidates."
            ),
            "official_seller_size_guide": (
                "Find official or authorized reseller or distributor size-guide surfaces for the brand when the brand "
                "sells through an official seller in a relevant country. Search seller site navigation, size-guide "
                "surfaces, help sections, FAQ sections, and other official seller-owned non-product surfaces. "
                "Evidence must prove the seller is official or authorized for the brand. Do not return ordinary "
                "product pages from this source type."
            ),
            "official_brand_product_page": (
                "Find official brand-owned product pages for the requested product types. Search the product card, "
                "product details, product questions or answers, size recommendation areas, and product-linked size "
                "evidence."
            ),
            "official_marketplace_product_page": (
                "Find official marketplace product pages where the seller is the brand or an authorized official "
                "seller and the page belongs to the requested product types. Search the product card, product "
                "details, product questions or answers, size recommendation areas, and product-linked size evidence."
            ),
            "official_marketplace_store": (
                "Find official or authorized marketplace store pages for the brand and use them to reach store-linked "
                "official products for the requested product types. Evidence must prove the marketplace store or "
                "seller is official or authorized for the brand."
            ),
        }

    def source_type_discovery_instruction_get(self, source_type: str) -> str:
        """Return discovery instruction text for one source type.

        Args:
            source_type: Source type key.

        Returns:
            Discovery instruction text.
        """

        return self.source_type_discovery_instruction_by_key_map[source_type]

    def source_type_list_get(self, *, have_product_type_request: bool, source_type_allow_list: list[str]) -> list[str]:
        """Return source types in priority order with product-type gating applied.

        Args:
            have_product_type_request: Whether the prompt has requested product types.
            source_type_allow_list: Prompt-selected source type allow list.

        Returns:
            Ordered source type key list.
        """

        source_type_list = source_type_allow_list or [
            source_type
            for source_type, _priority in sorted(
                self.source_type_priority_by_key_map.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
        known_source_type_list = list(source_type_list)
        if have_product_type_request:
            return known_source_type_list
        filtered_source_type_list = [
            source_type
            for source_type in known_source_type_list
            if source_type not in self.product_type_required_source_type_set
        ]
        if not filtered_source_type_list:
            raise RuntimeError("No source types remain after applying product-type scope rules.")
        return filtered_source_type_list

    def source_type_priority_get(self, source_type: str) -> int:
        """Return priority for one source type.

        Args:
            source_type: Source type key.

        Returns:
            Source priority.
        """

        return self.source_type_priority_by_key_map[source_type]

    def source_type_requires_product_type(self, source_type: str) -> bool:
        """Return whether one source type requires product-type scope.

        Args:
            source_type: Source type key.

        Returns:
            Whether the source type requires product-type scope.
        """

        return source_type in self.product_type_required_source_type_set


SOURCE_TYPE_REGISTRY = SourceTypeRegistry()
PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET = SOURCE_TYPE_REGISTRY.product_type_required_source_type_set
SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP = SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_by_key_map
SOURCE_TYPE_PRIORITY_BY_KEY_MAP = SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map
