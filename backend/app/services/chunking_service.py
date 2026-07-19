"""
app/services/chunking_service.py
--------------------------------
Hierarchical chunking service (Parent-Child splitting).
Splits document page lists into ParentChunks (~3000 tokens) and LeafChunks (~400 tokens, 50 token overlap).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog
import tiktoken
from tiktoken import Encoding

logger = structlog.get_logger()

# Tiktoken tokenizer — may be None if the tokenizer download fails
tokenizer: Encoding | None = None
try:
    tokenizer = tiktoken.get_encoding("cl100k_base")
except Exception as exc:
    logger.warning("tiktoken_initialization_failed", error=str(exc))

# Section header detection regex
SECTION_HEADER_REGEX = re.compile(
    r"^(?:#+\s+|SECTION\s+\d+|[IVXLCDM]+\.\s+)([A-Z\d\s,\.\-\'\"]{3,100})$", re.MULTILINE
)


def token_len(text: str) -> int:
    """Return the number of tokens in the given text."""
    if tokenizer:
        return len(tokenizer.encode(text))
    # Fallback to estimated tokens if tiktoken is offline / unavailable
    return len(text) // 4


def detect_section_header(text: str) -> str | None:
    """
    Search the text for patterns indicating a section title/header.
    Returns the title if found, otherwise None.
    """
    match = SECTION_HEADER_REGEX.search(text)
    if match:
        return match.group(1).strip()
    return None


def get_overlap_sentences(sentences: list[str], target_tokens: int = 50) -> tuple[list[str], int]:
    """
    Acquire sentences from the tail of a chunk to achieve target overlap tokens.
    """
    overlap_sents: list[str] = []
    overlap_tokens = 0
    for sent in reversed(sentences):
        sent_tokens = token_len(sent)
        if overlap_tokens + sent_tokens > target_tokens and overlap_sents:
            break
        overlap_sents.insert(0, sent)
        overlap_tokens += sent_tokens
    return overlap_sents, overlap_tokens


def build_leaf_chunks(
    parent_content: str,
    page_start: int,
    page_end: int,
    section_title: str | None,
) -> list[dict[str, Any]]:
    """
    Split parent text into leaf chunks (~400 tokens, ~50 token overlap).
    Extracts years_detected via regex and prepends structural metadata.
    """
    # Extract years (e.g. 1999, 2026)
    years_found = re.findall(r"\b((?:19|20)\d{2})\b", parent_content)
    years_detected = sorted(list({int(y) for y in years_found}))

    # Split parent content into sentences
    sentences = re.split(r"(?<=[.!?])\s+", parent_content)
    leaves: list[dict[str, Any]] = []
    current_sentences: list[str] = []
    current_tokens = 0
    chunk_index = 0

    # Prefix template
    metadata_prefix = f"[Page {page_start}-{page_end} | Section: {section_title or 'Untitled'}] "
    prefix_tokens = token_len(metadata_prefix)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sent_tokens = token_len(sentence)

        # Handle exceptionally long sentences (must be split by words)
        if sent_tokens > (400 - prefix_tokens):
            if current_sentences:
                content = metadata_prefix + " ".join(current_sentences)
                leaves.append(
                    {
                        "content": content,
                        "chunk_index": chunk_index,
                        "token_count": token_len(content),
                        "years_detected": years_detected,
                        "page_number": page_start,
                        "section_title": section_title,
                    }
                )
                chunk_index += 1
                overlap_sents, overlap_tokens = get_overlap_sentences(current_sentences)
                current_sentences = overlap_sents
                current_tokens = overlap_tokens

            words = sentence.split(" ")
            temp_words: list[str] = []
            temp_tokens = 0
            for word in words:
                word_tokens = token_len(word + " ")
                if temp_tokens + word_tokens > (400 - prefix_tokens):
                    frag = " ".join(temp_words)
                    content = metadata_prefix + frag
                    leaves.append(
                        {
                            "content": content,
                            "chunk_index": chunk_index,
                            "token_count": token_len(content),
                            "years_detected": years_detected,
                            "page_number": page_start,
                            "section_title": section_title,
                        }
                    )
                    chunk_index += 1
                    temp_words = temp_words[-5:]  # simple word overlap
                    temp_tokens = token_len(" ".join(temp_words))
                temp_words.append(word)
                temp_tokens += word_tokens
            if temp_words:
                current_sentences = [" ".join(temp_words)]
                current_tokens = temp_tokens
        else:
            # Check if adding sentence violates boundary
            if current_tokens + sent_tokens + prefix_tokens > 400:
                content = metadata_prefix + " ".join(current_sentences)
                leaves.append(
                    {
                        "content": content,
                        "chunk_index": chunk_index,
                        "token_count": token_len(content),
                        "years_detected": years_detected,
                        "page_number": page_start,
                        "section_title": section_title,
                    }
                )
                chunk_index += 1
                overlap_sents, overlap_tokens = get_overlap_sentences(current_sentences)
                current_sentences = overlap_sents
                current_tokens = overlap_tokens

            current_sentences.append(sentence)
            current_tokens += sent_tokens

    if current_sentences:
        content = metadata_prefix + " ".join(current_sentences)
        leaves.append(
            {
                "content": content,
                "chunk_index": chunk_index,
                "token_count": token_len(content),
                "years_detected": years_detected,
                "page_number": page_start,
                "section_title": section_title,
            }
        )

    return leaves


async def build_parent_chunks(pages: list[dict[str, int | str]]) -> list[dict[str, Any]]:
    """
    Group page streams into sections based on section headers, accumulated pages (max 5),
    or accumulated token count (~3000 tokens).

    Yields control back to the event loop after each parent generation.
    """
    parents: list[dict[str, Any]] = []

    current_pages: list[str] = []
    current_tokens = 0
    page_start = 1
    section_title: str | None = None

    for idx, page in enumerate(pages):
        page_num = int(page["page"])
        text = str(page["text"]).strip()
        if not text:
            continue

        page_tokens = token_len(text)

        # Check if page has a new section header
        detected = detect_section_header(text)

        # If a header is detected or size limits exceeded, flush current accumulator
        if (
            detected or len(current_pages) >= 5 or current_tokens + page_tokens > 3000
        ) and current_pages:
            parent_text = "\n\n".join(current_pages)
            parents.append(
                {
                    "content": parent_text,
                    "section_title": section_title,
                    "page_start": page_start,
                    "page_end": page_num - 1,
                    "token_count": token_len(parent_text),
                }
            )

            # Reset counters
            current_pages = []
            current_tokens = 0
            page_start = page_num
            await asyncio.sleep(0)  # yield control to event loop

        if detected:
            section_title = detected

        current_pages.append(text)
        current_tokens += page_tokens

    # Flush final parent chunk
    if current_pages:
        parent_text = "\n\n".join(current_pages)
        parents.append(
            {
                "content": parent_text,
                "section_title": section_title,
                "page_start": page_start,
                "page_end": int(pages[-1]["page"]),
                "token_count": token_len(parent_text),
            }
        )

    return parents
