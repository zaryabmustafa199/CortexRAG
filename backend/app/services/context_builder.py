"""
app/services/context_builder.py
-------------------------------
Formats retrieved leaf chunks into a structured context block for LLM prompts.
"""

from __future__ import annotations

from typing import Any


def build_context(results: list[dict[str, Any]]) -> str:
    """
    Format a list of ranked chunks into a single structured string.
    Injects source numbering, document metadata, page numbers, and section headers.

    Safe attribute access is used throughout because BM25 results may carry
    chunks whose ORM ``parent`` relationship is not eagerly loaded.  Using
    ``getattr(..., None)`` prevents AttributeError at runtime and allows the
    context block to be assembled even with partially-loaded objects.
    """
    parts = []
    for i, item in enumerate(results, start=1):
        chunk = item["chunk"]

        # Guard: parent may be None if the relationship was not eagerly loaded
        parent = getattr(chunk, "parent", None)
        doc_id = getattr(parent, "document_id", "unknown") if parent else "unknown"

        # Guard: leaf-level fields that may also be missing
        page_num = getattr(chunk, "page_number", None) or "N/A"
        section = getattr(chunk, "section_title", None) or "Untitled"
        content = getattr(chunk, "content", "")

        header = f"[Source {i} | Doc: {doc_id} | Page: {page_num} | Section: {section}]"
        parts.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(parts)
