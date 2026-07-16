"""
app/api/v1/usage.py
-------------------
API endpoints for retrieving user usage records and quotas.
"""
from __future__ import annotations

import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import get_current_user
from app.core.exceptions import UserNotFoundException
from app.db.session import AsyncSessionLocal
from app.models.user import Profile, User
from app.schemas.usage import UsageSummaryResponse
from app.services.usage_service import UsageService

router = APIRouter(prefix="/usage", tags=["Usage & Quota Tracking"])


@router.get("/me", response_model=UsageSummaryResponse)
async def get_my_usage(
    current_user: User = Depends(get_current_user),
) -> UsageSummaryResponse:
    """
    Get current month usage records and subscription limits for the authenticated user.

    NOTE: This endpoint does NOT require workspace_id because usage is tracked
    per-user (not per-workspace). Using get_rls_db here caused a 422 error since
    that dependency mandates a workspace_id query parameter.
    """
    async with AsyncSessionLocal() as db:
        profile_result = await db.execute(
            select(Profile).where(Profile.user_id == current_user.id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            raise UserNotFoundException("User profile not found.")

        usage_service = UsageService(db)
        usage_rec = await usage_service.get_current_usage_record(current_user.id)

        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        if usage_rec is None:
            return UsageSummaryResponse(
                month=start_of_month,
                query_count=0,
                query_limit=profile.query_limit_monthly,
                token_count=0,
                cost_usd=0.0,
                tier=profile.tier,
            )

        return UsageSummaryResponse(
            month=usage_rec.month,
            query_count=usage_rec.query_count,
            query_limit=profile.query_limit_monthly,
            token_count=usage_rec.token_count,
            cost_usd=float(usage_rec.cost_usd),
            tier=profile.tier,
        )
