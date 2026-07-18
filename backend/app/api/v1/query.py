"""
app/api/v1/query.py
-------------------
RAG query endpoints.
Handles multi-turn conversational ask queries, query rewriting, hybrid search, re-ranking,
and streaming the LLM response via SSE (Server-Sent Events) with DB completion persistence.
"""
from __future__ import annotations

import asyncio  # Required for asyncio.get_event_loop() and asyncio.gather() calls
import json
import uuid
from collections.abc import AsyncGenerator, Sequence
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_rls_db
from app.core.exceptions import ForbiddenException, SessionNotFoundException
from app.db.session import AsyncSessionLocal
from app.models.document import LeafChunk, ParentChunk
from app.models.query import Citation, Message, MessageRole, QuerySession
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.query import (
    CreateSessionRequest,
    MessageResponse,
    QueryRequest,
    QuerySessionResponse,
)
from app.services.chunking_service import token_len
from app.services.citation_service import CitationService
from app.services.context_builder import build_context
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.query_rewriter import QueryRewriter
from app.services.reranker_service import RerankerService
from app.services.retrieval_service import RetrievalService
from app.services.usage_service import UsageService

logger = structlog.get_logger()

router = APIRouter(prefix="/query", tags=["RAG Query Engine"])


@router.post("/ask")
async def ask_question(
    request: Request,
    body: QueryRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Submit a query to the RAG engine.
    Applies conversational query rewriting, hybrid pgvector + BM25 search, Cross-Encoder
    re-ranking, context building, and streams the answer using Server-Sent Events (SSE).
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    log = logger.bind(workspace_id=str(body.workspace_id), correlation_id=correlation_id)

    # Validate workspace membership and set up RLS session manually
    # (cannot use get_rls_db dependency because workspace_id is in the request body,
    # not in the URL query string — using it as a dep would cause a 422 conflict)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text as sa_text
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == body.workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if member_result.scalar_one_or_none() is None:
            raise ForbiddenException("You do not have access to this workspace.")
        await db.execute(sa_text(f"SET LOCAL app.workspace_id = '{body.workspace_id}'"))

        # Check query quota
        usage_service = UsageService(db)
        await usage_service.check_query_quota(current_user.id)

    # 1. Resolve or Create QuerySession
    session_id = body.session_id
    if session_id:
        session_result = await db.execute(
            select(QuerySession).where(QuerySession.id == session_id)
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            raise SessionNotFoundException("Query session not found.")
        if session.workspace_id != body.workspace_id:
            raise ForbiddenException("Query session belongs to a different workspace.")
    else:
        # Auto-create session
        title = " ".join(body.question.split()[:5]) + "..."
        session = QuerySession(
            workspace_id=body.workspace_id,
            user_id=current_user.id,
            title=title,
        )
        db.add(session)
        await db.flush()
        session_id = session.id
        log.info("query_session_auto_created", session_id=str(session_id))

    # 2. Save user's question as a Message record
    user_message = Message(
        session_id=session_id,
        workspace_id=body.workspace_id,
        role=MessageRole.USER,
        content=body.question.strip(),
        tokens_used=token_len(body.question),
    )
    db.add(user_message)
    await db.commit()

    # 3. Fetch recent conversation history
    history_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    # Exclude the user message we just inserted from the history when passing to rewriter
    history = list(history_result.scalars().all()[:-1])

    # 4. Rewrite follow-up question
    rewriter = QueryRewriter()
    rewritten_query = await rewriter.rewrite(history, body.question)
    log.info("query_rewritten", original=body.question, rewritten=rewritten_query)

    # Redis Query Cache Check
    import hashlib

    from app.core.redis_client import redis_client

    cache_hash = hashlib.sha256(rewritten_query.encode("utf-8")).hexdigest()
    cache_key = f"cache:{body.workspace_id}:{cache_hash}"
    cached_payload_str = None

    try:
        loop = asyncio.get_event_loop()
        cached_payload_str = await loop.run_in_executor(None, redis_client.get, cache_key)
    except Exception as exc:
        log.error("redis_cache_read_failed", error=str(exc))

    if cached_payload_str:
        log.info("query_cache_hit", cache_key=cache_key)
        try:
            if isinstance(cached_payload_str, bytes):
                cached_payload_str = cached_payload_str.decode("utf-8")
            cached_data = json.loads(cached_payload_str)  # type: ignore[arg-type]
            cached_reply = cached_data["reply"]
            cached_citations = cached_data.get("citations", [])

            async def sse_cached_generator() -> AsyncGenerator[str, None]:
                try:
                    yield f"data: {json.dumps({'session_id': str(session_id)})}\n\n"
                    # Stream chunks simulating real-time typing
                    words = cached_reply.split(" ")
                    for i, word in enumerate(words):
                        token = word + (" " if i < len(words) - 1 else "")
                        yield f"data: {json.dumps({'token': token})}\n\n"
                        await asyncio.sleep(0.01)
                    yield f"data: {json.dumps({'done': True})}\n\n"

                    # Persist messages and citations to DB
                    async with AsyncSessionLocal() as db_write:
                        await db_write.execute(text(f"SET LOCAL app.workspace_id = '{body.workspace_id}'"))
                        assistant_msg = Message(
                            session_id=session_id,
                            workspace_id=body.workspace_id,
                            role=MessageRole.ASSISTANT,
                            content=cached_reply,
                            tokens_used=token_len(cached_reply),
                        )
                        db_write.add(assistant_msg)
                        await db_write.flush()

                        if cached_citations:
                            db_citations = []
                            for c in cached_citations:
                                db_citations.append({
                                    "chunk_id": uuid.UUID(c["chunk_id"]) if c.get("chunk_id") else None,
                                    "page_number": c.get("page_number"),
                                    "section_title": c.get("section_title"),
                                    "confidence_score": c.get("confidence_score"),
                                })
                            citation_service = CitationService()
                            await citation_service.save_citations(
                                db=db_write,
                                message_id=assistant_msg.id,
                                citations_data=db_citations,
                            )

                        usage_service_write = UsageService(db_write)
                        total_tokens = token_len(body.question) + token_len(cached_reply)
                        await usage_service_write.record_query_usage(
                            user_id=current_user.id,
                            tokens_used=total_tokens,
                        )
                        await db_write.commit()
                except Exception as cache_err:
                    log.error("cached_stream_persistence_failed", error=str(cache_err), exc_info=True)
                    yield f"data: {json.dumps({'error': 'Failed to complete cached response.'})}\n\n"

            return StreamingResponse(sse_cached_generator(), media_type="text/event-stream")
        except Exception as parse_err:
            log.error("failed_to_parse_cache_payload", error=str(parse_err))

    # 5. Embed rewritten query
    embed_service = EmbeddingService()
    query_vectors = await embed_service.embed_texts([rewritten_query])
    query_vector = query_vectors[0]

    # 6. Hybrid Search (Parallel Vector + BM25)
    retrieval_service = RetrievalService(db)
    hybrid_results = await retrieval_service.hybrid_search(
        query_text=rewritten_query,
        query_vec=query_vector,
        workspace_id=body.workspace_id,
        top_k=20,
    )

    # 7. Cross-Encoder Re-ranking
    reranker_service = RerankerService()
    reranked_results = await reranker_service.rerank(
        query=rewritten_query,
        results=hybrid_results,
        top_k=5,
    )

    # 8. Assemble context block
    context_block = build_context(reranked_results)

    # 9. Format prompt structure
    system_prompt = (
        "You are a precise document intelligence assistant.\n"
        "Answer the user's question ONLY using the facts present in the provided [CONTEXT] block.\n"
        "Do NOT invent facts, assume facts not present, or extrapolate beyond the text.\n"
        "Cite every claim using the format: [Source N] where N is the source number (e.g. [Source 1]).\n"
        "If you cannot find the answer in the provided documents, say exactly: "
        "\"I cannot find this in the provided documents.\""
    )
    user_prompt = f"[CONTEXT]\n{context_block}\n\n[QUESTION]\n{rewritten_query}"

    # 10. Generate and Stream response via SSE
    llm_service = LLMService()

    async def sse_event_generator() -> AsyncGenerator[str, None]:
        accumulated_text = []
        try:
            # First event: yield session ID if we auto-created a new session
            yield f"data: {json.dumps({'session_id': str(session_id)})}\n\n"

            # Stream LLM generation tokens
            async for token in llm_service.stream_generate(user_prompt, system_prompt):
                accumulated_text.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

            # 11. Ingest full assistant reply to DB on completion
            full_reply = "".join(accumulated_text).strip()
            if full_reply:
                async with AsyncSessionLocal() as db_write:
                    # Enforce RLS setting in background completion thread
                    await db_write.execute(text(f"SET LOCAL app.workspace_id = '{body.workspace_id}'"))

                    assistant_msg = Message(
                        session_id=session_id,
                        workspace_id=body.workspace_id,
                        role=MessageRole.ASSISTANT,
                        content=full_reply,
                        tokens_used=token_len(full_reply),
                    )
                    db_write.add(assistant_msg)
                    await db_write.flush()  # Populate assistant_msg.id

                    # Extract and save citations
                    citation_service = CitationService()
                    citations_data = citation_service.extract_citations(
                        response_text=full_reply,
                        retrieved_results=reranked_results
                    )
                    if citations_data:
                        await citation_service.save_citations(
                            db=db_write,
                            message_id=assistant_msg.id,
                            citations_data=citations_data
                        )

                    # Record query usage
                    usage_service_write = UsageService(db_write)
                    total_tokens = token_len(body.question) + token_len(full_reply)
                    await usage_service_write.record_query_usage(
                        user_id=current_user.id,
                        tokens_used=total_tokens,
                    )

                    await db_write.commit()

                    # Save result to Redis query cache namespace
                    try:
                        serializable_citations = []
                        for c in citations_data:
                            serializable_citations.append({
                                "chunk_id": str(c["chunk_id"]) if c.get("chunk_id") else None,
                                "page_number": c.get("page_number"),
                                "section_title": c.get("section_title"),
                                "confidence_score": c.get("confidence_score"),
                            })
                        cache_payload = {
                            "reply": full_reply,
                            "citations": serializable_citations,
                        }
                        loop_write = asyncio.get_event_loop()
                        await loop_write.run_in_executor(
                            None,
                            lambda: redis_client.setex(cache_key, 300, json.dumps(cache_payload))
                        )
                    except Exception as cache_exc:
                        logger.error("failed_to_write_redis_cache", error=str(cache_exc))

                    logger.info(
                        "assistant_reply_persisted",
                        session_id=str(session_id),
                        len_chars=len(full_reply),
                        citations_count=len(citations_data),
                    )

        except Exception as exc:
            logger.error("sse_stream_generation_failed", error=str(exc), exc_info=True)
            yield f"data: {json.dumps({'error': 'Failed to complete generation. AI provider error.'})}\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")


@router.post("/sessions", response_model=QuerySessionResponse, status_code=201)
async def create_session(
    workspace_id: uuid.UUID,
    body: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> QuerySessionResponse:
    """
    Create a new query session in a workspace.
    """
    title = body.title or "New Chat Session"
    session = QuerySession(
        workspace_id=workspace_id,
        user_id=current_user.id,
        title=title,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session, attribute_names=["id", "created_at", "updated_at"])
    return QuerySessionResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        title=session.title,
        created_at=session.created_at,
        messages=[],
    )


@router.get("/sessions", response_model=list[QuerySessionResponse])
async def list_sessions(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> list[QuerySessionResponse]:
    """
    List all query sessions for a workspace, ordered by creation date descending.
    """
    result = await db.execute(
        select(QuerySession)
        .where(QuerySession.workspace_id == workspace_id)
        .order_by(QuerySession.created_at.desc())
        .options(
            selectinload(QuerySession.messages)
            .selectinload(Message.citations)
            .selectinload(Citation.chunk)
            .selectinload(LeafChunk.parent)
            .selectinload(ParentChunk.document)
        )
    )
    sessions = result.scalars().all()
    return [QuerySessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 50,
    cursor: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> Sequence[Message]:
    """
    Get paginated message history for a query session (cursor-based pagination).
    """
    session_result = await db.execute(
        select(QuerySession).where(QuerySession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundException("Query session not found or access denied.")

    query = select(Message).where(Message.session_id == session_id)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(Message.created_at > cursor_dt)
        except ValueError:
            pass

    # NOTE: Do NOT add another .where(session_id) here — it was already applied above.
    # The previous duplicate .where() was a bug: it shadowed the cursor filter
    # and produced a redundant SQL predicate.
    result = await db.execute(
        query.options(
            selectinload(Message.citations)
            .selectinload(Citation.chunk)
            .selectinload(LeafChunk.parent)
            .selectinload(ParentChunk.document)
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return result.scalars().all()


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_rls_db),
) -> Response:
    """
    Permanently delete a query session and its entire history.
    """
    session_result = await db.execute(
        select(QuerySession).where(QuerySession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise SessionNotFoundException("Query session not found or access denied.")

    await db.delete(session)
    await db.commit()
    return Response(status_code=204)

