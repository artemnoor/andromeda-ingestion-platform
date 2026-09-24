"""Composition root for the modular monolith."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_ingestion.application.changes.service import ChangeDetectionService
from andromeda_ingestion.application.extraction.service import ExtractionService
from andromeda_ingestion.application.fetching.service import FetchService
from andromeda_ingestion.application.jobs.service import JobService
from andromeda_ingestion.application.orchestration.service import PipelineOrchestrator
from andromeda_ingestion.application.preparation.service import PreparationService
from andromeda_ingestion.application.publishing.service import PublishingService
from andromeda_ingestion.application.sources.service import SourceService
from andromeda_ingestion.application.validation.service import ExtractionValidator
from andromeda_ingestion.application.validation.use_case import ValidationService
from andromeda_ingestion.domain.ports.repositories import IngestionRepositoryPort
from andromeda_ingestion.infrastructure.ai.http_json import StructuredJsonHttpAIAdapter
from andromeda_ingestion.infrastructure.ai.mock import MockAIProviderRouter
from andromeda_ingestion.infrastructure.config import Settings
from andromeda_ingestion.infrastructure.db.repositories import SqlAlchemyIngestionRepository
from andromeda_ingestion.infrastructure.fetchers.fixture import FixtureFileFetcher
from andromeda_ingestion.infrastructure.fetchers.http import SafeHttpFetcher
from andromeda_ingestion.infrastructure.knowledge_core.http import KnowledgeCoreHttpAdapter
from andromeda_ingestion.infrastructure.preparation.generic import GenericDocumentPreparation
from andromeda_ingestion.infrastructure.sources.discovery import ConfiguredSourceDiscovery
from andromeda_ingestion.infrastructure.storage.filesystem import FileSystemArtifactStorage


@dataclass(slots=True)
class AdapterContainer:
    settings: Settings
    storage: FileSystemArtifactStorage
    discovery: ConfiguredSourceDiscovery
    http_fetcher: SafeHttpFetcher
    fixture_fetcher: FixtureFileFetcher
    preparer: GenericDocumentPreparation
    ai_router: MockAIProviderRouter
    core: object

    @classmethod
    def from_settings(cls, settings: Settings, *, core: object | None = None) -> AdapterContainer:
        if core is None:
            if settings.app_env in {"test", "development"} and settings.mock_ai_enabled:
                from andromeda_ingestion.infrastructure.knowledge_core.mock import MockKnowledgeCoreAdapter

                core = MockKnowledgeCoreAdapter(settings.confidence_review_threshold)
            else:
                core = KnowledgeCoreHttpAdapter(settings)
        ai_router = MockAIProviderRouter()
        if settings.ai_provider != "mock" and settings.ai_endpoint and settings.ai_api_key:
            ai_router = MockAIProviderRouter(StructuredJsonHttpAIAdapter(settings.ai_endpoint, settings.ai_api_key, settings.ai_model))
        http_fetcher = SafeHttpFetcher(settings)
        return cls(
            settings=settings,
            storage=FileSystemArtifactStorage(settings.artifact_storage_root),
            discovery=ConfiguredSourceDiscovery(http_fetcher, settings.max_discovery_items),
            http_fetcher=http_fetcher,
            fixture_fetcher=FixtureFileFetcher(settings.max_artifact_bytes, settings.fixture_root),
            preparer=GenericDocumentPreparation(settings.max_prepared_chunks),
            ai_router=ai_router,
            core=core,
        )

    def services(self, session: AsyncSession) -> ServiceBundle:
        repository: IngestionRepositoryPort = SqlAlchemyIngestionRepository(session)
        fetch = FetchService(repository, self.storage, self.http_fetcher, file=self.fixture_fetcher, api=self.http_fetcher)
        preparation = PreparationService(repository, self.storage, self.preparer)
        extraction = ExtractionService(repository, preparation, self.ai_router, self.core, ChangeDetectionService())  # type: ignore[arg-type]
        validation = ValidationService(repository, ExtractionValidator(self.settings), self.core)  # type: ignore[arg-type]
        publishing = PublishingService(repository, self.core)  # type: ignore[arg-type]
        source = SourceService(repository, self.discovery)
        pipeline = PipelineOrchestrator(repository, fetch, preparation, extraction, validation, publishing, self.settings)
        return ServiceBundle(
            repository=repository,
            source=source,
            fetch=fetch,
            preparation=preparation,
            extraction=extraction,
            validation=validation,
            publishing=publishing,
            pipeline=pipeline,
            jobs=JobService(repository, pipeline),
        )


@dataclass(slots=True)
class ServiceBundle:
    repository: IngestionRepositoryPort
    source: SourceService
    fetch: FetchService
    preparation: PreparationService
    extraction: ExtractionService
    validation: ValidationService
    publishing: PublishingService
    pipeline: PipelineOrchestrator
    jobs: JobService
