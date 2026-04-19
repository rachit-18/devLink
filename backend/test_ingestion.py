from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.ingestion.chunker import chunk_file


def test_chunk_python_file() -> None:
    target = Path(__file__).resolve().parent / "ingestion" / "chunker.py"
    chunks = chunk_file(target)
    assert chunks, "Expected at least one chunk from chunker.py"
    assert all(chunk.file_path.endswith("chunker.py") for chunk in chunks)


if __name__ == "__main__":
    test_chunk_python_file()
    print("Chunking smoke test passed.")
