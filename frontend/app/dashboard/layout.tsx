"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import {
  FolderOpen,
  MessageSquare,
  Settings,
  LogOut,
  ChevronDown,
  Plus,
  ShieldCheck,
  User,
  Sparkles,
  AlertCircle,
} from "lucide-react";
import { api } from "@/lib/api";  // Needed to fetch real subscription tier from /users/me

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, isLoading: authLoading } = useAuth();
  const {
    workspaces,
    activeWorkspace,
    activeWorkspaceId,
    setActiveWorkspaceId,
    createWorkspace,
  } = useWorkspace();

  const pathname = usePathname();
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = React.useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = React.useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = React.useState("");
  const [isCreatingWorkspace, setIsCreatingWorkspace] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const menuRef = React.useRef<HTMLDivElement>(null);

  /**
   * User profile tier — fetched from /users/me on mount.
   * Kept in local state (not AuthContext) so the sidebar can show the
   * real tier label without bloating the global auth context shape.
   * Defaults to null during the initial load to show a skeleton.
   */
  const [userTier, setUserTier] = React.useState<string | null>(null);

  React.useEffect(() => {
    // Fetch the user's profile to read the subscription tier
    api.get("/users/me")
      .then((res) => {
        // res.data matches UserDetailResponse which includes a nested profile with tier
        const tier: string = res.data?.profile?.tier ?? "free";
        setUserTier(tier);
      })
      .catch(() => {
        // Fail silently — sidebar will fall back to 'Free Tier' default
        setUserTier("free");
      });
  }, [user]);  // Re-fetch when the auth user changes (e.g. after tier toggle in settings)

  // Close workspace selection dropdown on click outside
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsWorkspaceMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;

    setIsCreatingWorkspace(true);
    setCreateError(null);
    try {
      await createWorkspace(newWorkspaceName);
      setNewWorkspaceName("");
      setIsCreateModalOpen(false);
    } catch (err) {
      let errMsg = "Failed to create workspace.";
      if (err && typeof err === "object" && "response" in err) {
        const responseData = (err as { response?: { data?: { error?: { message?: string } } } }).response?.data;
        if (responseData?.error?.message) {
          errMsg = responseData.error.message;
        }
      } else if (err instanceof Error) {
        errMsg = err.message;
      }
      setCreateError(errMsg);
    } finally {
      setIsCreatingWorkspace(false);
    }
  };

  const navItems = [
    {
      name: "Documents",
      href: "/dashboard/documents",
      icon: FolderOpen,
    },
    {
      name: "Chat Engine",
      href: "/dashboard/chat",
      icon: MessageSquare,
    },
    {
      name: "Settings & Usage",
      href: "/dashboard/settings",
      icon: Settings,
    },
  ];

  if (authLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-border/40 bg-card/65 backdrop-blur-md">
        {/* Brand */}
        <div className="flex h-16 items-center px-6 border-b border-border/20">
          <Link href="/dashboard" className="flex items-center space-x-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <span className="text-lg font-bold tracking-tight text-foreground">
              Cortex<span className="text-primary">RAG</span>
            </span>
          </Link>
        </div>

        {/* Workspace Selector */}
        <div className="relative px-4 py-4" ref={menuRef}>
          <button
            onClick={() => setIsWorkspaceMenuOpen(!isWorkspaceMenuOpen)}
            className="flex w-full items-center justify-between rounded-lg border border-border/60 bg-background/50 px-3 py-2 text-sm text-foreground hover:bg-muted/50 transition-colors"
          >
            <span className="truncate font-medium">
              {activeWorkspace ? activeWorkspace.name : "Select Workspace"}
            </span>
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>

          {isWorkspaceMenuOpen && (
            <div className="absolute left-4 right-4 z-50 mt-1 max-h-60 overflow-y-auto rounded-lg border border-border bg-card p-1 shadow-xl animate-in fade-in-50 slide-in-from-top-1 duration-150">
              {workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => {
                    setActiveWorkspaceId(ws.id);
                    setIsWorkspaceMenuOpen(false);
                  }}
                  className={`flex w-full items-center rounded-md px-3 py-2 text-sm text-left hover:bg-muted/75 transition-colors ${
                    ws.id === activeWorkspaceId ? "bg-primary/10 text-primary font-medium" : "text-foreground"
                  }`}
                >
                  <span className="truncate">{ws.name}</span>
                </button>
              ))}
              <div className="my-1 border-t border-border/40" />
              <button
                onClick={() => {
                  setIsCreateModalOpen(true);
                  setIsWorkspaceMenuOpen(false);
                }}
                className="flex w-full items-center space-x-2 rounded-md px-3 py-2 text-sm text-primary hover:bg-primary/5 transition-colors"
              >
                <Plus className="h-4 w-4 shrink-0" />
                <span>Create Workspace</span>
              </button>
            </div>
          )}
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 space-y-1 px-3 py-2">
          {navItems.map((item) => {
            const isActive = pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-primary text-primary-foreground shadow-md shadow-primary/15"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>

          {/* User profile & Logout */}
          <div className="border-t border-border/20 p-4 space-y-3 bg-card/30">
            <div className="flex items-center space-x-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 border border-primary/20 text-primary font-semibold text-sm">
                <User className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-foreground">
                  {user?.email}
                </p>
                <div className="flex items-center space-x-1 mt-0.5">
                  {/* Render real tier — amber for Pro, blue primary for Free */}
                  {userTier === "pro" ? (
                    <>
                      <Sparkles className="h-3 w-3 text-amber-400" />
                      <span className="text-[10px] font-medium text-amber-400 uppercase tracking-wider">
                        Pro Tier
                      </span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3 w-3 text-primary" />
                      <span className="text-[10px] font-medium text-primary uppercase tracking-wider">
                        {userTier === null ? "Loading..." : "Free Tier"}
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={logout}
            className="w-full justify-start text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          >
            <LogOut className="mr-2 h-4 w-4" />
            Logout
          </Button>
        </div>
      </aside>

      {/* Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden bg-background">
        {children}
      </main>

      {/* Create Workspace Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Create Workspace"
      >
        <form onSubmit={handleCreateWorkspace} className="space-y-4">
          {createError && (
            <div className="flex items-center space-x-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{createError}</span>
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground" htmlFor="ws-name">
              Workspace Name
            </label>
            <input
              id="ws-name"
              type="text"
              required
              value={newWorkspaceName}
              onChange={(e) => setNewWorkspaceName(e.target.value)}
              placeholder="e.g. Project Alpha"
              disabled={isCreatingWorkspace}
              className="flex h-10 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
          <div className="flex justify-end space-x-2 pt-4 border-t border-border/20">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsCreateModalOpen(false)}
              disabled={isCreatingWorkspace}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={isCreatingWorkspace}>
              Create
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
