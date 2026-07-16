"""
app/api/v1/websocket.py
-----------------------
WebSocket endpoints for real-time document ingestion notifications.
"""
from __future__ import annotations

import asyncio
import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.workspace import WorkspaceMember

logger = structlog.get_logger()
router = APIRouter(tags=["Real-time Notifications"])


class ConnectionManager:
    def __init__(self) -> None:
        # Maps workspace_id -> set of active WebSockets
        self.active_connections: dict[uuid.UUID, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, workspace_id: uuid.UUID) -> None:
        await websocket.accept()
        if workspace_id not in self.active_connections:
            self.active_connections[workspace_id] = set()
        self.active_connections[workspace_id].add(websocket)

    def disconnect(self, websocket: WebSocket, workspace_id: uuid.UUID) -> None:
        if workspace_id in self.active_connections:
            self.active_connections[workspace_id].discard(websocket)
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]


manager = ConnectionManager()


@router.websocket("/ws/{workspace_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    token: str = Query(...),
) -> None:
    """
    Establish WebSocket connection for a workspace.
    Authenticates the user using the token passed in the query parameter.
    Listens to Redis Pub/Sub for background ingestion notifications.
    """
    # 1. Authenticate user from JWT token
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=4001, reason="Invalid token claims.")
            return
        user_id = uuid.UUID(user_id_str)
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed.")
        return

    # 2. Check workspace membership
    async with AsyncSessionLocal() as db:
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        membership = member_result.scalar_one_or_none()
        if membership is None:
            await websocket.close(code=4003, reason="Access denied to workspace.")
            return

    # 3. Register client connection
    await manager.connect(websocket, workspace_id)
    log = logger.bind(workspace_id=str(workspace_id), user_id=str(user_id))
    log.info("websocket_connected")

    # 4. Subscribe to Redis pub/sub channel for workspace notifications
    async_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = async_redis.pubsub()
    channel_name = f"cortex:notify:{workspace_id}"
    await pubsub.subscribe(channel_name)

    async def redis_listener() -> None:
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Send message payload directly to the connected websocket client
                    await websocket.send_text(message["data"])
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("websocket_redis_listener_error", error=str(exc))
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()
            await async_redis.close()

    listener_task = asyncio.create_task(redis_listener())

    # 5. Message loop (receives pings, handles disconnects)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        log.info("websocket_disconnected")
    except Exception as exc:
        log.error("websocket_error", error=str(exc))
    finally:
        manager.disconnect(websocket, workspace_id)
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
