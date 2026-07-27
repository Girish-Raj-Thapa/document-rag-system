from typing import Optional

from app.core.config import get_settings
from .base import BaseEnricher
from .providers.ollama_enricher import OllamaEnricher
from .providers.openai_enricher import OpenAIEnricher
from .providers.gemini_enricher import GeminiEnricher


class EnricherFactory:
    """
    Factory to return the appropriate enricher based on the configured provider.
    """
    @staticmethod
    def get_enricher(provider_name: Optional[str] = None) -> BaseEnricher:
        settings = get_settings()
        provider = provider_name or settings.DEFAULT_LLM_PROVIDER
        
        provider = provider.lower()
        if provider == "ollama":
            return OllamaEnricher()
        elif provider == "openai":
            return OpenAIEnricher()
        elif provider == "gemini":
            return GeminiEnricher()
        else:
            # Fallback to Ollama
            return OllamaEnricher()
