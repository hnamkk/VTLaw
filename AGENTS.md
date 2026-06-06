# AGENTS.md

Guidance for AI coding agents (Codex, Cursor, Gemini, Copilot) in this repository. Treat the project as production-shaped. Keep responses concise and use tables when helpful. Use the project virtualenv (`.venv`) to run or install dependencies.

## Project

**AI Trợ Lý Tra Cứu & Tuân Thủ Quy Định Giao Thông Vận Tải** — a Vietnamese legal Q&A AI agent over road-transport regulations. Answers cite Điều/Khoản, filter for in-force documents (`status=active`), and always show a legal disclaimer.

Single FastAPI app (not a monorepo). Stack: FastAPI + LangGraph + PostgreSQL 16/pgvector + OpenAI GPT-4o-mini + text-embedding-3-small + deterministic local legal ranking.

## Session Completion Requirement

If a session changes code or code-adjacent config, invoke `project-docs-maintenance` before the final response to keep `docs/project/` aligned with the implementation.

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
| Every RAG query MUST filter `status=active` BEFORE vector search — no bypass. | PRD F02 |
| Every legal answer MUST carry a citation (Điều/Khoản) or state insufficient evidence. | PRD F03/F04 |
| Every legal output MUST append the mandatory disclaimer (Luật AI 134/2025/QH15). | PRD F05 |
| All KB changes go through `kb_update_queue` HITL approval before becoming `active`. | PRD F01 |

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
| `app/backend/src/api/v1/` | FastAPI v1 routes; chat chính thức là `POST /api/v1/chat/stream` |
| `app/backend/src/models/` | SQLAlchemy database models |
| `app/backend/src/schemas/` | Pydantic schemas dùng chung cho RAG |
| `app/backend/src/core/config.py` | Pydantic Settings |
| `app/backend/src/main.py` | FastAPI entry point |
| `app/backend/tests/` | pytest suite (`test_api/`, `test_rag/`, `test_integrations/`) |
| `scripts/` | Maintenance and audit utilities |
| `docs/project/` | Project specs (single source of truth — see below) |
| `docs/guide/` | Technical Guidebook — consult before implementing (patterns, anti-patterns, code-style, testing, devops). Reference material, not a spec for this repo. |
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
| End of any code-changing session | [.claude/skills/project-docs-maintenance/SKILL.md](.claude/skills/project-docs-maintenance/SKILL.md) |

When the task does not match the table (e.g. plain FastAPI route, SQLAlchemy model, Alembic migration), proceed with general knowledge — no skill required.

## Project Documentation

`docs/project/` is the single source of truth for design. Update the relevant file when behavior changes:

| Document | Purpose |
|---|---|
| [01-research-brief.md](docs/project/01-research-brief.md) | Research & problem framing |
| [02-prd-product-requirements.md](docs/project/02-prd-product-requirements.md) | User stories, functional + non-functional requirements |
| [03-wireframes-mockups.md](docs/project/03-wireframes-mockups.md) | UI/UX wireframes |
| [04-api-spec.md](docs/project/04-api-spec.md) | API endpoints, request/response contracts |
| [05-architecture.md](docs/project/05-architecture.md) | System architecture, components, data flows |
| [06-database-schema.md](docs/project/06-database-schema.md) | PostgreSQL DDL, ERD, indexes (DB single source of truth) |
| [07-deployment-devops.md](docs/project/07-deployment-devops.md) | Docker, CI/CD, deployment |
| [08-testing-strategy.md](docs/project/08-testing-strategy.md) | Test layers, coverage targets |
| [09-rag-overview.md](docs/project/09-rag-overview.md) | RAG pipeline overview (gateway to 10-14) |
| [10-rag-chunking-spec.md](docs/project/10-rag-chunking-spec.md) | Parser + hierarchical chunking + chunk metadata |
| [11-rag-retrieval-ranking-spec.md](docs/project/11-rag-retrieval-ranking-spec.md) | Active filter, hybrid retrieval, scoring, rerank |
| [12-citation-verification-spec.md](docs/project/12-citation-verification-spec.md) | Citation schema, verifier status, claim-source checking |
| [13-rag-prompt-guardrail-spec.md](docs/project/13-rag-prompt-guardrail-spec.md) | Prompt contract, disclaimer, out-of-scope, injection |
| [14-rag-evaluation-dataset.md](docs/project/14-rag-evaluation-dataset.md) | Golden dataset, RAGAS metrics, release gate |

Supporting diagram (referenced by 05 / 06):

| Document | Purpose |
|---|---|
| [architecture_diagram.md](docs/architecture_diagram.md) | Mermaid diagrams — system overview, LangGraph flow, deployment topology |

## Development Commands

```bash
make run        # uvicorn app.main:app --reload --port 8000
make test       # pytest tests/ -v
make lint       # ruff check app/ tests/
make format     # ruff format app/ tests/
make typecheck  # mypy app/
make check      # lint + format + test
```

API docs: `http://localhost:8000/docs`.
