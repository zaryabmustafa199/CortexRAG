"""
app/core/exceptions.py
----------------------
Single source of all domain exceptions.

Rule: Every service function raises a subclass of CortexException —
NEVER let raw SQLAlchemy / httpx / asyncio exceptions bubble up to routes.

Usage:
    raise AuthenticationException()
    raise InvalidFileException("File content does not match extension.")
    raise LLMProviderException(details={"timeout": 30})
"""

from __future__ import annotations

from typing import Any


class CortexException(Exception):
    """Base for all application-level exceptions."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


# ── Authentication & Authorisation ───────────────────────────────────────────


class AuthenticationException(CortexException):
    code = "AUTH_FAILED"
    status_code = 401
    message = "Invalid or expired credentials."


class ForbiddenException(CortexException):
    code = "FORBIDDEN"
    status_code = 403
    message = "You do not have permission to perform this action."


class RateLimitException(CortexException):
    code = "RATE_LIMITED"
    status_code = 429
    message = "Too many requests. Please slow down."


# ── Resource Not Found ────────────────────────────────────────────────────────


class UserNotFoundException(CortexException):
    code = "USER_NOT_FOUND"
    status_code = 404
    message = "User not found."


class WorkspaceNotFoundException(CortexException):
    code = "WORKSPACE_NOT_FOUND"
    status_code = 404
    message = "Workspace not found."


class DocumentNotFoundException(CortexException):
    code = "DOCUMENT_NOT_FOUND"
    status_code = 404
    message = "Document not found."


class SessionNotFoundException(CortexException):
    code = "SESSION_NOT_FOUND"
    status_code = 404
    message = "Query session not found."


# ── Conflict ─────────────────────────────────────────────────────────────────


class ConflictException(CortexException):
    code = "CONFLICT"
    status_code = 409
    message = "A resource with this identifier already exists."


# ── Business Logic ────────────────────────────────────────────────────────────


class QuotaExceededException(CortexException):
    code = "QUOTA_EXCEEDED"
    status_code = 403
    message = "You have reached the limit for your current plan."


class AccountLockedException(CortexException):
    code = "ACCOUNT_LOCKED"
    status_code = 403
    message = "Account temporarily locked due to repeated failed login attempts."


class TokenRevokedException(CortexException):
    code = "TOKEN_REVOKED"
    status_code = 401
    message = "This token has been revoked."


# ── File Upload & Parsing ─────────────────────────────────────────────────────


class InvalidFileException(CortexException):
    code = "INVALID_FILE"
    status_code = 400
    message = "The uploaded file was rejected — invalid or suspicious format."


class FileParsingException(CortexException):
    code = "PARSE_FAILED"
    status_code = 422
    message = "Could not extract readable text from the uploaded document."


class FileTooLargeException(CortexException):
    code = "FILE_TOO_LARGE"
    status_code = 413
    message = "The uploaded file exceeds the size limit for your plan."


# ── External Services ─────────────────────────────────────────────────────────


class LLMProviderException(CortexException):
    code = "LLM_UNAVAILABLE"
    status_code = 503
    message = "The AI language model service is currently unavailable or timed out."


class EmbeddingException(CortexException):
    code = "EMBEDDING_FAILED"
    status_code = 503
    message = "Embedding generation failed. Please try again."


class StorageException(CortexException):
    code = "STORAGE_ERROR"
    status_code = 503
    message = "File storage operation failed. Please try again."


class SearchServiceException(CortexException):
    code = "SEARCH_ERROR"
    status_code = 503
    message = "Search service is temporarily unavailable."
