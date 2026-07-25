import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import List
from pydantic import ValidationError

from .base import BaseExtractor
from .schemas import ElementType, ElementMetadata, ExtractedElement
from .exceptions import ExtractionError, InvalidFileError, EngineTimeoutError

logger = logging.getLogger("ingestion_pipeline")

class UnstructuredExtractor(BaseExtractor):
    """Concrete extractor using unstructured with threading for CPU-bound tasks."""
    
    def __init__(self, strategy: str, infer_table_structure: bool, **kwargs):
        self.strategy = strategy
        self.infer_table_structure = infer_table_structure
        self.extra_config = kwargs

    def _validate_file(self, file_path: str) -> None:
        """Physical file integrity checks before allocating engine memory."""
        if not os.path.exists(file_path):
            raise InvalidFileError(f"Target payload missing: {file_path}")
        
        if os.path.getsize(file_path) == 0:
            raise InvalidFileError(f"Zero-byte payload detected. File is empty: {file_path}")
            
        if not os.access(file_path, os.R_OK):
            raise InvalidFileError(f"Read permissions denied for target payload: {file_path}")

    async def extract(self, file_path: str, file_type: str) -> List[ExtractedElement]:
        from unstructured.partition.auto import partition

        self._validate_file(file_path)
        
        raw_elements = []
        try:
            logger.info(f"Invoking Unstructured engine strategy: {self.strategy} on {file_path}")
            
            # Since unstructured is heavily CPU-bound and blocking, we offload to a thread
            loop = asyncio.get_running_loop()
            
            with ThreadPoolExecutor(max_workers=1) as executor:
                # We need a wrapper to pass kwargs nicely and enforce timeout
                def _run_partition():
                    return partition(
                        filename=file_path,
                        strategy=self.strategy,
                        infer_table_structure=self.infer_table_structure,
                        **self.extra_config
                    )
                
                # asyncio.wait_for provides the async timeout handling
                future = loop.run_in_executor(executor, _run_partition)
                raw_elements = await asyncio.wait_for(future, timeout=300)
                
        except asyncio.TimeoutError:
            logger.error(f"Vision model execution limit breached for document: {file_path}")
            raise EngineTimeoutError("Vision model exceeded 300s execution window.")
        except Exception as general_err:
            logger.error(f"Execution engine encountered runtime crash: {str(general_err)}")
            raise ExtractionError(f"Parser pipeline crash: {str(general_err)}")

        standardized_collection: List[ExtractedElement] = []
        
        for item in raw_elements:
            clean_text = getattr(item, "text", "").strip()
            if not clean_text:
                continue 

            try:
                raw_category = getattr(item, "category", "Unknown")
                
                unstructured_mapping = {
                    "UncategorizedText": ElementType.NARRATIVE_TEXT,
                    "CompositeElement": ElementType.NARRATIVE_TEXT,
                    "Footer": ElementType.HEADER_FOOTER,
                    "Header": ElementType.HEADER_FOOTER,
                    "EmailAddress": ElementType.NARRATIVE_TEXT,
                    "PageBreak": ElementType.UNKNOWN,
                    "Image": ElementType.UNKNOWN
                }
                
                if raw_category in unstructured_mapping:
                    resolved_type = unstructured_mapping[raw_category]
                else:
                    resolved_type = ElementType(raw_category)
                
                html_map = getattr(item.metadata, "text_as_html", None) if resolved_type == ElementType.TABLE else None
                
                raw_coords = getattr(item.metadata, "coordinates", None)
                coords = list(raw_coords.points) if raw_coords else None
                
                meta_payload = ElementMetadata(
                    text_as_html=html_map,
                    coordinates=coords,
                    file_name=os.path.basename(file_path)
                )

                element = ExtractedElement(
                    text=clean_text,
                    element_type=resolved_type,
                    page_number=getattr(item.metadata, "page_number", 1),
                    metadata=meta_payload,
                    confidence=getattr(item.metadata, "detection_class_prob", None)
                )
                standardized_collection.append(element)
                
            except ValidationError as ve:
                logger.warning(f"Element failed Pydantic schema validation. Skipping. Reason: {ve}")
                continue
            except Exception as mapping_err:
                logger.warning(f"Structural transformation failure. Skipping element. Reason: {mapping_err}")
                continue

        return standardized_collection
