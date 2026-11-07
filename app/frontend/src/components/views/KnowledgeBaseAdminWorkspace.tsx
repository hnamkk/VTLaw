import React from 'react';
import {
    ArrowClockwise,
    CaretDown,
    CheckCircle,
    DownloadSimple,
    FileArrowUp,
    MagnifyingGlass,
    PencilSimple,
    WarningCircle,
    X,
} from '@phosphor-icons/react';

import {
    createLegalKbMetadataProposal,
    createLegalKbRelationProposal,
    deleteLegalKbRelation,
    downloadAdminSource,
    fetchLegalKbRevisionDetail,
    fetchLegalKbRevisionList,
    fetchLegalKbRelationTargets,
    LegalKbDuplicateSourceError,
    publishLegalKbRevision,
    resetLegalKbNodeReview,
    reviewLegalKbMetadataProposal,
    reviewLegalKbNode,
    reviewLegalKbRelation,
    reviewLegalKbSummary,
    type LegalKbNodeOut,
    type LegalKbRelationOut,
    type LegalKbMetadataProposalOut,
    type LegalKbRevisionDetailResponse,
    type LegalKbRevisionListItem,
    type LegalKbRevisionListResponse,
    type LegalKbRelationTargetItem,
    updateLegalKbRelation,
    updateLegalKbPublishedDocument,
    updateLegalKbRevisionSource,
    uploadLegalKbRevision,
} from '../../lib/api';
import { DOCUMENT_CORPUS_PRESETS } from '../../lib/kbCorpusPresets';

type UploadDraft = {
    file: File | null;
    presetKey: string;
    title: string;
    sourceUrl: string;
    sourceDownloadedAt: string;
    sourceNote: string;
    documentNumber: string;
    documentType: string;
    documentRole: string;
    issuingAuthority: string;
    issuedDate: string;
    effectiveDate: string;
    expiryDate: string;
};

type UploadPhase = 'idle' | 'uploading' | 'parsing' | 'proposals' | 'opening';

type PublishPhase = 'idle' | 'validating' | 'publishing' | 'refreshing' | 'done' | 'failed';

type RelationType = 'amends' | 'supplements' | 'replaces' | 'annuls' | 'guides' | 'depends_on';

type RelationDraft = {
    targetDocumentId: string;
    relationType: RelationType;
    sourceLocator: string;
    targetLocator: string;
    note: string;
};

type RelationTargetOption = {
    value: string;
    label: string;
    searchText: string;
};

type DocumentFormDraft = {
    title: string;
    documentNumber: string;
    documentType: string;
    documentRole: string;
    issuingAuthority: string;
    issuedDate: string;
    effectiveDate: string;
    expiryDate: string;
    summary: string;
    sourceUrl: string;
    sourceDownloadedAt: string;
    sourceFileName: string;
};

type EditableMetadataField =
    | 'title'
    | 'document_number'
    | 'document_type'
    | 'document_role'
    | 'issuing_authority'
    | 'issued_date'
    | 'effective_date'
    | 'expiry_date';

type EditableSourceField = 'source_url' | 'source_downloaded_at' | 'source_file_name';

type WorkspaceConfirmation =
    | { kind: 'document-save' }
    | { kind: 'publish' }
    | { kind: 'relation-update'; relationId: string }
    | { kind: 'relation-reset'; relation: LegalKbRelationOut }
    | { kind: 'relation-delete'; relation: LegalKbRelationOut }
    | { kind: 'content-reset'; item: LegalKbNodeOut };

const PAGE_SIZE = 12;
const REVIEW_HISTORY_PAGE_SIZE = 5;
const SLOW_LOADING_THRESHOLD_MS = 10000;
const HITL_REVIEW_REVISION_KEY = 'hitl-review-revision-prefill';
const REVIEW_STATUS_OPTIONS = [
    { value: 'draft', label: 'Đang xử lý', tone: 'review-stat-card' },
    { value: 'published', label: 'Đã đưa vào kho', tone: 'review-stat-card review-stat-card-good' },
    { value: 'suspended', label: 'Tạm ngừng', tone: 'review-stat-card review-stat-card-danger' },
    { value: 'archived', label: 'Lưu kho', tone: 'review-stat-card' },
] as const;

const EMPTY_UPLOAD_DRAFT: UploadDraft = {
    file: null,
    presetKey: '',
    title: '',
    sourceUrl: '',
    sourceDownloadedAt: new Date().toISOString().slice(0, 10),
    sourceNote: '',
    documentNumber: '',
    documentType: 'THONG_TU',
    documentRole: 'primary',
    issuingAuthority: '',
    issuedDate: '',
    effectiveDate: '',
    expiryDate: '',
};

const UPLOAD_PHASES: Array<{ value: Exclude<UploadPhase, 'idle'>; label: string; description: string }> = [
    { value: 'uploading', label: 'Tải file', description: 'Đưa file nguồn vào vùng xử lý an toàn.' },
    { value: 'parsing', label: 'Tách nội dung', description: 'Đọc DOCX và nhận diện cấu trúc văn bản.' },
    { value: 'proposals', label: 'Tạo đề xuất', description: 'Chuẩn bị thông tin, tóm tắt và các mục cần kiểm tra.' },
    { value: 'opening', label: 'Mở hồ sơ', description: 'Chuyển sang màn duyệt để hoàn tất trước khi đưa vào kho.' },
];

const PUBLISH_PHASES: Array<{ value: Exclude<PublishPhase, 'idle' | 'failed'>; label: string; description: string }> = [
    { value: 'validating', label: 'Kiểm tra điều kiện', description: 'Đối chiếu các mục còn cần xử lý trước khi ghi vào kho.' },
    { value: 'publishing', label: 'Ghi vào kho', description: 'Cập nhật trạng thái công bố và dữ liệu văn bản đang quản lý.' },
    { value: 'refreshing', label: 'Cập nhật nhãn', description: 'Tải lại hồ sơ, danh sách và số lượng theo trạng thái mới.' },
    { value: 'done', label: 'Hoàn tất', description: 'Văn bản đã ở trong kho và các nhãn đã được làm mới.' },
];

const RELATION_REQUIRED_ROLES = new Set(['amendment', 'replacement', 'guidance']);

function DateInput({
    id,
    value,
    onChange,
    required = false,
}: {
    id: string;
    value: string;
    onChange: (value: string) => void;
    required?: boolean;
}) {
    return (
        <div className="localized-date-control" data-empty={!value || undefined}>
            <input
                id={id}
                type="date"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                required={required}
                aria-describedby={`${id}-hint`}
            />
            <span className="localized-date-placeholder" aria-hidden="true">Chọn ngày</span>
            <small id={`${id}-hint`} className="sr-only">Ngày theo định dạng ngày, tháng, năm.</small>
        </div>
    );
}

const DOCUMENT_TYPE_OPTIONS = [
    { value: 'LUAT', label: 'Luật' },
    { value: 'BO_LUAT', label: 'Bộ luật' },
    { value: 'NGHI_DINH', label: 'Nghị định' },
    { value: 'THONG_TU', label: 'Thông tư' },
    { value: 'QUYET_DINH', label: 'Quyết định' },
    { value: 'CONG_VAN', label: 'Công văn' },
    { value: 'QCVN', label: 'Quy chuẩn kỹ thuật' },
    { value: 'UNKNOWN', label: 'Khác hoặc chưa rõ' },
];

const DOCUMENT_ROLE_OPTIONS = [
    { value: 'primary', label: 'Văn bản chính để trả lời' },
    { value: 'amendment', label: 'Văn bản sửa đổi hoặc bổ sung' },
    { value: 'replacement', label: 'Văn bản thay thế hoặc ban hành mới' },
    { value: 'guidance', label: 'Văn bản hướng dẫn thi hành' },
    { value: 'foundation', label: 'Văn bản căn cứ để đối chiếu' },
    { value: 'reference', label: 'Tài liệu tham khảo bổ sung' },
    { value: 'technical', label: 'Quy chuẩn hoặc tài liệu kỹ thuật' },
];

const RELATION_OPTIONS: Array<{ value: RelationType; label: string; helper: string }> = [
    { value: 'amends', label: 'Sửa đổi', helper: 'Văn bản này sửa một phần nội dung của văn bản liên quan.' },
    { value: 'supplements', label: 'Bổ sung', helper: 'Văn bản này bổ sung thêm quy định cho văn bản liên quan.' },
    { value: 'replaces', label: 'Thay thế', helper: 'Văn bản này thay thế toàn bộ hoặc một phần văn bản liên quan.' },
    { value: 'annuls', label: 'Bãi bỏ', helper: 'Văn bản này bãi bỏ quy định của văn bản liên quan.' },
    { value: 'guides', label: 'Hướng dẫn', helper: 'Văn bản này hướng dẫn thi hành văn bản liên quan.' },
    { value: 'depends_on', label: 'Căn cứ liên quan', helper: 'Văn bản liên quan được dùng làm căn cứ hoặc bối cảnh.' },
];

function normalizeDocumentType(value: string | null | undefined) {
    const normalized = String(value ?? '').trim().toUpperCase();
    if (!normalized) return '';
    return normalized === 'QUY_CHUAN' ? 'QCVN' : normalized;
}

function normalizeDocumentRole(value: string | null | undefined) {
    const normalized = String(value ?? '').trim().toLowerCase();
    return {
        base: 'primary',
        original: 'primary',
        main: 'primary',
        primary: 'primary',
        amending: 'amendment',
        amendment: 'amendment',
        supplement: 'amendment',
        replacement: 'replacement',
        replacing: 'replacement',
        guiding: 'guidance',
        guidance: 'guidance',
        foundation: 'foundation',
        reference: 'reference',
        technical: 'technical',
    }[normalized] ?? normalized;
}

function formatDate(value: string | null | undefined) {
    if (!value) return 'Chưa cập nhật';
    return new Date(value).toLocaleDateString('vi-VN');
}

function formatDateTime(value: string | null | undefined) {
    if (!value) return 'Chưa cập nhật';
    return new Date(value).toLocaleString('vi-VN');
}

function formatCompactDate(value: string | null | undefined) {
    if (!value) return 'ChÆ°a cáº­p nháº­t';
    return new Date(value).toLocaleDateString('vi-VN');
}

function badgeTone(value: string) {
    if (value === 'published' || value === 'approved' || value === 'active') return 'active';
    if (value === 'suspended' || value === 'rejected') return 'expired';
    return 'pending';
}

function formatWorkspaceStatus(value: string) {
    return {
        draft: 'Đang xử lý',
        published: 'Đã đưa vào kho',
        suspended: 'Tạm ngừng',
        archived: 'Lưu kho',
    }[value] ?? value;
}

function formatReviewStatus(value: string) {
    return {
        needs_review: 'Cần kiểm tra',
        in_review: 'Đang kiểm tra',
        approved: 'Đã duyệt',
        rejected: 'Từ chối',
    }[value] ?? value;
}

function formatDocumentType(value: string | null | undefined) {
    const normalized = normalizeDocumentType(value);
    return DOCUMENT_TYPE_OPTIONS.find((option) => option.value === normalized)?.label ?? 'Khác hoặc chưa rõ';
}

function formatDocumentRole(value: string | null | undefined) {
    const normalized = normalizeDocumentRole(value);
    return DOCUMENT_ROLE_OPTIONS.find((option) => option.value === normalized)?.label ?? 'Chưa phân loại';
}

function formatContentType(value: string | null | undefined) {
    return {
        article: 'Điều',
        clause: 'Khoản',
        point: 'Điểm',
        table: 'Bảng',
        appendix: 'Phụ lục',
        form: 'Mẫu biểu',
        image_caption: 'Ảnh và chú thích',
        paragraph: 'Đoạn nội dung',
        heading: 'Tiêu đề',
    }[value ?? ''] ?? value ?? 'Mục nội dung';
}

function formatRelationType(value: RelationType | string | null | undefined) {
    return RELATION_OPTIONS.find((option) => option.value === value)?.label ?? 'Quan hệ văn bản';
}

function relationHelper(value: RelationType | string | null | undefined) {
    return RELATION_OPTIONS.find((option) => option.value === value)?.helper ?? '';
}

function relationCounterpartId(relation: LegalKbRelationOut, documentId: string) {
    return relation.source_document_id === documentId
        ? relation.target_document_id
        : relation.source_document_id;
}

function relationDirectionLabel(relation: LegalKbRelationOut, documentId: string) {
    return relation.source_document_id === documentId ? 'Quan hệ đi' : 'Quan hệ đến';
}

function formatMetadataFieldLabel(value: string | null | undefined) {
    return {
        title: 'Tiêu đề văn bản',
        document_number: 'Số hiệu',
        document_type: 'Loại văn bản',
        document_role: 'Vai trò văn bản',
        issuing_authority: 'Cơ quan ban hành',
        issued_date: 'Ngày ban hành',
        effective_date: 'Ngày có hiệu lực',
        expiry_date: 'Ngày hết hiệu lực',
        source_url: 'Đường dẫn nguồn',
        source_downloaded_at: 'Ngày lấy nguồn',
        source_note: 'Ghi chú nguồn',
    }[value ?? ''] ?? value ?? 'Thông tin văn bản';
}

function documentRoleFromMetadata(metadata: Record<string, unknown> | null | undefined) {
    const value = metadata?.document_role;
    return typeof value === 'string' ? value : null;
}

function emptyRelationDraft(): RelationDraft {
    return {
        targetDocumentId: '',
        relationType: 'depends_on',
        sourceLocator: '',
        targetLocator: '',
        note: '',
    };
}

function buildDocumentFormDraft(detail: LegalKbRevisionDetailResponse): DocumentFormDraft {
    return {
        title: detail.document.title ?? '',
        documentNumber: detail.document.document_number ?? '',
        documentType: normalizeDocumentType(detail.document.document_type) || 'UNKNOWN',
        documentRole: normalizeDocumentRole(documentRoleFromMetadata(detail.document.metadata_json)) || 'primary',
        issuingAuthority: detail.document.issuing_authority ?? '',
        issuedDate: detail.document.issued_date ?? '',
        effectiveDate: detail.document.effective_date ?? '',
        expiryDate: detail.document.expiry_date ?? '',
        summary: detail.summary?.content ?? '',
        sourceUrl: detail.revision.source_url ?? '',
        sourceDownloadedAt: detail.revision.source_downloaded_at ?? '',
        sourceFileName: detail.source_asset?.original_filename ?? '',
    };
}

function documentFormDraftFromDom(fallback: DocumentFormDraft, detail: LegalKbRevisionDetailResponse): DocumentFormDraft {
    if (typeof document === 'undefined') return fallback;
    const value = (id: string, fallbackValue: string) => {
        const element = document.getElementById(id);
        if (
            element instanceof HTMLInputElement
            || element instanceof HTMLTextAreaElement
            || element instanceof HTMLSelectElement
        ) {
            return element.value;
        }
        return fallbackValue;
    };

    return {
        title: value('legal-kb-editor-title', fallback.title),
        documentNumber: value('legal-kb-editor-number', fallback.documentNumber),
        documentType: normalizeDocumentType(value('legal-kb-editor-type', fallback.documentType || detail.document.document_type || 'UNKNOWN')) || 'UNKNOWN',
        documentRole: normalizeDocumentRole(value('legal-kb-editor-role', fallback.documentRole || documentRoleFromMetadata(detail.document.metadata_json) || 'primary')) || 'primary',
        issuingAuthority: value('legal-kb-editor-issuer', fallback.issuingAuthority),
        issuedDate: value('legal-kb-editor-issued-date', fallback.issuedDate),
        effectiveDate: value('legal-kb-editor-effective-date', fallback.effectiveDate),
        expiryDate: value('legal-kb-editor-expiry-date', fallback.expiryDate),
        sourceUrl: value('legal-kb-editor-source-url', fallback.sourceUrl),
        sourceDownloadedAt: value('legal-kb-editor-source-downloaded-at', fallback.sourceDownloadedAt),
        sourceFileName: value('legal-kb-editor-source-file-name', fallback.sourceFileName),
        summary: value('legal-kb-editor-summary', fallback.summary),
    };
}

function normalizeOptionalText(value: string) {
    return value.trim();
}

function normalizeOptionalDate(value: string) {
    return value.trim();
}

function AutoResizeTextarea({
    className = '',
    maxRows = 8,
    minRows = 2,
    onChange,
    value,
    ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { maxRows?: number; minRows?: number }) {
    const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

    React.useLayoutEffect(() => {
        const element = textareaRef.current;
        if (!element) return;

        const lineHeight = Number.parseFloat(window.getComputedStyle(element).lineHeight || '22');
        const verticalPadding = element.offsetHeight - element.clientHeight;
        const maxHeight = Math.max(lineHeight * maxRows + verticalPadding, lineHeight * minRows + verticalPadding);
        element.style.height = 'auto';
        element.style.height = `${Math.min(element.scrollHeight, maxHeight)}px`;
        element.style.overflowY = element.scrollHeight > maxHeight ? 'auto' : 'hidden';
    }, [maxRows, minRows, value]);

    return (
        <textarea
            {...props}
            ref={textareaRef}
            className={`auto-resize-textarea ${className}`.trim()}
            onChange={onChange}
            rows={minRows}
            value={value}
        />
    );
}

function SelectControl({
    children,
    className = '',
    ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
    return (
        <div className="review-select-shell">
            <select {...props} className={`review-select-control ${className}`.trim()}>
                {children}
            </select>
            <CaretDown aria-hidden="true" className="review-select-icon" size={16} weight="bold" />
        </div>
    );
}

function RelationTargetCombobox({
    id,
    onChange,
    onSearch,
    options,
    value,
}: {
    id: string;
    onChange: (value: string) => void;
    onSearch: (query: string) => void;
    options: RelationTargetOption[];
    value: string;
}) {
    const [open, setOpen] = React.useState(false);
    const selectedOption = options.find((option) => option.value === value);
    const [query, setQuery] = React.useState('');
    const normalizedValue = query.trim().toLowerCase();
    const filteredOptions = options
        .filter((option) => !normalizedValue || option.searchText.includes(normalizedValue));
    const listboxId = `${id}-options`;

    React.useEffect(() => {
        if (!open) setQuery(selectedOption?.label ?? '');
    }, [open, selectedOption?.label]);

    React.useEffect(() => {
        if (!open) return;
        const timer = window.setTimeout(() => onSearch(query.trim()), 250);
        return () => window.clearTimeout(timer);
    }, [onSearch, open, query]);

    return (
        <div className="relation-target-combobox">
            <input
                id={id}
                aria-autocomplete="list"
                aria-controls={listboxId}
                aria-expanded={open && filteredOptions.length > 0}
                autoComplete="off"
                role="combobox"
                value={query}
                onBlur={() => window.setTimeout(() => {
                    setOpen(false);
                    setQuery(selectedOption?.label ?? '');
                }, 120)}
                onChange={(event) => {
                    setQuery(event.target.value);
                    if (value) onChange('');
                    setOpen(true);
                }}
                onFocus={() => {
                    setQuery('');
                    setOpen(true);
                }}
            />
            {open && filteredOptions.length > 0 ? (
                <div className="relation-target-options" id={listboxId} role="listbox">
                    {filteredOptions.map((option) => (
                        <button
                            key={option.value}
                            aria-selected={option.value === value}
                            role="option"
                            type="button"
                            onMouseDown={(event) => {
                                event.preventDefault();
                                onChange(option.value);
                                setQuery(option.label);
                                setOpen(false);
                            }}
                        >
                            <span>{option.label}</span>
                        </button>
                    ))}
                </div>
            ) : null}
        </div>
    );
}

function parserWarnings(detail: LegalKbRevisionDetailResponse | null) {
    if (!detail) return [];
    const createdEvent = detail.review_events.find((event) => event.decision === 'created');
    const warnings = createdEvent?.details?.parser_warnings;
    return Array.isArray(warnings)
        ? Array.from(new Set(warnings.map((warning) => localizeReviewWarning(String(warning)))))
        : [];
}

function localizeReviewWarning(value: string) {
    const normalized = value.trim();
    const lower = normalized.toLowerCase();
    if (!normalized) return 'Hồ sơ có cảnh báo cần kiểm tra lại.';
    if (lower.includes('revision parsing is incomplete') || lower.includes('parsing is incomplete') || lower.includes('parse_failed')) {
        return 'Quá trình tách nội dung chưa hoàn tất hoặc bị lỗi. Vui lòng kiểm tra lại file nguồn trước khi đưa vào kho.';
    }
    if (lower.includes('summary proposal is missing') || lower.includes('summary') && lower.includes('missing')) {
        return 'Hồ sơ chưa có tóm tắt được xác nhận.';
    }
    if (lower.includes('metadata') && (lower.includes('pending') || lower.includes('proposal'))) {
        return 'Thông tin văn bản còn đề xuất cần xác nhận.';
    }
    if (lower.includes('relation') && (lower.includes('pending') || lower.includes('missing'))) {
        return 'Quan hệ văn bản còn thiếu hoặc chưa được xác nhận.';
    }
    if (lower.includes('risky') || lower.includes('needs_review') || lower.includes('review')) {
        return 'Có mục nội dung cần kiểm tra thủ công trước khi đưa vào kho.';
    }
    if (/^[\x00-\x7F]+$/.test(normalized)) {
        return 'Hồ sơ có cảnh báo kỹ thuật từ bộ tách nội dung. Vui lòng rà soát lại trước khi đưa vào kho.';
    }
    return normalized;
}

function reviewWarningMessages(detail: LegalKbRevisionDetailResponse | null) {
    if (!detail) return [];
    return Array.from(new Set([
        ...detail.publish_blockers.map((warning) => localizeReviewWarning(warning)),
        ...parserWarnings(detail),
    ]));
}

function needsUsageDecision(item: LegalKbNodeOut) {
    if (Boolean(item.structured_content?.review_only)) return false;
    return ['appendix', 'form', 'image_caption', 'table'].includes(item.node_type)
        && !Object.prototype.hasOwnProperty.call(item.structured_content || {}, 'answerable');
}

function isRiskyContent(item: LegalKbNodeOut) {
    return ['appendix', 'form', 'image_caption', 'table'].includes(item.node_type);
}

function needsManualContentReview(item: LegalKbNodeOut) {
    return isRiskyContent(item) && (item.review_status === 'needs_review' || needsUsageDecision(item));
}

function isReferenceOnly(item: LegalKbNodeOut) {
    return Boolean(item.structured_content?.review_only) || item.structured_content?.answerable === false;
}

function isAdminResolvedRiskyItem(item: LegalKbNodeOut) {
    return item.structured_content?.review_decision_source === 'admin'
        || item.structured_content?.review_only_role === 'admin_review_only'
        || typeof item.structured_content?.review_note === 'string';
}

function metadataNeedsReview(item: LegalKbMetadataProposalOut) {
    return item.review_status !== 'approved';
}

function relationNeedsReview(item: LegalKbRelationOut) {
    return item.review_status !== 'approved';
}

function initialRelationDrafts(relations: LegalKbRelationOut[]) {
    return Object.fromEntries(relations.map((relation) => [
        relation.relation_id,
        {
            targetDocumentId: relation.target_document_id,
            relationType: relation.relation_type as RelationType,
            sourceLocator: relation.source_locator ?? '',
            targetLocator: relation.target_locator ?? '',
            note: String(relation.metadata_json?.review_note || relation.metadata_json?.note || ''),
        },
    ]));
}

function initialMetadataDrafts(proposals: LegalKbMetadataProposalOut[]) {
    return Object.fromEntries(proposals.map((proposal) => [proposal.proposal_id, proposal.proposed_value]));
}

function initialContentNotes(items: LegalKbNodeOut[]) {
    return Object.fromEntries(items.map((item) => [item.node_id, String(item.structured_content?.review_note || '')]));
}

function queueTitle(item: LegalKbRevisionListItem) {
    return item.title || item.document_number || item.document_id;
}

function reviewSummaryStatusLabel(value: string | null | undefined) {
    if (!value || value === 'missing') return 'Thi\u1ebfu t\u00f3m t\u1eaft';
    return formatReviewStatus(value);
}

function revisionPendingCount(item: LegalKbRevisionListItem) {
    const summaryPending = item.summary_status && item.summary_status !== 'approved' ? 1 : 0;
    return item.pending_metadata_count + item.pending_relations_count + item.pending_risky_nodes_count + summaryPending;
}

function revisionPendingLabel(item: LegalKbRevisionListItem) {
    const total = revisionPendingCount(item);
    if (total === 0) return 'S\u1eb5n s\u00e0ng';
    return `C\u00f2n ${total} vi\u1ec7c`;
}

function revisionTimestampMeta(item: LegalKbRevisionListItem) {
    if (item.updated_at) {
        return `C\u1eadp nh\u1eadt g\u1ea7n nh\u1ea5t ${formatDateTime(item.updated_at)}`;
    }
    return `T\u1ea1o h\u1ed3 s\u01a1: ${formatDateTime(item.uploaded_at)}`;
}

function reviewEventLabel(value: string) {
    return {
        created: 'Tạo hồ sơ',
        metadata_reviewed: 'Duyệt thông tin',
        summary_reviewed: 'Duyệt tóm tắt',
        relation_reviewed: 'Duyệt quan hệ',
        relation_created: 'Tạo quan hệ',
        node_reviewed: 'Duyệt nội dung',
        deleted: 'Loại bỏ quan hệ',
        published: 'Đưa vào kho',
        suspended: 'Tạm ngừng',
        unsuspended: 'Khôi phục',
    }[value] ?? value;
}

function reviewEventDisplayLabel(value: string) {
    return {
        approved: 'Đã duyệt',
        created: 'Tạo hồ sơ',
        deleted: 'Loại bỏ quan hệ',
        metadata_reviewed: 'Duyệt thông tin',
        node_reviewed: 'Duyệt nội dung',
        published: 'Đưa vào kho',
        rejected: 'Từ chối',
        relation_created: 'Tạo quan hệ',
        relation_reviewed: 'Duyệt quan hệ',
        summary_reviewed: 'Duyệt tóm tắt',
        suspended: 'Tạm ngừng',
        updated: 'Cập nhật',
        unsuspended: 'Khôi phục',
    }[value] ?? reviewEventLabel(value);
}

function reviewEventActorLabel(actorUserId: string | null | undefined) {
    return actorUserId ? 'Quản trị viên' : 'Hệ thống';
}

function reviewEventNote(details: Record<string, unknown> | null | undefined) {
    const note = details?.note ?? details?.review_note;
    return typeof note === 'string' && note.trim()
        ? note.trim()
        : 'Không có ghi chú bổ sung cho lần xử lý này.';
}

function sourceDownloadPath(detail: LegalKbRevisionDetailResponse) {
    return `/api/v1/admin/legal-kb/revisions/${detail.revision.revision_id}/source`;
}

function sortReviewEventsByNewest(detail: LegalKbRevisionDetailResponse) {
    return [...detail.review_events].sort((left, right) => {
        const leftValue = Date.parse(left.created_at || '');
        const rightValue = Date.parse(right.created_at || '');
        return rightValue - leftValue;
    });
}

export default function LegalKbAdminWorkspace() {
    const [loading, setLoading] = React.useState(false);
    const [slowLoading, setSlowLoading] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);
    const [listResponse, setListResponse] = React.useState<LegalKbRevisionListResponse | null>(null);
    const [page, setPage] = React.useState(1);
    const [query, setQuery] = React.useState('');
    const [statusFilter, setStatusFilter] = React.useState<string>('draft');
    const [selectedRevisionId, setSelectedRevisionId] = React.useState<string | null>(null);
    const [expandedRevisionId, setExpandedRevisionId] = React.useState<string | null>(null);
    const [editorRevisionId, setEditorRevisionId] = React.useState<string | null>(null);
    const [detail, setDetail] = React.useState<LegalKbRevisionDetailResponse | null>(null);
    const [detailLoading, setDetailLoading] = React.useState(false);
    const [actionError, setActionError] = React.useState<string | null>(null);
    const [uploadDraft, setUploadDraft] = React.useState<UploadDraft>(EMPTY_UPLOAD_DRAFT);
    const [uploading, setUploading] = React.useState(false);
    const [uploadPhase, setUploadPhase] = React.useState<UploadPhase>('idle');
    const [uploadMessage, setUploadMessage] = React.useState<string | null>(null);
    const [uploadOpen, setUploadOpen] = React.useState(false);
    const [downloadDetail, setDownloadDetail] = React.useState<LegalKbRevisionDetailResponse | null>(null);
    const [documentDraft, setDocumentDraft] = React.useState<DocumentFormDraft | null>(null);
    const [metadataDrafts, setMetadataDrafts] = React.useState<Record<string, string>>({});
    const [relationDrafts, setRelationDrafts] = React.useState<Record<string, RelationDraft>>({});
    const [newRelationDraft, setNewRelationDraft] = React.useState<RelationDraft>(emptyRelationDraft());
    const [contentNotes, setContentNotes] = React.useState<Record<string, string>>({});
    const [busyKey, setBusyKey] = React.useState<string | null>(null);
    const [editorMessage, setEditorMessage] = React.useState<string | null>(null);
    const [publishPhase, setPublishPhase] = React.useState<PublishPhase>('idle');
    const [reviewHistoryPage, setReviewHistoryPage] = React.useState(1);
    const [statusCounts, setStatusCounts] = React.useState<Record<string, number>>({});
    const [relationTargetDocuments, setRelationTargetDocuments] = React.useState<LegalKbRelationTargetItem[]>([]);
    const [pendingConfirmation, setPendingConfirmation] = React.useState<WorkspaceConfirmation | null>(null);
    const metadataSectionRef = React.useRef<HTMLDetailsElement | null>(null);
    const relationSectionRef = React.useRef<HTMLDetailsElement | null>(null);
    const riskyContentSectionRef = React.useRef<HTMLDetailsElement | null>(null);

    const items = listResponse?.items ?? [];
    const currentDocumentId = detail?.document.document_id;
    const relatedDocumentOptions = Array.from(
        new Map(
            [...relationTargetDocuments, ...items]
                .filter((item) => item.document_id !== detail?.document.document_id)
                .map((item) => [item.document_id, {
                    value: item.document_id,
                    label: [item.document_number, item.title].filter(Boolean).join(' - ') || item.document_id,
                    searchText: [item.document_id, item.document_number, item.title].filter(Boolean).join(' ').toLowerCase(),
                }]),
        ).values(),
    );

    const searchRelationTargets = React.useCallback(async (searchQuery: string) => {
        try {
            const response = await fetchLegalKbRelationTargets({
                q: searchQuery || undefined,
                exclude_document_id: currentDocumentId,
                limit: 100,
            });
            setRelationTargetDocuments((current) => Array.from(
                new Map([...current, ...response.items].map((item) => [item.document_id, item])).values(),
            ));
        } catch {
            // Keep cached options available when a search request is interrupted.
        }
    }, [currentDocumentId]);

    const applyRevisionDetail = React.useCallback((response: LegalKbRevisionDetailResponse) => {
        setDetail(response);
        setListResponse((current) => {
            if (!current || !statusFilter || response.revision.publication_status === statusFilter) {
                return current;
            }
            const nextItems = current.items.filter((item) => item.revision_id !== response.revision.revision_id);
            return nextItems.length === current.items.length
                ? current
                : {
                    ...current,
                    items: nextItems,
                    total: Math.max(0, current.total - 1),
                };
        });
        setDocumentDraft(buildDocumentFormDraft(response));
        setMetadataDrafts(initialMetadataDrafts(response.metadata_proposals));
        setRelationDrafts(initialRelationDrafts(response.relations));
        setContentNotes(initialContentNotes(response.canonical_nodes));
        setNewRelationDraft(emptyRelationDraft());
        setReviewHistoryPage(1);
    }, [statusFilter]);

    const loadList = React.useCallback(async (
        nextPage = 1,
        publicationStatus = statusFilter,
        pinnedRevisionId: string | null = null,
        searchText = query,
    ) => {
        setLoading(true);
        setError(null);
        try {
            const normalizedStatus = publicationStatus || '';
            const normalizedQuery = searchText.trim();
            const [response, ...statusResponses] = await Promise.all([
                fetchLegalKbRevisionList({
                    page: nextPage,
                    page_size: PAGE_SIZE,
                    publication_status: normalizedStatus || undefined,
                    q: normalizedQuery || undefined,
                }),
                ...REVIEW_STATUS_OPTIONS.map((statusOption) => fetchLegalKbRevisionList({
                    page: 1,
                    page_size: 1,
                    publication_status: statusOption.value,
                    q: normalizedQuery || undefined,
                })),
            ]);
            const visibleItems = normalizedStatus
                ? response.items.filter((item) => item.publication_status === normalizedStatus)
                : response.items;
            setListResponse({
                ...response,
                items: visibleItems,
                total: visibleItems.length === response.items.length ? response.total : visibleItems.length,
            });
            setStatusCounts(Object.fromEntries(
                REVIEW_STATUS_OPTIONS.map((statusOption, index) => [statusOption.value, statusResponses[index]?.total ?? 0]),
            ));
            setPage(response.page);
            setSelectedRevisionId((current) => {
                if (pinnedRevisionId) return pinnedRevisionId;
                return current && visibleItems.some((item) => item.revision_id === current)
                    ? current
                    : visibleItems[0]?.revision_id ?? null;
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Không thể tải danh sách hồ sơ xử lý.');
        } finally {
            setLoading(false);
        }
    }, [query, statusFilter]);

    const loadDetail = React.useCallback(async (revisionId: string) => {
        setDetailLoading(true);
        setActionError(null);
        setEditorMessage(null);
        try {
            const response = await fetchLegalKbRevisionDetail(revisionId);
            applyRevisionDetail(response);
            return response;
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể tải chi tiết hồ sơ.');
            return null;
        } finally {
            setDetailLoading(false);
        }
    }, [applyRevisionDetail]);

    const openTransferredRevision = React.useCallback(async (revisionId: string) => {
        setQuery('');
        setPage(1);
        setSelectedRevisionId(revisionId);
        setExpandedRevisionId(revisionId);
        setEditorRevisionId(null);
        const loadedDetail = await loadDetail(revisionId);
        const targetStatus = loadedDetail?.revision.publication_status || 'draft';
        setStatusFilter(targetStatus);
        await loadList(1, targetStatus, revisionId, '');
        setSelectedRevisionId(revisionId);
        setExpandedRevisionId(revisionId);
        if (loadedDetail?.revision.revision_id === revisionId) {
            setEditorRevisionId(revisionId);
        }
    }, [loadDetail, loadList]);

    React.useEffect(() => {
        void loadList(1);
    }, [loadList]);

    React.useEffect(() => {
        function consumeTransferredRevision(revisionId: string) {
            try {
                sessionStorage.removeItem(HITL_REVIEW_REVISION_KEY);
            } catch {
                // Continue with the in-memory event when storage is unavailable.
            }
            void openTransferredRevision(revisionId);
        }

        function handleTransferredRevision(event: Event) {
            const revisionId = (event as CustomEvent<string>).detail;
            if (revisionId) consumeTransferredRevision(revisionId);
        }

        window.addEventListener('app:open-review-revision', handleTransferredRevision);
        try {
            const revisionId = sessionStorage.getItem(HITL_REVIEW_REVISION_KEY);
            if (revisionId) consumeTransferredRevision(revisionId);
        } catch {
            // Storage is optional; the custom event remains the primary handoff.
        }
        return () => window.removeEventListener('app:open-review-revision', handleTransferredRevision);
    }, [openTransferredRevision]);

    React.useEffect(() => {
        if (!loading) {
            setSlowLoading(false);
            return;
        }
        const timer = window.setTimeout(() => setSlowLoading(true), SLOW_LOADING_THRESHOLD_MS);
        return () => window.clearTimeout(timer);
    }, [loading]);

    React.useEffect(() => {
        setRelationTargetDocuments([]);
        void searchRelationTargets('');
    }, [searchRelationTargets]);

    React.useEffect(() => {
        if (!selectedRevisionId) return;
        void loadDetail(selectedRevisionId);
    }, [loadDetail, selectedRevisionId]);

    React.useEffect(() => {
        setActionError(null);
        setEditorMessage(null);
        setPublishPhase('idle');
    }, [editorRevisionId]);

    React.useEffect(() => {
        if (publishPhase !== 'done') return;
        const timer = window.setTimeout(() => {
            setPublishPhase((current) => (current === 'done' ? 'idle' : current));
        }, 1800);
        return () => window.clearTimeout(timer);
    }, [publishPhase]);

    React.useEffect(() => {
        if (!uploading) {
            setUploadPhase('idle');
            return;
        }
        setUploadPhase('uploading');
        const phases: UploadPhase[] = ['uploading', 'parsing', 'proposals'];
        let index = 0;
        const timer = window.setInterval(() => {
            index = Math.min(index + 1, phases.length - 1);
            setUploadPhase(phases[index]);
        }, 950);
        return () => window.clearInterval(timer);
    }, [uploading]);

    function handlePresetChange(presetKey: string) {
        const preset = DOCUMENT_CORPUS_PRESETS.find((item) => item.document_number === presetKey);
        if (!preset) {
            setUploadDraft((current) => ({ ...current, presetKey }));
            return;
        }
        setUploadDraft((current) => ({
            ...current,
            presetKey,
            title: preset.document_title,
            sourceUrl: preset.source_url,
            sourceDownloadedAt: preset.downloaded_at.slice(0, 10),
            sourceNote: preset.notes,
            documentNumber: preset.document_number,
            documentType: normalizeDocumentType(preset.document_type) || 'UNKNOWN',
            documentRole: normalizeDocumentRole(preset.role) || 'primary',
            issuingAuthority: preset.issuing_authority,
        }));
    }

    async function handleUpload(event: React.FormEvent) {
        event.preventDefault();
        if (!uploadDraft.file) {
            setUploadMessage('Cần chọn một file DOCX trước khi tạo hồ sơ.');
            return;
        }
        setUploading(true);
        setUploadMessage(null);
        try {
            const response = await uploadLegalKbRevision({
                file: uploadDraft.file,
                title: uploadDraft.title,
                source_url: uploadDraft.sourceUrl,
                source_downloaded_at: uploadDraft.sourceDownloadedAt,
                source_note: uploadDraft.sourceNote,
                document_number: uploadDraft.documentNumber || undefined,
                document_type: normalizeDocumentType(uploadDraft.documentType) || undefined,
                document_role: normalizeDocumentRole(uploadDraft.documentRole) || undefined,
                issuing_authority: uploadDraft.issuingAuthority || undefined,
                issued_date: uploadDraft.issuedDate || undefined,
                effective_date: uploadDraft.effectiveDate || undefined,
                expiry_date: uploadDraft.expiryDate || undefined,
            });
            setUploadPhase('opening');
            const revisionId = response.revision.revision_id;
            setUploadDraft(EMPTY_UPLOAD_DRAFT);
            setUploadMessage(null);
            setUploadOpen(false);
            await openTransferredRevision(revisionId);
        } catch (err) {
            if (err instanceof LegalKbDuplicateSourceError && err.revisionId) {
                const revisionId = err.revisionId;
                setUploadMessage(null);
                setUploadPhase('opening');
                setUploadOpen(false);
                await openTransferredRevision(revisionId);
                return;
            }
            setUploadMessage(err instanceof Error ? err.message : 'Không thể tạo hồ sơ mới.');
        } finally {
            setUploading(false);
        }
    }

    async function refreshSelected() {
        if (!selectedRevisionId) {
            await loadList(page);
            return;
        }
        await loadList(page);
        await loadDetail(selectedRevisionId);
    }

    async function handlePutIntoRepository(confirmed = false) {
        if (!selectedRevisionId || !detail) return;

        if (!readyToPublish) {
            const targetSection = pendingMetadataCount > 0 || summaryPending
                ? metadataSectionRef.current
                : pendingRelationCount > 0
                    ? relationSectionRef.current
                    : pendingRiskyCount > 0
                        ? riskyContentSectionRef.current
                        : null;

            if (targetSection) {
                targetSection.open = true;
                window.requestAnimationFrame(() => {
                    targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
            }
            setActionError('Hồ sơ còn nội dung cần xử lý nên chưa thể đưa vào kho. Hệ thống đã mở phần cần hoàn thiện trước.');
            return;
        }

        if (!confirmed) {
            setPendingConfirmation({ kind: 'publish' });
            return;
        }

        setBusyKey('publish');
        setPublishPhase('validating');
        setActionError(null);
        try {
            setPublishPhase('publishing');
            const response = await publishLegalKbRevision(selectedRevisionId);
            applyRevisionDetail(response);
            setPublishPhase('refreshing');
            setStatusFilter('published');
            await loadList(1, 'published');
            setSelectedRevisionId(selectedRevisionId);
            setExpandedRevisionId(selectedRevisionId);
            const refreshed = await fetchLegalKbRevisionDetail(selectedRevisionId);
            applyRevisionDetail(refreshed);
            setPublishPhase('done');
        } catch (err) {
            setPublishPhase('failed');
            setActionError(err instanceof Error ? err.message : 'Không thể đưa hồ sơ vào kho.');
            await loadDetail(selectedRevisionId);
        } finally {
            setBusyKey(null);
        }
    }

    async function handleDocumentSave(confirmed = false) {
        if (!detail || !documentDraft) return;
        const currentDraft = documentFormDraftFromDom(documentDraft, detail);

        const nextValues: Record<EditableMetadataField, string> = {
            title: normalizeOptionalText(currentDraft.title),
            document_number: normalizeOptionalText(currentDraft.documentNumber),
            document_type: normalizeOptionalText(normalizeDocumentType(currentDraft.documentType)),
            document_role: normalizeOptionalText(normalizeDocumentRole(currentDraft.documentRole)),
            issuing_authority: normalizeOptionalText(currentDraft.issuingAuthority),
            issued_date: normalizeOptionalDate(currentDraft.issuedDate),
            effective_date: normalizeOptionalDate(currentDraft.effectiveDate),
            expiry_date: normalizeOptionalDate(currentDraft.expiryDate),
        };

        const currentValues: Record<EditableMetadataField, string> = {
            title: detail.document.title ?? '',
            document_number: detail.document.document_number ?? '',
            document_type: normalizeDocumentType(detail.document.document_type),
            document_role: normalizeDocumentRole(documentRoleFromMetadata(detail.document.metadata_json)),
            issuing_authority: detail.document.issuing_authority ?? '',
            issued_date: detail.document.issued_date ?? '',
            effective_date: detail.document.effective_date ?? '',
            expiry_date: detail.document.expiry_date ?? '',
        };

        const nextSourceValues: Record<EditableSourceField, string> = {
            source_url: normalizeOptionalText(currentDraft.sourceUrl),
            source_downloaded_at: normalizeOptionalDate(currentDraft.sourceDownloadedAt),
            source_file_name: normalizeOptionalText(currentDraft.sourceFileName),
        };

        const currentSourceValues: Record<EditableSourceField, string> = {
            source_url: detail.revision.source_url ?? '',
            source_downloaded_at: detail.revision.source_downloaded_at ?? '',
            source_file_name: detail.source_asset?.original_filename ?? '',
        };

        const changedEntries = (Object.keys(nextValues) as EditableMetadataField[]).filter(
            (field) => nextValues[field] !== currentValues[field],
        );
        const changedSourceEntries = (Object.keys(nextSourceValues) as EditableSourceField[]).filter(
            (field) => nextSourceValues[field] !== currentSourceValues[field],
        );
        const summaryChanged = detail.summary
            ? normalizeOptionalText(currentDraft.summary) !== (detail.summary.content ?? '')
            : false;

        if (changedEntries.length === 0 && changedSourceEntries.length === 0 && !summaryChanged) {
            setEditorMessage('Chưa có thay đổi nào trong thông tin văn bản để lưu.');
            setActionError(null);
            return;
        }

        if (!confirmed) {
            setPendingConfirmation({ kind: 'document-save' });
            return;
        }

        setBusyKey('document-save');
        setActionError(null);
        setEditorMessage(null);

        try {
            let successMessage = '';
            if (detail.revision.publication_status !== 'draft') {
                const payload = Object.fromEntries([
                    ...changedEntries.map((field) => [field, nextValues[field] || null] as const),
                    ...changedSourceEntries.map((field) => [field, nextSourceValues[field] || null] as const),
                ]);
                const response = await updateLegalKbPublishedDocument(detail.document.document_id, payload);
                setDetail(response);
                setDocumentDraft(buildDocumentFormDraft(response));
                setMetadataDrafts(initialMetadataDrafts(response.metadata_proposals));
                successMessage = 'Đã cập nhật trực tiếp thông tin của văn bản đang quản lý trong Kho văn bản.';
            } else {
                for (const field of changedEntries) {
                    const existingProposal = detail.metadata_proposals.find(
                        (proposal) => proposal.field_name === field && proposal.review_status !== 'approved',
                    );
                    const proposal = existingProposal
                        ? existingProposal
                        : await createLegalKbMetadataProposal(detail.revision.revision_id, {
                            field_name: field,
                            proposed_value: nextValues[field],
                        });
                    await reviewLegalKbMetadataProposal(proposal.proposal_id, 'approved', undefined, nextValues[field]);
                }
                if (changedSourceEntries.length > 0) {
                    await updateLegalKbRevisionSource(detail.revision.revision_id, Object.fromEntries(
                        changedSourceEntries.map((field) => [field, nextSourceValues[field] || null]),
                    ));
                }
                successMessage = 'Đã lưu thông tin và duyệt ngay các trường vừa chỉnh cho hồ sơ chưa công bố.';
            }

            if (summaryChanged && detail.summary) {
                await reviewLegalKbSummary(detail.summary.summary_id, {
                    decision: 'approved',
                    content: currentDraft.summary,
                });
                successMessage = `${successMessage} ÄÃ£ cáº­p nháº­t tÃ³m táº¯t.`;
            }

            if (successMessage.includes('Ã')) {
                successMessage = summaryChanged
                    ? 'Đã lưu thông tin văn bản. Đã cập nhật tóm tắt.'
                    : 'Đã lưu thông tin văn bản.';
            }

            await refreshSelected();
            setEditorMessage(successMessage);
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể lưu thông tin văn bản.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleMetadataReview(proposalId: string, decision: 'approved' | 'rejected') {
        setBusyKey(`metadata:${proposalId}:${decision}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await reviewLegalKbMetadataProposal(
                proposalId,
                decision,
                undefined,
                metadataDrafts[proposalId] ?? '',
            );
            await refreshSelected();
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể lưu quyết định cho thông tin văn bản.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleRelationReview(relationId: string, decision: 'approved' | 'rejected') {
        setBusyKey(`relation:${relationId}:${decision}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await reviewLegalKbRelation(relationId, decision, relationDrafts[relationId]?.note);
            await refreshSelected();
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể lưu quyết định cho quan hệ văn bản.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleRelationUpdate(relationId: string, confirmed = false) {
        const draft = relationDrafts[relationId];
        if (!draft) return;
        if (!confirmed) {
            setPendingConfirmation({ kind: 'relation-update', relationId });
            return;
        }
        setBusyKey(`relation-save:${relationId}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await updateLegalKbRelation(relationId, {
                target_document_id: draft.targetDocumentId,
                relation_type: draft.relationType,
                source_locator: draft.sourceLocator || undefined,
                target_locator: draft.targetLocator || undefined,
                note: draft.note || undefined,
            });
            await refreshSelected();
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể cập nhật quan hệ văn bản.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleRelationReset(relation: LegalKbRelationOut, confirmed = false) {
        if (!confirmed) {
            setPendingConfirmation({ kind: 'relation-reset', relation });
            return;
        }
        const draft = relationDrafts[relation.relation_id] ?? emptyRelationDraft();
        setBusyKey(`relation-reset:${relation.relation_id}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await updateLegalKbRelation(relation.relation_id, {
                target_document_id: draft.targetDocumentId || relation.target_document_id,
                relation_type: draft.relationType || relation.relation_type as RelationType,
                source_locator: draft.sourceLocator || relation.source_locator || undefined,
                target_locator: draft.targetLocator || relation.target_locator || undefined,
                note: draft.note || String(relation.metadata_json?.note || '') || undefined,
            });
            await refreshSelected();
            setEditorMessage('Đã đưa quan hệ về nhóm cần xử lý.');
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể mở lại quan hệ để chỉnh sửa.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleRelationDelete(relation: LegalKbRelationOut, confirmed = false) {
        if (!confirmed) {
            setPendingConfirmation({ kind: 'relation-delete', relation });
            return;
        }
        setBusyKey(`relation-delete:${relation.relation_id}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await deleteLegalKbRelation(relation.relation_id);
            await refreshSelected();
            setEditorMessage('Đã loại bỏ quan hệ văn bản.');
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể loại bỏ quan hệ văn bản.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleCreateRelation() {
        if (!detail || !newRelationDraft.targetDocumentId) return;
        setBusyKey('relation-create');
        setActionError(null);
        setEditorMessage(null);
        try {
            await createLegalKbRelationProposal(detail.revision.revision_id, {
                target_document_id: newRelationDraft.targetDocumentId,
                relation_type: newRelationDraft.relationType,
                source_locator: newRelationDraft.sourceLocator || undefined,
                target_locator: newRelationDraft.targetLocator || undefined,
                note: newRelationDraft.note || undefined,
            });
            await refreshSelected();
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể tạo quan hệ văn bản.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleContentReview(item: LegalKbNodeOut, decision: 'approved' | 'rejected', usableForAnswers?: boolean) {
        setBusyKey(`content:${item.node_id}:${decision}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await reviewLegalKbNode(item.node_id, decision, contentNotes[item.node_id], usableForAnswers);
            await refreshSelected();
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể lưu quyết định cho mục nội dung.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleResetContentReview(item: LegalKbNodeOut, confirmed = false) {
        if (!confirmed) {
            setPendingConfirmation({ kind: 'content-reset', item });
            return;
        }
        setBusyKey(`content-reset:${item.node_id}`);
        setActionError(null);
        setEditorMessage(null);
        try {
            await resetLegalKbNodeReview(item.node_id, contentNotes[item.node_id]);
            await refreshSelected();
            setEditorMessage('Đã đưa mục nội dung về nhóm cần xử lý để chọn lại quyết định.');
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Không thể đưa mục nội dung về trạng thái cần kiểm tra.');
        } finally {
            setBusyKey(null);
        }
    }

    async function handleOpenEditor(revisionId: string) {
        if (editorRevisionId !== revisionId) setPublishPhase('idle');
        setSelectedRevisionId(revisionId);
        setExpandedRevisionId(revisionId);
        if (detail?.revision.revision_id === revisionId) {
            setEditorRevisionId(revisionId);
            return;
        }
        setEditorRevisionId(null);
        const loadedDetail = await loadDetail(revisionId);
        if (loadedDetail?.revision.revision_id === revisionId) {
            setEditorRevisionId(revisionId);
        }
    }

    async function handleToggleRevision(revisionId: string) {
        const nextExpanded = expandedRevisionId === revisionId ? null : revisionId;
        setExpandedRevisionId(nextExpanded);
        if (!nextExpanded) return;
        if (selectedRevisionId !== revisionId) setPublishPhase('idle');
        setSelectedRevisionId(revisionId);
        if (detail?.revision.revision_id !== revisionId) {
            await loadDetail(revisionId);
        }
    }

    function handleStatusFilterChange(status: string) {
        if (status === statusFilter) return;
        setStatusFilter(status);
        setPage(1);
        setSelectedRevisionId(null);
        setExpandedRevisionId(null);
        setEditorRevisionId(null);
        setDetail(null);
        setActionError(null);
        setEditorMessage(null);
        setPublishPhase('idle');
    }

    const detailItems = detail?.canonical_nodes ?? [];
    const riskyItems = detailItems.filter((item) => isRiskyContent(item));
    const pendingRiskyItems = detail?.pending_risky_nodes ?? riskyItems.filter((item) => needsManualContentReview(item));
    const visibleRiskyItems = pendingRiskyItems.slice(0, 12);
    const resolvedRiskyItems = (detail?.resolved_risky_nodes ?? riskyItems.filter((item) => !pendingRiskyItems.some((pending) => pending.node_id === item.node_id)))
        .filter((item) => isAdminResolvedRiskyItem(item));
    const visibleResolvedRiskyItems = resolvedRiskyItems.slice(0, 8);
    const resolvedRiskyCount = resolvedRiskyItems.length;
    const pendingCount = detail?.publish_blockers.length ?? 0;
    const readyToPublish = detail?.is_ready_to_publish ?? pendingCount === 0;
    const alreadyInRepository = detail?.revision.publication_status !== 'draft';
    const warningMessages = reviewWarningMessages(detail);
    const pendingMetadataProposals = detail?.pending_metadata ?? detail?.metadata_proposals.filter((item) => metadataNeedsReview(item)) ?? [];
    const pendingRelations = detail?.pending_relations ?? detail?.relations.filter((item) => (
        item.source_document_id === detail.document.document_id && relationNeedsReview(item)
    )) ?? [];
    const confirmedRelations = detail?.relations.filter((item) => item.review_status === 'approved') ?? [];
    const pendingMetadataCount = pendingMetadataProposals.length;
    const pendingRelationCount = pendingRelations.length;
    const pendingRiskyCount = pendingRiskyItems.length;
    const summaryPending = detail?.summary && detail.summary.review_status !== 'approved';
    const reviewEvents = detail ? sortReviewEventsByNewest(detail) : [];
    const reviewHistoryTotalPages = Math.max(1, Math.ceil(reviewEvents.length / REVIEW_HISTORY_PAGE_SIZE));
    const boundedReviewHistoryPage = Math.min(reviewHistoryPage, reviewHistoryTotalPages);
    const reviewHistoryStart = (boundedReviewHistoryPage - 1) * REVIEW_HISTORY_PAGE_SIZE;
    const visibleReviewEvents = reviewEvents.slice(reviewHistoryStart, reviewHistoryStart + REVIEW_HISTORY_PAGE_SIZE);
    const activeUploadPhaseIndex = UPLOAD_PHASES.findIndex((phase) => phase.value === uploadPhase);
    const uploadRoleLabel = formatDocumentRole(uploadDraft.documentRole);
    const uploadRoleNeedsRelation = RELATION_REQUIRED_ROLES.has(uploadDraft.documentRole);
    const detailPendingTotal = pendingMetadataCount + pendingRelationCount + pendingRiskyCount + (summaryPending ? 1 : 0);
    const displayedReviewStatus = detail && detail.revision.publication_status !== 'draft' && detailPendingTotal === 0
        ? 'Đã kiểm tra'
        : formatReviewStatus(detail?.revision.review_status ?? '');
    const displayedReviewTone = detail && detail.revision.publication_status !== 'draft' && detailPendingTotal === 0
        ? 'active'
        : badgeTone(detail?.revision.review_status ?? '');
    const activePublishPhaseIndex = publishPhase === 'failed'
        ? PUBLISH_PHASES.length - 1
        : Math.max(0, PUBLISH_PHASES.findIndex((phase) => phase.value === publishPhase));
    const activePublishPhase = publishPhase === 'failed'
        ? { label: 'Không thể hoàn tất', description: 'Hệ thống chưa đưa được hồ sơ vào kho. Vui lòng xem thông báo lỗi và thử lại.' }
        : PUBLISH_PHASES[activePublishPhaseIndex] ?? PUBLISH_PHASES[0];
    const publishProgressPercent = `${((activePublishPhaseIndex + 1) / PUBLISH_PHASES.length) * 100}%`;

    function confirmationCopy() {
        if (!pendingConfirmation) return null;
        const documentTitle = detail?.document.title || 'hồ sơ này';

        if (pendingConfirmation.kind === 'document-save') {
            return {
                title: 'Lưu thông tin văn bản?',
                description: `Các thay đổi của "${documentTitle}" sẽ được lưu vào hồ sơ hiện tại.`,
                confirmLabel: 'Lưu thông tin',
                danger: false,
            };
        }
        if (pendingConfirmation.kind === 'publish') {
            return {
                title: 'Đưa văn bản vào kho?',
                description: `"${documentTitle}" đã đủ điều kiện và sẽ được dùng theo trạng thái công bố sau khi xác nhận.`,
                confirmLabel: 'Đưa vào kho',
                danger: false,
            };
        }
        if (pendingConfirmation.kind === 'relation-update') {
            return {
                title: 'Lưu chỉnh sửa quan hệ?',
                description: 'Văn bản liên quan, loại quan hệ và các vị trí đối chiếu sẽ được cập nhật.',
                confirmLabel: 'Lưu quan hệ',
                danger: false,
            };
        }
        if (pendingConfirmation.kind === 'relation-reset') {
            return {
                title: 'Đưa quan hệ về cần xử lý?',
                description: 'Quan hệ này sẽ rời nhóm đã xác nhận để bạn chỉnh sửa và duyệt lại.',
                confirmLabel: 'Đưa về xử lý',
                danger: false,
            };
        }
        if (pendingConfirmation.kind === 'relation-delete') {
            return {
                title: 'Loại bỏ quan hệ văn bản?',
                description: 'Quan hệ này sẽ bị loại bỏ và thao tác được ghi vào lịch sử xử lý.',
                confirmLabel: 'Loại bỏ',
                danger: true,
            };
        }
        return {
            title: 'Đưa mục này về cần xử lý?',
            description: 'Quyết định hiện tại sẽ được mở lại để bạn chọn lại cách sử dụng nội dung.',
            confirmLabel: 'Đưa về xử lý',
            danger: false,
        };
    }

    async function confirmPendingAction() {
        if (!pendingConfirmation) return;
        const action = pendingConfirmation;
        setPendingConfirmation(null);

        if (action.kind === 'document-save') {
            await handleDocumentSave(true);
        } else if (action.kind === 'publish') {
            await handlePutIntoRepository(true);
        } else if (action.kind === 'relation-update') {
            await handleRelationUpdate(action.relationId, true);
        } else if (action.kind === 'relation-reset') {
            await handleRelationReset(action.relation, true);
        } else if (action.kind === 'relation-delete') {
            await handleRelationDelete(action.relation, true);
        } else {
            await handleResetContentReview(action.item, true);
        }
    }

    const confirmDialog = confirmationCopy();

    const filteredItems = items.filter((item) => {
        const matchesStatus = !statusFilter || item.publication_status === statusFilter;
        const haystack = `${item.title || ''} ${item.document_number || ''} ${item.source_file_name || ''}`.toLowerCase();
        const matchesQuery = !query.trim() || haystack.includes(query.trim().toLowerCase());
        return matchesStatus && matchesQuery;
    });

    const totalPages = listResponse ? Math.max(1, Math.ceil(listResponse.total / listResponse.page_size)) : 1;
    const selectedMatchesDetail = detail && selectedRevisionId === detail.revision.revision_id;
    const editorMatchesDetail = detail && editorRevisionId === detail.revision.revision_id;

    return (
        <section className="review-library-shell">
            <section className="review-intro review-hitl-intro">
                <div className="review-intro-main">
                    <div className="review-intro-copy">
                    <p className="kb-kicker">Duyệt văn bản</p>
                    <h2>Duyệt hồ sơ trước khi đưa vào kho</h2>
                    <p className="kb-subtle">
                        Mở hồ sơ, rà những mục còn chờ xác nhận, rồi chỉnh sửa và đưa vào kho trong một luồng làm
                        việc gọn, rõ và liền mạch hơn trên cả desktop lẫn mobile.
                    </p>
                    </div>
                </div>
                <div className="review-intro-actions">
                    <button className="btn-secondary" type="button" onClick={() => setUploadOpen(true)}>
                        <FileArrowUp size={18} />
                        Thêm văn bản
                    </button>
                </div>
                <div className="review-stat-row" aria-label="Tổng quan trạng thái hồ sơ">
                    {REVIEW_STATUS_OPTIONS.map((item) => (
                        <button
                            key={item.value}
                            className={`${item.tone} ${statusFilter === item.value ? 'active' : ''}`}
                            type="button"
                            aria-pressed={statusFilter === item.value}
                            data-testid={`review-status-${item.value}`}
                            onClick={() => handleStatusFilterChange(item.value)}
                        >
                            <div>
                                <span>{item.label}</span>
                                <strong>{statusCounts[item.value] ?? 0}</strong>
                            </div>
                        </button>
                    ))}
                </div>
            </section>

            <section className="kb-toolbar">
                <label className="kb-search">
                    <MagnifyingGlass size={18} />
                    <input
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="Tìm theo tiêu đề, số hiệu hoặc tên file nguồn"
                    />
                </label>
                <button className="btn-secondary kb-filter-toggle" type="button" onClick={() => void loadList(page)} disabled={loading}>
                    <ArrowClockwise size={18} />
                    Làm mới
                </button>
            </section>

            {uploadMessage ? <p className="review-upload-message">{uploadMessage}</p> : null}

            <section className="kb-list-panel kb-list-panel-expanded review-list-panel">
                <div className="kb-list-header">
                    <div>
                        <h3>Danh sách hồ sơ duyệt</h3>
                        <p>Mở hồ sơ để xem nhanh tình trạng, hoặc bấm chỉnh sửa để xử lý đầy đủ trong hộp thoại.</p>
                    </div>
                    {loading ? <span className="kb-loading-copy" role="status">Đang tải danh sách...</span> : null}
                </div>

                {error ? <p className="kb-inline-error">{error}</p> : null}
                {slowLoading ? (
                    <p className="kb-loading-timeout" role="alert">
                        Việc tải danh sách đang lâu hơn dự kiến. Bạn có thể chờ thêm hoặc chọn Làm mới để thử lại.
                    </p>
                ) : null}

                {loading ? (
                    <div className="kb-record-list kb-list-skeleton" aria-label="Đang tải danh sách hồ sơ">
                        {[0, 1, 2].map((index) => (
                            <div className="kb-record kb-record-accordion skeleton-panel !mt-0 !h-28" key={index} />
                        ))}
                    </div>
                ) : filteredItems.length > 0 ? (
                    <>
                        <div className="kb-record-list">
                            {filteredItems.map((item) => {
                                const expanded = expandedRevisionId === item.revision_id;
                                const detailReady = expanded && selectedMatchesDetail && detail?.revision.revision_id === item.revision_id;
                                const pendingTotal = revisionPendingCount(item);
                                return (
                                    <article className={`kb-record kb-record-accordion ${expanded ? 'active' : ''}`} key={item.revision_id}>
                                        <div className="kb-record-header review-record-header">
                                            <button className="kb-record-toggle" type="button" onClick={() => void handleToggleRevision(item.revision_id)}>
                                                <div className="kb-record-main">
                                                    <div className="kb-record-topline review-record-topline">
                                                        <span className={`badge ${badgeTone(item.publication_status)}`}>{formatWorkspaceStatus(item.publication_status)}</span>
                                                        <span className="kb-mini-flag">{formatDocumentType(item.document_type)}</span>
                                                        {item.document_number ? <span className="kb-mini-flag">{item.document_number}</span> : null}
                                                        <span className={`kb-mini-flag review-record-pending ${pendingTotal === 0 ? 'is-ready' : ''}`}>{revisionPendingLabel(item)}</span>
                                                    </div>
                                                    <h4>{queueTitle(item)}</h4>
                                                    <div className="kb-record-meta review-record-meta-legacy-hidden">
                                                        <span>{item.issuing_authority || 'ChÆ°a cáº­p nháº­t cÆ¡ quan ban hÃ nh'}</span>
                                                        <span>{`Hiệu lực từ ${formatCompactDate(item.effective_date)}`}</span>
                                                    </div>
                                                    <div className="kb-record-meta review-record-meta-primary">
                                                        <span>{item.issuing_authority || 'Ch\u01b0a c\u1eadp nh\u1eadt c\u01a1 quan ban h\u00e0nh'}</span>
                                                        <span>{`Hi\u1ec7u l\u1ef1c t\u1eeb ${formatCompactDate(item.effective_date)}`}</span>
                                                    </div>
                                                    <div className="kb-record-meta review-record-meta-secondary">
                                                        <span>{item.source_file_name || 'Chưa có file nguồn'}</span>
                                                        <span>{revisionTimestampMeta(item)}</span>
                                                    </div>
                                                </div>
                                            </button>
                                            <div className="review-record-actions">
                                                <button
                                                    className="review-record-icon-button"
                                                    type="button"
                                                    aria-label="Chỉnh sửa hồ sơ"
                                                    onClick={() => void handleOpenEditor(item.revision_id)}
                                                >
                                                    <PencilSimple size={18} />
                                                </button>
                                                <button
                                                    className={`review-record-icon-button ${expanded ? 'is-open' : ''}`}
                                                    type="button"
                                                    aria-label={expanded ? 'Thu gọn hồ sơ' : 'Mở rộng hồ sơ'}
                                                    onClick={() => void handleToggleRevision(item.revision_id)}
                                                >
                                                    <CaretDown size={18} />
                                                </button>
                                            </div>
                                        </div>

                                        {expanded ? (
                                            <div className="kb-inline-detail">
                                                {detailLoading && !detailReady ? (
                                                    <div className="empty-state">
                                                        <strong>Đang tải chi tiết hồ sơ</strong>
                                                        <p>Hệ thống đang mở đầy đủ thông tin để bạn tiếp tục duyệt.</p>
                                                    </div>
                                                ) : null}

                                                {actionError && selectedRevisionId === item.revision_id ? <p className="kb-inline-error">{actionError}</p> : null}

                                                {detailReady && detail ? (
                                                    <>
                                                        {warningMessages.length > 0 && (
                                                            <section className="kb-warning-stack">
                                                                {warningMessages.map((warning) => (
                                                                    <article className="kb-warning-card" key={warning}>
                                                                        <WarningCircle size={18} />
                                                                        <span>{warning}</span>
                                                                    </article>
                                                                ))}
                                                            </section>
                                                        )}

                                                        <dl className="kb-meta-list kb-meta-list-compact review-card-facts">
                                                            <div><dt>Số hiệu</dt><dd>{detail.document.document_number || 'Chưa cập nhật'}</dd></div>
                                                            <div><dt>Loại văn bản</dt><dd>{formatDocumentType(detail.document.document_type)}</dd></div>
                                                            <div><dt>Vai trò</dt><dd>{formatDocumentRole(documentRoleFromMetadata(detail.document.metadata_json))}</dd></div>
                                                            <div><dt>Cơ quan ban hành</dt><dd>{detail.document.issuing_authority || 'Chưa cập nhật'}</dd></div>
                                                            <div><dt>Ngày tạo hồ sơ</dt><dd>{formatDateTime(detail.revision.uploaded_at)}</dd></div>
                                                            <div><dt>File nguồn</dt><dd>{detail.source_asset?.original_filename || 'Chưa có file nguồn'}</dd></div>
                                                            <div><dt>Hiệu lực từ</dt><dd>{formatDate(item.effective_date)}</dd></div>
                                                            <div><dt>Hết hiệu lực</dt><dd>{formatDate(item.expiry_date)}</dd></div>
                                                            <div><dt>Còn việc xử lý</dt><dd>{revisionPendingLabel(item)}</dd></div>
                                                            <div><dt>Tóm tắt</dt><dd>{reviewSummaryStatusLabel(item.summary_status)}</dd></div>
                                                        </dl>

                                                    </>
                                                ) : null}
                                            </div>
                                        ) : null}
                                    </article>
                                );
                            })}
                        </div>

                        <div className="pagination">
                            <button className="btn-secondary" type="button" disabled={page <= 1 || loading} onClick={() => void loadList(page - 1)}>
                                Trước
                            </button>
                            <span>Trang {page} / {totalPages}</span>
                            <button className="btn-secondary" type="button" disabled={page >= totalPages || loading} onClick={() => void loadList(page + 1)}>
                                Sau
                            </button>
                        </div>
                    </>
                ) : (
                    <div className="empty-state review-empty-state">
                        <strong>{statusFilter === 'draft' ? 'Không còn hồ sơ cần duyệt' : 'Chưa có hồ sơ phù hợp'}</strong>
                        <p>
                            {statusFilter === 'draft'
                                ? 'Các hồ sơ hiện tại đã được xử lý. Bạn có thể xem lại nhóm đã đưa vào kho hoặc thêm văn bản mới.'
                                : 'Hãy đổi từ khóa tìm kiếm hoặc chọn một trạng thái khác.'}
                        </p>
                        {statusFilter === 'draft' && statusCounts.published > 0 ? (
                            <button className="btn-secondary" type="button" onClick={() => handleStatusFilterChange('published')}>
                                Xem hồ sơ đã đưa vào kho
                            </button>
                        ) : null}
                    </div>
                )}
            </section>

            {uploadOpen ? (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => !uploading && setUploadOpen(false)}>
                    <section
                        className="admin-modal review-editor-dialog review-upload-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Thêm hồ sơ văn bản"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head review-editor-head">
                            <div className="review-editor-head-copy">
                                <p className="kb-kicker">Thêm văn bản</p>
                                <h3>Tạo hồ sơ duyệt mới</h3>
                            </div>
                            <button className="admin-modal-close" type="button" onClick={() => setUploadOpen(false)} disabled={uploading} aria-label="Đóng">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body review-upload-dialog-body">
                            <form className={`review-upload-grid review-upload-grid-modern ${uploading ? 'is-uploading' : ''}`} onSubmit={handleUpload}>
                                <label className="filter-group review-field-full" htmlFor="legal-kb-preset">
                                    <span>Mẫu điền nhanh</span>
                                    <SelectControl id="legal-kb-preset" value={uploadDraft.presetKey} onChange={(event) => handlePresetChange(event.target.value)}>
                                        <option value="">Tự nhập toàn bộ thông tin</option>
                                        {DOCUMENT_CORPUS_PRESETS.map((preset) => (
                                            <option key={preset.document_number} value={preset.document_number}>
                                                P{preset.priority} - {preset.document_number}
                                            </option>
                                        ))}
                                    </SelectControl>
                                </label>

                                <label className="review-file-drop review-field-full" htmlFor="legal-kb-file">
                                    <FileArrowUp size={22} />
                                    <span>{uploadDraft.file?.name || 'Chọn file DOCX để tạo hồ sơ'}</span>
                                    <small>File mới chỉ được dùng cho tra cứu và chatbot sau khi hồ sơ được duyệt và đưa vào kho.</small>
                                    <input
                                        id="legal-kb-file"
                                        type="file"
                                        accept=".docx"
                                        onChange={(event) => setUploadDraft((current) => ({ ...current, file: event.target.files?.[0] ?? null }))}
                                    />
                                </label>

                                <label className="filter-group review-field-span" htmlFor="legal-kb-title">
                                    <span>Tiêu đề văn bản</span>
                                    <input
                                        id="legal-kb-title"
                                        required
                                        value={uploadDraft.title}
                                        onChange={(event) => setUploadDraft((current) => ({ ...current, title: event.target.value }))}
                                    />
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-number">
                                    <span>Số hiệu</span>
                                    <input id="legal-kb-number" value={uploadDraft.documentNumber} onChange={(event) => setUploadDraft((current) => ({ ...current, documentNumber: event.target.value }))} />
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-type">
                                    <span>Loại văn bản</span>
                                    <SelectControl id="legal-kb-type" value={uploadDraft.documentType} onChange={(event) => setUploadDraft((current) => ({ ...current, documentType: event.target.value }))}>
                                        {DOCUMENT_TYPE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </SelectControl>
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-role">
                                    <span>Vai trò văn bản</span>
                                    <SelectControl id="legal-kb-role" value={uploadDraft.documentRole} onChange={(event) => setUploadDraft((current) => ({ ...current, documentRole: event.target.value }))}>
                                        {DOCUMENT_ROLE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </SelectControl>
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-issuer">
                                    <span>Cơ quan ban hành</span>
                                    <input id="legal-kb-issuer" value={uploadDraft.issuingAuthority} onChange={(event) => setUploadDraft((current) => ({ ...current, issuingAuthority: event.target.value }))} />
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-issued-date">
                                    <span>Ngày ban hành</span>
                                    <DateInput id="legal-kb-issued-date" value={uploadDraft.issuedDate} onChange={(value) => setUploadDraft((current) => ({ ...current, issuedDate: value }))} />
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-effective-date">
                                    <span>Ngày có hiệu lực</span>
                                    <DateInput id="legal-kb-effective-date" value={uploadDraft.effectiveDate} onChange={(value) => setUploadDraft((current) => ({ ...current, effectiveDate: value }))} />
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-expiry-date">
                                    <span>Ngày hết hiệu lực</span>
                                    <DateInput id="legal-kb-expiry-date" value={uploadDraft.expiryDate} onChange={(value) => setUploadDraft((current) => ({ ...current, expiryDate: value }))} />
                                </label>

                                <label className="filter-group review-field-span" htmlFor="legal-kb-source-url">
                                    <span>Đường dẫn nguồn</span>
                                    <input id="legal-kb-source-url" value={uploadDraft.sourceUrl} onChange={(event) => setUploadDraft((current) => ({ ...current, sourceUrl: event.target.value }))} required />
                                </label>

                                <label className="filter-group" htmlFor="legal-kb-downloaded-at">
                                    <span>Ngày lấy nguồn</span>
                                    <DateInput id="legal-kb-downloaded-at" value={uploadDraft.sourceDownloadedAt} onChange={(value) => setUploadDraft((current) => ({ ...current, sourceDownloadedAt: value }))} required />
                                </label>

                                <label className="filter-group review-field-span" htmlFor="legal-kb-note">
                                    <span>Ghi chú nguồn</span>
                                    <input id="legal-kb-note" value={uploadDraft.sourceNote} onChange={(event) => setUploadDraft((current) => ({ ...current, sourceNote: event.target.value }))} required />
                                </label>

                                <section className="review-upload-next review-field-full" aria-live="polite">
                                    <article>
                                        <strong>Tóm tắt</strong>
                                        <span>Hệ thống sẽ tạo bản tóm tắt sau khi tách nội dung; bạn chỉnh và duyệt trong hồ sơ vừa tạo.</span>
                                    </article>
                                    <article className={uploadRoleNeedsRelation ? 'is-warning' : ''}>
                                        <strong>Quan hệ văn bản</strong>
                                        <span>
                                            {uploadRoleNeedsRelation
                                                ? `${uploadRoleLabel} thường cần chọn văn bản liên quan trước khi đưa vào kho.`
                                                : 'Nếu phát hiện quan hệ pháp lý, bạn có thể bổ sung ở bước duyệt sau khi hồ sơ được tạo.'}
                                        </span>
                                    </article>
                                </section>

                                {uploading ? (
                                    <section className="review-upload-progress review-field-full" aria-label="Tiến trình tạo hồ sơ">
                                        <div className="review-upload-progress-head">
                                            <strong>{UPLOAD_PHASES[Math.max(activeUploadPhaseIndex, 0)]?.label ?? 'Đang xử lý'}</strong>
                                            <span>{UPLOAD_PHASES[Math.max(activeUploadPhaseIndex, 0)]?.description ?? 'Vui lòng chờ trong giây lát.'}</span>
                                        </div>
                                        <div className="review-upload-progress-track" aria-hidden="true">
                                            <span style={{ width: `${Math.max(activeUploadPhaseIndex + 1, 1) / UPLOAD_PHASES.length * 100}%` }} />
                                        </div>
                                        <div className="review-upload-progress-steps">
                                            {UPLOAD_PHASES.map((phase, index) => (
                                                <span key={phase.value} className={index <= activeUploadPhaseIndex ? 'is-active' : ''}>{phase.label}</span>
                                            ))}
                                        </div>
                                    </section>
                                ) : null}

                                <div className="review-upload-actions review-field-full">
                                    <button className="btn-secondary" type="button" disabled={uploading} onClick={() => setUploadOpen(false)}>
                                        Hủy
                                    </button>
                                    <button className="btn-primary" type="submit" disabled={uploading}>
                                        <FileArrowUp size={18} />
                                        {uploading ? 'Đang tạo hồ sơ' : 'Tạo hồ sơ'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </section>
                </div>
            ) : null}

            {editorRevisionId ? (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setEditorRevisionId(null)}>
                    <section
                        className="admin-modal review-editor-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Chỉnh sửa hồ sơ văn bản"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head review-editor-head">
                            <div className="review-editor-head-copy">
                                <p className="kb-kicker">Duyệt văn bản</p>
                                <h3>{editorMatchesDetail ? detail.document.title || 'Hồ sơ chưa có tiêu đề' : 'Đang tải đúng hồ sơ vừa tạo'}</h3>
                            </div>
                            <button className="admin-modal-close" type="button" onClick={() => setEditorRevisionId(null)} aria-label="Đóng">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body review-editor-body">
                            {detailLoading || !selectedMatchesDetail || !editorMatchesDetail ? (
                                <div className="skeleton-panel !mt-0 !h-72" />
                            ) : detail ? (
                                <>
                                    <section className="review-editor-overview">
                                        <div className="review-editor-context">
                                            <div className="review-editor-hero">
                                                <div className="review-editor-copy">
                                                    <div className="kb-record-topline">
                                                        <span className={`badge ${badgeTone(detail.revision.publication_status)}`}>{formatWorkspaceStatus(detail.revision.publication_status)}</span>
                                                        <span className={`badge ${displayedReviewTone}`}>{displayedReviewStatus}</span>
                                                        <span className="kb-mini-flag">{formatDocumentType(detail.document.document_type)}</span>
                                                        <span className="kb-mini-flag">{formatDocumentRole(documentRoleFromMetadata(detail.document.metadata_json))}</span>
                                                    </div>
                                                </div>
                                            </div>

                                            <section className="review-impact-strip" aria-label="Việc còn cần xử lý">
                                                <article>
                                                    <span>Thông tin cần xác nhận</span>
                                                    <strong>{pendingMetadataCount}</strong>
                                                </article>
                                                <article>
                                                    <span>Quan hệ cần xử lý</span>
                                                    <strong>{pendingRelationCount}</strong>
                                                </article>
                                                <article>
                                                    <span>Mục cần xem kỹ</span>
                                                    <strong>{pendingRiskyCount}</strong>
                                                </article>
                                                <article>
                                                    <span>Tóm tắt</span>
                                                    <strong>{summaryPending ? 'Cần duyệt' : 'Đã ổn'}</strong>
                                                </article>
                                            </section>

                                        </div>

                                    </section>

                                    {actionError ? <p className="kb-inline-error">{actionError}</p> : null}
                                    {editorMessage ? <p className="review-upload-message">{editorMessage}</p> : null}
                                    {publishPhase !== 'idle' ? (
                                        <section
                                            className={`kb-publish-progress ${publishPhase === 'done' ? 'done' : ''} ${publishPhase === 'failed' ? 'failed' : ''}`}
                                            aria-live="polite"
                                            aria-label="Tiến trình đưa văn bản vào kho"
                                        >
                                            <div className="kb-publish-progress-topline">
                                                <div>
                                                    <strong>{activePublishPhase.label}</strong>
                                                    <p>{activePublishPhase.description}</p>
                                                </div>
                                                <span>{publishPhase === 'done' ? 'Đã cập nhật' : publishPhase === 'failed' ? 'Cần thử lại' : 'Đang xử lý'}</span>
                                            </div>
                                            <div className="kb-publish-progress-rail" aria-hidden="true">
                                                <span style={{ width: publishProgressPercent }} />
                                            </div>
                                            <ol className="kb-publish-progress-steps">
                                                {PUBLISH_PHASES.map((phase, index) => (
                                                    <li key={phase.value} className={index <= activePublishPhaseIndex ? 'active' : ''}>
                                                        {phase.label}
                                                    </li>
                                                ))}
                                            </ol>
                                        </section>
                                    ) : null}
                                    {!!warningMessages.length && (
                                        <section className="kb-warning-stack">
                                            {warningMessages.map((warning) => (
                                                <article className="kb-warning-card" key={warning}>
                                                    <WarningCircle size={18} />
                                                    <span>{warning}</span>
                                                </article>
                                            ))}
                                        </section>
                                    )}

                                    <details ref={metadataSectionRef} className="kb-detail-accordion" open={pendingMetadataCount > 0 || Boolean(summaryPending)}>
                                        <summary className="kb-detail-summary">
                                            <div>
                                                <strong>Thông tin văn bản</strong>
                                                <span>Chỉnh trực tiếp các trường chính của hồ sơ, rồi lưu theo đúng rule công bố hiện tại.</span>
                                            </div>
                                            <CaretDown size={18} />
                                        </summary>
                                        <section className="review-section">
                                            <form
                                                className="review-upload-grid review-metadata-form"
                                                onSubmit={(event) => {
                                                    event.preventDefault();
                                                    void handleDocumentSave();
                                                }}
                                            >
                                                <label className="filter-group review-field-span" htmlFor="legal-kb-editor-title">
                                                    <span>Tiêu đề văn bản</span>
                                                    <input
                                                        id="legal-kb-editor-title"
                                                        value={documentDraft?.title ?? ''}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            title: event.target.value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-number">
                                                    <span>Số hiệu</span>
                                                    <input
                                                        id="legal-kb-editor-number"
                                                        value={documentDraft?.documentNumber ?? ''}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            documentNumber: event.target.value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-type">
                                                    <span>Loại văn bản</span>
                                                    <SelectControl
                                                        id="legal-kb-editor-type"
                                                        value={documentDraft?.documentType ?? 'UNKNOWN'}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            documentType: event.target.value,
                                                        }))}
                                                    >
                                                        {DOCUMENT_TYPE_OPTIONS.map((option) => (
                                                            <option key={option.value} value={option.value}>{option.label}</option>
                                                        ))}
                                                    </SelectControl>
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-role">
                                                    <span>Vai trò văn bản</span>
                                                    <SelectControl
                                                        id="legal-kb-editor-role"
                                                        value={documentDraft?.documentRole ?? 'primary'}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            documentRole: event.target.value,
                                                        }))}
                                                    >
                                                        {DOCUMENT_ROLE_OPTIONS.map((option) => (
                                                            <option key={option.value} value={option.value}>{option.label}</option>
                                                        ))}
                                                    </SelectControl>
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-issuer">
                                                    <span>Cơ quan ban hành</span>
                                                    <input
                                                        id="legal-kb-editor-issuer"
                                                        value={documentDraft?.issuingAuthority ?? ''}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            issuingAuthority: event.target.value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-issued-date">
                                                    <span>Ngày ban hành</span>
                                                    <DateInput
                                                        id="legal-kb-editor-issued-date"
                                                        value={documentDraft?.issuedDate ?? ''}
                                                        onChange={(value) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            issuedDate: value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-effective-date">
                                                    <span>Ngày có hiệu lực</span>
                                                    <DateInput
                                                        id="legal-kb-editor-effective-date"
                                                        value={documentDraft?.effectiveDate ?? ''}
                                                        onChange={(value) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            effectiveDate: value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-expiry-date">
                                                    <span>Ngày hết hiệu lực</span>
                                                    <DateInput
                                                        id="legal-kb-editor-expiry-date"
                                                        value={documentDraft?.expiryDate ?? ''}
                                                        onChange={(value) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            expiryDate: value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-source-url">
                                                    <span>Đường dẫn nguồn</span>
                                                    <input
                                                        id="legal-kb-editor-source-url"
                                                        value={documentDraft?.sourceUrl ?? ''}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            sourceUrl: event.target.value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-source-downloaded-at">
                                                    <span>Ngày lấy nguồn</span>
                                                    <DateInput
                                                        id="legal-kb-editor-source-downloaded-at"
                                                        value={documentDraft?.sourceDownloadedAt ?? ''}
                                                        onChange={(value) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            sourceDownloadedAt: value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group" htmlFor="legal-kb-editor-source-file-name">
                                                    <span>File nguồn</span>
                                                    <input
                                                        id="legal-kb-editor-source-file-name"
                                                        value={documentDraft?.sourceFileName ?? ''}
                                                        onChange={(event) => setDocumentDraft((current) => ({
                                                            ...(current ?? buildDocumentFormDraft(detail)),
                                                            sourceFileName: event.target.value,
                                                        }))}
                                                    />
                                                </label>

                                                <label className="filter-group review-field-full" htmlFor="legal-kb-editor-summary">
                                                    <span>Tóm tắt</span>
                                                    <AutoResizeTextarea
                                                        id="legal-kb-editor-summary"
                                                        maxRows={8}
                                                        minRows={3}
                                                        value={documentDraft?.summary ?? ''}
                                                        onChange={(event) => {
                                                            setDocumentDraft((current) => ({
                                                                ...(current ?? buildDocumentFormDraft(detail)),
                                                                summary: event.target.value,
                                                            }));
                                                        }}
                                                    />
                                                </label>

                                                <div className="review-upload-actions review-field-full review-metadata-actions">
                                                    <button className="btn-primary" type="submit" disabled={busyKey === 'document-save'}>
                                                        <CheckCircle size={18} />
                                                        {busyKey === 'document-save' ? 'Đang lưu thông tin' : 'Lưu thông tin văn bản'}
                                                    </button>
                                                </div>
                                            </form>

                                            {pendingMetadataProposals.length > 0 ? (
                                                <div className="kb-record-list review-proposal-stack">
                                                    {pendingMetadataProposals.map((proposal) => (
                                                        <article className="kb-record kb-record-accordion" key={proposal.proposal_id}>
                                                            <div className="kb-inline-detail">
                                                                <div className="kb-record-topline">
                                                                    <span className={`badge ${badgeTone(proposal.review_status)}`}>{formatReviewStatus(proposal.review_status)}</span>
                                                                    <span className="kb-mini-flag">{formatMetadataFieldLabel(proposal.field_name)}</span>
                                                                </div>
                                                                <label className="filter-group">
                                                                    <span>Giá trị parser đang đề xuất</span>
                                                                    <input
                                                                        value={metadataDrafts[proposal.proposal_id] ?? ''}
                                                                        onChange={(event) => setMetadataDrafts((current) => ({ ...current, [proposal.proposal_id]: event.target.value }))}
                                                                    />
                                                                </label>
                                                                <div className="review-inline-actions">
                                                                    <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleMetadataReview(proposal.proposal_id, 'approved')}>Duyệt đề xuất này</button>
                                                                    <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleMetadataReview(proposal.proposal_id, 'rejected')}>Từ chối đề xuất này</button>
                                                                </div>
                                                            </div>
                                                        </article>
                                                    ))}
                                                </div>
                                            ) : null}
                                        </section>
                                    </details>

                                    <details ref={relationSectionRef} className="kb-detail-accordion" open={pendingRelationCount > 0}>
                                        <summary className="kb-detail-summary">
                                            <div>
                                                <strong>Quan hệ văn bản</strong>
                                                <span>Thiết lập và duyệt các liên kết để hệ thống hiểu đúng bối cảnh áp dụng.</span>
                                            </div>
                                            <CaretDown size={18} />
                                        </summary>
                                        <section className="review-section">
                                            <article className="kb-relation-editor">
                                                <div className="kb-relation-editor-heading">
                                                    <strong>Thêm quan hệ mới</strong>
                                                    <span>Tạo liên kết ngay trong cùng màn hình nếu văn bản này sửa đổi, bổ sung hoặc hướng dẫn văn bản khác.</span>
                                                </div>
                                                <div className="kb-relation-form-grid">
                                                    <label className="filter-group">
                                                        <span>Mã văn bản liên quan</span>
                                                        <RelationTargetCombobox
                                                            id="legal-kb-new-relation-target"
                                                            options={relatedDocumentOptions}
                                                            value={newRelationDraft.targetDocumentId}
                                                            onSearch={searchRelationTargets}
                                                            onChange={(value) => setNewRelationDraft((current) => ({ ...current, targetDocumentId: value }))}
                                                        />
                                                    </label>
                                                    <label className="filter-group">
                                                        <span>Loại quan hệ</span>
                                                        <SelectControl value={newRelationDraft.relationType} onChange={(event) => setNewRelationDraft((current) => ({ ...current, relationType: event.target.value as RelationType }))}>
                                                            {RELATION_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                                                        </SelectControl>
                                                    </label>
                                                    <label className="filter-group">
                                                        <span>Vị trí trong văn bản này</span>
                                                        <input value={newRelationDraft.sourceLocator} onChange={(event) => setNewRelationDraft((current) => ({ ...current, sourceLocator: event.target.value }))} />
                                                    </label>
                                                    <label className="filter-group">
                                                        <span>Vị trí trong văn bản liên quan</span>
                                                        <input value={newRelationDraft.targetLocator} onChange={(event) => setNewRelationDraft((current) => ({ ...current, targetLocator: event.target.value }))} />
                                                    </label>
                                                </div>
                                                <label className="filter-group">
                                                    <span>Ghi chú</span>
                                                    <textarea value={newRelationDraft.note} onChange={(event) => setNewRelationDraft((current) => ({ ...current, note: event.target.value }))} rows={2} />
                                                </label>
                                                <p className="kb-workspace-helper">{relationHelper(newRelationDraft.relationType)}</p>
                                                <div className="review-inline-actions review-relation-actions">
                                                    <button className="btn-secondary" type="button" disabled={busyKey === 'relation-create'} onClick={() => void handleCreateRelation()}>
                                                        {busyKey === 'relation-create' ? 'Đang tạo liên kết' : 'Tạo quan hệ văn bản'}
                                                    </button>
                                                </div>
                                            </article>

                                            {detail.relations.length === 0 ? (
                                                <div className="empty-state">
                                                    <strong>Chưa có quan hệ văn bản</strong>
                                                    <p>Nếu văn bản này sửa đổi, bổ sung hoặc hướng dẫn văn bản khác thì hãy thêm liên kết tại đây.</p>
                                                </div>
                                            ) : null}

                                            {pendingRelations.length > 0 ? (
                                                <div className="kb-record-list">
                                                    {pendingRelations.map((relation) => {
                                                        const draft = relationDrafts[relation.relation_id] ?? emptyRelationDraft();
                                                        return (
                                                            <article className="kb-record kb-record-accordion" key={relation.relation_id}>
                                                                <div className="kb-inline-detail">
                                                                    <div className="kb-record-topline">
                                                                        <span className={`badge ${badgeTone(relation.review_status)}`}>{formatReviewStatus(relation.review_status)}</span>
                                                                        <span className="kb-mini-flag">{formatRelationType(relation.relation_type)}</span>
                                                                    </div>
                                                                    <div className="kb-relation-form-grid">
                                                                        <label className="filter-group">
                                                                            <span>Mã văn bản liên quan</span>
                                                                            <RelationTargetCombobox
                                                                                id={`legal-kb-relation-target-${relation.relation_id}`}
                                                                                options={relatedDocumentOptions}
                                                                                value={draft.targetDocumentId}
                                                                                onSearch={searchRelationTargets}
                                                                                onChange={(value) => setRelationDrafts((current) => ({ ...current, [relation.relation_id]: { ...draft, targetDocumentId: value } }))}
                                                                            />
                                                                        </label>
                                                                        <label className="filter-group">
                                                                            <span>Loại quan hệ</span>
                                                                            <SelectControl value={draft.relationType} onChange={(event) => setRelationDrafts((current) => ({ ...current, [relation.relation_id]: { ...draft, relationType: event.target.value as RelationType } }))}>
                                                                                {RELATION_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                                                                            </SelectControl>
                                                                        </label>
                                                                        <label className="filter-group">
                                                                            <span>Vị trí trong văn bản này</span>
                                                                            <input value={draft.sourceLocator} onChange={(event) => setRelationDrafts((current) => ({ ...current, [relation.relation_id]: { ...draft, sourceLocator: event.target.value } }))} />
                                                                        </label>
                                                                        <label className="filter-group">
                                                                            <span>Vị trí trong văn bản liên quan</span>
                                                                            <input value={draft.targetLocator} onChange={(event) => setRelationDrafts((current) => ({ ...current, [relation.relation_id]: { ...draft, targetLocator: event.target.value } }))} />
                                                                        </label>
                                                                    </div>
                                                                    <label className="filter-group">
                                                                        <span>Ghi chú</span>
                                                                        <textarea value={draft.note} onChange={(event) => setRelationDrafts((current) => ({ ...current, [relation.relation_id]: { ...draft, note: event.target.value } }))} rows={2} />
                                                                    </label>
                                                                    <p className="kb-workspace-helper">{relationHelper(draft.relationType)}</p>
                                                                    <div className="review-inline-actions review-relation-actions">
                                                                        <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleRelationUpdate(relation.relation_id)}>Lưu chỉnh sửa</button>
                                                                        <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleRelationReview(relation.relation_id, 'approved')}>Duyệt</button>
                                                                        <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleRelationReview(relation.relation_id, 'rejected')}>Từ chối</button>
                                                                        <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleRelationDelete(relation)}>Loại bỏ</button>
                                                                    </div>
                                                                </div>
                                                            </article>
                                                        );
                                                    })}
                                                </div>
                                            ) : null}

                                            {confirmedRelations.length > 0 ? (
                                                <details className="review-evidence-panel review-confirmed-relations">
                                                    <summary>{confirmedRelations.length} quan hệ đã xác nhận</summary>
                                                    <div className="review-confirmed-relation-list">
                                                        {confirmedRelations.map((relation) => {
                                                            const counterpartId = relationCounterpartId(relation, detail.document.document_id);
                                                            const counterpart = relatedDocumentOptions.find((option) => option.value === counterpartId);
                                                            return (
                                                                <article className="review-confirmed-relation" key={relation.relation_id}>
                                                                    <div className="review-confirmed-relation-copy">
                                                                        <div className="kb-record-topline">
                                                                            <span className="badge good">Đã xác nhận</span>
                                                                            <span className="kb-mini-flag">{relationDirectionLabel(relation, detail.document.document_id)}</span>
                                                                            <span className="kb-mini-flag">{formatRelationType(relation.relation_type)}</span>
                                                                        </div>
                                                                        <strong>{counterpart?.label || 'Văn bản liên quan'}</strong>
                                                                        {(relation.source_locator || relation.target_locator) ? (
                                                                            <p>
                                                                                {relation.source_locator || 'Chưa ghi vị trí nguồn'}
                                                                                {' → '}
                                                                                {relation.target_locator || 'Chưa ghi vị trí liên quan'}
                                                                            </p>
                                                                        ) : null}
                                                                    </div>
                                                                    {relation.source_document_id === detail.document.document_id ? (
                                                                        <div className="review-inline-actions review-confirmed-relation-actions">
                                                                            <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleRelationReset(relation)}>Sửa quyết định</button>
                                                                            <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleRelationDelete(relation)}>Loại bỏ</button>
                                                                        </div>
                                                                    ) : null}
                                                                </article>
                                                            );
                                                        })}
                                                    </div>
                                                </details>
                                            ) : null}
                                        </section>
                                    </details>

                                    <details ref={riskyContentSectionRef} className="kb-detail-accordion" open={pendingRiskyCount > 0}>
                                        <summary className="kb-detail-summary">
                                            <div>
                                                <strong>Nội dung cần xem kỹ</strong>
                                                <span>Ưu tiên bảng, phụ lục, mẫu biểu và ảnh minh họa trước khi công bố.</span>
                                            </div>
                                            <CaretDown size={18} />
                                        </summary>
                                        <section className="review-section">
                                            {visibleRiskyItems.length === 0 ? (
                                                <div className="empty-state">
                                                    <strong>Không còn mục cần xem kỹ</strong>
                                                    <p>Các bảng, phụ lục, mẫu biểu và ảnh minh họa đã được xử lý hoặc hồ sơ này không có các mục đó.</p>
                                                </div>
                                            ) : (
                                                <div className="kb-record-list">
                                                    {visibleRiskyItems.map((item) => (
                                                        <article className="kb-record kb-record-accordion" key={item.node_id}>
                                                            <div className="kb-inline-detail">
                                                                <div className="kb-record-topline">
                                                                    <span className={`badge ${badgeTone(item.review_status)}`}>{formatReviewStatus(item.review_status)}</span>
                                                                    <span className="kb-mini-flag">{formatContentType(item.node_type)}</span>
                                                                    {isReferenceOnly(item) ? <span className="kb-mini-flag">Chỉ để đối chiếu</span> : null}
                                                                </div>
                                                                <p>{item.label || item.text || item.node_id}</p>
                                                                <details className="review-evidence-panel">
                                                                    <summary>Xem nội dung đã tách và nguồn đối chiếu</summary>
                                                                    <div className="review-evidence-body">
                                                                        <pre className="review-evidence-copy">{item.text || 'Mục này không có phần chữ để hiển thị.'}</pre>
                                                                        <pre className="review-evidence-json">{JSON.stringify(item.provenance, null, 2)}</pre>
                                                                    </div>
                                                                </details>
                                                                {needsUsageDecision(item) ? (
                                                                    <p className="text-sm text-amber-700">Mục này cần quyết định rõ là dùng cho trả lời hay chỉ dùng để đối chiếu.</p>
                                                                ) : null}
                                                                <label className="filter-group">
                                                                    <span>Ghi chú kiểm tra</span>
                                                                    <textarea value={contentNotes[item.node_id] ?? ''} onChange={(event) => setContentNotes((current) => ({ ...current, [item.node_id]: event.target.value }))} rows={2} />
                                                                </label>
                                                                <div className="review-inline-actions review-content-actions">
                                                                    <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleContentReview(item, 'approved', true)}>Dùng cho trả lời</button>
                                                                    <button className="btn-secondary" type="button" disabled={Boolean(busyKey)} onClick={() => void handleContentReview(item, 'approved', false)}>Chỉ để đối chiếu</button>
                                                                    <details className="review-more-actions">
                                                                        <summary>Thao tác khác</summary>
                                                                        <button type="button" disabled={Boolean(busyKey)} onClick={() => void handleResetContentReview(item)}>Cần xem lại</button>
                                                                        <button type="button" disabled={Boolean(busyKey)} onClick={() => void handleContentReview(item, 'rejected')}>Từ chối mục này</button>
                                                                    </details>
                                                                </div>
                                                            </div>
                                                        </article>
                                                    ))}
                                                </div>
                                            )}
                                        </section>
                                    </details>

                                    {resolvedRiskyCount > 0 ? (
                                        <details className="kb-detail-accordion review-resolved-accordion">
                                            <summary className="kb-detail-summary">
                                                <div>
                                                    <strong>Đã kiểm tra</strong>
                                                    <span>{resolvedRiskyCount} mục bảng, phụ lục, mẫu biểu hoặc ảnh đã có quyết định. Chỉ mở khi cần sửa lại quyết định.</span>
                                                </div>
                                                <CaretDown size={18} />
                                            </summary>
                                            <section className="review-section review-resolved-section">
                                                <div className="review-resolved-list">
                                                    {visibleResolvedRiskyItems.map((item) => (
                                                        <article className="review-resolved-item" key={item.node_id}>
                                                            <div>
                                                                <div className="kb-record-topline">
                                                                    <span className={`badge ${isReferenceOnly(item) ? 'good' : badgeTone(item.review_status)}`}>
                                                                        {isReferenceOnly(item) ? 'Chỉ để đối chiếu' : 'Dùng cho hỏi đáp'}
                                                                    </span>
                                                                    <span className="kb-mini-flag">{formatContentType(item.node_type)}</span>
                                                                </div>
                                                                <p>{item.label || item.text || item.node_id}</p>
                                                            </div>
                                                            <button className="btn-secondary btn-compact" type="button" disabled={Boolean(busyKey)} onClick={() => void handleResetContentReview(item)}>
                                                                Đưa về cần xử lý
                                                            </button>
                                                        </article>
                                                    ))}
                                                </div>
                                                {resolvedRiskyCount > visibleResolvedRiskyItems.length ? (
                                                    <p className="kb-workspace-helper">Còn {resolvedRiskyCount - visibleResolvedRiskyItems.length} mục đã kiểm tra khác được ẩn để giữ modal gọn.</p>
                                                ) : null}
                                            </section>
                                        </details>
                                    ) : null}

                                    <details className="kb-detail-accordion">
                                        <summary className="kb-detail-summary">
                                            <div>
                                                <strong>Lịch sử xử lý</strong>
                                                <span>Theo dõi những lần tạo hồ sơ, duyệt và thay đổi trạng thái gần nhất.</span>
                                            </div>
                                            <CaretDown size={18} />
                                        </summary>
                                        <section className="review-section">
                                            {reviewEvents.length === 0 ? (
                                                <div className="empty-state">
                                                    <strong>Chưa có lịch sử xử lý</strong>
                                                    <p>Hồ sơ này chưa ghi nhận thêm sự kiện nào ngoài lúc tạo ban đầu.</p>
                                                </div>
                                            ) : (
                                                <>
                                                    <div className="kb-history-list">
                                                        {visibleReviewEvents.map((event) => (
                                                            <article className="kb-history-card" key={event.review_event_id}>
                                                                <div className="kb-history-top">
                                                                    <span className={`badge ${badgeTone(event.decision)}`}>{reviewEventDisplayLabel(event.decision)}</span>
                                                                    <span className="kb-mini-flag">{formatDateTime(event.created_at)}</span>
                                                                </div>
                                                                <strong>{reviewEventActorLabel(event.actor_user_id)}</strong>
                                                                <p>{reviewEventNote(event.details)}</p>
                                                            </article>
                                                        ))}
                                                    </div>
                                                    {reviewHistoryTotalPages > 1 ? (
                                                        <div className="pagination">
                                                            <button
                                                                className="btn-secondary"
                                                                type="button"
                                                                disabled={boundedReviewHistoryPage <= 1}
                                                                onClick={() => setReviewHistoryPage((current) => Math.max(1, current - 1))}
                                                            >
                                                                Trước
                                                            </button>
                                                            <span>Trang {boundedReviewHistoryPage} / {reviewHistoryTotalPages}</span>
                                                            <button
                                                                className="btn-secondary"
                                                                type="button"
                                                                disabled={boundedReviewHistoryPage >= reviewHistoryTotalPages}
                                                                onClick={() => setReviewHistoryPage((current) => Math.min(reviewHistoryTotalPages, current + 1))}
                                                            >
                                                                Sau
                                                            </button>
                                                        </div>
                                                    ) : null}
                                                </>
                                            )}
                                        </section>
                                    </details>

                                    <footer className="review-editor-footer-actions" aria-label="Thao tác hồ sơ">
                                        <button className="btn-primary" type="button" disabled={busyKey === 'publish' || alreadyInRepository} onClick={() => void handlePutIntoRepository()}>
                                            <CheckCircle size={18} />
                                            {busyKey === 'publish' ? 'Đang đưa vào kho' : alreadyInRepository ? 'Đã ở trong kho' : 'Đưa vào kho'}
                                        </button>
                                        {detail.source_asset ? (
                                            <button className="btn-secondary" type="button" onClick={() => setDownloadDetail(detail)}>
                                                <DownloadSimple size={18} />
                                                Tải file nguồn
                                            </button>
                                        ) : null}
                                    </footer>
                                </>
                            ) : (
                                <div className="empty-state">
                                    <strong>Chưa có hồ sơ</strong>
                                    <p>Hãy chọn một hồ sơ từ danh sách để bắt đầu duyệt.</p>
                                </div>
                            )}
                        </div>
                    </section>
                </div>
            ) : null}

            {confirmDialog ? (
                <div className="admin-modal-backdrop review-confirm-backdrop" role="presentation" onClick={() => setPendingConfirmation(null)}>
                    <section
                        className="admin-modal review-confirm-dialog"
                        role="alertdialog"
                        aria-modal="true"
                        aria-label={confirmDialog.title}
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <div>
                                <p className="kb-kicker">Xác nhận thao tác</p>
                                <h3>{confirmDialog.title}</h3>
                            </div>
                            <button className="admin-modal-close" type="button" onClick={() => setPendingConfirmation(null)} aria-label="Đóng">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body">
                            <article className={`review-confirm-message ${confirmDialog.danger ? 'is-danger' : ''}`}>
                                <WarningCircle size={19} />
                                <p>{confirmDialog.description}</p>
                            </article>
                            <div className="admin-modal-actions review-confirm-actions">
                                <button className="btn-secondary" type="button" onClick={() => setPendingConfirmation(null)}>
                                    Hủy
                                </button>
                                <button
                                    className={confirmDialog.danger ? 'btn-danger' : 'btn-primary'}
                                    type="button"
                                    onClick={() => void confirmPendingAction()}
                                >
                                    {confirmDialog.confirmLabel}
                                </button>
                            </div>
                        </div>
                    </section>
                </div>
            ) : null}

            {downloadDetail ? (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setDownloadDetail(null)}>
                    <section
                        className="admin-modal review-dialog kb-action-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Lưu ý khi tải file nguồn"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <div>
                                <p className="kb-kicker">Tải file nguồn</p>
                                <h3>Lưu ý khi tải file nguồn</h3>
                            </div>
                            <button className="admin-modal-close" type="button" onClick={() => setDownloadDetail(null)} aria-label="Đóng">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body">
                            <section className="kb-warning-card">
                                <WarningCircle size={18} />
                                <div className="kb-warning-copy">
                                    <strong>Cảnh báo</strong>
                                    <p>
                                        Bản này phục vụ tra cứu trong hệ thống. Khi dùng cho mục đích pháp lý hoặc chính thức,
                                        vui lòng đối chiếu với nguồn văn bản chính thức.
                                    </p>
                                </div>
                            </section>
                            <dl className="kb-meta-list kb-modal-meta-grid">
                                <div><dt>Tên file</dt><dd>{downloadDetail.source_asset?.original_filename || 'Chưa có file nguồn'}</dd></div>
                                <div><dt>Ngày lấy nguồn</dt><dd>{formatDate(downloadDetail.revision.source_downloaded_at)}</dd></div>
                                <div><dt>Đường dẫn nguồn</dt><dd>{downloadDetail.revision.source_url || 'Chưa cập nhật'}</dd></div>
                            </dl>
                            <div className="review-action-buttons review-action-buttons-inline">
                                <button className="btn-secondary" type="button" onClick={() => setDownloadDetail(null)}>
                                    Đóng
                                </button>
                                <button
                                    className="btn-primary"
                                    type="button"
                                    disabled={!downloadDetail.source_asset}
                                    onClick={() => {
                                        void downloadAdminSource(
                                            sourceDownloadPath(downloadDetail),
                                            downloadDetail.source_asset?.original_filename || 'van-ban-nguon',
                                        );
                                        setDownloadDetail(null);
                                    }}
                                >
                                    <DownloadSimple size={18} />
                                    Tải file
                                </button>
                            </div>
                        </div>
                    </section>
                </div>
            ) : null}
        </section>
    );
}
