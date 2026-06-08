"""add unique source checksum index

Revision ID: 0004_unique_source_checksum
Revises: 0003_corpus_lifecycle_assets
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_unique_source_checksum"
down_revision: Union[str, None] = "0003_corpus_lifecycle_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_legal_docs_source_checksum",
        "legal_documents",
        ["source_checksum"],
        unique=True,
        postgresql_where=sa.text("source_checksum IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_legal_docs_source_checksum", table_name="legal_documents")
