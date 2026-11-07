from __future__ import annotations

from datetime import date

from src.legal_kb.evidence import EvidenceBundle, _conflict_notices
from src.models.legal_kb import LegalKbProvision, LegalKbProvisionVersion


def test_evidence_bundle_prompt_notice_includes_conflict_and_amendment_count():
    version = LegalKbProvisionVersion(
        provision_version_id="version-1",
        canonical_provision_id="provision-1",
        revision_id="rev-1",
        text="Noi dung hien hanh.",
        answerable_status="active",
    )
    bundle = EvidenceBundle(
        query_date=date(2026, 7, 3),
        provision_versions=(version,),
        amendment_operations=(object(),),  # type: ignore[arg-type]
        conflict_notices=("Canh bao xung dot: Dieu 1.",),
    )

    assert bundle.has_conflict is True
    assert "1 provision version" in bundle.prompt_notice
    assert "1 thao tac sua doi" in bundle.prompt_notice
    assert "Canh bao xung dot: Dieu 1." in bundle.prompt_notice


def test_conflict_notices_flags_multiple_versions_for_same_provision():
    provision = LegalKbProvision(
        canonical_provision_id="provision-1",
        document_id="doc-1",
        provision_key="dieu-1",
        label="Dieu 1",
    )
    version_a = LegalKbProvisionVersion(
        provision_version_id="version-a",
        canonical_provision_id="provision-1",
        revision_id="rev-1",
        text="Noi dung A.",
        answerable_status="active",
    )
    version_b = LegalKbProvisionVersion(
        provision_version_id="version-b",
        canonical_provision_id="provision-1",
        revision_id="rev-2",
        text="Noi dung B.",
        answerable_status="active",
    )
    version_a.canonical_provision = provision
    version_b.canonical_provision = provision

    notices = _conflict_notices([version_a, version_b], query_date=date(2026, 7, 3))

    assert notices == [
        "Canh bao xung dot: provision `Dieu 1` co nhieu version cung hieu luc tai ngay 2026-07-03."
    ]
