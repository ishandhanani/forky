"""
Attachment utilities for Forky.

Provides file type detection, content extraction, and preparation
of attachments for LLM API calls.
"""

import base64
import mimetypes
import os
from typing import Optional, Dict, Tuple, List

# Supported file types for LLM APIs
SUPPORTED_IMAGE_TYPES = [
    "image/jpeg",
    "image/png", 
    "image/gif",
    "image/webp"
]

SUPPORTED_TEXT_TYPES = [
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "text/css",
    "application/json",
    "application/xml",
]

# Code file extensions that should be treated as text
CODE_EXTENSIONS = [
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
    ".sql", ".r", ".m", ".mm", ".cs", ".vb", ".lua", ".pl", ".pm"
]

# Maximum file sizes (in bytes)
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB for images
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB for documents


def get_mime_type(filename: str) -> str:
    """
    Determines the MIME type of a file based on its extension.
    
    Args:
        filename: The name of the file.
        
    Returns:
        The MIME type string.
    """
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        return mime_type
    
    # Handle code files explicitly
    ext = os.path.splitext(filename)[1].lower()
    if ext in CODE_EXTENSIONS:
        return "text/plain"
    
    return "application/octet-stream"


def get_attachment_type(mime_type: str, filename: str) -> str:
    """
    Determines whether an attachment is an image, document, or unsupported.
    
    Args:
        mime_type: The MIME type of the file.
        filename: The name of the file.
        
    Returns:
        'image', 'document', or 'unsupported'
    """
    if mime_type in SUPPORTED_IMAGE_TYPES:
        return "image"
    
    if mime_type in SUPPORTED_TEXT_TYPES:
        return "document"
    
    # Check for code files by extension
    ext = os.path.splitext(filename)[1].lower()
    if ext in CODE_EXTENSIONS:
        return "document"
    
    # Check for PDF
    if mime_type == "application/pdf":
        return "document"
    
    return "unsupported"


def is_supported_file(mime_type: str, filename: str) -> bool:
    """
    Checks if a file type is supported for attachment.
    
    Args:
        mime_type: The MIME type of the file.
        filename: The name of the file.
        
    Returns:
        True if the file type is supported.
    """
    return get_attachment_type(mime_type, filename) != "unsupported"


def read_file_as_base64(filepath: str) -> str:
    """
    Reads a file and returns its content as base64-encoded string.
    
    Args:
        filepath: Path to the file.
        
    Returns:
        Base64-encoded content.
    """
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_text_from_pdf(filepath: str) -> Optional[str]:
    """
    Extracts text content from a PDF file.
    
    Args:
        filepath: Path to the PDF file.
        
    Returns:
        Extracted text content, or None if extraction fails.
    """
    try:
        import PyPDF2
        
        text_parts = []
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        
        return "\n\n".join(text_parts) if text_parts else None
    except ImportError:
        print("PyPDF2 not installed. PDF text extraction unavailable.")
        return None
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None


def extract_text_from_file(filepath: str, mime_type: str) -> Optional[str]:
    """
    Extracts text content from supported document types.
    
    Args:
        filepath: Path to the file.
        mime_type: MIME type of the file.
        
    Returns:
        Text content, or None if extraction fails.
    """
    if mime_type == "application/pdf":
        return extract_text_from_pdf(filepath)
    
    # For text-based files, read directly
    try:
        # Try UTF-8 first
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # Fallback to latin-1
        try:
            with open(filepath, "r", encoding="latin-1") as f:
                return f.read()
        except Exception:
            return None
    except Exception as e:
        print(f"Error reading text file: {e}")
        return None


def prepare_attachment_for_llm(
    filepath: str,
    original_name: str,
    mime_type: str
) -> Optional[Dict]:
    """
    Prepares an attachment dictionary for LLM API call.
    
    Args:
        filepath: Path to the saved file.
        original_name: Original filename from upload.
        mime_type: MIME type of the file.
        
    Returns:
        Dictionary with attachment data ready for LLM, or None if unsupported.
        Format: {type, name, mime_type, data}
    """
    attachment_type = get_attachment_type(mime_type, original_name)
    
    if attachment_type == "unsupported":
        return None
    
    if attachment_type == "image":
        try:
            data = read_file_as_base64(filepath)
            return {
                "type": "image",
                "name": original_name,
                "mime_type": mime_type,
                "data": data
            }
        except Exception as e:
            print(f"Error reading image file: {e}")
            return None
    
    elif attachment_type == "document":
        text = extract_text_from_file(filepath, mime_type)
        if text:
            # Truncate very long documents
            max_chars = 100000  # ~25k tokens
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[... truncated due to length ...]"
            
            return {
                "type": "document",
                "name": original_name,
                "mime_type": mime_type,
                "data": text
            }
        return None
    
    return None


def get_supported_extensions() -> List[str]:
    """
    Returns a list of supported file extensions for the frontend.
    
    Returns:
        List of extension strings (e.g., ['.jpg', '.pdf', ...])
    """
    extensions = []
    
    # Image extensions
    for mime in SUPPORTED_IMAGE_TYPES:
        exts = mimetypes.guess_all_extensions(mime)
        extensions.extend(exts)
    
    # Text extensions
    extensions.extend([".txt", ".md", ".csv", ".json", ".html", ".css", ".xml"])
    
    # Code extensions
    extensions.extend(CODE_EXTENSIONS)
    
    # PDF
    extensions.append(".pdf")
    
    return list(set(extensions))


def validate_file_size(size_bytes: int, mime_type: str) -> Tuple[bool, str]:
    """
    Validates that a file size is within limits.
    
    Args:
        size_bytes: File size in bytes.
        mime_type: MIME type of the file.
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if mime_type in SUPPORTED_IMAGE_TYPES:
        if size_bytes > MAX_IMAGE_SIZE:
            return False, f"Image too large. Maximum size is {MAX_IMAGE_SIZE // (1024*1024)}MB"
    else:
        if size_bytes > MAX_DOCUMENT_SIZE:
            return False, f"Document too large. Maximum size is {MAX_DOCUMENT_SIZE // (1024*1024)}MB"
    
    return True, ""
