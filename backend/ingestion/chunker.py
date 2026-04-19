from __future__ import annotations

import ast
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".go",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}

IGNORED_PARTS = {
    ".git",
    ".next",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
}


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    file_path: str
    symbol_name: str
    symbol_type: str
    language: str
    start_line: int
    end_line: int
    content: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def should_skip_path(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def get_language(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".java": "java",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
    }
    return mapping.get(suffix, "text")


def build_chunk_id(file_path: str, symbol_name: str, start_line: int, end_line: int, content: str) -> str:
    digest = hashlib.sha1(
        f"{file_path}:{symbol_name}:{start_line}:{end_line}:{content}".encode("utf-8")
    ).hexdigest()
    return digest


def slice_source(lines: list[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[start_line - 1 : end_line]).rstrip()


def collect_python_chunks(source: str, file_path: Path) -> list[CodeChunk]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    class_stack: list[str] = []
    function_stack: list[str] = []

    def qualified_name(name: str) -> str:
        parts = class_stack + function_stack + [name]
        return ".".join(parts)

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            start_line = getattr(node, "lineno", 1)
            end_line = getattr(node, "end_lineno", start_line)
            content = slice_source(lines, start_line, end_line)
            symbol_name = ".".join(class_stack + [node.name]) if class_stack else node.name
            chunk_id = build_chunk_id(str(file_path), symbol_name, start_line, end_line, content)
            chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    file_path=str(file_path),
                    symbol_name=symbol_name,
                    symbol_type="class",
                    language="python",
                    start_line=start_line,
                    end_line=end_line,
                    content=content,
                )
            )
            class_stack.append(node.name)
            for child in node.body:
                visit(child)
            class_stack.pop()
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start_line = getattr(node, "lineno", 1)
            end_line = getattr(node, "end_lineno", start_line)
            content = slice_source(lines, start_line, end_line)
            symbol_name = qualified_name(node.name)
            chunk_id = build_chunk_id(str(file_path), symbol_name, start_line, end_line, content)
            chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    file_path=str(file_path),
                    symbol_name=symbol_name,
                    symbol_type="function",
                    language="python",
                    start_line=start_line,
                    end_line=end_line,
                    content=content,
                )
            )
            function_stack.append(node.name)
            for child in getattr(node, "body", []):
                visit(child)
            function_stack.pop()
            return

        for child in ast.iter_child_nodes(node):
            visit(child)

    for child in tree.body:
        visit(child)

    return chunks


def collect_generic_chunk(source: str, file_path: Path) -> CodeChunk | None:
    stripped = source.strip()
    if not stripped:
        return None

    content_lines = source.splitlines()
    end_line = max(len(content_lines), 1)
    symbol_name = file_path.stem or file_path.name
    content = stripped[:12000]
    return CodeChunk(
        chunk_id=build_chunk_id(str(file_path), symbol_name, 1, end_line, content),
        file_path=str(file_path),
        symbol_name=symbol_name,
        symbol_type="file",
        language=get_language(file_path),
        start_line=1,
        end_line=end_line,
        content=content,
    )


def iter_code_files(root_path: Path) -> Iterable[Path]:
    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
        if should_skip_path(file_path):
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        yield file_path


def chunk_file(file_path: Path) -> list[CodeChunk]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    if file_path.suffix.lower() == ".py":
        chunks = collect_python_chunks(source, file_path)
        if chunks:
            return chunks

    fallback = collect_generic_chunk(source, file_path)
    return [fallback] if fallback else []


def chunk_repository(root_path: Path) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for file_path in iter_code_files(root_path):
        chunks.extend(chunk_file(file_path))
    return chunks
