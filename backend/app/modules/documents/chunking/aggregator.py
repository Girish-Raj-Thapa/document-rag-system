import logging
from typing import List, Generator
from html.parser import HTMLParser

from .schemas import RawChunk
from .tokenizer import count_tokens
from app.modules.documents.extraction.schemas import ExtractedElement, ElementType

logger = logging.getLogger("chunking_pipeline")

MAX_CHUNK_TOKENS = 500
OVERLAP_PERCENTAGE = 0.15


class TableRowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.in_row = False
        self.in_cell = False
        self.current_data = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_data = []

    def handle_endtag(self, tag):
        if tag == "tr":
            self.in_row = False
            if self.current_row:
                self.rows.append(" | ".join(self.current_row))
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = False
            self.current_row.append("".join(self.current_data).strip())

    def handle_data(self, data):
        if self.in_cell:
            self.current_data.append(data)


def parse_table_rows(html: str) -> List[str]:
    parser = TableRowParser()
    parser.feed(html)
    return parser.rows


class SemanticAggregator:
    def __init__(self, max_tokens: int = MAX_CHUNK_TOKENS, overlap: float = OVERLAP_PERCENTAGE):
        self.max_tokens = max_tokens
        self.overlap = overlap
        
        self.current_title = ""
        self.current_header = ""
        
        self._current_chunk_text = ""
        self._current_chunk_metadata = []

    def _get_context_prefix(self) -> str:
        parts = []
        if self.current_title:
            parts.append(self.current_title)
        if self.current_header:
            parts.append(self.current_header)
        
        if not parts:
            return ""
        return " > ".join(parts) + "\n\n"

    def _flush_chunk(self) -> RawChunk | None:
        if not self._current_chunk_text.strip():
            return None
            
        chunk = RawChunk(
            raw_text=self._current_chunk_text.strip(),
            contextualized_text=self._get_context_prefix() + self._current_chunk_text.strip(),
            metadata={"source_elements": list(self._current_chunk_metadata)}
        )
        self._current_chunk_text = ""
        self._current_chunk_metadata = []
        return chunk

    def _split_and_yield_text(self, text: str) -> Generator[RawChunk, None, None]:
        # Simple splitting logic by tokens (sliding window)
        words = text.split()
        current_words = []
        current_tokens = 0
        
        overlap_tokens_limit = int(self.max_tokens * self.overlap)
        
        for word in words:
            word_tokens = count_tokens(word + " ")
            if current_tokens + word_tokens > self.max_tokens and current_words:
                self._current_chunk_text = " ".join(current_words)
                yield self._flush_chunk()
                
                # Keep overlap
                overlap_words = []
                overlap_t = 0
                for w in reversed(current_words):
                    wt = count_tokens(w + " ")
                    if overlap_t + wt > overlap_tokens_limit:
                        break
                    overlap_words.insert(0, w)
                    overlap_t += wt
                
                current_words = overlap_words
                current_tokens = overlap_t

            current_words.append(word)
            current_tokens += word_tokens
            
        if current_words:
            self._current_chunk_text = " ".join(current_words)
            yield self._flush_chunk()

    def process(self, elements: List[ExtractedElement]) -> Generator[RawChunk, None, None]:
        for element in elements:
            # Skip HeaderFooter for chunking as they add noise
            if element.element_type == ElementType.HEADER_FOOTER:
                continue

            if element.element_type == ElementType.TITLE:
                if self._current_chunk_text:
                    yield self._flush_chunk()
                self.current_title = element.text.strip()
                self.current_header = ""  # Reset header on new title
                
            elif element.element_type == ElementType.HEADER:
                if self._current_chunk_text:
                    yield self._flush_chunk()
                self.current_header = element.text.strip()
                
            elif element.element_type == ElementType.TABLE:
                if self._current_chunk_text:
                    yield self._flush_chunk()
                
                if element.metadata.text_as_html:
                    rows = parse_table_rows(element.metadata.text_as_html)
                    # We group rows into chunks that fit within MAX_TOKENS
                    for row in rows:
                        row_tokens = count_tokens(row)
                        if count_tokens(self._current_chunk_text) + row_tokens > self.max_tokens:
                            if self._current_chunk_text:
                                yield self._flush_chunk()
                        self._current_chunk_text += row + "\n"
                        self._current_chunk_metadata.append(element.element_type.value)
                    
                    if self._current_chunk_text:
                        yield self._flush_chunk()
                else:
                    # Fallback to plain text if HTML isn't available
                    self._current_chunk_metadata.append(element.element_type.value)
                    yield from self._split_and_yield_text(element.text)
                    
            elif element.element_type in (ElementType.NARRATIVE_TEXT, ElementType.LIST_ITEM, ElementType.UNKNOWN):
                text = element.text.strip()
                if element.element_type == ElementType.LIST_ITEM:
                    text = f"- {text}"
                
                text_tokens = count_tokens(text)
                
                # Check if this addition would exceed the limit
                current_c_tokens = count_tokens(self._current_chunk_text)
                if current_c_tokens + text_tokens > self.max_tokens:
                    # If this single text itself is too large, we must split it
                    if text_tokens > self.max_tokens:
                        if self._current_chunk_text:
                            yield self._flush_chunk()
                        self._current_chunk_metadata.append(element.element_type.value)
                        yield from self._split_and_yield_text(text)
                        continue
                    else:
                        yield self._flush_chunk()
                
                self._current_chunk_text += text + "\n\n"
                self._current_chunk_metadata.append(element.element_type.value)

        if self._current_chunk_text:
            yield self._flush_chunk()
