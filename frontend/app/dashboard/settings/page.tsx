"use client";

import * as React from "react";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import {
  Settings,
  User,
  ShieldAlert,
  Key,
  FolderLock,
  Plus,
  Trash2,
  Copy,
  Check,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Lock,
  Mail,
  UserPlus,
} from "lucide-react";

interface UsageSummary {
  month: string;
  query_count: number;
  query_limit: number;
  token_count: number;
  cost_usd: number;
  tier: string;
}

interface WorkspaceMemberItem {
  user_id: string;
  role: string;
  invited_at: string;
}

interface WorkspaceDetails {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
  members: WorkspaceMemberItem[];
}

interface APIKeyItem {
  id: string;
  name: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export default function SettingsPage() {
  const { activeWorkspaceId, refreshWorkspaces } = useWorkspace();
  const { user, refreshSession, logout } = useAuth();

  // Settings State
  const [usage, setUsage] = React.useState<UsageSummary | null>(null);
  const [workspace, setWorkspace] = React.useState<WorkspaceDetails | null>(null);
  const [apiKeys, setApiKeys] = React.useState<APIKeyItem[]>([]);
  
  // Loading states
  const [isUsageLoading, setIsUsageLoading] = React.useState(true);
  const [isWorkspaceLoading, setIsWorkspaceLoading] = React.useState(true);
  const [isKeysLoading, setIsKeysLoading] = React.useState(true);
  const [isTogglingTier, setIsTogglingTier] = React.useState(false);

  // Forms states
  const [newWorkspaceName, setNewWorkspaceName] = React.useState("");
  const [isRenamingWorkspace, setIsRenamingWorkspace] = React.useState(false);
  const [renameError, setRenameError] = React.useState<string | null>(null);

  // Invite states
  const [inviteUserId, setInviteUserId] = React.useState("");
  const [inviteRole, setInviteRole] = React.useState("editor");
  const [isInviting, setIsInviting] = React.useState(false);
  const [inviteError, setInviteError] = React.useState<string | null>(null);

  // Key creation states
  const [newKeyName, setNewKeyName] = React.useState("");
  const [isCreatingKey, setIsCreatingKey] = React.useState(false);
  const [createdKeyRaw, setCreatedKeyRaw] = React.useState<string | null>(null);
  const [copiedKey, setCopiedKey] = React.useState(false);
  const [keyError, setKeyError] = React.useState<string | null>(null);

  // Change Password states
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [isChangingPassword, setIsChangingPassword] = React.useState(false);
  const [passwordError, setPasswordError] = React.useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = React.useState<string | null>(null);

  // Account Delete states
  const [deleteConfirmation, setDeleteConfirmation] = React.useState("");
  const [isDeletingAccount, setIsDeletingAccount] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  // Load usages, workspace details, and api keys
  const fetchUsage = React.useCallback(async () => {
    setIsUsageLoading(true);
    try {
      const response = await api.get("/usage/me");
      setUsage(response.data);
    } catch (err) {
      console.error("Failed to fetch usage summary:", err);
    } finally {
      setIsUsageLoading(false);
    }
  }, []);

  const fetchWorkspaceDetails = React.useCallback(async () => {
    if (!activeWorkspaceId) return;
    setIsWorkspaceLoading(true);
    setRenameError(null);
    setInviteError(null);
    try {
      const response = await api.get(`/workspaces/${activeWorkspaceId}`);
      setWorkspace(response.data);
      setNewWorkspaceName(response.data.name);
    } catch (err) {
      console.error("Failed to fetch workspace details:", err);
    } finally {
      setIsWorkspaceLoading(false);
    }
  }, [activeWorkspaceId]);

  const fetchApiKeys = React.useCallback(async () => {
    setIsKeysLoading(true);
    setKeyError(null);
    try {
      const response = await api.get("/keys");
      setApiKeys(response.data);
    } catch (err) {
      console.error("Failed to fetch API keys:", err);
    } finally {
      setIsKeysLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchUsage();
    fetchApiKeys();
  }, [fetchUsage, fetchApiKeys]);

  React.useEffect(() => {
    fetchWorkspaceDetails();
  }, [activeWorkspaceId, fetchWorkspaceDetails]);

  // Handle Mock Tier Toggle
  const handleToggleTier = async () => {
    if (!usage) return;
    setIsTogglingTier(true);
    const targetTier = usage.tier === "free" ? "pro" : "free";
    try {
      await api.put("/users/me/tier", { tier: targetTier });
      // Re-fetch usage to update tier badge and quota limits in the UI.
      // NOTE: refreshSession() was previously called here but is NOT needed —
      // tier changes are reflected in the next /usage/me response.
      // refreshSession() is an auth operation that can redirect to /login
      // if the token is still valid but the refresh endpoint returns an error,
      // causing the upgrade button to appear to silently do nothing.
      await fetchUsage();
    } catch (err: any) {
      console.error("Failed to toggle tier:", err);
      alert("Failed to switch subscription tiers.");
    } finally {
      setIsTogglingTier(false);
    }
  };

  // Handle Workspace Rename
  const handleRenameWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorkspaceName.trim() || !activeWorkspaceId) return;
    setIsRenamingWorkspace(true);
    setRenameError(null);
    try {
      await api.put(`/workspaces/${activeWorkspaceId}`, { name: newWorkspaceName });
      await refreshWorkspaces();
      await fetchWorkspaceDetails();
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || "Failed to rename workspace.";
      setRenameError(msg);
    } finally {
      setIsRenamingWorkspace(false);
    }
  };

  // Handle Invite Member
  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteUserId.trim() || !activeWorkspaceId) return;
    setIsInviting(true);
    setInviteError(null);
    try {
      await api.post(`/workspaces/${activeWorkspaceId}/members`, {
        user_id: inviteUserId.trim(),
        role: inviteRole,
      });
      setInviteUserId("");
      await fetchWorkspaceDetails();
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || "Failed to add workspace member. Check if User UUID exists.";
      setInviteError(msg);
    } finally {
      setIsInviting(false);
    }
  };

  // Handle Remove Member
  const handleRemoveMember = async (targetUserId: string) => {
    if (!activeWorkspaceId) return;
    if (!confirm("Are you sure you want to remove this member from the workspace?")) return;
    try {
      await api.delete(`/workspaces/${activeWorkspaceId}/members/${targetUserId}`);
      await fetchWorkspaceDetails();
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || "Failed to remove member.";
      alert(msg);
    }
  };

  // Handle Create API Key
  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    setIsCreatingKey(true);
    setKeyError(null);
    try {
      const response = await api.post("/keys", { name: newKeyName });
      setCreatedKeyRaw(response.data.raw_key);
      setNewKeyName("");
      await fetchApiKeys();
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || "Failed to generate API key.";
      setKeyError(msg);
    } finally {
      setIsCreatingKey(false);
    }
  };

  // Handle Revoke API Key
  const handleRevokeKey = async (keyId: string) => {
    if (!confirm("Are you sure you want to revoke this API key? This action is permanent and cannot be undone.")) return;
    try {
      await api.delete(`/keys/${keyId}`);
      await fetchApiKeys();
    } catch (err: any) {
      alert("Failed to deactivate API key.");
    }
  };

  // Copy created key raw token
  const copyToClipboard = () => {
    if (createdKeyRaw) {
      navigator.clipboard.writeText(createdKeyRaw);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  // Handle Change Password
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match.");
      return;
    }

    setIsChangingPassword(true);
    try {
      await api.put("/users/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess("Password updated successfully.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || "Failed to update password. Verify complexity rules.";
      setPasswordError(msg);
    } finally {
      setIsChangingPassword(false);
    }
  };

  // Handle Deactivate/Delete Account
  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (deleteConfirmation !== "DELETE") return;
    setIsDeletingAccount(true);
    setDeleteError(null);
    try {
      await api.delete("/users/me", { data: { confirmation: "DELETE" } });
      alert("Account successfully deactivated. Logging out.");
      await logout();
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || "Failed to deactivate account.";
      setDeleteError(msg);
      setIsDeletingAccount(false);
    }
  };

  // Progress bar percentages
  const queryPercent = usage ? Math.min((usage.query_count / usage.query_limit) * 100, 100) : 0;
  const isPro = usage?.tier === "pro";

  return (
    <div className="flex-1 overflow-y-auto px-8 py-8 space-y-8 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground flex items-center space-x-2">
          <Settings className="h-7 w-7 text-primary" />
          <span>Settings & Quota Management</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage workspace members, generate program keys, monitor API usage, and edit your profile settings.
        </p>
      </div>

      {/* Grid: 1. Usage Summary */}
      <Card className="relative overflow-hidden bg-card/65 backdrop-blur-md border-border/30">
        <div className={`absolute top-0 right-0 h-28 w-28 bg-gradient-to-br ${isPro ? "from-amber-500/15 to-transparent" : "from-primary/15 to-transparent"} rounded-bl-full pointer-events-none`} />
        
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Usage & Subscription Plan</CardTitle>
              <CardDescription>Monitor your monthly search query volumes and index thresholds.</CardDescription>
            </div>
            <div className="flex items-center space-x-2">
              <Badge variant={isPro ? "warning" : "primary"} className="px-3 py-1 font-mono uppercase font-bold tracking-wider">
                {isPro ? "Pro Subscription" : "Free Subscription"}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={handleToggleTier}
                isLoading={isTogglingTier}
                className="h-8 border-primary/20 text-primary hover:bg-primary hover:text-white"
              >
                <Sparkles className="mr-1 h-3.5 w-3.5" />
                {isPro ? "Switch to Free" : "Upgrade to Pro"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {isUsageLoading ? (
            <div className="flex justify-center py-6">
              <Spinner size="sm" />
            </div>
          ) : usage && (
            <div className="grid grid-cols-3 gap-6">
              {/* Queries Progress */}
              <div className="col-span-2 space-y-2.5">
                <div className="flex items-center justify-between text-sm font-medium">
                  <span className="text-muted-foreground flex items-center">
                    <RefreshCw className="mr-2 h-4 w-4 text-primary" />
                    Queries Used this month
                  </span>
                  <span className="text-foreground font-semibold">
                    {usage.query_count} / {usage.query_limit}
                  </span>
                </div>
                <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${isPro ? "bg-amber-400" : "bg-primary"}`}
                    style={{ width: `${queryPercent}%` }}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground font-mono">
                  Reset date: Next month (1st of the month). Enforced by UsageService quota block.
                </p>
              </div>

              {/* Tokens Stats */}
              <div className="p-4 rounded-xl border border-border/40 bg-background/40 flex flex-col justify-between">
                <div>
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block">
                    Total Tokens Processed
                  </span>
                  <span className="text-2xl font-black text-foreground font-mono mt-1 block">
                    {usage.token_count.toLocaleString()}
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground block mt-2">
                  Cumulative LLM prompts + responses tokens
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Grid: 2. Workspace Management */}
      <Card className="bg-card/65 backdrop-blur-md border-border/30">
        <CardHeader>
          <CardTitle>Workspace Settings</CardTitle>
          <CardDescription>Rename the active workspace and manage editors or viewers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {isWorkspaceLoading ? (
            <div className="flex justify-center py-6">
              <Spinner size="sm" />
            </div>
          ) : workspace && (
            <div className="space-y-6">
              {/* Rename Form */}
              <form onSubmit={handleRenameWorkspace} className="space-y-3 max-w-md">
                <div className="flex items-end gap-3">
                  <div className="flex-1 space-y-1.5">
                    <label htmlFor="w-name" className="text-xs font-semibold text-muted-foreground uppercase">
                      Workspace Name
                    </label>
                    <input
                      id="w-name"
                      type="text"
                      required
                      value={newWorkspaceName}
                      onChange={(e) => setNewWorkspaceName(e.target.value)}
                      placeholder="Workspace name"
                      className="flex h-10 w-full rounded-lg border border-input bg-background/50 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
                    />
                  </div>
                  <Button type="submit" isLoading={isRenamingWorkspace} className="h-10">
                    Rename
                  </Button>
                </div>
                {renameError && (
                  <div className="flex items-center space-x-1.5 text-xs text-destructive">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    <span>{renameError}</span>
                  </div>
                )}
              </form>

              <div className="h-px bg-border/40 my-4" />

              {/* Invite Member Section */}
              <div className="grid grid-cols-3 gap-6">
                {/* Invite Form */}
                <div className="space-y-4">
                  <h3 className="text-sm font-bold text-foreground flex items-center">
                    <UserPlus className="mr-2 h-4 w-4 text-primary" />
                    Invite Member
                  </h3>
                  <form onSubmit={handleInviteMember} className="space-y-3.5">
                    <div className="space-y-1.5">
                      <label htmlFor="invitee-id" className="text-xs font-semibold text-muted-foreground uppercase">
                        Invitee User ID (UUID)
                      </label>
                      <input
                        id="invitee-id"
                        type="text"
                        required
                        value={inviteUserId}
                        onChange={(e) => setInviteUserId(e.target.value)}
                        placeholder="e.g. 550e8400-e29b-..."
                        className="flex h-9 w-full rounded-lg border border-input bg-background/50 px-3 py-1.5 text-xs font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      />
                    </div>
                    
                    <div className="space-y-1.5">
                      <label htmlFor="invitee-role" className="text-xs font-semibold text-muted-foreground uppercase">
                        Workspace Role
                      </label>
                      <select
                        id="invitee-role"
                        value={inviteRole}
                        onChange={(e) => setInviteRole(e.target.value)}
                        className="flex h-9 w-full rounded-lg border border-input bg-card px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        <option value="viewer">Viewer (Read Only)</option>
                        <option value="editor">Editor (Read & Write)</option>
                        <option value="admin">Admin (Full Permissions)</option>
                      </select>
                    </div>

                    <Button type="submit" size="sm" isLoading={isInviting} className="w-full">
                      Add to Workspace
                    </Button>
                    
                    {inviteError && (
                      <div className="flex items-center space-x-1.5 text-xs text-destructive rounded bg-destructive/5 border border-destructive/10 p-2.5">
                        <AlertCircle className="h-4 w-4 shrink-0" />
                        <span className="leading-tight">{inviteError}</span>
                      </div>
                    )}
                  </form>
                </div>

                {/* Members list */}
                <div className="col-span-2 space-y-4">
                  <h3 className="text-sm font-bold text-foreground">Workspace Members ({workspace.members.length})</h3>
                  <div className="rounded-xl border border-border/30 bg-background/40 divide-y divide-border/20 max-h-60 overflow-y-auto">
                    {workspace.members.map((member) => {
                      const isOwner = member.user_id === workspace.owner_id;
                      return (
                        <div key={member.user_id} className="p-3 flex items-center justify-between text-xs">
                          <div className="min-w-0 flex-1">
                            <div className="font-mono text-foreground font-medium truncate flex items-center">
                              <Mail className="h-3 w-3 mr-1 text-muted-foreground" />
                              {member.user_id}
                              {isOwner && (
                                <Badge variant="outline" className="ml-1.5 border-primary/20 text-primary font-sans text-[8px] py-0">
                                  Owner
                                </Badge>
                              )}
                            </div>
                            <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">
                              Invited: {new Date(member.invited_at).toLocaleDateString()}
                            </p>
                          </div>
                          
                          <div className="flex items-center space-x-2.5">
                            <Badge variant={member.role === "admin" ? "warning" : member.role === "editor" ? "primary" : "outline"} className="text-[9px] uppercase font-bold py-0.5 px-2 font-mono">
                              {member.role}
                            </Badge>
                            
                            {!isOwner && user?.id === workspace.owner_id && (
                              <button
                                onClick={() => handleRemoveMember(member.user_id)}
                                className="text-muted-foreground hover:text-destructive p-1 rounded hover:bg-destructive/10 transition-all cursor-pointer"
                                title="Remove member"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Grid: 3. API Keys Section */}
      <Card className="bg-card/65 backdrop-blur-md border-border/30">
        <CardHeader>
          <CardTitle>API Key Management</CardTitle>
          <CardDescription>Generate token keys for secure programmatic API integration.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Create Key Form */}
          <form onSubmit={handleCreateKey} className="space-y-3 max-w-md">
            <div className="flex items-end gap-3">
              <div className="flex-1 space-y-1.5">
                <label htmlFor="k-name" className="text-xs font-semibold text-muted-foreground uppercase">
                  Key Label Name
                </label>
                <input
                  id="k-name"
                  type="text"
                  required
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="e.g. Ingestion Script"
                  className="flex h-10 w-full rounded-lg border border-input bg-background/50 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                />
              </div>
              <Button type="submit" isLoading={isCreatingKey} className="h-10">
                <Plus className="mr-1.5 h-4 w-4" />
                Generate
              </Button>
            </div>
            {keyError && (
              <div className="flex items-center space-x-1.5 text-xs text-destructive">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                <span>{keyError}</span>
              </div>
            )}
          </form>

          {/* Keys loop */}
          <div className="space-y-3 pt-2">
            <h3 className="text-sm font-bold text-foreground flex items-center">
              <Key className="mr-2 h-4 w-4 text-primary" />
              Active Keys List
            </h3>
            
            {isKeysLoading ? (
              <div className="flex justify-center py-4">
                <Spinner size="sm" />
              </div>
            ) : apiKeys.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2 italic">No active API keys created yet.</p>
            ) : (
              <div className="rounded-xl border border-border/30 bg-background/40 divide-y divide-border/20">
                {apiKeys.map((k) => (
                  <div key={k.id} className="p-3.5 flex items-center justify-between text-xs font-mono">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-foreground font-sans text-sm">{k.name}</p>
                      <div className="flex items-center space-x-3 text-[10px] text-muted-foreground mt-1">
                        <span>ID: {k.id}</span>
                        <span>•</span>
                        <span>Created: {new Date(k.created_at).toLocaleDateString()}</span>
                        <span>•</span>
                        <span>Last Used: {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "Never"}</span>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-3 ml-4">
                      {k.is_active ? (
                        <Badge variant="success" className="text-[9px] uppercase font-bold py-0.5 px-2">Active</Badge>
                      ) : (
                        <Badge variant="outline" className="text-[9px] uppercase font-bold py-0.5 px-2">Revoked</Badge>
                      )}
                      
                      {k.is_active && (
                        <button
                          onClick={() => handleRevokeKey(k.id)}
                          className="text-muted-foreground hover:text-destructive p-1.5 rounded hover:bg-destructive/10 transition-all cursor-pointer"
                          title="Revoke API key"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Grid: 4. Account Settings */}
      <div className="grid grid-cols-2 gap-6">
        {/* Update Password */}
        <Card className="bg-card/65 backdrop-blur-md border-border/30">
          <CardHeader>
            <CardTitle>Change Password</CardTitle>
            <CardDescription>Update your login credentials securely.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="curr-pw" className="text-xs font-semibold text-muted-foreground uppercase flex items-center">
                  <Lock className="mr-1.5 h-3.5 w-3.5 text-muted-foreground" />
                  Current Password
                </label>
                <input
                  id="curr-pw"
                  type="password"
                  required
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-input bg-background/50 px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="new-pw" className="text-xs font-semibold text-muted-foreground uppercase flex items-center">
                  <Lock className="mr-1.5 h-3.5 w-3.5 text-muted-foreground" />
                  New Password
                </label>
                <input
                  id="new-pw"
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-input bg-background/50 px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="conf-pw" className="text-xs font-semibold text-muted-foreground uppercase flex items-center">
                  <Lock className="mr-1.5 h-3.5 w-3.5 text-muted-foreground" />
                  Confirm New Password
                </label>
                <input
                  id="conf-pw"
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-input bg-background/50 px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                />
              </div>

              <Button type="submit" size="sm" isLoading={isChangingPassword} className="w-full">
                Update Password
              </Button>

              {passwordError && (
                <div className="flex items-center space-x-1.5 text-xs text-destructive rounded bg-destructive/5 border border-destructive/10 p-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{passwordError}</span>
                </div>
              )}
              {passwordSuccess && (
                <div className="flex items-center space-x-1.5 text-xs text-emerald-400 rounded bg-emerald-500/5 border border-emerald-500/10 p-2">
                  <Check className="h-4 w-4 shrink-0" />
                  <span>{passwordSuccess}</span>
                </div>
              )}
            </form>
          </CardContent>
        </Card>

        {/* Delete Account (Safety Prompt) */}
        <Card className="bg-card/65 backdrop-blur-md border-destructive/25 border">
          <CardHeader>
            <CardTitle className="text-destructive">Delete Account</CardTitle>
            <CardDescription>Permanently deactivate your profile and remove all data.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg bg-destructive/10 border border-destructive/25 p-3.5 text-xs text-destructive leading-relaxed space-y-1.5">
              <p className="font-semibold flex items-center">
                <ShieldAlert className="mr-1.5 h-4 w-4 text-destructive" />
                DANGER: Permanent Cascade Data Purge
              </p>
              <p className="opacity-90">
                This triggers a GDPR compliant cleanup worker. All your databases, RLS workspaces, documents, MinIO storage objects, and pgvector embeddings will be permanently wiped within 24 hours.
              </p>
            </div>
            
            <form onSubmit={handleDeleteAccount} className="space-y-3.5">
              <div className="space-y-1.5">
                <label htmlFor="confirm-del" className="text-[11px] font-semibold text-muted-foreground uppercase leading-tight">
                  Type <span className="text-destructive font-bold">DELETE</span> to confirm deactivation:
                </label>
                <input
                  id="confirm-del"
                  type="text"
                  required
                  value={deleteConfirmation}
                  onChange={(e) => setDeleteConfirmation(e.target.value)}
                  placeholder="DELETE"
                  className="flex h-9 w-full rounded-lg border border-border/50 bg-background/50 px-3 py-1.5 text-xs font-bold text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive"
                />
              </div>

              <Button
                type="submit"
                variant="destructive"
                size="sm"
                disabled={deleteConfirmation !== "DELETE" || isDeletingAccount}
                isLoading={isDeletingAccount}
                className="w-full font-bold"
              >
                Deactivate My Account
              </Button>
              
              {deleteError && (
                <div className="flex items-center space-x-1.5 text-xs text-destructive rounded bg-destructive/5 border border-destructive/10 p-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{deleteError}</span>
                </div>
              )}
            </form>
          </CardContent>
        </Card>
      </div>

      {/* Modal showing generated raw API key (ONE-TIME VIEW) */}
      <Modal
        isOpen={!!createdKeyRaw}
        onClose={() => setCreatedKeyRaw(null)}
        title="API Key Generated Successfully"
      >
        <div className="space-y-4 font-sans text-sm">
          <div className="flex items-start space-x-3 rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-sm text-amber-400">
            <ShieldAlert className="h-5 w-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Security Warning: Single Disclosure</p>
              <p className="mt-1 text-xs opacity-90 leading-relaxed">
                Save this API key somewhere secure. For security reasons, you will **never** be able to view this raw token again. If lost, you must revoke and create a new key.
              </p>
            </div>
          </div>

          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-muted-foreground uppercase">
              Your New API Key
            </span>
            <div className="relative flex items-center border border-border/50 bg-slate-950 rounded-lg p-2.5 pr-12 font-mono text-xs text-slate-200">
              <span className="break-all select-all font-semibold">{createdKeyRaw}</span>
              <button
                onClick={copyToClipboard}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
                title="Copy to clipboard"
              >
                {copiedKey ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t border-border/20">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setCreatedKeyRaw(null)}
            >
              Done & I Saved It
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
