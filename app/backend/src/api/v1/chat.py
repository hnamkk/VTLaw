import asyncio
import json
import logging
import time
import uuid
from contextlib import nullcontext
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langfuse import propagate_attributes
from sqlalchemy import delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.schemas import (
    ChatMessageOut,
    ChatMessagesResponse,
    ChatSessionBookmarkRequest,
    ChatSessionBookmarkResponse,
    ChatSessionOut,
    ChatSessionsResponse,
    ChatStreamDoneEvent,
    ChatStreamRequest,
)
from src.auth.dependencies import get_optional_user, require_user
from src.core.config import settings
from src.core.observability import get_langfuse_callback
from src.core.rate_limit import RateLimitResult, public_chat_rate_limiter
from src.db.session import get_session
from src.models.chat_session import ChatMessage, ChatSession
from src.models.quality import QualityObservation
from src.models.user import User
from src.quality.service import complete_observation, fail_observation, start_observation
from src.rag.agent.graph import build_agent
from src.rag.response_metadata import build_chat_response_metadata

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Module-level compiled agent singleton
_rag_agent = build_agent()


def _client_rate_limit_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    cf_connecting_ip = request.headers.get("cf-connecting-ip")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _check_public_chat_rate_limit(request: Request) -> RateLimitResult:
    if not settings.PUBLIC_CHAT_RATE_LIMIT_ENABLED:
        return RateLimitResult(allowed=True)

    key = f"public-chat:{_client_rate_limit_key(request)}"
    return await public_chat_rate_limiter.check_many(
        [
            (
                key,
                settings.PUBLIC_CHAT_RATE_LIMIT_BURST_REQUESTS,
                settings.PUBLIC_CHAT_RATE_LIMIT_BURST_WINDOW_SECONDS,
            ),
            (
                f"{key}:sustained",
                settings.PUBLIC_CHAT_RATE_LIMIT_SUSTAINED_REQUESTS,
                settings.PUBLIC_CHAT_RATE_LIMIT_SUSTAINED_WINDOW_SECONDS,
            ),
        ]
    )


def _make_session_title(question: str) -> str:
    title = " ".join(question.split())
    return title[:77] + "..." if len(title) > 80 else title


def _session_out(session: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        is_bookmarked=getattr(session, "is_bookmarked", False),
        bookmark_title=getattr(session, "bookmark_title", None),
        bookmarked_at=getattr(session, "bookmarked_at", None),
    )


def _message_out(message: ChatMessage) -> ChatMessageOut:
    metadata = message.response_metadata or build_chat_response_metadata(
        content=message.content,
        citations=message.citations or [],
        faithfulness_score=message.faithfulness_score,
        is_out_of_scope=message.is_out_of_scope,
    )
    return ChatMessageOut(
        message_id=message.message_id,
        role=message.role,
        content=message.content,
        citations=message.citations or [],
        faithfulness_score=message.faithfulness_score,
        is_out_of_scope=message.is_out_of_scope,
        created_at=message.created_at,
        **metadata,
    )


async def _get_owned_session(
    db_session: AsyncSession, session_id: str, user_id: str
) -> ChatSession | None:
    result = await db_session.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id, ChatSession.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def _create_or_get_owned_session(
    db_session: AsyncSession,
    *,
    session_id: str,
    user_id: str,
    question: str,
) -> ChatSession:
    await db_session.execute(
        pg_insert(ChatSession)
        .values(session_id=session_id, user_id=user_id, title=_make_session_title(question))
        .on_conflict_do_nothing(index_elements=[ChatSession.session_id])
    )
    session = await _get_owned_session(db_session, session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện này.",
        )
    return session


async def _persist_assistant_message_if_owned(
    db_session: AsyncSession,
    *,
    session_id: str,
    user_id: str,
    done_payload: dict,
) -> bool:
    session = await _get_owned_session(db_session, session_id, user_id)
    if session is None:
        return False

    session.updated_at = func.now()
    db_session.add(
        ChatMessage(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=done_payload["content"],
            citations=done_payload["citations"],
            response_metadata={
                "risk_level": done_payload["risk_level"],
                "answer_mode": done_payload["answer_mode"],
                "confidence": done_payload["confidence"],
                "provision_citations": done_payload["provision_citations"],
                "document_sources": done_payload["document_sources"],
                "historical_references": done_payload["historical_references"],
                "clarification_question": done_payload["clarification_question"],
            },
            faithfulness_score=done_payload["faithfulness_score"],
            is_out_of_scope=done_payload["is_out_of_scope"],
        )
    )
    await db_session.commit()
    return True


async def _recent_conversation_context(
    db_session: AsyncSession,
    *,
    session_id: str,
    user_id: str,
    limit: int = 6,
) -> str:
    """Load a small, bounded window used only to resolve follow-up questions."""
    result = await db_session.execute(
        select(ChatMessage.role, ChatMessage.content)
        .where(ChatMessage.session_id == session_id, ChatMessage.user_id == user_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    messages = list(reversed(result.all()))
    if not messages:
        return ""

    lines: list[str] = []
    for role, content in messages:
        clean_content = content.split("LƯU Ý PHÁP LÝ:", 1)[0].strip()
        if clean_content:
            speaker = "Người dùng" if role == "user" else "Trợ lý"
            lines.append(f"{speaker}: {clean_content[:600]}")
    return "\n".join(lines)[-3000:]


@router.get("/chat/sessions", response_model=ChatSessionsResponse)
async def list_chat_sessions(
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    """List only chat sessions owned by the authenticated user."""
    result = await db_session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.user_id)
        .order_by(
            desc(ChatSession.is_bookmarked),
            desc(ChatSession.bookmarked_at).nullslast(),
            desc(ChatSession.updated_at),
            desc(ChatSession.created_at),
        )
        .limit(100)
    )
    return ChatSessionsResponse(items=[_session_out(session) for session in result.scalars().all()])


@router.get("/chat/bookmarks", response_model=ChatSessionsResponse)
async def list_bookmarked_chat_sessions(
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    """List bookmarked chat sessions owned by the authenticated user."""
    result = await db_session.execute(
        select(ChatSession)
        .where(
            ChatSession.user_id == current_user.user_id,
            ChatSession.is_bookmarked.is_(True),
        )
        .order_by(desc(ChatSession.bookmarked_at).nullslast(), desc(ChatSession.updated_at))
        .limit(100)
    )
    return ChatSessionsResponse(items=[_session_out(session) for session in result.scalars().all()])


@router.get("/chat/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
async def get_chat_session_messages(
    session_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    """Return messages for one owned chat session."""
    session_id = str(session_id)
    session = await _get_owned_session(db_session, session_id, current_user.user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện này.",
        )

    result = await db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.user_id == current_user.user_id)
        .order_by(ChatMessage.created_at)
    )
    return ChatMessagesResponse(
        session=_session_out(session),
        messages=[_message_out(message) for message in result.scalars().all()],
    )


@router.patch(
    "/chat/sessions/{session_id}/bookmark",
    response_model=ChatSessionBookmarkResponse,
)
async def bookmark_chat_session(
    session_id: UUID,
    payload: ChatSessionBookmarkRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    """Bookmark or rename one owned chat session."""
    session_id = str(session_id)
    session = await _get_owned_session(db_session, session_id, current_user.user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện này.",
        )

    title = " ".join(payload.bookmark_title.split())
    if len(title) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tên đã lưu phải có ít nhất 2 ký tự.",
        )

    session.is_bookmarked = True
    session.bookmark_title = title
    session.bookmarked_at = func.now()
    session.updated_at = func.now()
    await db_session.commit()
    await db_session.refresh(session)
    return ChatSessionBookmarkResponse(session=_session_out(session))


@router.delete("/chat/sessions/{session_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def unbookmark_chat_session(
    session_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    """Remove the saved marker from one owned chat session."""
    session_id = str(session_id)
    session = await _get_owned_session(db_session, session_id, current_user.user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện này.",
        )

    session.is_bookmarked = False
    session.bookmark_title = None
    session.bookmarked_at = None
    session.updated_at = func.now()
    await db_session.commit()


@router.delete("/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    """Delete one owned chat session and its messages."""
    session_id = str(session_id)
    result = await db_session.execute(
        delete(ChatSession).where(
            ChatSession.session_id == session_id, ChatSession.user_id == current_user.user_id
        )
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cuộc trò chuyện này.",
        )
    await db_session.commit()


@router.post("/chat/stream")
async def chat_stream(
    request: ChatStreamRequest,
    raw_request: Request,
    db_session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_optional_user),
):
    """POST /api/v1/chat/stream SSE streaming endpoint.

    Returns one guarded final event with citations and quality metadata.
    """
    session_id = str(request.session_id or uuid.uuid4())
    trace_id = str(uuid.uuid4())
    conversation_context = ""
    if current_user is None:
        rate_limit = await _check_public_chat_rate_limit(raw_request)
        if not rate_limit.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Bạn đang gửi câu hỏi hơi nhanh. Vui lòng chờ "
                    f"khoảng {rate_limit.retry_after_seconds} giây rồi thử lại."
                ),
                headers={"Retry-After": str(rate_limit.retry_after_seconds)},
            )
    if current_user:
        try:
            session = await _create_or_get_owned_session(
                db_session,
                session_id=session_id,
                user_id=current_user.user_id,
                question=request.question,
            )
            conversation_context = await _recent_conversation_context(
                db_session,
                session_id=session_id,
                user_id=current_user.user_id,
            )
            session.updated_at = func.now()
            db_session.add(
                ChatMessage(
                    session_id=session_id,
                    user_id=current_user.user_id,
                    role="user",
                    content=request.question,
                )
            )
            await db_session.commit()
        except HTTPException:
            await db_session.rollback()
            raise

    # Initialize LangGraph configurable config
    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        openai_api_key=settings.OPENAI_API_KEY,
        streaming=False,
        temperature=0.0,
    )

    config = {
        "configurable": {
            # The graph does not use checkpoints as chat history. A unique key
            # prevents concurrent requests from sharing in-memory graph state.
            "thread_id": f"chat:{trace_id}",
            "db_session": db_session,
            "llm": llm,
            "user_id": current_user.user_id if current_user else None,
        }
    }
    langfuse_callback = get_langfuse_callback()
    if langfuse_callback is not None:
        config["callbacks"] = [langfuse_callback]
        config["run_name"] = "legal-chat-response"

    initial_state = {
        "query": request.question,
        "normalized_query": None,
        "retrieval_query": None,
        "query_intent": None,
        "query_document_number": None,
        "query_has_explicit_date": False,
        "conversation_context": conversation_context,
        "follow_up_used": False,
        "follow_up_confidence": None,
        "follow_up_reason": None,
        "scope_result": None,
        "status_filter": "active",
        "retrieved_contexts": [],
        "reranker_failed": False,
        "reranker_used": False,
        "reranker_error_code": None,
        "low_confidence": False,
        "retrieval_candidate_count": 0,
        "rerank_top_score": None,
        "llm_output": None,
        "repealed_notice": None,
        "temporal_notice": None,
        "evidence_policy_notice": None,
        "response_document_sources": [],
        "response_historical_references": [],
        "verified_citations": [],
        "faithfulness_score": None,
        "has_hallucination": False,
        "disclaimer_appended": False,
        "guardrail_triggered": False,
        "guardrail_stage": None,
        "guardrail_reason": None,
        "final_response": None,
        "is_out_of_scope": False,
        "injection_detected": False,
        "kb_version": "kb_v2",
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        started_at = time.perf_counter()
        first_token_latency_ms: int | None = None
        quality_observation: QualityObservation | None = None
        try:
            try:
                quality_observation = await start_observation(
                    db_session,
                    trace_id=trace_id,
                    session_id=session_id,
                    user_id=current_user.user_id if current_user else None,
                    query=request.question,
                    external_tracing_enabled=langfuse_callback is not None,
                )
            except Exception:
                await db_session.rollback()
                logger.warning("Failed to start quality observation %s", trace_id, exc_info=True)

            trace_context = (
                propagate_attributes(
                    trace_name="legal-chat-response",
                    user_id=current_user.user_id if current_user else None,
                    session_id=session_id,
                    tags=["legal-chat", settings.APP_ENV.lower()],
                    metadata={"quality_trace_id": trace_id, "feature": "legal-chat"},
                )
                if langfuse_callback is not None
                else nullcontext()
            )
            with trace_context:
                values = await _rag_agent.ainvoke(initial_state, config=config)
            first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)

            citations_raw = values.get("verified_citations", [])
            citations = [c.model_dump(mode="json") for c in citations_raw]

            metadata = build_chat_response_metadata(
                content=values.get("final_response") or "",
                citations=citations_raw,
                faithfulness_score=values.get("faithfulness_score"),
                is_out_of_scope=values.get("is_out_of_scope", False),
                query_intent=values.get("query_intent"),
                guardrail_reason=values.get("guardrail_reason"),
                query_text=values.get("query"),
                low_confidence=values.get("low_confidence", False),
                document_sources=values.get("response_document_sources"),
                historical_references=values.get("response_historical_references"),
            )
            done_payload = ChatStreamDoneEvent(
                type="done",
                trace_id=trace_id,
                session_id=session_id,
                content=values.get("final_response") or "",
                citations=citations,
                faithfulness_score=values.get("faithfulness_score"),
                is_out_of_scope=values.get("is_out_of_scope", False),
                reranker_failed=values.get("reranker_failed", False),
                reranker_used=values.get("reranker_used", False),
                reranker_error_code=values.get("reranker_error_code"),
                low_confidence=values.get("low_confidence", False),
                retrieval_candidate_count=values.get("retrieval_candidate_count", 0),
                rerank_top_score=values.get("rerank_top_score"),
                query_intent=values.get("query_intent"),
                guardrail_triggered=values.get("guardrail_triggered", False),
                guardrail_stage=values.get("guardrail_stage"),
                guardrail_reason=values.get("guardrail_reason"),
                **metadata,
            ).model_dump(mode="json")

            if quality_observation is not None:
                try:
                    await complete_observation(
                        db_session,
                        quality_observation,
                        values=values,
                        latency_ms=int((time.perf_counter() - started_at) * 1000),
                        first_token_latency_ms=first_token_latency_ms,
                    )
                except Exception:
                    await db_session.rollback()
                    logger.warning(
                        "Failed to complete quality observation %s", trace_id, exc_info=True
                    )

            if current_user:
                try:
                    persisted = await _persist_assistant_message_if_owned(
                        db_session,
                        session_id=session_id,
                        user_id=current_user.user_id,
                        done_payload=done_payload,
                    )
                    if not persisted:
                        logger.info(
                            "Skipped assistant persistence because chat session %s was deleted",
                            session_id,
                        )
                except Exception:
                    await db_session.rollback()
                    logger.error("Failed to persist chat session %s", session_id, exc_info=True)

            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except asyncio.CancelledError:
            logger.info(f"Chat stream for session {session_id} was cancelled by client.")
            if quality_observation is not None:
                try:
                    await asyncio.shield(
                        fail_observation(
                            db_session,
                            quality_observation,
                            error="client_cancelled",
                            latency_ms=int((time.perf_counter() - started_at) * 1000),
                            cancelled=True,
                        )
                    )
                except Exception:
                    logger.warning(
                        "Failed to cancel quality observation %s", trace_id, exc_info=True
                    )
            raise
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            if quality_observation is not None:
                try:
                    await fail_observation(
                        db_session,
                        quality_observation,
                        error=str(e),
                        latency_ms=int((time.perf_counter() - started_at) * 1000),
                    )
                except Exception:
                    await db_session.rollback()
                    logger.warning("Failed to mark quality observation %s", trace_id, exc_info=True)
            error_payload = {"type": "error", "detail": str(e)}
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
