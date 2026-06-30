# Source Discovery

Use the configured browser to find sources for the requested source type. Every source page, source asset, and source data load must happen through that browser. Other loading mechanisms are forbidden for source data. Write browser-visible evidence artifacts and return only candidates backed by those artifacts.

Run discovery as a bounded workflow. Build a source-surface inventory for the requested source type before returning candidates: search queries, candidate URLs, opened URLs, accepted tables, rejected URLs, rejection reasons, blocker errors, and evidence paths must be represented in browser-visible evidence artifacts.

Search for size-chart data in any browser-visible form: HTML table, page text, modal, rendered widget, PDF, image, embedded asset, product image, help section, FAQ section, Q&A section, seller answer, product details, or size recommendation block. These forms are universal; source types differ only by authority, location, and applicability boundaries.

Return every concrete size-chart table candidate that matches the source type. One page with multiple tables must produce multiple candidates. Do not return aggregate page-level candidates.

Do not silently skip a source type. If browser access, search, page rendering, selectors, sitemap traversal, or candidate URL loading prevents reliable completion, return a failed terminal result with concrete blocker details so the workflow can retry and then fail loudly.
