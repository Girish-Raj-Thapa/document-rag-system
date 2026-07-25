class ExtractionError(Exception):
    """Base exception for all extraction failures."""
    pass

class InvalidFileError(ExtractionError):
    """Raised when a file is missing, empty, or unreadable."""
    pass

class EngineTimeoutError(ExtractionError):
    """Raised when the extraction engine exceeds the execution timeout."""
    pass
