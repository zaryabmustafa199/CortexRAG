"""
app/services/usage_service.py
-----------------------------
Tracks monthly usage (token count, query count) and enforces subscription quotas.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import QuotaExceededException, UserNotFoundException
from app.models.user import Profile, UsageRecord

logger = structlog.get_logger()


class UsageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_current_usage_record(self, user_id: uuid.UUID) -> UsageRecord | None:
        """Fetch the UsageRecord for the current month."""
        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        result = await self.db.execute(
            select(UsageRecord).where(
                UsageRecord.user_id == user_id, UsageRecord.month == start_of_month
            )
        )
        return result.scalar_one_or_none()

    async def check_query_quota(self, user_id: uuid.UUID) -> None:
        """
        Verify if the user has remaining monthly queries.
        Raises QuotaExceededException if user exceeded limit.
        """
        # Fetch user's profile
        profile_result = await self.db.execute(select(Profile).where(Profile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            raise UserNotFoundException("User profile not found.")

        # Fetch usage record for current month
        usage_rec = await self.get_current_usage_record(user_id)
        if usage_rec and usage_rec.query_count >= profile.query_limit_monthly:
            logger.warning(
                "quota_limit_exceeded",
                user_id=str(user_id),
                query_count=usage_rec.query_count,
                limit=profile.query_limit_monthly,
            )
            raise QuotaExceededException("Monthly query limit reached for your plan.")

    async def record_query_usage(
        self,
        user_id: uuid.UUID,
        tokens_used: int,
    ) -> None:
        """
        Increment query count and token count for the user's current monthly usage.
        Calculates a mock cost per token count.
        """
        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        usage_rec = await self.get_current_usage_record(user_id)

        # Mock cost calculation ($0.0001 per 1000 tokens for local Ollama / nominal operations)
        calculated_cost = Decimal(str(round((tokens_used / 1000.0) * 0.0001, 6)))

        if usage_rec is None:
            usage_rec = UsageRecord(
                user_id=user_id,
                month=start_of_month,
                query_count=1,
                token_count=tokens_used,
                cost_usd=calculated_cost,
            )
            self.db.add(usage_rec)
        else:
            usage_rec.query_count += 1
            usage_rec.token_count += tokens_used
            usage_rec.cost_usd = float(
                Decimal(str(float(usage_rec.cost_usd or 0))) + calculated_cost
            )

        await self.db.flush()
        logger.info(
            "usage_recorded",
            user_id=str(user_id),
            tokens_added=tokens_used,
            total_tokens=usage_rec.token_count,
            total_queries=usage_rec.query_count,
        )
