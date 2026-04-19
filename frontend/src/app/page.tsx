"use client";

import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import { Bot, FileText, GitBranch, LayoutGrid, Send, Sparkles, Wand2 } from "lucide-react";

type IndexedFile = {
  file_path: string;
  language: string;
};

type ChatMessage = {
  role: "assistant" | "user";
  content: string;
};

type RefactorPreviewResponse = {
  file_path: string;
  summary: string;
  proposal_id: string | null;
  diff: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

const starterFiles: IndexedFile[] = [
  { file_path: "backend/main.py", language: "python" },
  { file_path: "backend/ingestion/chunker.py", language: "python" },
  { file_path: "frontend/src/app/page.tsx", language: "typescript" },
];

const starterContent: Record<string, string> = {
  "backend/main.py": `from fastapi import FastAPI\n\napp = FastAPI()\n`,
  "backend/ingestion/chunker.py": `def chunk_python_file(source: str):\n    return []\n`,
  "frontend/src/app/page.tsx": `export default function Page() {\n  return <div>DevLink</div>;\n}\n`,
};

export default function Home() {
  const [files, setFiles] = useState<IndexedFile[]>(starterFiles);
  const [selectedFile, setSelectedFile] = useState(starterFiles[0].file_path);
  const [content, setContent] = useState(starterContent[starterFiles[0].file_path]);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "Index the repository, then ask a question about a file, function, or refactor idea.",
    },
  ]);
  const [input, setInput] = useState("");
  const [indexing, setIndexing] = useState(false);
  const [runningAction, setRunningAction] = useState(false);
  const [refactorInstruction, setRefactorInstruction] = useState("Improve readability and keep behavior unchanged.");
  const [refactorDiff, setRefactorDiff] = useState("");
  const [proposalId, setProposalId] = useState<string | null>(null);
  const [autoDocMarkdown, setAutoDocMarkdown] = useState("");

  const loadFileContent = async (filePath: string) => {
    try {
      const response = await fetch(`${backendUrl}/file?path=${encodeURIComponent(filePath)}`);
      if (!response.ok) {
        setContent(starterContent[filePath] ?? "");
        return;
      }
      const payload = await response.json();
      setContent(payload.content ?? starterContent[filePath] ?? "");
    } catch {
      setContent(starterContent[filePath] ?? "");
    }
  };

  useEffect(() => {
    const loadFiles = async () => {
      try {
        const response = await fetch(`${backendUrl}/files`);
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as { files: IndexedFile[] };
        if (payload.files?.length) {
          setFiles(payload.files);
          setSelectedFile(payload.files[0].file_path);
        }
      } catch {
        return;
      }
    };

    loadFiles();
  }, []);

  useEffect(() => {
    loadFileContent(selectedFile);
  }, [selectedFile]);

  const fileGroups = useMemo(() => {
    const byLanguage = new Map<string, IndexedFile[]>();
    for (const file of files) {
      const current = byLanguage.get(file.language) ?? [];
      current.push(file);
      byLanguage.set(file.language, current);
    }
    return Array.from(byLanguage.entries());
  }, [files]);

  const sendQuestion = async () => {
    const question = input.trim();
    if (!question) {
      return;
    }

    setMessages((current) => [...current, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setInput("");

    try {
      const response = await fetch(`${backendUrl}/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, limit: 5 }),
      });

      if (!response.body) {
        throw new Error("Missing response body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        fullText += decoder.decode(value, { stream: true });
        setMessages((current) => {
          const next = [...current];
          next[next.length - 1] = { role: "assistant", content: fullText };
          return next;
        });
      }
    } catch (error) {
      setMessages((current) => {
        const next = [...current];
        next[next.length - 1] = {
          role: "assistant",
          content: error instanceof Error ? error.message : "Unable to reach the backend.",
        };
        return next;
      });
    }
  };

  const indexProject = async () => {
    setIndexing(true);
    try {
      await fetch(`${backendUrl}/index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const response = await fetch(`${backendUrl}/files`);
      if (response.ok) {
        const payload = (await response.json()) as { files: IndexedFile[] };
        if (payload.files?.length) {
          setFiles(payload.files);
          setSelectedFile(payload.files[0].file_path);
        }
      }
    } finally {
      setIndexing(false);
    }
  };

  const runAutoDoc = async () => {
    setRunningAction(true);
    setAutoDocMarkdown("");
    try {
      const response = await fetch(`${backendUrl}/actions/auto-doc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: selectedFile }),
      });
      if (!response.ok) {
        throw new Error("Unable to generate documentation.");
      }
      const payload = (await response.json()) as { markdown: string };
      setAutoDocMarkdown(payload.markdown ?? "No documentation generated.");
    } catch (error) {
      setAutoDocMarkdown(error instanceof Error ? error.message : "Auto-doc failed.");
    } finally {
      setRunningAction(false);
    }
  };

  const previewRefactor = async () => {
    const instruction = refactorInstruction.trim();
    if (!instruction) {
      return;
    }

    setRunningAction(true);
    setRefactorDiff("");
    setProposalId(null);
    try {
      const response = await fetch(`${backendUrl}/actions/refactor/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: selectedFile, instruction }),
      });
      if (!response.ok) {
        throw new Error("Unable to create refactor proposal.");
      }
      const payload = (await response.json()) as RefactorPreviewResponse;
      setRefactorDiff(payload.diff || "No changes suggested.");
      setProposalId(payload.proposal_id);
    } catch (error) {
      setRefactorDiff(error instanceof Error ? error.message : "Refactor preview failed.");
    } finally {
      setRunningAction(false);
    }
  };

  const applyRefactor = async () => {
    if (!proposalId) {
      return;
    }

    setRunningAction(true);
    try {
      const response = await fetch(`${backendUrl}/actions/refactor/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal_id: proposalId, approve: true }),
      });
      if (!response.ok) {
        throw new Error("Apply failed.");
      }
      setProposalId(null);
      setRefactorDiff("Refactor applied successfully.");
      await loadFileContent(selectedFile);
    } catch (error) {
      setRefactorDiff(error instanceof Error ? error.message : "Apply failed.");
    } finally {
      setRunningAction(false);
    }
  };

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(255,200,87,0.24),_transparent_30%),linear-gradient(135deg,_#08111f_0%,_#101a2b_45%,_#0f1728_100%)] text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-[1800px] flex-col p-4 lg:p-6">
        <header className="mb-4 flex items-center justify-between rounded-3xl border border-white/10 bg-white/5 px-5 py-4 backdrop-blur-xl">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-amber-300/80">DevLink</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">Code memory, AI reasoning, and action execution</h1>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1">
              <LayoutGrid className="h-4 w-4" />
              IDE shell
            </span>
            <button
              type="button"
              onClick={indexProject}
              disabled={indexing}
              className="inline-flex items-center gap-2 rounded-full bg-amber-400 px-4 py-2 font-medium text-slate-950 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <GitBranch className="h-4 w-4" />
              {indexing ? "Indexing..." : "Index project"}
            </button>
          </div>
        </header>

        <div className="grid flex-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)_380px]">
          <aside className="rounded-3xl border border-white/10 bg-slate-950/70 p-4 shadow-2xl shadow-black/20 backdrop-blur-xl">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.25em] text-slate-400">File tree</p>
                <h2 className="mt-1 text-lg font-medium text-white">Indexed sources</h2>
              </div>
              <FileText className="h-5 w-5 text-amber-300" />
            </div>

            <div className="space-y-4 overflow-y-auto pr-1">
              {fileGroups.map(([language, groupedFiles]) => (
                <div key={language} className="space-y-2">
                  <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{language}</p>
                  <div className="space-y-1">
                    {groupedFiles.map((file) => (
                      <button
                        key={file.file_path}
                        type="button"
                        onClick={() => setSelectedFile(file.file_path)}
                        className={`w-full rounded-2xl border px-3 py-2 text-left text-sm transition ${
                          selectedFile === file.file_path
                            ? "border-amber-300/30 bg-amber-300/10 text-white"
                            : "border-white/5 bg-white/5 text-slate-300 hover:border-white/10 hover:bg-white/10"
                        }`}
                      >
                        {file.file_path}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <section className="flex min-h-[72vh] flex-col overflow-hidden rounded-3xl border border-white/10 bg-slate-950/70 shadow-2xl shadow-black/25 backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <div>
                <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Editor</p>
                <h2 className="text-sm font-medium text-white">{selectedFile}</h2>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={runAutoDoc}
                  disabled={runningAction}
                  className="inline-flex items-center gap-2 rounded-full border border-amber-300/30 bg-amber-300/10 px-3 py-1 text-xs text-amber-100 transition hover:bg-amber-300/20 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Auto-doc
                </button>
                <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-200">
                  <Sparkles className="h-3.5 w-3.5" />
                  Monaco active
                </div>
              </div>
            </div>
            <div className="min-h-0 flex-1">
              <Editor
                height="100%"
                language={selectedFile.endsWith(".tsx") || selectedFile.endsWith(".ts") ? "typescript" : selectedFile.endsWith(".py") ? "python" : "plaintext"}
                value={content}
                theme="vs-dark"
                onChange={(value) => setContent(value ?? "")}
                options={{
                  minimap: { enabled: false },
                  fontSize: 14,
                  smoothScrolling: true,
                  wordWrap: "on",
                  padding: { top: 16, bottom: 16 },
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </section>

          <aside className="flex min-h-[72vh] flex-col overflow-hidden rounded-3xl border border-white/10 bg-slate-950/70 shadow-2xl shadow-black/25 backdrop-blur-xl">
            <div className="border-b border-white/10 px-4 py-3">
              <p className="text-xs uppercase tracking-[0.25em] text-slate-500">AI Sidebar</p>
              <h2 className="mt-1 flex items-center gap-2 text-lg font-medium text-white">
                <Bot className="h-5 w-5 text-amber-300" />
                DevLink assistant
              </h2>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "ml-10 border-amber-400/20 bg-amber-400/10 text-amber-50"
                      : "mr-10 border-white/10 bg-white/5 text-slate-200"
                  }`}
                >
                  {message.content || (message.role === "assistant" ? "Thinking..." : "")}
                </div>
              ))}
            </div>

            <div className="border-t border-white/10 p-4">
              <label className="mb-2 block text-xs uppercase tracking-[0.25em] text-slate-500">Ask a question</label>
              <div className="flex gap-2">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  rows={4}
                  placeholder="How is the ingestion pipeline structured?"
                  className="min-h-[104px] flex-1 resize-none rounded-2xl border border-white/10 bg-slate-900/80 px-3 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-amber-300/30"
                />
                <button
                  type="button"
                  onClick={sendQuestion}
                  className="inline-flex h-14 w-14 items-center justify-center self-end rounded-2xl bg-amber-400 text-slate-950 transition hover:bg-amber-300"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-3">
                <p className="mb-2 text-xs uppercase tracking-[0.25em] text-slate-500">Refactor Agent</p>
                <textarea
                  value={refactorInstruction}
                  onChange={(event) => setRefactorInstruction(event.target.value)}
                  rows={3}
                  className="w-full resize-none rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
                />
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={previewRefactor}
                    disabled={runningAction}
                    className="inline-flex items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Wand2 className="h-3.5 w-3.5" />
                    Preview changes
                  </button>
                  <button
                    type="button"
                    onClick={applyRefactor}
                    disabled={runningAction || !proposalId}
                    className="rounded-xl bg-emerald-400 px-3 py-2 text-xs font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Review and approve
                  </button>
                </div>
              </div>
            </div>
          </aside>
        </div>

        <section className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl">
            <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Auto-Doc Output</p>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-2xl border border-white/10 bg-slate-950/70 p-3 text-xs leading-6 text-slate-200">
              {autoDocMarkdown || "Generate documentation for the selected file."}
            </pre>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl">
            <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Refactor Preview (Diff)</p>
            <pre className="mt-2 max-h-64 overflow-auto rounded-2xl border border-white/10 bg-slate-950/70 p-3 text-xs leading-6 text-slate-200">
              {refactorDiff || "Run preview to see a proposed patch before applying."}
            </pre>
          </div>
        </section>

        <section className="mt-4 grid gap-3 md:grid-cols-3">
          {[
            { title: "Memory", value: "AST chunking + Qdrant", detail: "Indexes code into retrievable chunks with contextual payloads." },
            { title: "Brain", value: "FastAPI + Gemini", detail: "Retrieves the top matches and streams answers back to the UI." },
            { title: "Agent", value: "Review + approve", detail: "Generates doc/refactor proposals and only writes files after approval." },
          ].map((card) => (
            <div key={card.title} className="rounded-3xl border border-white/10 bg-white/5 px-4 py-4 backdrop-blur-xl">
              <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{card.title}</p>
              <h3 className="mt-2 text-lg font-medium text-white">{card.value}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-400">{card.detail}</p>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
