"""
app/api/v1/users.py
-------------------
User profile and workspace management endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.workspace import (
    MemberRole,  # Required for role comparison in update_workspace; was previously missing
    Workspace,
    WorkspaceMember,
)
from app.schemas.auth import MessageResponse
from app.schemas.user import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    TierToggleRequest,
    UserDetailResponse,
)
from app.schemas.workspace import (
    InviteMemberRequest,
    WorkspaceCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)
from app.services.user_service import UserService, WorkspaceService

router = APIRouter(prefix="/users", tags=["Users & Profile"])
ws_router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# ── Profile ───────────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserDetailResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserDetailResponse:
    """Return the authenticated user's profile including tier and limits."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == current_user.id).options(selectinload(User.profile))
        )
        user = result.scalar_one_or_none()
        if user is None:
            from app.core.exceptions import UserNotFoundException

            raise UserNotFoundException()
        return UserDetailResponse.model_validate(user)


@router.put("/me/password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Change password — verifies current password before updating."""
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        await service.change_password(current_user.id, body.current_password, body.new_password)
    return MessageResponse(message="Password updated successfully.")


@router.put("/me/tier", response_model=MessageResponse)
async def toggle_tier(
    body: TierToggleRequest,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Demo mode: toggle between free and pro tier.
    Instantly updates all limits. No Stripe involved.
    """
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        await service.toggle_tier(current_user.id, body.tier)
    return MessageResponse(message=f"Tier switched to {body.tier}.")


@router.delete("/me", response_model=MessageResponse)
async def delete_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Soft-delete account. User must type 'DELETE' to confirm.
    All data will be purged by a background cleanup job.
    """
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        await service.deactivate_account(current_user.id)
    return MessageResponse(
        message="Account deactivated. Your data will be permanently deleted shortly."
    )


# ── Workspaces ────────────────────────────────────────────────────────────────


@ws_router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceResponse]:
    """List all workspaces the user is a member of."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace)
            .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == current_user.id)
            .options(selectinload(Workspace.members))
        )
        workspaces = result.scalars().all()
        return [WorkspaceResponse.model_validate(ws) for ws in workspaces]


@ws_router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    body: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    """Create a new workspace. Enforces tier workspace count limits."""
    async with AsyncSessionLocal() as db:
        # Get profile for limit check
        from sqlalchemy import select as sa_select

        from app.models.user import Profile

        profile_result = await db.execute(
            sa_select(Profile).where(Profile.user_id == current_user.id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            from app.core.exceptions import UserNotFoundException

            raise UserNotFoundException("Profile not found.")

        service = WorkspaceService(db)
        workspace = await service.create_workspace(current_user.id, body.name, profile)
        return WorkspaceResponse.model_validate(workspace)


@ws_router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    """Get workspace details including member list."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .options(selectinload(Workspace.members))
        )
        workspace = result.scalar_one_or_none()
        if workspace is None:
            from app.core.exceptions import WorkspaceNotFoundException

            raise WorkspaceNotFoundException()

        # Verify membership
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if member_result.scalar_one_or_none() is None:
            from app.core.exceptions import ForbiddenException

            raise ForbiddenException("You are not a member of this workspace.")

        return WorkspaceResponse.model_validate(workspace)


@ws_router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    """Rename a workspace. Requester must be ADMIN."""
    async with AsyncSessionLocal() as db:
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        membership = member_result.scalar_one_or_none()
        if membership is None or membership.role != MemberRole.ADMIN:
            from app.core.exceptions import ForbiddenException

            raise ForbiddenException("Only workspace admins can rename the workspace.")

        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if workspace is None:
            from app.core.exceptions import WorkspaceNotFoundException

            raise WorkspaceNotFoundException()

        workspace.name = body.name
        await db.commit()

        # Re-query with selectinload to populate workspace.members in the response.
        # db.refresh() alone does not eagerly load relationships, which caused the
        # returned WorkspaceResponse.members list to always be empty after a rename.
        refreshed = await db.execute(
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .options(selectinload(Workspace.members))
        )
        workspace = refreshed.scalar_one()
        return WorkspaceResponse.model_validate(workspace)


@ws_router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse, status_code=201)
async def add_member(
    workspace_id: uuid.UUID,
    body: InviteMemberRequest,
    current_user: User = Depends(get_current_user),
) -> WorkspaceMemberResponse:
    """Add a user to workspace. Requester must be ADMIN."""
    async with AsyncSessionLocal() as db:
        service = WorkspaceService(db)
        member = await service.add_member(workspace_id, current_user.id, body.user_id, body.role)
        return WorkspaceMemberResponse.model_validate(member)


@ws_router.delete("/{workspace_id}/members/{user_id}", response_model=MessageResponse)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Remove a member from workspace. Requester must be ADMIN."""
    async with AsyncSessionLocal() as db:
        service = WorkspaceService(db)
        await service.remove_member(workspace_id, current_user.id, user_id)
    return MessageResponse(message="Member removed from workspace.")
