"""Format preparation into bounded, locator-preserving chunks."""

from __future__ import annotations

import io
import json
from hashlib import sha256
from html import unescape
from uuid import uuid4

from bs4 import BeautifulSoup
from pypdf import PdfReader

from andromeda_ingestion.domain.common import utc_now
from andromeda_ingestion.domain.contracts import ContentChunk, EvidenceLocator, PreparedDocument, RawArtifact
from andromeda_ingestion.domain.errors import ValidationError
from andromeda_ingestion.domain.ports.preparation import DocumentPreparationPort


class GenericDocumentPreparation(DocumentPreparationPort):
    def __init__(self, max_chunks: int = 500) -> None:
        self.max_chunks = max_chunks

    async def prepare(self, artifact: RawArtifact, body: bytes) -> PreparedDocument:
        content_type = (artifact.content_type or "").lower()
        suffix = artifact.canonical_url.lower().split("?")[0].rsplit(".", 1)[-1] if "." in artifact.canonical_url else ""
        try:
            if "pdf" in content_type or suffix == "pdf":
                title, sections, tables, links, chunks, hints = self._pdf(artifact, body)
            elif "html" in content_type or suffix in {"html", "htm"}:
                title, sections, tables, links, chunks, hints = self._html(artifact, body)
            elif "json" in content_type or suffix == "json":
                title, sections, tables, links, chunks, hints = self._json(artifact, body)
            elif "csv" in content_type or suffix == "csv":
                title, sections, tables, links, chunks, hints = self._text(artifact, body, "csv")
            else:
                title, sections, tables, links, chunks, hints = self._text(artifact, body, "text")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(
                "PREPARATION_FAILED", "Document could not be decoded into a prepared representation", {"artifact_id": artifact.id}
            ) from exc
        if not chunks:
            raise ValidationError("PREPARATION_FAILED", "Document produced no content chunks", {"artifact_id": artifact.id})
        if len(chunks) > self.max_chunks:
            chunks = chunks[: self.max_chunks]
            hints["truncated_chunks"] = True
        serialized = [chunk.model_dump(mode="json") for chunk in chunks]
        return PreparedDocument(
            id=uuid4().hex,
            artifact_id=artifact.id,
            preparation_version="generic-1",
            content_fingerprint=sha256(json.dumps(serialized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            document_type=str(artifact.metadata.get("document_kind", "document")),
            title=title,
            sections=sections,
            tables=tables,
            links=links,
            content_chunks=chunks,
            structural_hints=hints,
            prepared_at=utc_now(),
        )

    def _html(self, artifact: RawArtifact, body: bytes) -> tuple[str | None, list[dict], list[dict], list[dict], list[ContentChunk], dict]:
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        sections: list[dict] = []
        tables: list[dict] = []
        links: list[dict] = []
        chunks: list[ContentChunk] = []
        for index, element in enumerate(soup.find_all(["h1", "h2", "h3", "p", "li", "article", "section", "pre"])):
            text = element.get_text(" ", strip=True)
            if not text:
                continue
            selector = element.name if not element.get("id") else f"#{element.get('id')}"
            locator = EvidenceLocator(
                artifact_id=artifact.id,
                source_url=artifact.canonical_url,
                selector=selector,
                text_start=index,
                text_end=index + len(text),
                quote=text[:4000],
            )
            chunks.extend(self._split_chunk(artifact, text, index, locator, "html"))
            if element.name in {"h1", "h2", "h3"}:
                sections.append({"heading": text, "level": int(element.name[1])})
        for table_index, table in enumerate(soup.find_all("table"), start=1):
            rows = [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])] for row in table.find_all("tr")]
            rows = [row for row in rows if row]
            if rows:
                tables.append({"index": table_index, "rows": rows})
                for row_index, row in enumerate(rows, start=1):
                    text = " | ".join(row)
                    locator = EvidenceLocator(
                        artifact_id=artifact.id, source_url=artifact.canonical_url, table=str(table_index), row=row_index, quote=text[:4000]
                    )
                    chunks.extend(self._split_chunk(artifact, text, len(chunks), locator, "table"))
        for link in soup.find_all("a", href=True):
            links.append({"href": str(link["href"]), "text": link.get_text(" ", strip=True)[:512]})
        return title, sections, tables, links, chunks, {"format": "html"}

    def _pdf(self, artifact: RawArtifact, body: bytes) -> tuple[str | None, list[dict], list[dict], list[dict], list[ContentChunk], dict]:
        reader = PdfReader(io.BytesIO(body))
        chunks: list[ContentChunk] = []
        sections: list[dict] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                locator = EvidenceLocator(artifact_id=artifact.id, source_url=artifact.canonical_url, page=page_number, quote=text[:4000])
                chunks.extend(self._split_chunk(artifact, text, page_number, locator, "pdf"))
        metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items() if value is not None}
        return metadata.get("/Title"), sections, [], [], chunks, {"format": "pdf", "pages": len(reader.pages), "pdf_metadata": metadata}

    def _json(self, artifact: RawArtifact, body: bytes) -> tuple[str | None, list[dict], list[dict], list[dict], list[ContentChunk], dict]:
        payload = json.loads(body.decode("utf-8"))
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        locator = EvidenceLocator(artifact_id=artifact.id, source_url=artifact.canonical_url, fragment_id="json-root", quote=text[:4000])
        return (
            None,
            [],
            [],
            [],
            self._split_chunk(artifact, text, 0, locator, "json"),
            {"format": "json", "top_level_type": type(payload).__name__},
        )

    def _text(
        self, artifact: RawArtifact, body: bytes, format_name: str
    ) -> tuple[str | None, list[dict], list[dict], list[dict], list[ContentChunk], dict]:
        text = unescape(body.decode("utf-8", errors="replace")).strip()
        locator = EvidenceLocator(artifact_id=artifact.id, source_url=artifact.canonical_url, fragment_id="text-root", quote=text[:4000])
        return None, [], [], [], self._split_chunk(artifact, text, 0, locator, format_name), {"format": format_name}

    @staticmethod
    def _split_chunk(artifact: RawArtifact, text: str, ordinal: int, locator: EvidenceLocator, kind: str) -> list[ContentChunk]:
        limit = 6000
        parts = [text[index : index + limit] for index in range(0, len(text), limit)]
        return [
            ContentChunk(id=uuid4().hex, artifact_id=artifact.id, text=part, ordinal=ordinal + offset, locator=locator, kind=kind)
            for offset, part in enumerate(parts)
            if part.strip()
        ]
