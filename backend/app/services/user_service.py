"""
app/services/user_service.py
-----------------------------
Business logic for user profile and workspace management.

Engineering rules:
  - All DB fetches use .scalar_one_or_none() + manual None raise
  - Tier limits applied via TIER_LIMITS dict — single source of truth
  - Account deletion: soft-delete user (is_active=False), queue full purge via Celery
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    QuotaExceededException,
    UserNotFoundException,
    WorkspaceNotFoundException,
)
from app.core.security import hash_password, verify_password
from app.models.user import Profile, User
from app.models.workspace import MemberRole, Workspace, WorkspaceMember

logger = structlog.get_logger()

# Single source of truth for tier limits
TIER_LIMITS: dict[str, dict[str, int]] = {
    "free": {
        "doc_limit": settings.MAX_DOCS_FREE,
        "storage_limit_mb": settings.MAX_UPLOAD_SIZE_MB_FREE,
        "query_limit_monthly": settings.MAX_QUERIES_MONTHLY_FREE,
        "workspace_limit": 1,
    },
    "pro": {
        "doc_limit": settings.MAX_DOCS_PRO,
        "storage_limit_mb": settings.MAX_UPLOAD_SIZE_MB_PRO,
        "query_limit_monthly": settings.MAX_QUERIES_MONTHLY_PRO,
        "workspace_limit": 10,
    },
}


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user_with_profile(self, user_id: uuid.UUID) -> tuple[User, Profile]:
        """Fetch user + profile. Raises UserNotFoundException if either missing."""
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise UserNotFoundException()

        profile_result = await self.db.execute(select(Profile).where(Profile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            raise UserNotFoundException("User profile not found.")

        return user, profile

    async def change_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> None:
        """Verify current password before updating to new hash."""
        user, _ = await self.get_user_with_profile(user_id)

        if not verify_password(current_password, user.hashed_password):
            raise ForbiddenException("Current password is incorrect.")

        user.hashed_password = hash_password(new_password)
        await self.db.commit()
        logger.info("password_changed", user_id=str(user_id))

    async def toggle_tier(self, user_id: uuid.UUID, new_tier: str) -> Profile:
        """
        Demo-only tier toggle (free ↔ pro).
        Updates Profile limits to match the selected tier.
        """
        _, profile = await self.get_user_with_profile(user_id)
        limits = TIER_LIMITS.get(new_tier)
        if limits is None:
            raise ForbiddenException(f"Unknown tier: {new_tier}")

        profile.tier = new_tier
        profile.doc_limit = limits["doc_limit"]
        profile.storage_limit_mb = limits["storage_limit_mb"]
        profile.query_limit_monthly = limits["query_limit_monthly"]

        await self.db.commit()
        await self.db.refresh(profile)
        logger.info("tier_toggled", user_id=str(user_id), tier=new_tier)
        return profile

    async def deactivate_account(self, user_id: uuid.UUID) -> None:
        """
        Soft-delete: set is_active=False.
        A Celery cleanup task (Step 10) handles full data purge asynchronously.
        """
        user, _ = await self.get_user_with_profile(user_id)
        user.is_active = False
        await self.db.commit()
        logger.info("account_deactivated", user_id=str(user_id))

        # Enqueue Celery task to purge all user data (GDPR compliant)
        from app.worker.tasks.cleanup import cleanup_user_data

        cleanup_user_data.delay(str(user_id))


class WorkspaceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workspace(self, owner_id: uuid.UUID, name: str, profile: Profile) -> Workspace:
        """
        Create a new workspace for the user.
        Enforces workspace count limit based on tier.
        """
        # Count existing workspaces owned by user
        from sqlalchemy import func
        from sqlalchemy import select as sa_select

        count_result = await self.db.execute(
            sa_select(func.count()).select_from(Workspace).where(Workspace.owner_id == owner_id)
        )
        owned_count = count_result.scalar() or 0
        ws_limit = TIER_LIMITS.get(profile.tier, TIER_LIMITS["free"])["workspace_limit"]

        if owned_count >= ws_limit:
            raise QuotaExceededException(
                f"Your {profile.tier} plan allows up to {ws_limit} workspace(s).",
                details={"current": owned_count, "limit": ws_limit},
            )

        workspace = Workspace(name=name, owner_id=owner_id)
        self.db.add(workspace)
        await self.db.flush()

        # Auto-add owner as ADMIN
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=owner_id,
            role=MemberRole.ADMIN,
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(workspace)
        logger.info("workspace_created", workspace_id=str(workspace.id), owner=str(owner_id))
        return workspace

    async def get_workspace(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Workspace:
        """Fetch workspace — validates user is a member."""
        ws_result = await self.db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = ws_result.scalar_one_or_none()
        if workspace is None:
            raise WorkspaceNotFoundException()

        member_result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if member_result.scalar_one_or_none() is None:
            raise ForbiddenException("You are not a member of this workspace.")

        return workspace

    async def add_member(
        self,
        workspace_id: uuid.UUID,
        inviter_id: uuid.UUID,
        invitee_id: uuid.UUID,
        role: str,
    ) -> WorkspaceMember:
        """
        Add a user to a workspace. Inviter must be ADMIN.
        Raises ConflictException if user is already a member.
        """
        # Check inviter is admin
        inviter_result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == inviter_id,
            )
        )
        inviter_membership = inviter_result.scalar_one_or_none()
        if inviter_membership is None or inviter_membership.role != MemberRole.ADMIN:
            raise ForbiddenException("Only workspace admins can add members.")

        # Check invitee not already a member
        existing_result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == invitee_id,
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            raise ConflictException("User is already a member of this workspace.")

        # Verify invitee user exists
        invitee_result = await self.db.execute(select(User).where(User.id == invitee_id))
        if invitee_result.scalar_one_or_none() is None:
            raise UserNotFoundException("Invited user not found.")

        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=invitee_id,
            role=MemberRole(role),
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        logger.info(
            "member_added", workspace_id=str(workspace_id), user_id=str(invitee_id), role=role
        )
        return member

    async def remove_member(
        self,
        workspace_id: uuid.UUID,
        remover_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """
        Remove a member from workspace. Remover must be ADMIN.
        Cannot remove the workspace owner.
        """
        ws_result = await self.db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = ws_result.scalar_one_or_none()
        if workspace is None:
            raise WorkspaceNotFoundException()

        if target_user_id == workspace.owner_id:
            raise ForbiddenException("Cannot remove the workspace owner.")

        remover_result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == remover_id,
            )
        )
        remover = remover_result.scalar_one_or_none()
        if remover is None or remover.role != MemberRole.ADMIN:
            raise ForbiddenException("Only workspace admins can remove members.")

        target_result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == target_user_id,
            )
        )
        target = target_result.scalar_one_or_none()
        if target is None:
            raise ForbiddenException("User is not a member of this workspace.")

        await self.db.delete(target)
        await self.db.commit()
        logger.info("member_removed", workspace_id=str(workspace_id), user_id=str(target_user_id))
