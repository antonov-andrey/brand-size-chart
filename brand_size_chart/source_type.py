"""Static source type registry for brand size-chart discovery."""

SOURCE_TYPE_PRIORITY_BY_KEY_MAP = {
    "official_brand_size_guide": 600,
    "official_seller_size_guide": 550,
    "official_brand_product_page": 500,
    "official_marketplace_product_page": 300,
    "official_marketplace_store": 200,
}
PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET = {
    "official_brand_product_page",
    "official_marketplace_product_page",
    "official_marketplace_store",
}
SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP = {
    "official_brand_size_guide": (
        "Find official brand size-guide or size-chart surfaces on the brand-owned website. Prefer Turkish official "
        "pages, then official global pages. Search official site navigation, size-guide surfaces, help sections, FAQ "
        "sections, and other official brand-owned non-product surfaces. Do not return ordinary product pages from this "
        "source type; product-page measurement sections belong only to official_brand_product_page. Build an inventory "
        "of official host candidates, accepted tables, rejected URLs, and rejection reasons before returning candidates."
    ),
    "official_seller_size_guide": (
        "Find official or authorized reseller or distributor size-guide surfaces for the brand when the brand sells "
        "through an official seller in a relevant country. Search seller site navigation, size-guide surfaces, help "
        "sections, FAQ sections, and other official seller-owned non-product surfaces. Evidence must prove the seller "
        "is official or authorized for the brand. Do not return ordinary product pages from this source type."
    ),
    "official_brand_product_page": (
        "Find official brand-owned product pages for the requested product types. Search the product card, product "
        "details, product questions or answers, size recommendation areas, and product-linked size evidence."
    ),
    "official_marketplace_product_page": (
        "Find official marketplace product pages where the seller is the brand or an authorized official seller and "
        "the page belongs to the requested product types. Search the product card, product details, product questions "
        "or answers, size recommendation areas, and product-linked size evidence."
    ),
    "official_marketplace_store": (
        "Find official or authorized marketplace store pages for the brand and use them to reach store-linked official "
        "products for the requested product types. Evidence must prove the marketplace store or seller is official or "
        "authorized for the brand."
    ),
}
