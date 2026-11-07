"""SQLAlchemy models. Import all models here so Base.metadata is complete."""

from src.models.base import Base
from src.models.chat_session import ChatMessage, ChatSession
from src.models.document_asset import DocumentAsset
from src.models.document_chunk import DocumentChunk
from src.models.document_lifecycle_event import DocumentLifecycleEvent
from src.models.document_relation import DocumentRelation
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument
from src.models.legal_kb import (
    LegalKbAmendmentOperation,
    LegalKbDocument,
    LegalKbMetadataProposal,
    LegalKbNode,
    LegalKbProvision,
    LegalKbProvisionSource,
    LegalKbProvisionVersion,
    LegalKbRelation,
    LegalKbRetrievalUnit,
    LegalKbReviewEvent,
    LegalKbRevision,
    LegalKbSourceAsset,
    LegalKbSummary,
)
from src.models.notification import InAppNotification, UserNotificationRead
from src.models.quality import (
    QualityIssue,
    QualityObservation,
    QualityReleaseCase,
    QualityReleaseCheck,
)
from src.models.traffic_sign import TrafficSign
from src.models.user import User

__all__ = [
    "Base",
    "ChatSession",
    "ChatMessage",
    "LegalDocument",
    "InAppNotification",
    "UserNotificationRead",
    "QualityObservation",
    "QualityIssue",
    "QualityReleaseCheck",
    "QualityReleaseCase",
    "DocumentChunk",
    "DocumentLifecycleEvent",
    "KbUpdateQueue",
    "LegalKbDocument",
    "LegalKbRevision",
    "LegalKbSourceAsset",
    "LegalKbNode",
    "LegalKbRetrievalUnit",
    "LegalKbRelation",
    "LegalKbMetadataProposal",
    "LegalKbProvision",
    "LegalKbProvisionVersion",
    "LegalKbProvisionSource",
    "LegalKbAmendmentOperation",
    "LegalKbSummary",
    "LegalKbReviewEvent",
    "DocumentRelation",
    "DocumentAsset",
    "TrafficSign",
    "User",
]
