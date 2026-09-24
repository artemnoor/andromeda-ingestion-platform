"""Optional Playwright adapter for JavaScript-rendered official pages."""

from __future__ import annotations

import time

from andromeda_ingestion.domain.contracts import DiscoveredItem, FetchedArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError
from andromeda_ingestion.infrastructure.config import Settings

from .http import SafeHttpFetcher


class PlaywrightBrowserFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.url_policy = SafeHttpFetcher(settings)

    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact:
        url = self.url_policy._validate_url(item.canonical_url, source)
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise UpstreamError("FETCH_FAILED", "Playwright adapter is not installed; install the browser extra", {}) from exc
        started = time.perf_counter()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=int(self.settings.fetch_timeout_seconds * 1000))
                body = (await page.content()).encode("utf-8")
                if len(body) > self.settings.max_artifact_bytes:
                    raise UpstreamError("FETCH_BODY_TOO_LARGE", "Rendered page exceeds configured artifact limit", {})
                return FetchedArtifact(
                    requested_url=item.canonical_url,
                    final_url=page.url,
                    status_code=200,
                    content_type="text/html; charset=utf-8",
                    body=body,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                    access_mode="browser",
                )
            finally:
                await browser.close()
