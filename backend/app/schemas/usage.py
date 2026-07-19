"""
app/schemas/usage.py
--------------------
Pydantic schemas for usage records API endpoints.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class UsageSummaryResponse(BaseModel):
    month: datetime.date
    query_count: int
    query_limit: int
    token_count: int
    cost_usd: float
    tier: str

    model_config = {"from_attributes": True}
