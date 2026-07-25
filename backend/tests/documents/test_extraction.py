import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from app.modules.documents.extraction.schemas import ElementType, ExtractedElement, ElementMetadata
from app.modules.documents.extraction.exceptions import ExtractionError, InvalidFileError, EngineTimeoutError
from app.modules.documents.extraction.factory import ExtractorFactory
from app.modules.documents.extraction.unstructured_extractor import UnstructuredExtractor
from pydantic import ValidationError


# ---------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------

def test_element_type_missing_fallback():
    # When an unknown type is passed to ElementType, it should fallback to UNKNOWN
    assert ElementType("SomeRandomType") == ElementType.UNKNOWN
    assert ElementType("AnotherUnknown") == ElementType.UNKNOWN

def test_extracted_element_validation():
    # Valid element
    el = ExtractedElement(
        text="Hello World",
        element_type=ElementType.NARRATIVE_TEXT,
        page_number=1,
        confidence=0.95
    )
    assert el.text == "Hello World"
    assert el.element_type == ElementType.NARRATIVE_TEXT

    # Empty text should fail min_length=1
    with pytest.raises(ValidationError):
        ExtractedElement(text="", element_type=ElementType.NARRATIVE_TEXT)

    # Confidence > 1.0 should fail
    with pytest.raises(ValidationError):
        ExtractedElement(text="Valid", element_type=ElementType.NARRATIVE_TEXT, confidence=1.5)

    # Confidence < 0.0 should fail
    with pytest.raises(ValidationError):
        ExtractedElement(text="Valid", element_type=ElementType.NARRATIVE_TEXT, confidence=-0.1)

# ---------------------------------------------------------
# Factory Tests
# ---------------------------------------------------------

def test_extractor_factory():
    # PDF should use hi_res strategy
    extractor = ExtractorFactory.get_extractor(".pdf")
    assert isinstance(extractor, UnstructuredExtractor)
    assert extractor.strategy == "hi_res"
    assert extractor.infer_table_structure is True

    # DOCX should use hi_res strategy
    extractor = ExtractorFactory.get_extractor(" .DOCX ") # Test normalization
    assert extractor.strategy == "hi_res"

    # TXT, MD, CSV should use fast strategy
    for ext in [".txt", ".md", ".csv"]:
        extractor = ExtractorFactory.get_extractor(ext)
        assert extractor.strategy == "fast"
        assert extractor.infer_table_structure is False

    # Unsupported type should raise ValueError
    with pytest.raises(ValueError, match="Unsupported file type"):
        ExtractorFactory.get_extractor(".xyz")

# ---------------------------------------------------------
# UnstructuredExtractor Tests
# ---------------------------------------------------------

@pytest.fixture
def mock_unstructured_element():
    def _create_mock(text, category, page_number=1, text_as_html=None, coordinates=None, prob=0.9):
        mock_el = MagicMock()
        mock_el.text = text
        mock_el.category = category
        mock_el.metadata.page_number = page_number
        mock_el.metadata.text_as_html = text_as_html
        
        if coordinates:
            mock_coords = MagicMock()
            mock_coords.points = coordinates
            mock_el.metadata.coordinates = mock_coords
        else:
            mock_el.metadata.coordinates = None
            
        mock_el.metadata.detection_class_prob = prob
        return mock_el
    return _create_mock


@patch("os.path.exists")
@patch("os.path.getsize")
@patch("os.access")
@pytest.mark.asyncio
async def test_extractor_file_validation(mock_access, mock_getsize, mock_exists):
    extractor = UnstructuredExtractor(strategy="fast", infer_table_structure=False)
    
    # Test missing file
    mock_exists.return_value = False
    with pytest.raises(InvalidFileError, match="Target payload missing"):
        await extractor.extract("/fake/path.txt", ".txt")
        
    # Test empty file
    mock_exists.return_value = True
    mock_getsize.return_value = 0
    with pytest.raises(InvalidFileError, match="Zero-byte payload detected"):
        await extractor.extract("/fake/path.txt", ".txt")
        
    # Test unreadable file
    mock_getsize.return_value = 100
    mock_access.return_value = False
    with pytest.raises(InvalidFileError, match="Read permissions denied"):
        await extractor.extract("/fake/path.txt", ".txt")


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=100)
@patch("os.access", return_value=True)
@patch("app.modules.documents.extraction.unstructured_extractor.asyncio.wait_for", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_extractor_timeout(mock_wait_for, mock_access, mock_getsize, mock_exists):
    extractor = UnstructuredExtractor(strategy="fast", infer_table_structure=False)
    
    mock_wait_for.side_effect = asyncio.TimeoutError()
    
    with pytest.raises(EngineTimeoutError, match="exceeded 300s"):
        await extractor.extract("/fake/path.txt", ".txt")


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=100)
@patch("os.access", return_value=True)
@patch("app.modules.documents.extraction.unstructured_extractor.asyncio.wait_for", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_extractor_general_error(mock_wait_for, mock_access, mock_getsize, mock_exists):
    extractor = UnstructuredExtractor(strategy="fast", infer_table_structure=False)
    
    mock_wait_for.side_effect = Exception("Some weird unstructured error")
    
    with pytest.raises(ExtractionError, match="Parser pipeline crash"):
        await extractor.extract("/fake/path.txt", ".txt")


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=100)
@patch("os.access", return_value=True)
@patch("app.modules.documents.extraction.unstructured_extractor.asyncio.wait_for", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_extractor_successful_parsing(mock_wait_for, mock_access, mock_getsize, mock_exists, mock_unstructured_element):
    extractor = UnstructuredExtractor(strategy="fast", infer_table_structure=False)
    
    # Mocking the output of wait_for (which is the raw elements from unstructured)
    mock_wait_for.return_value = [
        mock_unstructured_element("Title text", "Title"),
        mock_unstructured_element("Some paragraph", "UncategorizedText"),
        mock_unstructured_element("Footer text", "Footer"),
        mock_unstructured_element("Table data", "Table", text_as_html="<table>...</table>", coordinates=((0,0),(1,1))),
        mock_unstructured_element("   ", "Title"), # Empty text should be skipped silently
        mock_unstructured_element("Bad type", "RandomTypeThatDoesntExist")
    ]
    
    with patch('app.modules.documents.extraction.unstructured_extractor.asyncio.get_running_loop'):
        elements = await extractor.extract("/fake/path.pdf", ".pdf")
        
    assert len(elements) == 5
    
    # Verify standard types
    assert elements[0].text == "Title text"
    assert elements[0].element_type == ElementType.TITLE
    
    # Verify noisy type mapping
    assert elements[1].text == "Some paragraph"
    assert elements[1].element_type == ElementType.NARRATIVE_TEXT
    
    assert elements[2].text == "Footer text"
    assert elements[2].element_type == ElementType.HEADER_FOOTER
    
    # Verify metadata mapping
    assert elements[3].text == "Table data"
    assert elements[3].element_type == ElementType.TABLE
    assert elements[3].metadata.text_as_html == "<table>...</table>"
    assert elements[3].metadata.coordinates == [(0.0, 0.0), (1.0, 1.0)]
    
    # Verify unknown fallback
    assert elements[4].text == "Bad type"
    assert elements[4].element_type == ElementType.UNKNOWN
