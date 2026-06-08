"""SQLAlchemy models. Import all models here so Base.metadata is complete."""

from src.models.base import Base
from src.models.chat_session import ChatMessage, ChatSession
from src.models.document_asset import DocumentAsset
from src.models.document_chunk import DocumentChunk
from src.models.document_lifecycle_event import DocumentLifecycleEvent
from src.models.document_relation import DocumentRelation
from src.models.kb_update_queue import KbUpdateQueue
from src.models.kb_v2 import (
    KbV2AmendmentOperation,
    KbV2CanonicalNode,
    KbV2CanonicalProvision,
    KbV2DocumentRelation,
    KbV2DocumentRevision,
    KbV2LegalDocument,
    KbV2MetadataProposal,
    KbV2ProvisionSource,
    KbV2ProvisionVersion,
    KbV2RetrievalUnit,
    KbV2ReviewEvent,
    KbV2SourceAsset,
    KbV2StandardSummary,
)
from src.models.legal_document import LegalDocument
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
    "KbV2LegalDocument",
    "KbV2DocumentRevision",
    "KbV2SourceAsset",
    "KbV2CanonicalNode",
    "KbV2RetrievalUnit",
    "KbV2DocumentRelation",
    "KbV2MetadataProposal",
    "KbV2CanonicalProvision",
    "KbV2ProvisionVersion",
    "KbV2ProvisionSource",
    "KbV2AmendmentOperation",
    "KbV2StandardSummary",
    "KbV2ReviewEvent",
    "DocumentRelation",
    "DocumentAsset",
    "TrafficSign",
    "User",
]
