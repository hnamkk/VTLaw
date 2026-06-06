---
name: project-docs-maintenance
description: "Invoke this skill after any work session that changes code or code-adjacent configuration to keep docs/project documentation up to date."
---

# Project Documentation Maintenance

Use this skill before completing any work session that changed source code, tests, migrations, infrastructure configuration, environment examples, API contracts, agent/RAG behavior, or user-facing behavior.

## Goal

Keep the project documentation in `docs/project/` accurate with the current implementation. Documentation should describe the system as it is now, not the plan, the previous behavior, or the implementation journey.

## Scope

Review and update documentation under `docs/project/`. The project documents are:

- `docs/project/01-research-brief.md`
- `docs/project/02-prd-product-requirements.md`
- `docs/project/03-wireframes-mockups.md`
- `docs/project/04-api-spec.md`
- `docs/project/05-architecture.md`
- `docs/project/06-database-schema.md`
- `docs/project/07-deployment-devops.md`
- `docs/project/08-testing-strategy.md`
- `docs/project/09-rag-overview.md`
- `docs/project/10-rag-chunking-spec.md`
- `docs/project/11-rag-retrieval-ranking-spec.md`
- `docs/project/12-citation-verification-spec.md`
- `docs/project/13-rag-prompt-guardrail-spec.md`
- `docs/project/14-rag-evaluation-dataset.md`

Planned but not yet created (create the file when you implement the corresponding area):

- `docs/project/15-security-rbac-spec.md` — auth, JWT, RBAC, encryption, audit trail, AI Law 134/2025 compliance
- `docs/project/16-kb-update-workflow.md` — admin upload → parse → chunk → embed → HITL queue → publish → notification lifecycle
- `docs/project/17-observability-monitoring.md` — LangSmith, metrics dashboard, alert thresholds, log retention

## When to Run

Run this skill when the session includes any of these changes:

- New or changed backend endpoints, schemas, services, jobs, permissions, or business rules
- New or changed frontend routes, workflows, forms, roles, or visible behavior
- New or changed database models, migrations, relationships, indexes, or seed assumptions
- New or changed RAG, retrieval, prompt, model, embedding, vector, chunking, citation, or ingestion behavior
- New or changed environment variables, Docker services, setup commands, or deployment assumptions
- Test changes that document behavior not already captured in project docs

Do not run this skill for documentation-only edits that already fully update `docs/project/`, pure formatting, dependency lockfile churn with no behavior change, or exploratory work with no repository changes.

## Workflow

1. Inspect the actual changed files and diffs.
2. Identify which project docs describe the changed behavior (use the Review Map below).
3. Read the relevant docs before editing them.
4. Update only the sections that are stale or incomplete.
5. Keep documentation concise, factual, and implementation-aligned.
6. Remove or correct obsolete claims instead of appending contradictory notes.
7. If no documentation update is needed, state that the docs were checked and why no change was required.

## Documentation Standards

- Write documentation in the language of the existing document (the project docs are in Vietnamese; keep them Vietnamese).
- Prefer stable product and architecture facts over commit/session narratives.
- Do not mention the AI assistant, the current session, temporary implementation details, or internal TODOs unless the document already tracks them.
- Preserve existing headings, tables, and terminology where practical.
- Use paths and names that exist in the current repository.
- Verify file paths, environment variable names, endpoint names, and role names against the code before documenting them.
- Keep `docs/project/` flat with the `NN-name.md` numbering — do not introduce subfolders.

## Suggested Review Map

| Change area | Documentation to check |
|---|---|
| Backend API routes/schemas/auth | `04-api-spec.md`, `05-architecture.md` |
| Database models/migrations/indexes | `06-database-schema.md`, `05-architecture.md` |
| Frontend workflows/UX/wireframes | `03-wireframes-mockups.md`, `02-prd-product-requirements.md` |
| RAG pipeline orchestration | `09-rag-overview.md` |
| RAG ingestion/parsing/chunking | `10-rag-chunking-spec.md` |
| RAG retrieval/hybrid/reranker | `11-rag-retrieval-ranking-spec.md` |
| Citation verifier | `12-citation-verification-spec.md` |
| Prompts/guardrails/disclaimer | `13-rag-prompt-guardrail-spec.md` |
| Eval dataset/RAGAS metrics | `14-rag-evaluation-dataset.md` |
| Docker/CI/deploy | `07-deployment-devops.md` |
| Tests | `08-testing-strategy.md` |
| Auth/RBAC/security/compliance | `15-security-rbac-spec.md` (create if implementing) |
| KB update lifecycle | `16-kb-update-workflow.md` (create if implementing) |
| Observability/metrics | `17-observability-monitoring.md` (create if implementing) |

## Completion Checklist

Before ending the session, confirm:

- Relevant docs in `docs/project/` were reviewed.
- Any stale documentation was updated.
- New behavior is documented at the product, API, architecture, database, or RAG level as appropriate.
- Documentation does not contradict the current code.
- If no doc edits were needed, the final response says so briefly.
