"use client";

import * as React from "react";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import {
  MessageSquare,
  Plus,
  Trash2,
  SendHorizontal,
  User,
  Sparkles,
  AlertCircle,
  FileText,
  ExternalLink,
  RefreshCw,
} from "lucide-react";

interface CitationItem {
  id: string;
  message_id: string;
  chunk_id: string | null;
  page_number: number | null;
  section_title: string | null;
  confidence_score: number | null;
  chunk_content: string | null;
  document_name: string | null;
  document_id: string | null;
}

interface MessageItem {
  id: string;
  session_id: string;
  role: "user" | "assistant" | string;
  content: string;
  tokens_used: number;
  created_at: string;
  citations: CitationItem[];
}

interface SessionItem {
  id: string;
  workspace_id: string;
  title: string | null;
  created_at: string;
}

export default function ChatPage() {
  const { activeWorkspaceId } = useWorkspace();
  const { accessToken } = useAuth();

  const [sessions, setSessions] = React.useState<SessionItem[]>([]);
  const [activeSession, setActiveSession] = React.useState<SessionItem | null>(null);
  const [messages, setMessages] = React.useState<MessageItem[]>([]);
  
  const [inputText, setInputText] = React.useState("");
  const [isSessionsLoading, setIsSessionsLoading] = React.useState(true);
  const [isMessagesLoading, setIsMessagesLoading] = React.useState(false);
  const [isGenerating, setIsGenerating] = React.useState(false);
  
  // Error handling
  const [error, setError] = React.useState<string | null>(null);
  
  // Session Deletion
  const [deletingSession, setDeletingSession] = React.useState<SessionItem | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);

  // Citation Details Modal
  const [selectedCitation, setSelectedCitation] = React.useState<CitationItem | null>(null);
  const [selectedCitationNum, setSelectedCitationNum] = React.useState<number | null>(null);
  const [isFetchingDocUrl, setIsFetchingDocUrl] = React.useState(false);

  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  React.useEffect(() => {
    scrollToBottom();
  }, [messages, isGenerating]);

  // Fetch session list
  const fetchSessions = React.useCallback(async (selectIdAfterFetch?: string) => {
    if (!activeWorkspaceId) return;
    setIsSessionsLoading(true);
    setError(null);
    try {
      const response = await api.get(`/query/sessions?workspace_id=${activeWorkspaceId}`);
      const sessionList: SessionItem[] = response.data;
      setSessions(sessionList);
      
      if (selectIdAfterFetch) {
        const found = sessionList.find(s => s.id === selectIdAfterFetch);
        if (found) {
          setActiveSession(found);
        }
      }
    } catch (err) {
      console.error("Failed to load sessions:", err);
      setError("Failed to load sessions.");
    } finally {
      setIsSessionsLoading(false);
    }
  }, [activeWorkspaceId]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      fetchSessions();
      setActiveSession(null);
      setMessages([]);
    }, 0);
    return () => clearTimeout(timer);
  }, [activeWorkspaceId, fetchSessions]);

  // Fetch messages in current session
  const fetchMessages = React.useCallback(async (sessionId: string) => {
    if (!activeWorkspaceId) return;
    setIsMessagesLoading(true);
    setError(null);
    try {
      const response = await api.get(`/query/sessions/${sessionId}/messages`, {
        params: { workspace_id: activeWorkspaceId }
      });
      setMessages(response.data);
    } catch (err) {
      console.error("Failed to load messages:", err);
      setError("Failed to load message history.");
    } finally {
      setIsMessagesLoading(false);
    }
  }, [activeWorkspaceId]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      if (activeSession) {
        fetchMessages(activeSession.id);
      } else {
        setMessages([]);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [activeSession, fetchMessages]);

  // Start new session
  const handleCreateSession = async () => {
    if (!activeWorkspaceId) return;
    setError(null);
    try {
      const response = await api.post(`/query/sessions?workspace_id=${activeWorkspaceId}`, {
        title: "New Chat Session"
      });
      const newSession: SessionItem = response.data;
      setSessions(prev => [newSession, ...prev]);
      setActiveSession(newSession);
    } catch (err) {
      console.error("Failed to create session:", err);
      setError("Failed to create new session.");
    }
  };

  // Delete session
  const handleDeleteSession = async () => {
    if (!deletingSession || !activeWorkspaceId) return;
    setIsDeleting(true);
    setError(null);
    try {
      await api.delete(`/query/sessions/${deletingSession.id}?workspace_id=${activeWorkspaceId}`);
      setSessions(prev => prev.filter(s => s.id !== deletingSession.id));
      if (activeSession?.id === deletingSession.id) {
        setActiveSession(null);
        setMessages([]);
      }
      setDeletingSession(null);
    } catch (err) {
      console.error("Failed to delete session:", err);
      setError("Failed to delete session.");
    } finally {
      setIsDeleting(false);
    }
  };

  // Handle keydown in textarea (Ctrl+Enter to submit)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea height
  React.useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [inputText]);

  // Send message with custom SSE reader stream consumption
  const handleSend = async () => {
    if (!inputText.trim() || isGenerating || !activeWorkspaceId) return;

    const queryText = inputText.trim();
    setInputText("");
    setIsGenerating(true);
    setError(null);

    // 1. Add user message locally
    const tempUserMsgId = `temp-user-${Date.now()}`;
    const userMsg: MessageItem = {
      id: tempUserMsgId,
      session_id: activeSession?.id || "",
      role: "user",
      content: queryText,
      tokens_used: Math.ceil(queryText.length / 4),
      created_at: new Date().toISOString(),
      citations: [],
    };

    // 2. Add empty assistant placeholder locally
    const tempAssistantMsgId = `temp-assistant-${Date.now()}`;
    const assistantPlaceholder: MessageItem = {
      id: tempAssistantMsgId,
      session_id: activeSession?.id || "",
      role: "assistant",
      content: "",
      tokens_used: 0,
      created_at: new Date().toISOString(),
      citations: [],
    };

    setMessages(prev => [...prev, userMsg, assistantPlaceholder]);

    let currentSessionId = activeSession?.id || null;

    try {
      const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080/api/v1"}/query/ask?workspace_id=${activeWorkspaceId}`;
      
      // Inject unique Correlation ID matching api.ts
      const randomHex = Math.random().toString(36).substring(2, 15);
      const correlationId = `req-${randomHex}`;

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Correlation-ID": correlationId,
      };

      if (accessToken) {
        headers["Authorization"] = `Bearer ${accessToken}`;
      }

      const body = {
        question: queryText,
        workspace_id: activeWorkspaceId,
        session_id: currentSessionId,
      };

      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData?.error?.message || "Failed to query the AI engine.");
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Failed to read server response stream.");
      }

      const decoder = new TextDecoder();
      let partialChunk = "";
      let accumulatedText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const textBlock = decoder.decode(value, { stream: true });
        partialChunk += textBlock;

        const lines = partialChunk.split("\n\n");
        // Keep the last partial line (in case it wasn't complete yet)
        partialChunk = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6).trim();
            try {
              const parsed = JSON.parse(jsonStr);
              if (parsed.session_id) {
                currentSessionId = parsed.session_id;
              } else if (parsed.token) {
                accumulatedText += parsed.token;
                setMessages(prev =>
                  prev.map(msg => {
                    if (msg.id === tempAssistantMsgId) {
                      return { ...msg, content: accumulatedText };
                    }
                    return msg;
                  })
                );
              } else if (parsed.done) {
                // Done event
              } else if (parsed.error) {
                throw new Error(parsed.error);
              }
            } catch {
              // Ignore JSON parse errors for incomplete chunks
            }
          }
        }
      }

      setIsGenerating(false);

      // 3. After completion, fetch messages again to load generated citations & confidence scores
      if (currentSessionId) {
        if (!activeSession) {
          // If we auto-created a session, fetch the sessions list and select this new session
          await fetchSessions(currentSessionId);
        } else {
          // Otherwise, just reload this session's messages
          await fetchMessages(currentSessionId);
        }
      }

    } catch (err) {
      console.error("Streaming error:", err);
      const errMsg = err instanceof Error ? err.message : "An error occurred during response generation.";
      setError(errMsg);
      setIsGenerating(false);
      // Remove the placeholder assistant message if it remained empty on crash
      setMessages(prev => prev.filter(msg => !(msg.id === tempAssistantMsgId && msg.content === "")));
    }
  };

  // Download or open source file in new tab
  const handleOpenSourceFile = async (docId: string) => {
    if (!activeWorkspaceId) return;
    setIsFetchingDocUrl(true);
    try {
      const response = await api.get(`/documents/${docId}/url`, {
        params: { workspace_id: activeWorkspaceId }
      });
      window.open(response.data.url, "_blank");
    } catch (err) {
      console.error("Failed to get document URL:", err);
      alert("Failed to load document link. It might have been deleted.");
    } finally {
      setIsFetchingDocUrl(false);
    }
  };

  // Open Citation Detail Modal
  const openCitationModal = (citation: CitationItem, sourceNum: number) => {
    setSelectedCitation(citation);
    setSelectedCitationNum(sourceNum);
  };

  // Markdown-like line-by-line renderer
  const formatInline = (text: string, citations: CitationItem[]): React.ReactNode => {
    if (!text) return "";
    
    // Split by inline code, bold, and citations: `code`, **bold**, [Source N]
    const regex = /(\*\*.*?\*\*|`.*?`|\[Source \d+\])/g;
    const parts = text.split(regex);
    
    return parts.map((part, idx) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={idx} className="font-bold text-foreground">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return (
          <code key={idx} className="px-1.5 py-0.5 rounded bg-muted text-primary font-mono text-xs border border-border/20">
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith("[Source ") && part.endsWith("]")) {
        const sourceNumMatch = part.match(/\d+/);
        if (sourceNumMatch) {
          const sourceNum = parseInt(sourceNumMatch[0], 10);
          const citation = citations[sourceNum - 1];
          if (citation) {
            return (
              <button
                key={idx}
                onClick={() => openCitationModal(citation, sourceNum)}
                className="inline-flex items-center justify-center h-4 px-1.5 mx-0.5 text-[9px] font-bold font-mono rounded bg-primary/20 text-primary border border-primary/30 hover:bg-primary hover:text-primary-foreground transition-all cursor-pointer align-super"
                title={`Source ${sourceNum}: ${citation.document_name || "Document"}`}
              >
                {sourceNum}
              </button>
            );
          }
        }
        return part;
      }
      return part;
    });
  };

  const formatMessageText = (text: string, citations: CitationItem[]) => {
    const lines = text.split("\n");
    
    return lines.map((line, index) => {
      let content: React.ReactNode = line;
      
      const isListItem = line.startsWith("- ") || line.startsWith("* ");
      if (isListItem) {
        content = line.substring(2);
      }
      
      const isHeader3 = line.startsWith("### ");
      if (isHeader3) {
        content = (
          <h3 className="text-base font-semibold text-foreground mt-3 mb-1.5 flex items-center">
            {line.substring(4)}
          </h3>
        );
      } else {
        content = formatInline(String(content), citations);
      }
      
      if (isListItem) {
        return (
          <li key={index} className="ml-5 list-disc text-sm text-foreground/90 my-1 leading-relaxed pl-1">
            {content}
          </li>
        );
      }
      
      if (isHeader3) {
        return <div key={index}>{content}</div>;
      }
      
      return (
        <p key={index} className="text-sm text-foreground/90 leading-relaxed my-1.5 min-h-[1em]">
          {content}
        </p>
      );
    });
  };

  // Helper to render confidence badges
  const renderConfidenceBadge = (citations: CitationItem[]) => {
    if (!citations || citations.length === 0) return null;
    
    const validScores = citations
      .map(c => c.confidence_score)
      .filter((s): s is number => s !== null && s !== undefined);
      
    if (validScores.length === 0) return null;
    
    const avgScore = validScores.reduce((a, b) => a + b, 0) / validScores.length;
    
    let label = "Low Confidence";
    let variant: "destructive" | "warning" | "success" = "destructive";
    
    if (avgScore >= 0.7) {
      label = "High Confidence";
      variant = "success";
    } else if (avgScore >= 0.4) {
      label = "Medium Confidence";
      variant = "warning";
    }
    
    return (
      <Badge variant={variant} className="ml-2 font-mono text-[10px] uppercase py-0.5 px-2">
        {label} ({Math.round(avgScore * 100)}%)
      </Badge>
    );
  };

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      {/* Sidebar - Sessions List */}
      <aside className="w-80 shrink-0 border-r border-border/40 bg-card/10 flex flex-col h-full">
        {/* Sidebar Header */}
        <div className="p-4 border-b border-border/20 flex items-center justify-between">
          <span className="text-sm font-semibold tracking-tight text-foreground flex items-center space-x-2">
            <MessageSquare className="h-4 w-4 text-primary" />
            <span>Chat History</span>
          </span>
          <Button
            onClick={handleCreateSession}
            variant="outline"
            size="sm"
            className="h-8 px-2 bg-primary/5 hover:bg-primary hover:text-white border-primary/20 text-primary"
            title="Start a new chat session"
          >
            <Plus className="h-4 w-4 mr-1" />
            New
          </Button>
        </div>

        {/* Sessions Loop */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isSessionsLoading ? (
            <div className="flex justify-center py-8">
              <Spinner size="sm" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-10 px-4">
              <MessageSquare className="h-8 w-8 mx-auto text-muted-foreground/45 mb-2" />
              <p className="text-xs font-medium text-muted-foreground">
                No active conversations.
              </p>
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = activeSession?.id === session.id;
              return (
                <div
                  key={session.id}
                  className={`group flex items-center justify-between rounded-lg px-3 py-2.5 transition-all duration-200 cursor-pointer ${
                    isActive
                      ? "bg-primary/10 border border-primary/20 text-foreground"
                      : "border border-transparent text-muted-foreground hover:bg-muted/30 hover:text-foreground"
                  }`}
                  onClick={() => setActiveSession(session)}
                >
                  <div className="flex items-center space-x-2.5 min-w-0 flex-1">
                    <MessageSquare className={`h-4 w-4 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                    <span className="text-sm truncate font-medium">
                      {session.title || "Chat Session"}
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeletingSession(session);
                    }}
                    className="opacity-0 group-hover:opacity-100 hover:text-destructive p-1 rounded transition-opacity cursor-pointer ml-1"
                    title="Delete session"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Chat Panel */}
      <section className="flex-1 flex flex-col h-full bg-background relative overflow-hidden">
        {/* Header */}
        {activeSession ? (
          <div className="h-16 shrink-0 border-b border-border/20 px-6 flex items-center justify-between bg-card/15 backdrop-blur-sm">
            <div className="min-w-0 flex-1 flex items-center">
              <h2 className="text-sm font-semibold truncate text-foreground">
                {activeSession.title || "Chat Session"}
              </h2>
              <div className="h-4 w-px bg-border/40 mx-3" />
              <span className="text-xs text-muted-foreground font-mono truncate">
                ID: {activeSession.id}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fetchMessages(activeSession.id)}
              className="h-8 px-2 text-muted-foreground hover:text-foreground"
              disabled={isMessagesLoading}
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isMessagesLoading ? "animate-spin" : ""}`} />
              Sync
            </Button>
          </div>
        ) : null}

        {/* Messages viewport */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {error && (
            <div className="flex items-center space-x-2.5 rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive max-w-2xl mx-auto shadow-md">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <span className="font-medium">{error}</span>
            </div>
          )}

          {!activeSession ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto">
              <div className="h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 border border-primary/25 text-primary flex mb-6 shadow-xl shadow-primary/5 animate-pulse">
                <Sparkles className="h-8 w-8" />
              </div>
              <h2 className="text-2xl font-bold tracking-tight text-foreground">
                CortexRAG Chat Engine
              </h2>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                Connect and query local document intelligence. Start a conversation session from the sidebar or click &ldquo;New&rdquo; to ask about your documents.
              </p>
              
              <div className="grid grid-cols-2 gap-4 mt-8 w-full">
                <Card className="bg-card/25 border-border/30 hover:border-primary/30 transition-colors cursor-pointer" onClick={handleCreateSession}>
                  <CardContent className="p-4 flex flex-col items-center text-center">
                    <MessageSquare className="h-5 w-5 text-primary mb-2" />
                    <h3 className="text-xs font-semibold text-foreground">Interactive Chat</h3>
                    <p className="text-[11px] text-muted-foreground mt-1">Multi-turn conversation RAG.</p>
                  </CardContent>
                </Card>
                <Card className="bg-card/25 border-border/30 hover:border-primary/30 transition-colors cursor-pointer" onClick={() => window.location.href = "/dashboard/documents"}>
                  <CardContent className="p-4 flex flex-col items-center text-center">
                    <FileText className="h-5 w-5 text-primary mb-2" />
                    <h3 className="text-xs font-semibold text-foreground">Knowledge Base</h3>
                    <p className="text-[11px] text-muted-foreground mt-1">Upload and manage source files.</p>
                  </CardContent>
                </Card>
              </div>
            </div>
          ) : isMessagesLoading ? (
            <div className="h-full flex items-center justify-center">
              <Spinner size="md" />
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-sm mx-auto">
              <MessageSquare className="h-8 w-8 text-muted-foreground/35 mb-2" />
              <p className="text-sm font-semibold text-foreground">Conversation Empty</p>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                Send a question below to trigger the RAG query pipeline. The system will retrieve context automatically.
              </p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((msg) => {
                const isUser = msg.role === "user";
                return (
                  <div
                    key={msg.id}
                    className={`flex items-start gap-4 ${isUser ? "justify-end" : "justify-start"}`}
                  >
                    {/* Assistant Avatar */}
                    {!isUser && (
                      <div className="h-8 w-8 shrink-0 rounded-lg bg-primary/10 border border-primary/25 text-primary flex items-center justify-center shadow">
                        <Sparkles className="h-4 w-4" />
                      </div>
                    )}

                    {/* Message Bubble */}
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-md border ${
                        isUser
                          ? "bg-primary text-primary-foreground border-primary/10"
                          : "bg-card/65 backdrop-blur-md text-foreground border-border/30"
                      }`}
                    >
                      {/* Bubble Header for Assistant */}
                      {!isUser && (msg.citations?.length > 0 || isGenerating) && (
                        <div className="flex items-center justify-between border-b border-border/10 pb-1.5 mb-2 text-[10px] text-muted-foreground font-mono">
                          <span className="flex items-center">
                            <FileText className="h-3 w-3 mr-1 text-primary" />
                            {isGenerating && (!msg.citations || msg.citations.length === 0)
                              ? "Analyzing context..."
                              : `${msg.citations?.length || 0} sources cited`}
                          </span>
                          {renderConfidenceBadge(msg.citations)}
                        </div>
                      )}

                      {/* Content */}
                      <div className="space-y-1 font-sans">
                        {isUser ? (
                          <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                        ) : (
                          formatMessageText(msg.content, msg.citations)
                        )}
                      </div>

                      {/* Message Footer */}
                      <div className="mt-2 text-[9px] text-muted-foreground/60 font-mono text-right">
                        {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>

                    {/* User Avatar */}
                    {isUser && (
                      <div className="h-8 w-8 shrink-0 rounded-lg bg-muted text-foreground/80 flex items-center justify-center shadow border border-border/30">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                );
              })}
              {/* Ref point for auto scroll */}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input box */}
        {activeSession ? (
          <div className="p-4 border-t border-border/20 bg-card/5 shrink-0">
            <div className="max-w-3xl mx-auto relative">
              <div className="relative flex items-center border border-border/60 bg-card rounded-xl shadow-lg focus-within:ring-2 focus-within:ring-primary focus-within:ring-offset-2 transition-all p-1.5 pr-2">
                <textarea
                  ref={textareaRef}
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value.substring(0, 2000))}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about your indexed knowledge base..."
                  disabled={isGenerating}
                  rows={1}
                  className="flex-1 bg-transparent px-3 py-2 text-sm text-foreground focus:outline-none resize-none min-h-[36px] max-h-[200px]"
                />
                
                <div className="flex items-center space-x-1">
                  <span className="text-[10px] text-muted-foreground/60 font-mono select-none px-1.5">
                    {inputText.length}/2000
                  </span>
                  <Button
                    onClick={handleSend}
                    disabled={!inputText.trim() || isGenerating}
                    variant="primary"
                    size="icon"
                    className="h-8 w-8 shrink-0 rounded-lg shadow-sm"
                  >
                    {isGenerating ? (
                      <Spinner size="sm" className="h-4 w-4 text-white" />
                    ) : (
                      <SendHorizontal className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground/50 text-center mt-2 font-mono">
                Press Enter to send, Shift+Enter for a new line. Answers are fully grounded in indexed sources.
              </p>
            </div>
          </div>
        ) : null}
      </section>

      {/* Delete Session Modal */}
      <Modal
        isOpen={!!deletingSession}
        onClose={() => setDeletingSession(null)}
        title="Delete Conversation"
      >
        <div className="space-y-4">
          <div className="flex items-start space-x-3 rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Confirm Deletion</p>
              <p className="mt-1 text-xs opacity-90 leading-relaxed">
                This will permanently delete this conversation and its entire history. This action is irreversible.
              </p>
            </div>
          </div>
          <p className="text-sm text-foreground">
            Are you sure you want to delete <span className="font-semibold">&ldquo;{deletingSession?.title}&rdquo;</span>?
          </p>
          <div className="flex justify-end space-x-2 pt-4 border-t border-border/20">
            <Button
              variant="outline"
              onClick={() => setDeletingSession(null)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteSession}
              isLoading={isDeleting}
            >
              Delete
            </Button>
          </div>
        </div>
      </Modal>

      {/* Citation Detail Modal */}
      <Modal
        isOpen={!!selectedCitation}
        onClose={() => setSelectedCitation(null)}
        title={`Source Citation Details [${selectedCitationNum}]`}
        className="max-w-xl"
      >
        {selectedCitation && (
          <div className="space-y-4 font-sans text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 rounded-lg border border-border/40 bg-card/25">
                <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider font-semibold">
                  Source File
                </span>
                <div className="font-bold text-foreground mt-0.5 truncate flex items-center space-x-1.5" title={selectedCitation.document_name || "Document"}>
                  <FileText className="h-4 w-4 text-primary shrink-0" />
                  <span className="truncate">{selectedCitation.document_name || "Unnamed Document"}</span>
                </div>
              </div>

              <div className="p-3 rounded-lg border border-border/40 bg-card/25">
                <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider font-semibold">
                  Location & Score
                </span>
                <div className="font-bold text-foreground mt-0.5 flex items-center justify-between">
                  <span>Page {selectedCitation.page_number ?? "N/A"}</span>
                  {selectedCitation.confidence_score !== null && (
                    <Badge variant={selectedCitation.confidence_score >= 0.7 ? "success" : "warning"} className="font-mono text-[9px] uppercase px-1.5 py-0">
                      Match: {Math.round(selectedCitation.confidence_score * 100)}%
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            {selectedCitation.section_title && (
              <div className="px-3 py-2 rounded-lg border border-border/40 bg-card/10 text-xs">
                <span className="font-semibold text-muted-foreground">Section:</span> {selectedCitation.section_title}
              </div>
            )}

            <div className="space-y-1">
              <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider font-semibold">
                Indexed Chunk Context Snippet
              </span>
              <div className="rounded-lg border border-border/50 bg-slate-950 p-4 max-h-60 overflow-y-auto">
                <p className="font-mono text-xs text-slate-300 leading-relaxed whitespace-pre-wrap select-all">
                  {selectedCitation.chunk_content || "No chunk content snippet stored."}
                </p>
              </div>
            </div>

            <div className="flex justify-between items-center pt-4 border-t border-border/20">
              {selectedCitation.document_id ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleOpenSourceFile(selectedCitation.document_id!)}
                  isLoading={isFetchingDocUrl}
                  className="h-9 hover:bg-primary/10 border-primary/20 hover:text-primary text-primary"
                >
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                  View Original File
                </Button>
              ) : (
                <div />
              )}
              <Button variant="outline" size="sm" onClick={() => setSelectedCitation(null)} className="h-9">
                Close
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
