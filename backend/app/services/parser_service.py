"""
app/services/parser_service.py
------------------------------
Text extraction service for PDF, DOCX, TXT, and MD files.
Extracts text page-by-page or block-by-block streaming to prevent RAM exhaustion.
"""

from __future__ import annotations

import io
from collections.abc import Generator

import docx  # python-docx
import fitz  # PyMuPDF
import structlog

from app.core.exceptions import FileParsingException

logger = structlog.get_logger()


def extract_text_streaming(
    file_bytes: bytes, mime_type: str
) -> Generator[dict[str, int | str], None, None]:
    """
    Stream text from file bytes page-by-page/block-by-block.
    Yields dicts with format: {"page": page_number, "text": page_text}.

    Raises:
        FileParsingException — if the document cannot be parsed or has unsupported formatting.
    """
    try:
        if mime_type == "application/pdf":
            # PDF streaming page-by-page using PyMuPDF
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                # Basic check for empty or corrupted PDF
                if len(doc) == 0:
                    raise FileParsingException("PDF file contains no pages or is corrupted.")

                for page_num, page in enumerate(doc, start=1):
                    raw_text = page.get_text()
                    # Secure clean: encode to UTF-8 replacing invalid sequences and decode back
                    clean_text = raw_text.encode("utf-8", errors="replace").decode("utf-8")
                    yield {"page": page_num, "text": clean_text.strip()}

        elif mime_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",  # docx files are zip archives
        }:
            # Word documents do not have physical pages in raw format.
            # We yield paragraph blocks grouped as mock pages (e.g., every 5 paragraphs)
            doc = docx.Document(io.BytesIO(file_bytes))
            current_page = 1
            buffer = []
            para_count = 0

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                buffer.append(text)
                para_count += 1

                # Yield mock page every 5 non-empty paragraphs
                if para_count >= 5:
                    clean_text = "\n".join(buffer).encode("utf-8", errors="replace").decode("utf-8")
                    yield {"page": current_page, "text": clean_text}
                    buffer = []
                    para_count = 0
                    current_page += 1

            if buffer:
                clean_text = "\n".join(buffer).encode("utf-8", errors="replace").decode("utf-8")
                yield {"page": current_page, "text": clean_text}

        elif mime_type in {"text/plain", "text/markdown", "application/octet-stream"}:
            # Text / Markdown file: treat as a single page
            text = file_bytes.decode("utf-8", errors="replace")
            yield {"page": 1, "text": text}

        else:
            raise FileParsingException(f"Unsupported MIME type for text extraction: {mime_type}")

    except Exception as exc:
        if isinstance(exc, FileParsingException):
            raise exc
        logger.error("parser_extraction_failed", mime_type=mime_type, error=str(exc), exc_info=True)
        raise FileParsingException(f"Failed to parse document: {str(exc)}")
