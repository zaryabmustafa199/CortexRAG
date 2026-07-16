"""
app/api/v1/router.py
--------------------
Main API v1 router — mounts all sub-routers.

Add new routers here as each step is completed.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as docs_router  # Step 6
from app.api.v1.keys import router as keys_router  # Step 5
from app.api.v1.query import router as query_router  # Step 14
from app.api.v1.usage import router as usage_router  # Step 16
from app.api.v1.users import router as users_router
from app.api.v1.users import ws_router
from app.api.v1.websocket import router as ws_notifications_router  # Step 19

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(ws_router)
api_router.include_router(keys_router)
api_router.include_router(docs_router)
api_router.include_router(query_router)
api_router.include_router(usage_router)
api_router.include_router(ws_notifications_router)





