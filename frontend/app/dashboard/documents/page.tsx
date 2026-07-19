"use client";

import * as React from "react";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useDocumentStatus, IngestionStatusEvent } from "@/hooks/useDocumentStatus";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import {
  UploadCloud,
  FileText,
  Trash2,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  Database,
  Sparkles,
} from "lucide-react";

interface DocumentItem {
  id: string;
  filename: string;
  status: "PENDING" | "PROCESSING" | "READY" | "FAILED" | string;
  mime_type: string | null;
  file_size: number | null;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
}

interface ChunkLeaf {
  id: string;
  content: string;
  chunk_index: number;
  token_count: number;
}

interface ChunkParent {
  id: string;
  content: string;
  section_title: string | null;
  page_start: number | null;
  page_end: number | null;
  token_count: number;
  summary: string | null;
  leaf_chunks: ChunkLeaf[];
}

export default function DocumentsPage() {
  const { activeWorkspaceId } = useWorkspace();
  const [documents, setDocuments] = React.useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  
  // Drag & Drop State
  const [isDragging, setIsDragging] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState<string | null>(null);
  const [uploadError, setUploadError] = React.useState<string | null>(null);

  // Inspector Modal State
  const [inspectedDoc, setInspectedDoc] = React.useState<DocumentItem | null>(null);
  const [docChunks, setDocChunks] = React.useState<ChunkParent[]>([]);
  const [isLoadingChunks, setIsLoadingChunks] = React.useState(false);

  // Delete Modal State
  const [deletingDoc, setDeletingDoc] = React.useState<DocumentItem | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Fetch documents list from API
  const fetchDocuments = React.useCallback(async () => {
    if (!activeWorkspaceId) return;
    setIsLoading(true);
    try {
      const response = await api.get(`/documents?workspace_id=${activeWorkspaceId}`);
      setDocuments(response.data);
    } catch (error) {
      console.error("Failed to load documents:", error);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspaceId]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      fetchDocuments();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchDocuments]);

  // Real-time status update handler via WebSocket
  const handleWebSocketStatus = React.useCallback((event: IngestionStatusEvent) => {
    setDocuments((prevDocs) =>
      prevDocs.map((doc) => {
        if (doc.id === event.document_id) {
          return {
            ...doc,
            status: event.status,
            error_message: event.error || null,
          };
        }
        return doc;
      })
    );
  }, []);

  // Initialize status WebSocket hook
  useDocumentStatus(activeWorkspaceId, handleWebSocketStatus);

  // Drag & Drop Event Handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await uploadFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      await uploadFile(e.target.files[0]);
    }
  };

  const uploadFile = async (file: File) => {
    if (!activeWorkspaceId) return;
    setUploadProgress("Uploading file...");
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      await api.post(`/documents/upload?workspace_id=${activeWorkspaceId}`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      setUploadProgress(null);
      fetchDocuments(); // Refresh list to show PENDING file
    } catch (error) {
      let errMsg = "File upload failed. Unsupported type or file size exceeded.";
      if (error && typeof error === "object" && "response" in error) {
        const responseData = (error as { response?: { data?: { error?: { message?: string } } } }).response?.data;
        if (responseData?.error?.message) {
          errMsg = responseData.error.message;
        }
      } else if (error instanceof Error) {
        errMsg = error.message;
      }
      setUploadError(errMsg);
      setUploadProgress(null);
    }
  };

  // presigned URL getter for downloading files
  const handleDownload = async (doc: DocumentItem) => {
    if (!activeWorkspaceId) return;
    try {
      const response = await api.get(`/documents/${doc.id}/url?workspace_id=${activeWorkspaceId}`);
      window.open(response.data.url, "_blank");
    } catch (error) {
      console.error("Failed to generate download URL:", error);
    }
  };

  // Chunk Inspection Handler
  const openInspector = async (doc: DocumentItem) => {
    if (!activeWorkspaceId) return;
    setInspectedDoc(doc);
    setDocChunks([]);
    setIsLoadingChunks(true);
    try {
      const response = await api.get(`/documents/${doc.id}/chunks?workspace_id=${activeWorkspaceId}`);
      setDocChunks(response.data);
    } catch (error) {
      console.error("Failed to load document chunks:", error);
    } finally {
      setIsLoadingChunks(false);
    }
  };

  // Delete Handler
  const handleDelete = async () => {
    if (!deletingDoc || !activeWorkspaceId) return;
    setIsDeleting(true);
    try {
      await api.delete(`/documents/${deletingDoc.id}?workspace_id=${activeWorkspaceId}`);
      setDocuments((prev) => prev.filter((d) => d.id !== deletingDoc.id));
      setDeletingDoc(null);
    } catch (error) {
      console.error("Failed to delete document:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const formatSize = (bytes: number | null) => {
    if (bytes === null) return "Unknown";
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(1)} MB`;
  };

  const getStatusBadge = (status: string, errorMsg: string | null) => {
    switch (status) {
      case "READY":
        return <Badge variant="success">Ready</Badge>;
      case "PROCESSING":
        return (
          <Badge variant="primary" className="animate-pulse bg-blue-500/10 text-blue-400 border border-blue-500/30">
            Processing
          </Badge>
        );
      case "FAILED":
        return (
          <div className="group relative inline-block">
            <Badge variant="destructive" className="cursor-help">Failed</Badge>
            {errorMsg && (
              <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 rounded bg-slate-950 px-2 py-1 text-[10px] text-slate-200 opacity-0 group-hover:opacity-100 transition-opacity duration-200 border border-border w-48 text-center shadow-lg">
                {errorMsg}
                <div className="absolute top-full left-1/2 h-1 w-1 -translate-x-1/2 -translate-y-[2.5px] rotate-45 bg-slate-950 border-r border-b border-border" />
              </div>
            )}
          </div>
        );
      default:
        return <Badge variant="outline">Pending</Badge>;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col space-y-4 md:flex-row md:items-center md:justify-between md:space-y-0">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Document Manager
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Upload, inspect, and delete AI-indexed document pipelines in this workspace.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchDocuments} className="self-start">
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Drag & Drop Upload Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`flex flex-col items-center justify-center rounded-xl border border-dashed p-8 text-center cursor-pointer transition-all duration-200 ${
          isDragging
            ? "border-primary bg-primary/5 scale-[0.99]"
            : "border-border hover:border-primary/50 hover:bg-muted/30"
        }`}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".pdf,.docx,.txt,.md"
          className="hidden"
        />
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20 mb-4">
          <UploadCloud className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-semibold text-foreground">
          Drag & drop your files here
        </h3>
        <p className="text-sm text-muted-foreground mt-1 max-w-sm">
          Supports PDF, DOCX, TXT, and Markdown files up to 10MB (Free) or 500MB (Pro).
        </p>

        {uploadProgress && (
          <p className="text-sm font-medium text-primary mt-4 animate-pulse">
            {uploadProgress}
          </p>
        )}
        {uploadError && (
          <div className="flex items-center space-x-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive mt-4">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{uploadError}</span>
          </div>
        )}
      </div>

      {/* Documents Grid / Table */}
      <Card>
        <CardHeader>
          <CardTitle>Workspace Documents</CardTitle>
          <CardDescription>
            Files currently indexed and accessible by the RAG search pipeline.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-40 items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
            </div>
          ) : documents.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center text-center">
              <FileText className="h-10 w-10 text-muted-foreground mb-2" />
              <p className="text-sm font-medium text-muted-foreground">
                No documents uploaded yet in this workspace.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left text-foreground">
                <thead className="text-xs uppercase bg-card border-b border-border/40 text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-6 py-3">Filename</th>
                    <th scope="col" className="px-6 py-3">Size</th>
                    <th scope="col" className="px-6 py-3">Pages</th>
                    <th scope="col" className="px-6 py-3">Status</th>
                    <th scope="col" className="px-6 py-3">Uploaded</th>
                    <th scope="col" className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-muted/20">
                      <td className="px-6 py-4 font-medium max-w-xs truncate flex items-center space-x-2">
                        <FileText className="h-4 w-4 shrink-0 text-primary" />
                        <span className="truncate">{doc.filename}</span>
                      </td>
                      <td className="px-6 py-4">{formatSize(doc.file_size)}</td>
                      <td className="px-6 py-4">{doc.page_count ?? "N/A"}</td>
                      <td className="px-6 py-4">
                        {getStatusBadge(doc.status, doc.error_message)}
                      </td>
                      <td className="px-6 py-4">
                        {new Date(doc.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 text-right space-x-2">
                        {doc.status === "READY" && (
                          <>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => openInspector(doc)}
                              className="h-8 w-8 hover:bg-primary/10 hover:text-primary"
                            >
                              <Database className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDownload(doc)}
                              className="h-8 w-8 hover:bg-indigo-500/10 hover:text-indigo-400"
                            >
                              <ExternalLink className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeletingDoc(doc)}
                          className="h-8 w-8 hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deletingDoc}
        onClose={() => setDeletingDoc(null)}
        title="Delete Document"
      >
        <div className="space-y-4">
          <div className="flex items-start space-x-3 rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Warning: Cascade Purge</p>
              <p className="mt-1 text-xs opacity-90 leading-relaxed">
                This will permanently remove all AI-indexed vectors, chunks, and storage binaries associated with this document. This action is irreversible.
              </p>
            </div>
          </div>
          <p className="text-sm text-foreground">
            Are you sure you want to delete <span className="font-semibold">{deletingDoc?.filename}</span>?
          </p>
          <div className="flex justify-end space-x-2 pt-4 border-t border-border/20">
            <Button
              variant="outline"
              onClick={() => setDeletingDoc(null)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              isLoading={isDeleting}
            >
              Delete Permanently
            </Button>
          </div>
        </div>
      </Modal>

      {/* Chunk Inspector Modal */}
      <Modal
        isOpen={!!inspectedDoc}
        onClose={() => setInspectedDoc(null)}
        title="Hierarchical Chunk Inspector"
        className="max-w-2xl"
      >
        <div className="space-y-4">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Document</p>
            <h3 className="text-base font-bold text-foreground mt-0.5">{inspectedDoc?.filename}</h3>
          </div>

          <div className="border border-border rounded-xl bg-background/50 overflow-hidden">
            <div className="bg-card border-b border-border/30 px-4 py-2.5 flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground flex items-center">
                <Database className="h-3.5 w-3.5 mr-1.5 text-primary" />
                Indexed Database Chunks
              </span>
              <Badge variant="outline">{docChunks.length} Parent Sections</Badge>
            </div>
            
            <div className="p-4 max-h-96 overflow-y-auto space-y-4 font-sans text-sm">
              {isLoadingChunks ? (
                <div className="flex h-40 items-center justify-center">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
                </div>
              ) : docChunks.length === 0 ? (
                <p className="text-center text-muted-foreground py-10">No chunks retrieved.</p>
              ) : (
                docChunks.map((parent, pIdx) => (
                  <div key={parent.id} className="border border-border/40 rounded-lg bg-card/40 p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-border/20 pb-2">
                      <span className="font-semibold text-xs text-primary uppercase">
                        Parent Section {pIdx + 1}: {parent.section_title || "Unnamed Section"}
                      </span>
                      <div className="text-[10px] text-muted-foreground font-mono">
                        Pages {parent.page_start ?? "?"} - {parent.page_end ?? "?"} · {parent.token_count} tokens
                      </div>
                    </div>
                    
                    {parent.summary && (
                      <div className="rounded bg-primary/5 border border-primary/15 p-2 text-xs">
                        <span className="font-semibold text-primary flex items-center mb-1">
                          <Sparkles className="h-3 w-3 mr-1" />
                          AI Section Summary:
                        </span>
                        <p className="text-muted-foreground italic">&ldquo;{parent.summary}&rdquo;</p>
                      </div>
                    )}

                    <div className="space-y-2 pl-3 border-l border-border/40">
                      {parent.leaf_chunks.map((leaf) => (
                        <div key={leaf.id} className="bg-background/40 border border-border/25 rounded p-2.5 space-y-1.5">
                          <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono border-b border-border/10 pb-1">
                            <span>Leaf Chunk {leaf.chunk_index + 1}</span>
                            <span>{leaf.token_count} tokens</span>
                          </div>
                          <p className="text-xs font-mono text-muted-foreground leading-relaxed">
                            {leaf.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
          
          <div className="flex justify-end pt-4 border-t border-border/20">
            <Button variant="outline" onClick={() => setInspectedDoc(null)}>
              Close Inspector
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
