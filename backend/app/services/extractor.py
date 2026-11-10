"""Text extraction services for PDFs (page-by-page), web links (cleaned article), and notes."""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.security_ssrf import SSRFValidationError, validate_url_safe

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPage:
    """Represents text extracted from a document with optional page location."""
    content: str
    page_number: Optional[int] = None


class ExtractionError(Exception):
    """Raised when document parsing or extraction fails."""
    pass


def extract_from_pdf(file_path: str) -> List[ExtractedPage]:
    """Extract text from a PDF document page by page, tracking 1-based page numbers.

    Raises:
        ExtractionError: If PDF is corrupted, encrypted without password, or unreadable.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise ExtractionError(f"PDF file not found at: {file_path}")

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:
                raise ExtractionError(f"Encrypted PDF document cannot be read: {e}") from e

        pages: List[ExtractedPage] = []
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ExtractionError("PDF file contains no pages")

        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            cleaned = page_text.strip()
            if cleaned:
                pages.append(ExtractedPage(content=cleaned, page_number=idx + 1))

        if not pages:
            # Handle empty PDF or scanned PDF without OCR text
            pages.append(ExtractedPage(content="[No extractable text found in PDF]", page_number=1))

        return pages

    except PdfReadError as e:
        logger.warning("Corrupted PDF rejected during extraction: %s", e)
        raise ExtractionError(f"Corrupted or invalid PDF format: {e}") from e
    except Exception as e:
        logger.warning("Error reading PDF %s: %s", file_path, e)
        raise ExtractionError(f"Corrupted or invalid PDF: {e}") from e


async def extract_from_link(url: str) -> List[ExtractedPage]:
    """Fetch URL and extract readable main article text, with SSRF protection."""
    try:
        # Validate URL to prevent SSRF against private/loopback/cloud metadata services
        safe_url = validate_url_safe(url)
    except SSRFValidationError as e:
        logger.warning("SSRF blocked during link extraction: %s", e)
        raise ExtractionError(f"Prohibited external link target: {e}") from e

    try:
        headers = {"User-Agent": "RecallBox-Ingestion-Bot/1.0"}
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(safe_url, headers=headers)
            response.raise_for_status()

            # Ensure final redirected URL is also safe
            if str(response.url) != safe_url:
                try:
                    validate_url_safe(str(response.url))
                except SSRFValidationError as e:
                    raise ExtractionError(f"Redirected to prohibited target: {e}") from e

            html_text = response.text

        soup = BeautifulSoup(html_text, "html.parser")

        # Strip scripts, styles, navigation, footer, ads
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            element.decompose()

        # Target article or main tag if present, else body
        target = soup.find("article") or soup.find("main") or soup.body or soup
        text = target.get_text(separator="\n", strip=True)

        if not text:
            raise ExtractionError("No readable content could be extracted from URL")

        return [ExtractedPage(content=text, page_number=None)]

    except httpx.HTTPError as e:
        raise ExtractionError(f"Failed to fetch external link: {e}") from e
    except Exception as e:
        raise ExtractionError(f"Error extracting link content: {e}") from e


def extract_from_note(content: str) -> List[ExtractedPage]:
    """Extract note content as-is."""
    cleaned = content.strip()
    if not cleaned:
        raise ExtractionError("Note content cannot be empty")
    return [ExtractedPage(content=cleaned, page_number=None)]
