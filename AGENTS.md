# AGENTS.md

Guidance for AI coding agents (Codex, Cursor, Gemini, Copilot) in this repository. Treat the project as production-shaped. Keep responses concise and use tables when helpful. Use the project virtualenv (`.venv`) to run or install dependencies.

## Project

**AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải** — a Vietnamese legal Q&A AI agent over road-transport regulations. Answers cite Điều/Khoản, filter for in-force documents (`status=active`), and always show a legal disclaimer.

Single FastAPI app (not a monorepo). Stack: FastAPI + LangGraph + PostgreSQL 16/pgvector + OpenAI GPT-4o-mini + text-embedding-3-small + deterministic local legal ranking.

## Session Completion Requirement

If a session changes code or code-adjacent config, review and update the relevant `docs/project/` pages before the final response so they match the implementation.

## Behavioral Guidelines

These rules reduce common LLM coding mistakes and bias toward caution over speed. Use judgment for trivial tasks.

| Rule | Apply it this way |
|---|---|
| Think before coding | State assumptions, surface tradeoffs, ask when unclear, and do not pick silently between valid interpretations. |
| Simplicity first | Write the minimum code that solves the request; no speculative features, abstractions, flexibility, or impossible-case handling. |
| Surgical changes | Touch only required lines, match existing style, avoid adjacent cleanup, and mention unrelated dead code instead of deleting it. |
| Clean own mess | Remove imports, variables, or functions made unused by your change; do not remove pre-existing dead code unless asked. |
| Goal-driven execution | Turn work into verifiable goals and loop until checks pass. |

For multi-step tasks, state a brief plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

## Domain Rules (zero-tolerance)

These come from the PRD and must never be silently violated:

| Rule | Source |
|---|---|
| Every RAG query MUST filter eligible active sources BEFORE vector search — no bypass. | `docs/project/10-rag-retrieval-ranking-spec.md` |
| Every legal answer MUST carry a citation (Điều/Khoản) or state insufficient evidence. | `docs/project/10-rag-retrieval-ranking-spec.md` |
| Every legal output MUST append the mandatory disclaimer. | `docs/project/11-rag-guardrail-spec.md` |
| All corpus changes go through admin review and publish before becoming available to chat. | `docs/project/13-kb-workflow.md` |

## Agent and PR Rules

| Topic | Rule |
|---|---|
| PR body | Include `## Summary` and `## Changes` with changed files. |
| Venv | Use `.venv` at the repo root. |

### One-Time Setup

```bash
cp .env.example .env   # then add OPENAI_API_KEY
```

## Project Structure

| Path | Purpose |
|---|---|
| `app/backend/src/rag/agent/` | LangGraph RAG agent đầy đủ: graph, state, nodes, tools |
| `app/backend/src/legal_kb/` | Upload, parse, review, publish và dữ liệu kho văn bản |
| `app/backend/src/rag/retrieval/hybrid_legal.py` | Exact, full-text, vector retrieval và ranking |
| `app/backend/src/api/v1/` | FastAPI v1 routes; chat chính thức là `POST /api/v1/chat/stream` |
| `app/backend/src/models/` | SQLAlchemy database models |
| `app/backend/src/schemas/` | Pydantic schemas dùng chung cho RAG |
| `app/backend/src/core/config.py` | Pydantic Settings |
| `app/backend/src/main.py` | FastAPI entry point |
| `app/backend/tests/` | pytest suite (`test_api/`, `test_rag/`, `test_integrations/`) |
| `scripts/` | Maintenance and audit utilities |
| `docs/project/` | Project specs (single source of truth — see below) |
| `eval/` | Evaluation results (RAGAS) |

## Skill Reference Map

This repo ships skill definitions in `.claude/skills/`. Claude Code auto-loads them by description, but **other agents (Antigravity, Codex, Cursor, Gemini) must read the relevant SKILL.md before implementing the corresponding task**. Pinned versions are in `skills-lock.json`.

| Task | Skill file to read first |
|---|---|
| Choosing LangChain vs LangGraph vs Deep Agents | [.claude/skills/framework-selection/SKILL.md](.claude/skills/framework-selection/SKILL.md) |
| Pinning langchain-* / langgraph-* package versions | [.claude/skills/langchain-dependencies/SKILL.md](.claude/skills/langchain-dependencies/SKILL.md) |
| `create_agent`, defining tools, agent basics | [.claude/skills/langchain-fundamentals/SKILL.md](.claude/skills/langchain-fundamentals/SKILL.md) |
| Custom middleware, structured output (Pydantic) | [.claude/skills/langchain-middleware/SKILL.md](.claude/skills/langchain-middleware/SKILL.md) |
| RAG ingestion, embeddings, vector store, splitter | [.claude/skills/langchain-rag/SKILL.md](.claude/skills/langchain-rag/SKILL.md) |
| StateGraph, nodes, edges, Command, Send, streaming | [.claude/skills/langgraph-fundamentals/SKILL.md](.claude/skills/langgraph-fundamentals/SKILL.md) |
| HITL approval (e.g. admin duyệt KB), `interrupt()`, `Command(resume=...)` | [.claude/skills/langgraph-human-in-the-loop/SKILL.md](.claude/skills/langgraph-human-in-the-loop/SKILL.md) |
| Checkpointer, thread_id, time travel, persistence | [.claude/skills/langgraph-persistence/SKILL.md](.claude/skills/langgraph-persistence/SKILL.md) |
| Building Deep Agents (`create_deep_agent`, harness) | [.claude/skills/deep-agents-core/SKILL.md](.claude/skills/deep-agents-core/SKILL.md) |
| Deep Agent memory / persistence / filesystem | [.claude/skills/deep-agents-memory/SKILL.md](.claude/skills/deep-agents-memory/SKILL.md) |
| Subagents, task planning, HITL in Deep Agents | [.claude/skills/deep-agents-orchestration/SKILL.md](.claude/skills/deep-agents-orchestration/SKILL.md) |
| Langfuse tracing, prompts, datasets, scores | [.claude/skills/langfuse/SKILL.md](.claude/skills/langfuse/SKILL.md) |
| Frontend (Next.js / React) UI implementation | [.claude/skills/design-taste-frontend/SKILL.md](.claude/skills/design-taste-frontend/SKILL.md) |
| Auditing & redesigning existing UI | [.claude/skills/redesign-existing-projects/SKILL.md](.claude/skills/redesign-existing-projects/SKILL.md) |

When the task does not match the table (e.g. plain FastAPI route, SQLAlchemy model, Alembic migration), proceed with general knowledge — no skill required.

## Project Documentation

`docs/project/` is the single source of truth for design. Update the relevant file when behavior changes:

| Document | Purpose |
|---|---|
| [01-product-scope-and-corpus.md](docs/project/01-product-scope-and-corpus.md) | Phạm vi, persona và điều kiện corpus |
| [02-ui-workflows.md](docs/project/02-ui-workflows.md) | Các màn hình và luồng người dùng/admin |
| [03-api-spec.md](docs/project/03-api-spec.md) | Endpoint và contract request/response |
| [04-architecture.md](docs/project/04-architecture.md) | Thành phần và luồng dữ liệu |
| [05-database-schema.md](docs/project/05-database-schema.md) | Schema và migration PostgreSQL |
| [06-deployment-operations.md](docs/project/06-deployment-operations.md) | Cấu hình, storage, backup và triển khai |
| [07-testing-strategy.md](docs/project/07-testing-strategy.md) | Test, golden dataset và release gate |
| [08-rag-overview.md](docs/project/08-rag-overview.md) | Luồng RAG và nguyên tắc retrieval |
| [09-rag-chunking-spec.md](docs/project/09-rag-chunking-spec.md) | Parse, cấu trúc pháp lý và chunking |
| [10-rag-retrieval-ranking-spec.md](docs/project/10-rag-retrieval-ranking-spec.md) | Eligibility, hybrid search, ranking và citation |
| [11-rag-guardrail-spec.md](docs/project/11-rag-guardrail-spec.md) | Prompt, disclaimer, scope và injection |
| [12-security-rbac.md](docs/project/12-security-rbac.md) | Authentication, authorization và dữ liệu nhạy cảm |
| [13-kb-workflow.md](docs/project/13-kb-workflow.md) | Upload, review, publish và suspend |
| [14-observability.md](docs/project/14-observability.md) | Logs, traces và quality operations |

## Development Commands

```bash
\.venv\Scripts\python.exe -m pytest app/backend/tests -q
cd app/frontend
npm run lint
npm run build
```

API docs: `http://localhost:8000/docs`.
