# Database schema

PostgreSQL 16 with pgvector. SQLAlchemy models and Alembic migrations are the executable schema source of truth; this document records the current table groups and invariants.

## Legal knowledge base

The current ingestion and retrieval workflow uses the `legal_kb_*` tables defined in `app/backend/src/models/legal_kb.py`:

| Table | Purpose |
|---|---|
| `legal_kb_legal_documents` | Stable identity and legal metadata for a document |
| `legal_kb_document_revisions` | Upload, parse, review, and publication lifecycle per revision |
| `legal_kb_source_assets` | Original files, checksums, storage URI, and provenance |
| `legal_kb_canonical_nodes` | Parsed document tree, source order, and review decisions |
| `legal_kb_retrieval_units` | Searchable text, embedding, citation locator, and effective interval |
| `legal_kb_document_relations` | Reviewed relations between documents |
| `legal_kb_metadata_proposals` | Proposed metadata with review state and provenance |
| `legal_kb_canonical_provisions` | Stable identities for legal provisions |
| `legal_kb_provision_versions` | Provision text and validity by revision |
| `legal_kb_provision_sources` | Links provision versions to parsed source nodes |
| `legal_kb_amendment_operations` | Structured amendment operations and source references |
| `legal_kb_standard_summaries` | Proposed summaries that require review |
| `legal_kb_review_events` | Audit history for review and publication actions |

Important invariants:

- A document, revision, and source asset are separate records so re-uploads do not overwrite provenance.
- Review state, publication state, and legal validity are independent dimensions.
- Retrieval units are created at publication. Draft, rejected, suspended, or otherwise ineligible content is not public evidence.
- `content_hash` is unique for retrieval units; source assets retain SHA-256 and a unique storage URI.
- File bytes live in local or S3-compatible storage, not PostgreSQL.

## Other application tables

These current models support identity, chat, notifications, quality operations, and existing document/catalog endpoints:

| Area | Tables |
|---|---|
| Identity and chat | `users`, `qa_sessions`, `qa_messages` |
| Existing legal-document and catalog workflows | `legal_documents`, `document_chunks`, `document_assets`, `document_relations`, `document_lifecycle_events`, `traffic_signs`, `kb_update_queue` |
| Notifications | `in_app_notifications`, `user_notification_reads` |
| Quality operations | `quality_observations`, `quality_issues`, `quality_release_checks`, `quality_release_cases` |

Do not infer that a document is eligible for chat from its presence in these tables. The active legal knowledge base workflow and its eligibility filters define answerable evidence.

## Migrations and operations

Alembic is the schema-change mechanism. The current head includes the legal knowledge base foundation and review workflow, chat response metadata, and a naming/path migration that standardizes the knowledge base schema identifiers and local source paths. Historical revision identifiers are retained so existing databases can follow the same migration chain.

Before applying migrations to a database with data, back up both PostgreSQL and source-file storage. Afterward, verify row counts, source URIs, and file checksums. The naming migration does not rename objects inside an S3 bucket; existing object keys remain valid.
