"""Rename the legal knowledge base schema and local source paths."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_legal_kb_names"
down_revision: str | None = "0015_chat_response_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = (
    ("kb_v2_legal_documents", "legal_kb_legal_documents"),
    ("kb_v2_source_assets", "legal_kb_source_assets"),
    ("kb_v2_document_revisions", "legal_kb_document_revisions"),
    ("kb_v2_canonical_nodes", "legal_kb_canonical_nodes"),
    ("kb_v2_retrieval_units", "legal_kb_retrieval_units"),
    ("kb_v2_document_relations", "legal_kb_document_relations"),
    ("kb_v2_metadata_proposals", "legal_kb_metadata_proposals"),
    ("kb_v2_canonical_provisions", "legal_kb_canonical_provisions"),
    ("kb_v2_provision_versions", "legal_kb_provision_versions"),
    ("kb_v2_provision_sources", "legal_kb_provision_sources"),
    ("kb_v2_amendment_operations", "legal_kb_amendment_operations"),
    ("kb_v2_standard_summaries", "legal_kb_standard_summaries"),
    ("kb_v2_review_events", "legal_kb_review_events"),
)


def _rename_catalog_objects(old_prefix: str, new_prefix: str) -> None:
    op.execute(
        f"""
            DO $$
            DECLARE item record;
            BEGIN
                FOR item IN
                    SELECT n.nspname AS schema_name,
                           t.relname AS table_name,
                           c.conname AS object_name
                    FROM pg_constraint c
                    JOIN pg_class t ON t.oid = c.conrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    WHERE n.nspname = current_schema()
                      AND strpos(c.conname, '{old_prefix}') > 0
                LOOP
                    EXECUTE format(
                        'ALTER TABLE %I.%I RENAME CONSTRAINT %I TO %I',
                        item.schema_name,
                        item.table_name,
                        item.object_name,
                        replace(item.object_name, '{old_prefix}', '{new_prefix}')
                    );
                END LOOP;

                FOR item IN
                    SELECT schemaname AS schema_name, indexname AS object_name
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND strpos(indexname, '{old_prefix}') > 0
                LOOP
                    EXECUTE format(
                        'ALTER INDEX %I.%I RENAME TO %I',
                        item.schema_name,
                        item.object_name,
                        replace(item.object_name, '{old_prefix}', '{new_prefix}')
                    );
                END LOOP;
            END $$;
            """
    )


def _rewrite_local_source_paths(old_root: str, new_root: str) -> None:
    op.execute(
        sa.text(
            """
            UPDATE legal_kb_source_assets
            SET storage_uri = replace(storage_uri, :old_root, :new_root)
            WHERE storage_uri NOT LIKE 's3://%'
              AND position(:old_root IN storage_uri) > 0
            """
        ).bindparams(old_root=old_root, new_root=new_root)
    )


def upgrade() -> None:
    for old_name, new_name in _TABLES:
        op.rename_table(old_name, new_name)

    _rename_catalog_objects("kb_v2_", "legal_kb_")
    _rewrite_local_source_paths(
        "storage/kb_v2/kb-v2/",
        "storage/legal_kb/legal-kb/",
    )
    _rewrite_local_source_paths(
        "storage" + chr(92) + "kb_v2" + chr(92) + "kb-v2" + chr(92),
        "storage" + chr(92) + "legal_kb" + chr(92) + "legal-kb" + chr(92),
    )
    op.execute(
        sa.text(
            "UPDATE legal_kb_document_revisions "
            "SET parser_version = 'legal-kb-p1' "
            "WHERE parser_version = 'kb-v2-p1'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE legal_kb_retrieval_units "
            "SET embedding_version = 'legal_kb_v1' "
            "WHERE embedding_version = 'kb_v2_v1'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE legal_kb_retrieval_units "
            "SET index_version = 'legal_kb_v1' "
            "WHERE index_version = 'kb_v2_v1'"
        )
    )


def downgrade() -> None:
    _rewrite_local_source_paths(
        "storage/legal_kb/legal-kb/",
        "storage/kb_v2/kb-v2/",
    )
    _rewrite_local_source_paths(
        "storage" + chr(92) + "legal_kb" + chr(92) + "legal-kb" + chr(92),
        "storage" + chr(92) + "kb_v2" + chr(92) + "kb-v2" + chr(92),
    )
    op.execute(
        sa.text(
            "UPDATE legal_kb_document_revisions "
            "SET parser_version = 'kb-v2-p1' "
            "WHERE parser_version = 'legal-kb-p1'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE legal_kb_retrieval_units "
            "SET embedding_version = 'kb_v2_v1' "
            "WHERE embedding_version = 'legal_kb_v1'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE legal_kb_retrieval_units "
            "SET index_version = 'kb_v2_v1' "
            "WHERE index_version = 'legal_kb_v1'"
        )
    )
    _rename_catalog_objects("legal_kb_", "kb_v2_")

    for old_name, new_name in reversed(_TABLES):
        op.rename_table(new_name, old_name)
