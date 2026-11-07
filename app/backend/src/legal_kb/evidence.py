from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.legal_kb import (
    LegalKbAmendmentOperation,
    LegalKbDocument,
    LegalKbProvision,
    LegalKbProvisionVersion,
    LegalKbRevision,
)


@dataclass(frozen=True)
class EvidenceBundle:
    query_date: date
    provision_versions: tuple[LegalKbProvisionVersion, ...]
    amendment_operations: tuple[LegalKbAmendmentOperation, ...]
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
) -> list[LegalKbProvisionVersion]:
    stmt = (
        select(LegalKbProvisionVersion)
        .join(LegalKbRevision, LegalKbRevision.revision_id == LegalKbProvisionVersion.revision_id)
        .join(
            LegalKbProvision,
            LegalKbProvision.canonical_provision_id
            == LegalKbProvisionVersion.canonical_provision_id,
        )
        .join(LegalKbDocument, LegalKbDocument.document_id == LegalKbProvision.document_id)
        .where(
            LegalKbRevision.publication_status == "published",
            LegalKbRevision.review_status == "approved",
            LegalKbDocument.legal_status != "suspended",
            LegalKbProvisionVersion.answerable_status.notin_(("suspended", "not_answerable")),
            or_(LegalKbProvisionVersion.effective_from.is_(None), LegalKbProvisionVersion.effective_from <= query_date),
            or_(LegalKbProvisionVersion.effective_to.is_(None), LegalKbProvisionVersion.effective_to > query_date),
        )
        .options(
            selectinload(LegalKbProvisionVersion.canonical_provision).selectinload(
                LegalKbProvision.document
            ),
            selectinload(LegalKbProvisionVersion.provision_sources),
        )
        .order_by(LegalKbProvision.document_id, LegalKbProvision.provision_key)
    )
    if document_ids:
        stmt = stmt.where(LegalKbProvision.document_id.in_(document_ids))
    return list((await session.execute(stmt)).scalars().all())


async def _load_amendment_operations(
    session: AsyncSession,
    *,
    versions: list[LegalKbProvisionVersion],
) -> list[LegalKbAmendmentOperation]:
    version_ids = [version.provision_version_id for version in versions]
    if not version_ids:
        return []
    stmt = (
        select(LegalKbAmendmentOperation)
        .where(LegalKbAmendmentOperation.provision_version_id.in_(version_ids))
        .order_by(LegalKbAmendmentOperation.provision_version_id, LegalKbAmendmentOperation.operation_order)
    )
    return list((await session.execute(stmt)).scalars().all())


def _conflict_notices(versions: list[LegalKbProvisionVersion], *, query_date: date) -> list[str]:
    grouped: dict[str, list[LegalKbProvisionVersion]] = defaultdict(list)
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
