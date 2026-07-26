import tiktoken
import logging

logger = logging.getLogger("chunking_pipeline")

# We use cl100k_base as a standard tokenizer. 
# While bge-base-en-v1.5 uses its own WordPiece tokenizer, cl100k_base is a  reasonable, fast proxy for token counting before embedding.
_tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    """
    Returns the number of tokens in a text string.
    """
    if not text:
        return 0
    return len(_tokenizer.encode(text, disallowed_special=()))
