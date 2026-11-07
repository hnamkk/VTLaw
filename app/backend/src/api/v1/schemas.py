"""API schemas for chat, public documents, and admin KB endpoints."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    session_id: UUID | None = None
    question: str = Field(min_length=1, max_length=1000)
    language: str = "vi"


class ChatSessionOut(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    is_bookmarked: bool = False
    bookmark_title: str | None = None
    bookmarked_at: datetime | None = None


class ChatSessionsResponse(BaseModel):
    items: list[ChatSessionOut]


class ChatSessionBookmarkRequest(BaseModel):
    bookmark_title: str = Field(min_length=2, max_length=120)


class ChatSessionBookmarkResponse(BaseModel):
    session: ChatSessionOut


class ChatConfidenceOut(BaseModel):
    level: Literal["low", "medium", "high"] = "medium"
    reason: str = "metadata_default"


class ChatProvisionCitationOut(BaseModel):
    document_id: str
    article_num: int | None = None
    clause_num: int | None = None
    point_num: str | None = None
    effective_status: str
    retrieval_unit_id: str


class ChatDocumentSourceOut(BaseModel):
    document_id: str
    title: str | None = None
    issuing_body: str | None = None
    date: date_type | None = None
    url: str | None = None


class ChatHistoricalReferenceOut(BaseModel):
    document_id: str
    title: str | None = None
    article_num: int | None = None
    clause_num: int | None = None
    point_num: str | None = None
    effective_from: date_type | None = None
    effective_to: date_type | None = None
    status: str | None = None
    replaced_by: str | None = None


class ChatResponseMetadataOut(BaseModel):
    risk_level: Literal["low", "medium", "high"] = "medium"
    answer_mode: Literal[
        "direct",
        "summary",
        "historical",
        "clarification_needed",
        "multiple_possibilities",
        "insufficient_evidence",
        "out_of_scope",
    ] = "direct"
    confidence: ChatConfidenceOut = Field(default_factory=ChatConfidenceOut)
    provision_citations: list[ChatProvisionCitationOut] = Field(default_factory=list)
    document_sources: list[ChatDocumentSourceOut] = Field(default_factory=list)
    historical_references: list[ChatHistoricalReferenceOut] = Field(default_factory=list)
    clarification_question: str | None = None


class ChatMessageOut(ChatResponseMetadataOut):
    message_id: str
    role: str
    content: str
    citations: list[dict] = Field(default_factory=list)
    faithfulness_score: float | None = None
    is_out_of_scope: bool = False
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    session: ChatSessionOut
    messages: list[ChatMessageOut]


class ChatStreamDoneEvent(ChatResponseMetadataOut):
    type: Literal["done"]
    trace_id: str
    session_id: str
    content: str
    citations: list[dict] = Field(default_factory=list)
    faithfulness_score: float | None = None
    is_out_of_scope: bool = False
    reranker_failed: bool = False
    reranker_used: bool = False
    reranker_error_code: str | None = None
    low_confidence: bool = False
    retrieval_candidate_count: int = 0
    rerank_top_score: float | None = None
    query_intent: str | None = None
    guardrail_triggered: bool = False
    guardrail_stage: str | None = None
    guardrail_reason: str | None = None


class PublicDocumentRelationOut(BaseModel):
    relation_id: str
    relation_type: str
    direction: Literal["outgoing", "incoming"]
    source_locator: str | None = None
    target_locator: str | None = None
    counterpart_document_id: str
    counterpart_title: str | None = None
    counterpart_document_number: str | None = None
    counterpart_legal_status: str | None = None


class LegalDocumentOut(BaseModel):
    doc_id: str
    title: str
    document_number: str | None = None
    doc_type: str
    status: str
    issued_date: date_type | None = None
    effective_date: date_type
    expiry_date: date_type | None = None
    issuer: str
    source_url: str | None = None
    source_file_name: str | None = None
    source_download_url: str | None = None
    viewer_warning: str | None = None
    standard_summary_url: str | None = None
    current_revision_id: str | None = None
    relations: list[PublicDocumentRelationOut] = Field(default_factory=list)


class DocumentsResponse(BaseModel):
    items: list[LegalDocumentOut]
    total: int
    page: int
    page_size: int


class LegalKbDocumentSummaryOut(BaseModel):
    document_id: str
    revision_id: str
    summary_type: Literal["standard", "dynamic"]
    content: str
    effective_date: date_type | None = None
    citations: list[dict] = Field(default_factory=list)
    faithfulness_score: float | None = None
    related_document_ids: list[str] = Field(default_factory=list)


class LegalKbDynamicSummaryRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    query_date: date_type | None = None


class LegalKbPublicDocumentDetailOut(BaseModel):
    document_id: str
    revision_id: str
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    effective_date: date_type | None = None
    expiry_date: date_type | None = None
    legal_status: str
    publication_status: str
    source_file_name: str | None = None
    source_download_url: str | None = None
    standard_summary_url: str | None = None
    viewer_warning: str


class LegalKbHistoricalCitationOut(BaseModel):
    retrieval_unit_id: str
    document_id: str
    revision_id: str
    title: str | None = None
    document_number: str | None = None
    citation_label: str | None = None
    legal_status: str
    publication_status: str
    source_file_name: str | None = None
    source_download_url: str | None = None
    viewer_warning: str
    historical: bool = True


class AdminDocumentItem(LegalDocumentOut):
    review_status: str
    legal_status: str
    valid_from: date_type | None = None
    valid_to: date_type | None = None
    chunk_count: int = 0
    indexed_chunk_count: int = 0
    pending_queue_count: int = 0
    source_file_name: str | None = None
    source_download_url: str | None = None
    created_at: datetime


class AdminDocumentSummary(BaseModel):
    total: int
    active: int
    pending_review: int
    future_effective: int = 0
    repealed: int
    processing_failed: int


class AdminDocumentsResponse(BaseModel):
    items: list[AdminDocumentItem]
    total: int
    page: int
    page_size: int
    summary: AdminDocumentSummary


class AdminDocumentChunkOut(BaseModel):
    chunk_id: str
    chunk_type: str
    article_num: int | None = None
    clause_num: int | None = None
    point_num: str | None = None
    source_order: int | None = None
    content_kind: str = "legal_text"
    text_content: str
    display_path: str | None = None
    parser_confidence: float | None = None
    source_page: int | None = None
    has_embedding: bool = False


class AdminDocumentHistoryItem(BaseModel):
    queue_id: str
    change_type: str
    review_status: str
    processing_status: str
    source_file_name: str | None = None
    reviewer_note: str | None = None
    reject_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AdminDocumentDetail(AdminDocumentItem):
    replaced_by_id: str | None = None
    domain_tags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_file_name: str | None = None
    structure_summary: dict[str, int] = Field(default_factory=dict)
    history: list[AdminDocumentHistoryItem] = Field(default_factory=list)
    chunks: list[AdminDocumentChunkOut] = Field(default_factory=list)


class KbQueueItemOut(BaseModel):
    queue_id: str
    doc_id: str
    target_doc_id: str | None = None
    title: str
    issuer: str
    doc_type: str
    effective_date: date_type
    review_status: str
    processing_status: str
    change_type: str
    parser_confidence: float | None = None
    warning_count: int = 0
    source_file_name: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class KbQueueSummary(BaseModel):
    pending: int
    approved: int
    rejected: int


class KbQueueListResponse(BaseModel):
    items: list[KbQueueItemOut]
    total: int
    page: int
    page_size: int
    summary: KbQueueSummary


class KbQueueDocumentOut(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    status: str
    issuer: str
    effective_date: date_type
    expiry_date: date_type | None = None
    source_url: str | None = None
    domain_tags: list[str] = Field(default_factory=list)


class KbQueueDetailOut(BaseModel):
    queue_id: str
    doc_id: str
    target_doc_id: str | None = None
    change_type: str
    review_status: str
    processing_status: str
    parser_confidence: float | None = None
    warning_messages: list[str] = Field(default_factory=list)
    extracted_metadata: dict = Field(default_factory=dict)
    review_checklist: dict = Field(default_factory=dict)
    reviewer_draft_note: str | None = None
    reviewer_note: str | None = None
    reject_reason: str | None = None
    processing_error: str | None = None
    source_file_name: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    document: KbQueueDocumentOut
    target_document: KbQueueDocumentOut | None = None
    chunks: list[AdminDocumentChunkOut] = Field(default_factory=list)


class KbQueueDraftRequest(BaseModel):
    title: str | None = None
    issuer: str | None = None
    source_url: str | None = None
    effective_date: date_type | None = None
    expiry_date: date_type | None = None
    domain_tags: list[str] | None = None
    target_doc_id: str | None = None
    reviewer_draft_note: str | None = None
    review_checklist: dict | None = None


class DocumentRepealRequest(BaseModel):
    expiry_date: date_type
    reason: str = Field(min_length=3, max_length=2000)
    replaced_by_id: UUID | None = None


class KbQueueApproveRequest(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=5000)
    reviewed_by: str | None = None


class KbQueueRejectRequest(BaseModel):
    reject_reason: str = Field(min_length=1, max_length=40)
    reviewer_note: str | None = Field(default=None, max_length=5000)
    reviewed_by: str | None = None


class TrafficSignAssetOut(BaseModel):
    asset_id: str
    url: str
    width: int | None = None
    height: int | None = None
    mime_type: str


class TrafficSignOut(BaseModel):
    sign_code: str
    sign_name: str
    aliases: list[str] = Field(default_factory=list)
    sign_group: str | None = None
    recognition_text: str | None = None
    meaning_text: str
    application_text: str | None = None
    exception_text: str | None = None
    source_locator: str
    citation_chunk_id: str
    primary_asset: TrafficSignAssetOut | None = None


class TrafficSignListResponse(BaseModel):
    items: list[TrafficSignOut]
    total: int


class NotificationOut(BaseModel):
    notification_id: str
    doc_id: str
    queue_id: str | None = None
    change_type: str
    title: str
    summary: str
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    total: int
    page: int
    page_size: int


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class AssetReviewItemOut(BaseModel):
    asset_id: str
    doc_id: str
    asset_kind: str
    source_locator: str | None = None
    relationship_id: str | None = None
    caption: str | None = None
    alt_text: str | None = None
    mapping_confidence: str
    publish_status: str
    checksum: str


class AssetReviewRequest(BaseModel):
    publish_status: str
    mapping_confidence: str
    caption: str | None = None
    alt_text: str | None = None
    reviewed_by: str | None = None


class LegalKbDocumentOut(BaseModel):
    document_id: str
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    issued_date: date_type | None = None
    effective_date: date_type | None = None
    expiry_date: date_type | None = None
    legal_status: str
    metadata_json: dict = Field(default_factory=dict)


class LegalKbRevisionOut(BaseModel):
    revision_id: str
    document_id: str
    revision_number: int
    ingestion_status: str
    review_status: str
    publication_status: str
    checksum_sha256: str | None = None
    source_url: str | None = None
    source_downloaded_at: date_type | None = None
    source_note: str | None = None
    parser_version: str | None = None
    uploaded_at: datetime


class LegalKbSourceAssetOut(BaseModel):
    asset_id: str
    document_id: str
    revision_id: str | None = None
    asset_role: str
    storage_uri: str
    original_filename: str
    mime_type: str
    sha256: str
    file_size_bytes: int | None = None
    source_url: str | None = None
    source_downloaded_at: date_type | None = None
    source_note: str | None = None


class LegalKbNodeOut(BaseModel):
    node_id: str
    revision_id: str
    parent_id: str | None = None
    node_type: str
    label: str | None = None
    text: str | None = None
    order_index: int
    review_status: str
    provenance: dict = Field(default_factory=dict)
    structured_content: dict = Field(default_factory=dict)


class LegalKbMetadataProposalOut(BaseModel):
    proposal_id: str
    document_id: str
    revision_id: str
    field_name: str
    proposed_value: str
    source_type: str
    confidence: float | None = None
    review_status: str
    provenance: dict = Field(default_factory=dict)
    review_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None


class LegalKbRelationOut(BaseModel):
    relation_id: str
    source_document_id: str
    target_document_id: str
    relation_type: str
    source_locator: str | None = None
    target_locator: str | None = None
    review_status: str
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class LegalKbSummaryOut(BaseModel):
    summary_id: str
    document_id: str
    revision_id: str
    content: str
    review_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None


class LegalKbRetrievalUnitOut(BaseModel):
    retrieval_unit_id: str
    canonical_node_id: str
    document_id: str
    revision_id: str
    answerable_status: str
    citation_label: str | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    index_version: str | None = None


class LegalKbReviewEventOut(BaseModel):
    review_event_id: str
    document_id: str
    revision_id: str | None = None
    entity_type: str
    entity_id: str
    decision: str
    actor_user_id: str | None = None
    details: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class LegalKbRevisionDetailResponse(BaseModel):
    document: LegalKbDocumentOut
    revision: LegalKbRevisionOut
    source_asset: LegalKbSourceAssetOut | None = None
    canonical_nodes: list[LegalKbNodeOut] = Field(default_factory=list)
    metadata_proposals: list[LegalKbMetadataProposalOut] = Field(default_factory=list)
    relations: list[LegalKbRelationOut] = Field(default_factory=list)
    summary: LegalKbSummaryOut | None = None
    retrieval_units: list[LegalKbRetrievalUnitOut] = Field(default_factory=list)
    review_events: list[LegalKbReviewEventOut] = Field(default_factory=list)
    publish_blockers: list[str] = Field(default_factory=list)
    pending_metadata: list[LegalKbMetadataProposalOut] = Field(default_factory=list)
    pending_relations: list[LegalKbRelationOut] = Field(default_factory=list)
    pending_risky_nodes: list[LegalKbNodeOut] = Field(default_factory=list)
    resolved_risky_nodes: list[LegalKbNodeOut] = Field(default_factory=list)
    resolved_risky_count: int = 0
    risky_reference_only_count: int = 0
    risky_answerable_count: int = 0
    is_ready_to_publish: bool = False


class LegalKbUploadResponse(BaseModel):
    document: LegalKbDocumentOut
    revision: LegalKbRevisionOut
    source_asset: LegalKbSourceAssetOut
    parser_confidence: float
    parser_warnings: list[str] = Field(default_factory=list)
    canonical_nodes: list[LegalKbNodeOut] = Field(default_factory=list)


class LegalKbMetadataProposalCreateRequest(BaseModel):
    field_name: str = Field(min_length=2, max_length=64)
    proposed_value: str = Field(min_length=1, max_length=5000)
    note: str | None = Field(default=None, max_length=5000)


class LegalKbProposalReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=5000)
    proposed_value: str | None = Field(default=None, min_length=1, max_length=5000)


class LegalKbNodeReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=5000)
    answerable: bool | None = None


class LegalKbNodeResetReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class LegalKbRiskyNodeBulkReviewRequest(BaseModel):
    node_type: Literal["table", "appendix", "form", "image_caption"]
    mode: Literal["answerable", "review_only", "reset", "rejected"]
    note: str | None = Field(default=None, max_length=5000)


class LegalKbRelationCreateRequest(BaseModel):
    target_document_id: str
    relation_type: Literal["amends", "supplements", "replaces", "annuls", "guides", "depends_on"]
    source_locator: str | None = Field(default=None, max_length=255)
    target_locator: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=5000)


class LegalKbRelationReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=5000)


class LegalKbRelationUpdateRequest(BaseModel):
    target_document_id: str | None = None
    relation_type: Literal["amends", "supplements", "replaces", "annuls", "guides", "depends_on"] | None = None
    source_locator: str | None = Field(default=None, max_length=255)
    target_locator: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=5000)


class LegalKbSummaryReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    content: str | None = Field(default=None, max_length=8000)


class LegalKbSuspendRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=5000)


class LegalKbRevisionListItemOut(BaseModel):
    revision_id: str
    document_id: str
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    effective_date: date_type | None = None
    expiry_date: date_type | None = None
    review_status: str
    publication_status: str
    ingestion_status: str
    legal_status: str
    source_file_name: str | None = None
    pending_metadata_count: int = 0
    pending_relations_count: int = 0
    pending_risky_nodes_count: int = 0
    summary_status: str | None = None
    publish_blockers_count: int = 0
    is_ready_to_publish: bool = False
    relation_count: int = 0
    uploaded_at: datetime
    updated_at: datetime | None = None


class LegalKbRevisionListResponse(BaseModel):
    items: list[LegalKbRevisionListItemOut]
    total: int
    page: int
    page_size: int


class LegalKbPublishedDocumentListItemOut(BaseModel):
    document_id: str
    revision_id: str
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    effective_date: date_type | None = None
    expiry_date: date_type | None = None
    legal_status: str
    publication_status: str
    display_status: str
    source_file_name: str | None = None
    updated_at: datetime | None = None
    relation_count: int = 0


class LegalKbPublishedDocumentListResponse(BaseModel):
    items: list[LegalKbPublishedDocumentListItemOut]
    total: int
    page: int
    page_size: int


class LegalKbRelationTargetItemOut(BaseModel):
    document_id: str
    title: str | None = None
    document_number: str | None = None


class LegalKbRelationTargetListResponse(BaseModel):
    items: list[LegalKbRelationTargetItemOut]
    total: int


class LegalKbPublishedDocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=500)
    document_number: str | None = Field(default=None, max_length=120)
    document_type: str | None = Field(default=None, max_length=40)
    issuing_authority: str | None = Field(default=None, max_length=255)
    issued_date: date_type | None = None
    effective_date: date_type | None = None
    expiry_date: date_type | None = None
    source_url: str | None = Field(default=None, max_length=1000)
    source_downloaded_at: date_type | None = None
    source_note: str | None = Field(default=None, max_length=5000)
    source_file_name: str | None = Field(default=None, max_length=255)
    document_role: str | None = Field(default=None, max_length=40)


class LegalKbRevisionSourceUpdateRequest(BaseModel):
    source_url: str | None = Field(default=None, max_length=1000)
    source_downloaded_at: date_type | None = None
    source_note: str | None = Field(default=None, max_length=5000)
    source_file_name: str | None = Field(default=None, max_length=255)


class LegalKbPublishedDocumentStatusRequest(BaseModel):
    status: Literal["active", "suspended", "expired", "replaced", "annulled"]
    note: str | None = Field(default=None, max_length=5000)
    replacement_document_id: str | None = None
