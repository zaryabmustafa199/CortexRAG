"use client";

import * as React from "react";
import { api } from "@/lib/api";
import { useAuth } from "./AuthContext";

export interface Workspace {
  id: string;
  name: string;
  owner_id: string;
}

interface WorkspaceContextType {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  activeWorkspaceId: string | null;
  isLoading: boolean;
  setActiveWorkspaceId: (id: string) => void;
  createWorkspace: (name: string) => Promise<Workspace>;
  refreshWorkspaces: () => Promise<void>;
}

const WorkspaceContext = React.createContext<WorkspaceContextType | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [workspaces, setWorkspaces] = React.useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  // Refresh workspaces list from API
  const refreshWorkspaces = React.useCallback(async () => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    try {
      const response = await api.get("/workspaces");
      const list: Workspace[] = response.data;
      setWorkspaces(list);

      // Auto-select workspace if none is active or selected is not in list anymore
      if (list.length > 0) {
        const storedId = localStorage.getItem("active_workspace_id");
        const exists = list.some((w) => w.id === storedId);
        if (storedId && exists) {
          setActiveWorkspaceIdState(storedId);
        } else {
          setActiveWorkspaceIdState(list[0].id);
          localStorage.setItem("active_workspace_id", list[0].id);
        }
      } else {
        setActiveWorkspaceIdState(null);
        localStorage.removeItem("active_workspace_id");
      }
    } catch (error) {
      console.error("Failed to load workspaces:", error);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  // Set active workspace
  const setActiveWorkspaceId = (id: string) => {
    setActiveWorkspaceIdState(id);
    localStorage.setItem("active_workspace_id", id);
  };

  // Create new workspace
  const createWorkspace = async (name: string): Promise<Workspace> => {
    try {
      const response = await api.post("/workspaces", { name });
      const newWorkspace: Workspace = response.data;
      setWorkspaces((prev) => [...prev, newWorkspace]);
      setActiveWorkspaceId(newWorkspace.id);
      return newWorkspace;
    } catch (error) {
      console.error("Failed to create workspace:", error);
      throw error;
    }
  };

  // Fetch workspaces on auth status changes
  React.useEffect(() => {
    const timer = setTimeout(() => {
      if (isAuthenticated) {
        refreshWorkspaces();
      } else {
        setWorkspaces([]);
        setActiveWorkspaceIdState(null);
        setIsLoading(false);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [isAuthenticated, refreshWorkspaces]);

  const activeWorkspace = React.useMemo(() => {
    return workspaces.find((w) => w.id === activeWorkspaceId) || null;
  }, [workspaces, activeWorkspaceId]);

  return (
    <WorkspaceContext.Provider
      value={{
        workspaces,
        activeWorkspace,
        activeWorkspaceId,
        isLoading,
        setActiveWorkspaceId,
        createWorkspace,
        refreshWorkspaces,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = React.useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
