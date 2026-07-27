import json
import logging
from typing import List
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.modules.documents.enrichment.base import BaseEnricher
from app.modules.documents.enrichment.schemas import EnrichedMetadata

logger = logging.getLogger(__name__)

class OpenAIEnricher(BaseEnricher):
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.model_name = model_name

    async def enrich_chunk(self, text: str) -> EnrichedMetadata:
        if not self.settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
            
        messages = [
            {"role": "system", "content": "You are an expert document analyzer. Extract a summary, keywords, and a refined category. Respond ONLY with a valid JSON object matching the requested keys."},
            {"role": "user", "content": f"Analyze this text:\n{text}"}
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            return EnrichedMetadata(
                summary=data.get("summary", ""),
                keywords=data.get("keywords", []),
                refined_category=data.get("refined_category")
            )
        except Exception as e:
            logger.error(f"OpenAI enrichment failed: {str(e)}")
            raise

    async def generate_global_summary(self, chunk_summaries: List[str]) -> str:
        if not self.settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
            
        combined_summaries = "\n".join([f"- {s}" for s in chunk_summaries])
        messages = [
            {"role": "system", "content": "You are an expert document summarizer. Generate a single cohesive global summary."},
            {"role": "user", "content": f"Section summaries:\n{combined_summaries}"}
        ]
        
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages
        )
        return response.choices[0].message.content.strip()
