from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.kb_v2 import (
    KbV2AmendmentOperation,
    KbV2CanonicalProvision,
    KbV2DocumentRevision,
    KbV2LegalDocument,
    KbV2ProvisionVersion,
)


@dataclass(frozen=True)
class EvidenceBundle:
    query_date: date
    provision_versions: tuple[KbV2ProvisionVersion, ...]
    amendment_operations: tuple[KbV2AmendmentOperation, ...]
    conflict_notices: tuple[str, ...] = ()

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflict_notices)

    @property
    def prompt_notice(self) -> str:
        lines: list[str] = []
        if self.provision_versions:
            lines.append(
                "Evidence bundle: noi dung hien hanh duoc doi chieu tu "
                f"{len(self.provision_versions)} provision version da publish/review."
            )
        if self.amendment_operations:
            lines.append(
                "Evidence bundle: co "
                f"{len(self.amendment_operations)} thao tac sua doi da duyet lien quan."
            )
        lines.extend(self.conflict_notices)
        return "\n".join(lines)


async def assemble_evidence_bundle(
    session: AsyncSession,
    *,
    query_date: date,
    document_ids: tuple[str, ...] | None = None,
) -> EvidenceBundle:
    versions = await _load_effective_provision_versions(
        session,
        query_date=query_date,
        document_ids=document_ids,
    )
    operations = await _load_amendment_operations(session, versions=versions)
    return EvidenceBundle(
        query_date=query_date,
        provision_versions=tuple(versions),
        amendment_operations=tuple(operations),
        conflict_notices=tuple(_conflict_notices(versions, query_date=query_date)),
    )


async def _load_effective_provision_versions(
    session: AsyncSession,
    *,
    query_date: date,
    document_ids: tuple[str, ...] | None,
) -> list[KbV2ProvisionVersion]:
    stmt = (
        select(KbV2ProvisionVersion)
        .join(KbV2DocumentRevision, KbV2DocumentRevision.revision_id == KbV2ProvisionVersion.revision_id)
        .join(
            KbV2CanonicalProvision,
            KbV2CanonicalProvision.canonical_provision_id
            == KbV2ProvisionVersion.canonical_provision_id,
        )
        .join(KbV2LegalDocument, KbV2LegalDocument.document_id == KbV2CanonicalProvision.document_id)
        .where(
            KbV2DocumentRevision.publication_status == "published",
            KbV2DocumentRevision.review_status == "approved",
            KbV2LegalDocument.legal_status != "suspended",
            KbV2ProvisionVersion.answerable_status.notin_(("suspended", "not_answerable")),
            or_(KbV2ProvisionVersion.effective_from.is_(None), KbV2ProvisionVersion.effective_from <= query_date),
            or_(KbV2ProvisionVersion.effective_to.is_(None), KbV2ProvisionVersion.effective_to > query_date),
        )
        .options(
            selectinload(KbV2ProvisionVersion.canonical_provision).selectinload(
                KbV2CanonicalProvision.document
            ),
            selectinload(KbV2ProvisionVersion.provision_sources),
        )
        .order_by(KbV2CanonicalProvision.document_id, KbV2CanonicalProvision.provision_key)
    )
    if document_ids:
        stmt = stmt.where(KbV2CanonicalProvision.document_id.in_(document_ids))
    return list((await session.execute(stmt)).scalars().all())


async def _load_amendment_operations(
    session: AsyncSession,
    *,
    versions: list[KbV2ProvisionVersion],
) -> list[KbV2AmendmentOperation]:
    version_ids = [version.provision_version_id for version in versions]
    if not version_ids:
        return []
    stmt = (
        select(KbV2AmendmentOperation)
        .where(KbV2AmendmentOperation.provision_version_id.in_(version_ids))
        .order_by(KbV2AmendmentOperation.provision_version_id, KbV2AmendmentOperation.operation_order)
    )
    return list((await session.execute(stmt)).scalars().all())


def _conflict_notices(versions: list[KbV2ProvisionVersion], *, query_date: date) -> list[str]:
    grouped: dict[str, list[KbV2ProvisionVersion]] = defaultdict(list)
    for version in versions:
        grouped[version.canonical_provision_id].append(version)

    notices: list[str] = []
    for provision_versions in grouped.values():
        if len(provision_versions) <= 1:
            continue
        provision = provision_versions[0].canonical_provision
        label = provision.label if provision else provision_versions[0].canonical_provision_id
        notices.append(
            "Canh bao xung dot: provision "
            f"`{label}` co nhieu version cung hieu luc tai ngay "
            f"{query_date.isoformat()}."
        )
    return notices
