import json
import logging
import httpx
from typing import List

from app.core.config import get_settings
from app.modules.documents.enrichment.base import BaseEnricher
from app.modules.documents.enrichment.schemas import EnrichedMetadata

logger = logging.getLogger(__name__)

class OllamaEnricher(BaseEnricher):
    def __init__(self, model_name: str = "llama3"):
        self.settings = get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")
        self.model_name = model_name
        self.timeout = 120.0

    async def _call_ollama(self, prompt: str, format_json: bool = False) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }
        if format_json:
            payload["format"] = "json"
            
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
            except Exception as e:
                logger.error(f"Ollama enrichment failed: {str(e)}")
                raise

    async def enrich_chunk(self, text: str) -> EnrichedMetadata:
        prompt = f"""
You are an expert document analyzer. Read the following text chunk and provide a brief summary and a list of keywords. 
If you can infer the category of the text, provide it.
Format your output strictly as a JSON object with the following keys:
- "summary": (string) a concise summary
- "keywords": (list of strings) key topics or entities
- "refined_category": (string or null)

Text chunk:
{text}
"""
        response_text = await self._call_ollama(prompt, format_json=True)
        try:
            data = json.loads(response_text)
            return EnrichedMetadata(
                summary=data.get("summary", ""),
                keywords=data.get("keywords", []),
                refined_category=data.get("refined_category")
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Ollama JSON response: {response_text}")
            return EnrichedMetadata(
                summary="",
                keywords=[],
                refined_category=None
            )

    async def generate_global_summary(self, chunk_summaries: List[str]) -> str:
        combined_summaries = "\n".join([f"- {s}" for s in chunk_summaries])
        prompt = f"""
You are an expert document summarizer. Read the following list of section summaries from a document and generate a single, cohesive, and concise global summary of the entire document. Do not output JSON. Just output the text summary directly.

Section summaries:
{combined_summaries}
"""
        response_text = await self._call_ollama(prompt, format_json=False)
        return response_text.strip()
