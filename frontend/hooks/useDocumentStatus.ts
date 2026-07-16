import { useEffect, useRef } from "react";
import { useAuth } from "@/context/AuthContext";

export interface IngestionStatusEvent {
  type: "DOCUMENT_READY" | "DOCUMENT_FAILED" | "DOCUMENT_PROCESSING";
  document_id: string;
  status: string;
  error?: string;
}

export function useDocumentStatus(
  workspaceId: string | null,
  onStatusUpdate: (event: IngestionStatusEvent) => void
) {
  const { accessToken } = useAuth();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!workspaceId || !accessToken) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    let host = process.env.NEXT_PUBLIC_WS_URL;
    if (!host) {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (apiUrl && apiUrl.startsWith("http")) {
        try {
          const parsedUrl = new URL(apiUrl);
          host = parsedUrl.host;
        } catch (e) {
          host = "localhost:8080";
        }
      } else {
        host = "localhost:8080";
      }
    }
    const wsUrl = `${protocol}//${host}/api/v1/ws/${workspaceId}?token=${accessToken}`;

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as IngestionStatusEvent;
        onStatusUpdate(data);
      } catch (e) {
        console.error("Failed to parse WebSocket notification:", e);
      }
    };

    socket.onclose = () => {
      // Automatic reconnection logic can be added here if needed, 
      // but keeping it simple for the baseline setup.
    };

    return () => {
      socket.close();
    };
  }, [workspaceId, accessToken, onStatusUpdate]);

  return {
    sendPing: () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send("ping");
      }
    }
  };
}
