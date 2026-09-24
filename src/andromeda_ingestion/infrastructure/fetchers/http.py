"""Bounded, allowlisted HTTP fetcher with redirect and body-size controls."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx

from andromeda_ingestion.domain.contracts import DiscoveredItem, FetchedArtifact, SourceDefinition
from andromeda_ingestion.domain.errors import UpstreamError
from andromeda_ingestion.infrastructure.config import Settings


class SafeHttpFetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        resolve_host: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.resolve_host = resolve_host or resolve_public_addresses

    async def fetch(self, source: SourceDefinition, item: DiscoveredItem) -> FetchedArtifact:
        url = self._validate_url(item.canonical_url, source)
        start = time.perf_counter()
        redirects: list[str] = []
        headers = {"User-Agent": "Andromeda-Ingestion/0.1", "Accept": "text/html,application/pdf,application/json;q=0.9,*/*;q=0.5"}
        last_error: Exception | None = None
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=self.settings.fetch_timeout_seconds,
            follow_redirects=False,
            headers=headers,
        )
        try:
            for attempt in range(self.settings.fetch_retries + 1):
                try:
                    current_url = url
                    for _ in range(self.settings.fetch_max_redirects + 1):
                        await self._validate_dns(current_url)
                        async with client.stream("GET", current_url) as response:
                            if response.status_code in {301, 302, 303, 307, 308}:
                                location = response.headers.get("location")
                                if not location:
                                    raise UpstreamError("FETCH_FAILED", "Redirect response has no Location header", {"url": current_url})
                                current_url = self._validate_url(urljoin(current_url, location), source)
                                redirects.append(current_url)
                                continue
                            if 400 <= response.status_code < 500:
                                raise UpstreamError(
                                    "FETCH_CLIENT_ERROR",
                                    "Source rejected the fetch request",
                                    {"url": item.canonical_url, "status_code": response.status_code},
                                )
                            if response.status_code >= 500:
                                raise UpstreamError(
                                    "FETCH_SERVER_ERROR",
                                    "Source returned a server error",
                                    {"url": item.canonical_url, "status_code": response.status_code},
                                )
                            body = await self._read_bounded(response)
                            return FetchedArtifact(
                                requested_url=item.canonical_url,
                                final_url=str(response.url),
                                status_code=response.status_code,
                                content_type=response.headers.get("content-type"),
                                headers={
                                    key.lower(): value
                                    for key, value in response.headers.items()
                                    if key.lower() in {"etag", "last-modified", "content-type"}
                                },
                                body=body,
                                etag=response.headers.get("etag"),
                                last_modified=response.headers.get("last-modified"),
                                redirects=redirects,
                                elapsed_ms=(time.perf_counter() - start) * 1000,
                            )
                    raise UpstreamError("FETCH_FAILED", "Redirect limit exceeded", {"url": item.canonical_url})
                except UpstreamError as exc:
                    last_error = exc
                    if exc.code in {"FETCH_CLIENT_ERROR", "FETCH_SSRF_REJECTED", "FETCH_BODY_TOO_LARGE"}:
                        raise
                    if attempt >= self.settings.fetch_retries:
                        raise
                    await asyncio.sleep(min(2**attempt, 4))
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                    last_error = exc
                    if attempt >= self.settings.fetch_retries:
                        break
                    await asyncio.sleep(min(2**attempt, 4))
        finally:
            if owned_client:
                await client.aclose()
        raise UpstreamError("FETCH_FAILED", "Source fetch failed after bounded retries", {"url": item.canonical_url}) from last_error

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        try:
            declared_length = int(content_length) if content_length else None
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > self.settings.max_artifact_bytes:
            raise UpstreamError(
                "FETCH_BODY_TOO_LARGE", "Response exceeds configured artifact limit", {"limit": self.settings.max_artifact_bytes}
            )
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.settings.max_artifact_bytes:
                raise UpstreamError(
                    "FETCH_BODY_TOO_LARGE", "Response exceeds configured artifact limit", {"limit": self.settings.max_artifact_bytes}
                )
            chunks.append(chunk)
        body = b"".join(chunks)
        if not body:
            raise UpstreamError("FETCH_FAILED", "Source returned an empty body", {"status_code": response.status_code})
        return body

    def _validate_url(self, url: str, source: SourceDefinition) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise UpstreamError("FETCH_SSRF_REJECTED", "Only credential-free HTTP(S) URLs are allowed", {"url": url})
        host = parsed.hostname.lower().rstrip(".")
        allowed = {value.lower().rstrip(".") for value in source.allowed_hosts}
        if allowed and host not in allowed and not any(host.endswith(f".{item}") for item in allowed):
            raise UpstreamError("FETCH_SSRF_REJECTED", "URL host is not allowlisted for the source", {"host": host})
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                raise UpstreamError("FETCH_SSRF_REJECTED", "Private or special network address is not allowed", {"host": host})
        except ValueError:
            pass
        return url

    async def _validate_dns(self, url: str) -> None:
        host = urlparse(url).hostname
        if not host:
            raise UpstreamError("FETCH_SSRF_REJECTED", "URL has no hostname", {})
        try:
            addresses = await asyncio.to_thread(self.resolve_host, host)
        except OSError as exc:
            raise UpstreamError("FETCH_SSRF_REJECTED", "Hostname could not be resolved safely", {"host": host}) from exc
        try:
            unsafe = any(not ipaddress.ip_address(address).is_global for address in addresses)
        except ValueError as exc:
            raise UpstreamError("FETCH_SSRF_REJECTED", "Hostname resolved to an invalid address", {"host": host}) from exc
        if not addresses or unsafe:
            raise UpstreamError("FETCH_SSRF_REJECTED", "Hostname resolves to a private or special network address", {"host": host})


def resolve_public_addresses(host: str) -> list[str]:
    """Small testable DNS safety helper for deployments that enable DNS pinning."""

    return [str(item[4][0]) for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
