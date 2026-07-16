"""
app/core/sanitizer.py
---------------------
Input sanitization utilities using bleach.
"""
from __future__ import annotations

from typing import Annotated
import bleach  # type: ignore[import-untyped]
from pydantic import BeforeValidator

def sanitize_string(v: str | None) -> str | None:
    """Strip all HTML tags and attributes from the input string using bleach."""
    if v is None:
        return None
    if isinstance(v, str):
        return str(bleach.clean(v, tags=[], attributes={}, strip=True))
    return v

# Reusable Pydantic v2 type that automatically sanitizes inputs
SanitizedStr = Annotated[str, BeforeValidator(sanitize_string)]
SanitizedStrOptional = Annotated[str | None, BeforeValidator(sanitize_string)]
