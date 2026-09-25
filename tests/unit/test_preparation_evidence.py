from datetime import UTC, datetime

import pytest

from andromeda_ingestion.domain.contracts import RawArtifact
from andromeda_ingestion.infrastructure.preparation.generic import GenericDocumentPreparation


def _artifact(content_type: str, url: str = "https://example.com/document.html") -> RawArtifact:
    return RawArtifact(
        id="artifact-1",
        source_id="source-1",
        discovered_item_id="item-1",
        requested_url=url,
        canonical_url=url,
        final_url=url,
        retrieved_at=datetime.now(UTC),
        content_type=content_type,
        http_status=200,
        checksum="a" * 64,
        raw_content_location="source-1/aa.bin",
        byte_size=1,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_html_preparation_emits_stable_selector_and_exact_chunk_offsets() -> None:
    body = b"<html><body><main id='program'><h1>Program</h1><p>Admission requirements</p></main></body></html>"

    prepared = await GenericDocumentPreparation().prepare(_artifact("text/html"), body)

    paragraph = next(chunk for chunk in prepared.content_chunks if chunk.text == "Admission requirements")
    assert paragraph.locator.selector == "#program > p"
    assert paragraph.locator.text_start == 0
    assert paragraph.locator.text_end == len(paragraph.text)
    assert paragraph.locator.quote == paragraph.text


@pytest.mark.asyncio
async def test_html_preparation_excludes_page_chrome_and_nested_container_duplicates() -> None:
    body = (
        b"<html><body><nav>Navigation noise</nav><main id='program'><article><section>"
        b"<h1>Program title</h1><p>Admission requirement</p></section></article></main>"
        b"<footer>Footer noise</footer></body></html>"
    )

    prepared = await GenericDocumentPreparation().prepare(_artifact("text/html"), body)

    assert [chunk.text for chunk in prepared.content_chunks] == ["Program title", "Admission requirement"]
    assert prepared.preparation_version == "generic-2"
    assert prepared.structural_hints["content_root"] == "#program"


@pytest.mark.asyncio
async def test_json_preparation_preserves_root_fragment_and_offsets() -> None:
    prepared = await GenericDocumentPreparation().prepare(_artifact("application/json", "https://example.com/data.json"), b'{"code": "09.03.01"}')

    chunk = prepared.content_chunks[0]
    assert chunk.locator.fragment_id == "json-root"
    assert chunk.locator.text_start == 0
    assert chunk.locator.text_end == len(chunk.text)
