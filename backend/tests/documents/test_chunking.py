import pytest
from app.modules.documents.extraction.schemas import ExtractedElement, ElementType, ElementMetadata
from app.modules.documents.chunking.builder import build_chunks

def test_basic_semantic_grouping():
    elements = [
        ExtractedElement(text="Annual Report 2026", element_type=ElementType.TITLE),
        ExtractedElement(text="Financial Highlights", element_type=ElementType.HEADER),
        ExtractedElement(text="Revenue was up 20% this quarter.", element_type=ElementType.NARRATIVE_TEXT),
        ExtractedElement(text="Profits soared to new heights.", element_type=ElementType.NARRATIVE_TEXT),
    ]
    
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 1
    
    # Check that context was properly prepended
    assert "Annual Report 2026 > Financial Highlights" in chunks[0].contextualized_text
    assert "Revenue was up 20% this quarter." in chunks[0].raw_text
    assert "Profits soared to new heights." in chunks[0].raw_text


def test_chunking_size_limit():
    # Construct a massive narrative text
    massive_text = "word " * 600
    elements = [
        ExtractedElement(text="Long Section", element_type=ElementType.HEADER),
        ExtractedElement(text=massive_text, element_type=ElementType.NARRATIVE_TEXT),
    ]
    
    # Using 500 tokens as limit
    chunks = build_chunks(elements, max_tokens=500, overlap=0.1)
    
    assert len(chunks) > 1
    
    for chunk in chunks:
        # All chunks should inherit the header context
        assert "Long Section" in chunk.contextualized_text
        
        # We can't perfectly assert token count without re-importing tiktoken,
        # but we can ensure they've been split up.
        assert len(chunk.raw_text.split()) < 600


def test_table_splitting():
    html_table = \"\"\"
    <table>
        <tr><th>Q1</th><th>Q2</th></tr>
        <tr><td>100</td><td>200</td></tr>
        <tr><td>300</td><td>400</td></tr>
    </table>
    \"\"\"
    elements = [
        ExtractedElement(text="Data Table", element_type=ElementType.HEADER),
        ExtractedElement(
            text="Raw fallback text", 
            element_type=ElementType.TABLE,
            metadata=ElementMetadata(text_as_html=html_table)
        )
    ]
    
    # Setting an artificially low max_tokens to force row splitting
    chunks = build_chunks(elements, max_tokens=10)
    
    assert len(chunks) >= 2
    # Ensure HTML was parsed out (tr/td tags stripped)
    assert "100 | 200" in chunks[1].raw_text or "Q1 | Q2" in chunks[0].raw_text


def test_skip_header_footer():
    elements = [
        ExtractedElement(text="Page 1", element_type=ElementType.HEADER_FOOTER),
        ExtractedElement(text="Real Title", element_type=ElementType.TITLE),
        ExtractedElement(text="Real text.", element_type=ElementType.NARRATIVE_TEXT),
        ExtractedElement(text="Page 1 Footer", element_type=ElementType.HEADER_FOOTER),
    ]
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 1
    assert "Page 1" not in chunks[0].raw_text
    assert "Page 1 Footer" not in chunks[0].raw_text
    assert "Real Title" in chunks[0].contextualized_text
    assert "Real text." in chunks[0].raw_text


def test_list_item_formatting():
    elements = [
        ExtractedElement(text="List Header", element_type=ElementType.HEADER),
        ExtractedElement(text="Item 1", element_type=ElementType.LIST_ITEM),
        ExtractedElement(text="Item 2", element_type=ElementType.LIST_ITEM),
    ]
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 1
    assert "- Item 1" in chunks[0].raw_text
    assert "- Item 2" in chunks[0].raw_text


def test_table_fallback():
    elements = [
        ExtractedElement(
            text="Raw Table Text Row 1 Row 2", 
            element_type=ElementType.TABLE,
            metadata=ElementMetadata() # no HTML
        )
    ]
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 1
    assert "Raw Table Text Row 1 Row 2" in chunks[0].raw_text


def test_successive_headers():
    elements = [
        ExtractedElement(text="Header 1", element_type=ElementType.HEADER),
        ExtractedElement(text="Text A", element_type=ElementType.NARRATIVE_TEXT),
        ExtractedElement(text="Header 2", element_type=ElementType.HEADER),
        ExtractedElement(text="Text B", element_type=ElementType.NARRATIVE_TEXT),
    ]
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 2
    
    assert "Header 1" in chunks[0].contextualized_text
    assert "Text A" in chunks[0].raw_text
    
    assert "Header 2" in chunks[1].contextualized_text
    assert "Text B" in chunks[1].raw_text


def test_massive_single_word():
    # A single word with no spaces that exceeds the token limit
    massive_word = "A" * 2000
    elements = [
        ExtractedElement(text=massive_word, element_type=ElementType.NARRATIVE_TEXT),
    ]
    # Because there are no spaces, _split_and_yield_text can't split it.
    # It should yield a single chunk containing the massive word rather than crashing.
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 1
    assert massive_word in chunks[0].raw_text


def test_massive_table_row():
    # A table row that exceeds max_tokens
    html_table = f\"\"\"
    <table>
        <tr><th>Col1</th></tr>
        <tr><td>{"word " * 600}</td></tr>
    </table>
    \"\"\"
    elements = [
        ExtractedElement(
            text="Fallback text", 
            element_type=ElementType.TABLE,
            metadata=ElementMetadata(text_as_html=html_table)
        )
    ]
    # It should isolate the massive row into its own chunk.
    chunks = build_chunks(elements, max_tokens=100)
    assert len(chunks) == 2
    assert "Col1" in chunks[0].raw_text
    assert "word word" in chunks[1].raw_text


