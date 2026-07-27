import json
import logging
from typing import List
from google import genai
from google.genai import types

from app.core.config import get_settings
from app.modules.documents.enrichment.base import BaseEnricher
from app.modules.documents.enrichment.schemas import EnrichedMetadata

logger = logging.getLogger(__name__)

class GeminiEnricher(BaseEnricher):
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
        self.model_name = model_name

    async def enrich_chunk(self, text: str) -> EnrichedMetadata:
        if not self.settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")
            
        prompt = f"""
You are an expert document analyzer. Read the following text chunk and provide a brief summary and a list of keywords. 
If you can infer the category of the text, provide it.

Text chunk:
{text}
"""
        try:
            # We use the sync client here as a placeholder for async if not available natively in genai
            # For a production system, we'd run this in a threadpool or use the async client methods
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "summary": {"type": "STRING"},
                            "keywords": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            },
                            "refined_category": {"type": "STRING"}
                        },
                        "required": ["summary", "keywords"]
                    },
                )
            )
            data = json.loads(response.text)
            return EnrichedMetadata(
                summary=data.get("summary", ""),
                keywords=data.get("keywords", []),
                refined_category=data.get("refined_category")
            )
        except Exception as e:
            logger.error(f"Gemini enrichment failed: {str(e)}")
            raise

    async def generate_global_summary(self, chunk_summaries: List[str]) -> str:
        if not self.settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")
            
        combined_summaries = "\n".join([f"- {s}" for s in chunk_summaries])
        prompt = f"""
You are an expert document summarizer. Read the following list of section summaries from a document and generate a single, cohesive, and concise global summary of the entire document. Do not output JSON. Just output the text summary directly.

Section summaries:
{combined_summaries}
"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        return response.text.strip()
