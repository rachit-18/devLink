from __future__ import annotations

import difflib
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.ingestion.indexer import CodeIndexer

load_dotenv()

app = FastAPI(title="DevLink Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IndexRequest(BaseModel):
    path: str | None = Field(default=None, description="Root path to index")


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


class AutoDocRequest(BaseModel):
    file_path: str = Field(min_length=1)
    symbol_name: str | None = None


class RefactorPreviewRequest(BaseModel):
    file_path: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class RefactorApplyRequest(BaseModel):
    proposal_id: str = Field(min_length=1)
    approve: bool = True


PROPOSALS: dict[str, dict[str, Any]] = {}


@lru_cache(maxsize=1)
def get_indexer() -> CodeIndexer:
    return CodeIndexer()


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_file(file_path: str) -> Path:
    repo_root = get_repo_root().resolve()
    candidate = (repo_root / file_path).resolve()
    if not str(candidate).startswith(str(repo_root)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="File does not exist")
    return candidate


def format_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "No indexed code was found."

    sections: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        sections.append(
            "\n".join(
                [
                    f"[{index}] {chunk['file_path']} :: {chunk['symbol_name']}",
                    f"Type: {chunk['symbol_type']} | Language: {chunk['language']} | Lines: {chunk['start_line']}-{chunk['end_line']}",
                    chunk["content"],
                ]
            )
        )
    return "\n\n".join(sections)


def build_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    context = format_context(chunks)
    return (
        "You are DevLink, a coding assistant that answers questions using retrieved project code.\n\n"
        "Rules:\n"
        "- Only use the provided code context unless the user asks for general advice.\n"
        "- Quote file paths and symbol names when relevant.\n"
        "- If the answer is uncertain, say what is missing.\n\n"
        f"Question: {question}\n\n"
        f"Context:\n{context}\n\n"
        "Answer clearly and directly."
    )


async def stream_gemini_answer(prompt: str) -> AsyncIterator[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        yield "GEMINI_API_KEY is not configured. Index the repository first, then provide a Gemini key to enable streaming answers."
        return

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt, stream=True)
    for chunk in response:
        text = getattr(chunk, "text", "")
        if text:
            yield text


def generate_gemini_text(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise HTTPException(status_code=502, detail="Gemini returned an empty response")
    return text.strip()


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return cleaned


def build_readme_prompt(file_path: str, code: str, symbol_name: str | None) -> str:
    symbol_hint = symbol_name or "the main symbols in this file"
    return (
        "You are generating documentation for a codebase.\n"
        "Write a concise README section in Markdown for a developer.\n"
        "Include: purpose, inputs/outputs, important behavior, and one example usage.\n"
        "If details are missing, explicitly state assumptions.\n\n"
        f"File path: {file_path}\n"
        f"Focus symbol: {symbol_hint}\n\n"
        "Code:\n"
        f"{code}\n"
    )


def build_refactor_prompt(file_path: str, instruction: str, code: str) -> str:
    return (
        "You are a senior software engineer. Refactor the given file exactly once.\n"
        "Rules:\n"
        "- Apply only changes required by the instruction.\n"
        "- Preserve behavior unless instruction asks to change it.\n"
        "- Return only the full updated file content, no explanations, no markdown fences.\n\n"
        f"File path: {file_path}\n"
        f"Instruction: {instruction}\n\n"
        "Current file content:\n"
        f"{code}\n"
    )


def build_diff(file_path: str, original: str, proposed: str) -> str:
    diff_lines = difflib.unified_diff(
        original.splitlines(),
        proposed.splitlines(),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    )
    return "\n".join(diff_lines)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"status": "ok", "message": "DevLink Backend is running"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/index")
async def index_repository(request: IndexRequest) -> dict[str, Any]:
    indexer = get_indexer()
    target_path = Path(request.path) if request.path else get_repo_root()
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"Path does not exist: {target_path}")

    result = indexer.index_path(target_path)
    return {"status": "indexed", **result}


@app.get("/files")
async def list_indexed_files() -> dict[str, Any]:
    indexer = get_indexer()
    return {"files": indexer.list_files()}


@app.get("/file")
async def get_file_content(path: str = Query(..., min_length=1)) -> dict[str, Any]:
    indexer = get_indexer()
    content = indexer.get_file_payload(path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found in the index")
    return content


@app.post("/ask/stream")
async def ask_stream(request: AskRequest) -> StreamingResponse:
    indexer = get_indexer()
    matches = indexer.search(request.question, limit=request.limit)
    prompt = build_prompt(request.question, matches)

    async def event_stream() -> AsyncIterator[bytes]:
        async for chunk in stream_gemini_answer(prompt):
            yield chunk.encode("utf-8")

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


@app.post("/actions/auto-doc")
async def auto_doc(request: AutoDocRequest) -> dict[str, Any]:
    target = resolve_repo_file(request.file_path)
    content = target.read_text(encoding="utf-8")
    prompt = build_readme_prompt(request.file_path, content, request.symbol_name)
    markdown = generate_gemini_text(prompt)
    return {
        "file_path": request.file_path,
        "symbol_name": request.symbol_name,
        "markdown": markdown,
    }


@app.post("/actions/refactor/preview")
async def refactor_preview(request: RefactorPreviewRequest) -> dict[str, Any]:
    target = resolve_repo_file(request.file_path)
    original = target.read_text(encoding="utf-8")
    prompt = build_refactor_prompt(request.file_path, request.instruction, original)
    proposed = strip_code_fences(generate_gemini_text(prompt))

    if proposed == original:
        return {
            "file_path": request.file_path,
            "summary": "No changes suggested.",
            "proposal_id": None,
            "diff": "",
        }

    proposal_id = str(uuid.uuid4())
    PROPOSALS[proposal_id] = {
        "proposal_id": proposal_id,
        "file_path": request.file_path,
        "original": original,
        "proposed": proposed,
        "instruction": request.instruction,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "file_path": request.file_path,
        "summary": "Review the proposed diff and approve to apply.",
        "proposal_id": proposal_id,
        "diff": build_diff(request.file_path, original, proposed),
    }


@app.post("/actions/refactor/apply")
async def refactor_apply(request: RefactorApplyRequest) -> dict[str, Any]:
    proposal = PROPOSALS.get(request.proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if not request.approve:
        PROPOSALS.pop(request.proposal_id, None)
        return {"status": "rejected", "proposal_id": request.proposal_id}

    target = resolve_repo_file(proposal["file_path"])
    target.write_text(proposal["proposed"], encoding="utf-8")
    PROPOSALS.pop(request.proposal_id, None)
    return {
        "status": "applied",
        "proposal_id": request.proposal_id,
        "file_path": proposal["file_path"],
    }
