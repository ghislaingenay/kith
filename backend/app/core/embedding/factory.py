"""Factory for instantiating an `EmbeddingProvider` from configuration."""

from core.embedding.config import EmbeddingSettings
from core.embedding.provider import EmbeddingProvider
from core.embedding.voyage_provider import VoyageEmbeddingProvider


class EmbeddingProviderFactory:
    """Builds the configured `EmbeddingProvider`."""

    @staticmethod
    def create(settings: EmbeddingSettings) -> EmbeddingProvider:
        return VoyageEmbeddingProvider(settings)
