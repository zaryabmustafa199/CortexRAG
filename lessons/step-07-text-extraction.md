# Step 07 — Text Extraction

## What You're Building
A streaming text extraction pipeline for the background workers. It downloads document binaries from MinIO, detects format types, and extracts clean, normalized UTF-8 text page-by-page (or block-by-block for DOCX paragraphs) without reading the entire document into RAM. It manages DB statuses (`PROCESSING`, `FAILED`), catches transient parsing and network errors, and logs events using structured logs.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **Streaming Text Extraction** | Slicing document structures page-by-page or block-by-block | Crucial for processing large files (e.g. 500-page PDFs) without blowing the memory limit of Celery workers |
| **PyMuPDF (`fitz`)** | A high-performance PDF parsing engine that runs in-process | Rapid, local PDF parsing without executing sub-processes, protecting against XML entity SSRF/XXE vulnerabilities |
| **DOCX Mock Paging** | Grouping structural paragraph lists into logical pages | Normalizes XML paragraphs into page-like structures so downstream chunkers receive uniform input |
| **Strict Error State Machine** | Marking DB records `FAILED` and capturing traceback trace details | Allows the client/dashboard to poll and immediately see exact parse failure causes |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/services/parser_service.py` | PyMuPDF and python-docx text extraction routines | Created |
| `app/worker/tasks/extraction.py` | Worker extraction handler (status setting, download, parse orchestration) | Created |
| `app/services/storage_service.py` | Added `get_file` downloader method | Modified |

---

## Engineering Standards Applied (§5)

- **No RAM Bloat** — Binaries are processed via file streams rather than loading entire files in-memory where possible.
- **Fail-Safe DB Deactivation** — Catching exceptions updates `Document.status` to `FAILED` and persists details in the `error_message` field.
- **UTF-8 normalization** — Encodes to UTF-8 using `errors="replace"` to prune null bytes or broken binary bleeding.
- **Structured Correlation Log Bind** — Logs bind `correlation_id` and `document_id` for tracing.

---

## How to Test This Step

```python
# Create a test script in the scratch directory:
# scratch/test_parser.py
import asyncio
from app.services.parser_service import extract_text_streaming

# Mock file bytes of a simple plain text or read a sample file:
content = b"Page 1 content\n\nPage 2 content"
for page in extract_text_streaming(content, "text/plain"):
    print(page)

# Expected:
# {'page': 1, 'text': 'Page 1 content\n\nPage 2 content'}
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `FileParsingException` (PDF corrupted) | Input binary stream has size 0 or invalid PDF headers | Validate that the file was completely uploaded to MinIO first |
| `ImportError` on `fitz` / `docx` | Missing local python-docx or pymupdf package installs | Re-run package sync/install via the virtual environment |
| Text contains replacement chars `` | Source file contains non-standard binary encodings | Normal behavior of `errors="replace"`; prevents DB character injection crash |

---

## What's Next

**Step 8** — Hierarchical Chunking: parse the page-level text into logical ParentChunks (section boundaries) and LeafChunks (recursively split paragraphs with overlaps) injecting metadata tags.
