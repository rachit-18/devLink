<<<<<<< HEAD
﻿# DevLink

DevLink is an AI-assisted code workspace that indexes a repository into Qdrant, retrieves relevant code snippets, and answers questions with Gemini inside a developer-focused Next.js UI.

## What is implemented now

- AST-based chunking for Python source files
- Generic fallback chunking for other source files
- Qdrant vector storage with contextual payloads
- FastAPI ingestion, file listing, file content lookup, and streaming question answering
- FastAPI action endpoints for auto-doc and refactor preview/apply
- Next.js IDE shell with Monaco, file tree, and chat panel
- Docker Compose for Qdrant

## Project Layout

- `backend/` FastAPI backend and indexing pipeline
- `frontend/` Next.js app shell and editor UI
- `docker/` local Qdrant compose file

## Required environment variables

- `GEMINI_API_KEY`
- `GEMINI_MODEL` optional, defaults to `gemini-1.5-flash`
- `QDRANT_URL` optional, defaults to `http://localhost:6333`
- `QDRANT_API_KEY` optional
- `QDRANT_COLLECTION` optional, defaults to `devlink_code_chunks`

## Run Qdrant

```bash
docker compose -f docker/docker-compose.yml up -d
```

## Run backend

```bash
cd backend
uvicorn backend.main:app --reload --port 8000
```

## Run frontend

```bash
cd frontend
npm run dev
```

## Index the project

```bash
curl -X POST http://localhost:8000/index -H "Content-Type: application/json" -d "{}"
```

## Ask a question

```bash
curl -N -X POST http://localhost:8000/ask/stream -H "Content-Type: application/json" -d "{\"question\":\"How is the backend structured?\",\"limit\":5}"
```

## Auto-doc for a file

```bash
curl -X POST http://localhost:8000/actions/auto-doc -H "Content-Type: application/json" -d "{\"file_path\":\"backend/main.py\"}"
```

## Refactor with review and approval

1. Generate a proposal diff:

```bash
curl -X POST http://localhost:8000/actions/refactor/preview -H "Content-Type: application/json" -d "{\"file_path\":\"backend/main.py\",\"instruction\":\"Improve readability without changing behavior\"}"
```

2. Apply only after review:

```bash
curl -X POST http://localhost:8000/actions/refactor/apply -H "Content-Type: application/json" -d "{\"proposal_id\":\"<proposal-id>\",\"approve\":true}"
```
=======
# devLink
>>>>>>> 489ed6311d08b66333deac63434a591e2b33a624
