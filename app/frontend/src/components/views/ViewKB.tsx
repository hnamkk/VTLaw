import React from 'react';
import {
    ArrowCounterClockwise,
    Book,
    CaretDown,
    DownloadSimple,
    FileArrowUp,
    FileText,
    Link,
    MagnifyingGlass,
    NotePencil,
    WarningCircle,
    X,
} from '@phosphor-icons/react';

import { PageFrame } from '../ui';
import {
    KbV2DuplicateSourceError,
    createDocumentRelationProposal,
    deleteDocumentRelation,
    downloadAdminSource,
    fetchPublishedDocumentDetail,
    fetchPublishedDocuments,
    reviewKbV2Summary,
    reviewDocumentRelation,
    type PublishedDocumentDetailResponse,
    type PublishedDocumentListItem,
    type PublishedDocumentListResponse,
    updateDocumentRelation,
    updatePublishedDocument,
    updatePublishedDocumentStatus,
    uploadKbV2ReplacementRevision,
} from '../../lib/api';

const HITL_REVIEW_SEARCH_KEY = 'hitl-review-search-prefill';
const HITL_REVIEW_REVISION_KEY = 'hitl-review-revision-prefill';

type StatusFilter = '' | 'active' | 'suspended' | 'expired' | 'replaced' | 'annulled';
type RelationType = 'amends' | 'supplements' | 'replaces' | 'annuls' | 'guides' | 'depends_on';

type MetadataDraft = {
    title: string;
    documentNumber: string;
    documentType: string;
    issuingAuthority: string;
    issuedDate: string;
    effectiveDate: string;
    expiryDate: string;
    sourceUrl: string;
    sourceDownloadedAt: string;
    sourceNote: string;
    summary: string;
    documentRole: string;
};

type RelationDraft = {
    targetDocumentId: string;
    relationType: RelationType;
    sourceLocator: string;
    targetLocator: string;
    note: string;
};

type ReplacementDraft = {
    documentId: string;
    title: string;
    documentNumber: string;
    documentType: string;
    documentRole: string;
    issuingAuthority: string;
    issuedDate: string;
    effectiveDate: string;
    expiryDate: string;
    sourceUrl: string;
    sourceDownloadedAt: string;
    sourceNote: string;
    file: File | null;
    confirmedDocumentNumber: boolean;
    confirmedRelationReview: boolean;
    original: Omit<MetadataDraft, 'summary'>;
};

type ReplacementUploadPhase = 'idle' | 'uploading' | 'parsing' | 'proposals' | 'opening';

type PendingConfirmation =
    | { kind: 'metadata'; documentId: string }
    | { kind: 'status'; documentId: string; status: Exclude<StatusFilter, ''>; replacementDocumentId?: string; note: string }
    | { kind: 'relation-save'; documentId: string; relationId: string }
    | { kind: 'relation-delete'; documentId: string; relationId: string }
    | { kind: 'relation-create'; documentId: string; revisionId: string };

const REVIEW_EVENTS_PAGE_SIZE = 5;
const SLOW_LOADING_THRESHOLD_MS = 10000;
const REPLACEMENT_UPLOAD_PHASES: Array<{
    value: Exclude<ReplacementUploadPhase, 'idle'>;
    label: string;
    description: string;
}> = [
    { value: 'uploading', label: 'Tải file', description: 'Đưa file nguồn mới vào vùng xử lý an toàn.' },
    { value: 'parsing', label: 'Tách nội dung', description: 'Đọc DOCX và nhận diện cấu trúc của bản mới.' },
    { value: 'proposals', label: 'Tạo đề xuất', description: 'Chuẩn bị thông tin và các mục cần kiểm tra.' },
    { value: 'opening', label: 'Mở hồ sơ', description: 'Chuyển đúng hồ sơ vừa tạo sang Duyệt văn bản.' },
];

function DateInput({
    id,
    value,
    onChange,
    required = false,
}: {
    id?: string;
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
                aria-describedby={id ? `${id}-hint` : undefined}
            />
            <span className="localized-date-placeholder" aria-hidden="true">Chọn ngày</span>
            {id ? <small id={`${id}-hint`} className="sr-only">Ngày theo định dạng ngày, tháng, năm.</small> : null}
        </div>
    );
}

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
    LUAT: 'Luật',
    BO_LUAT: 'Bộ luật',
    NGHI_DINH: 'Nghị định',
    THONG_TU: 'Thông tư',
    QUYET_DINH: 'Quyết định',
    CONG_VAN: 'Công văn',
    QCVN: 'Quy chuẩn kỹ thuật',
    UNKNOWN: 'Khác hoặc chưa rõ',
};

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

const RELATION_OPTIONS: Array<{ value: RelationType; label: string; helper: string }> = [
    { value: 'amends', label: 'Sửa đổi', helper: 'Văn bản này sửa một phần nội dung của văn bản liên quan.' },
    { value: 'supplements', label: 'Bổ sung', helper: 'Văn bản này bổ sung thêm quy định cho văn bản liên quan.' },
    { value: 'replaces', label: 'Thay thế', helper: 'Văn bản này thay thế toàn bộ hoặc một phần văn bản liên quan.' },
    { value: 'annuls', label: 'Bãi bỏ', helper: 'Văn bản này bãi bỏ quy định của văn bản liên quan.' },
    { value: 'guides', label: 'Hướng dẫn', helper: 'Văn bản này hướng dẫn thi hành văn bản liên quan.' },
    { value: 'depends_on', label: 'Căn cứ liên quan', helper: 'Văn bản liên quan được dùng làm căn cứ hoặc bối cảnh.' },
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

const STATUS_ACTIONS: Array<{ value: Exclude<StatusFilter, ''>; label: string; helper: string }> = [
    { value: 'active', label: 'Đang công bố', helper: 'Người dùng trên màn tra cứu nhìn thấy và trợ lý AI được phép dùng lại.' },
    { value: 'suspended', label: 'Tạm ngừng', helper: 'Ẩn khỏi màn tra cứu và trợ lý AI cho tới khi khôi phục.' },
    { value: 'expired', label: 'Hết hiệu lực', helper: 'Chỉ lưu trong kho quản trị; không hiện ở trang tra cứu và không dùng cho hỏi đáp.' },
    { value: 'replaced', label: 'Được thay thế', helper: 'Chỉ lưu trong kho quản trị; không hiện ở trang tra cứu và không dùng cho hỏi đáp.' },
    { value: 'annulled', label: 'Bị bãi bỏ', helper: 'Chỉ lưu trong kho quản trị; không hiện ở trang tra cứu và không dùng cho hỏi đáp.' },
];

function formatDate(value: string | null | undefined) {
    if (!value) return 'Chưa có';
    return new Date(value).toLocaleDateString('vi-VN');
}

function formatDateTime(value: string | null | undefined) {
    if (!value) return 'Chưa cập nhật';
    return new Date(value).toLocaleString('vi-VN');
}

function formatDocType(value: string | null | undefined) {
    const normalized = normalizeDocumentType(value);
    if (!normalized) return 'Chưa cập nhật';
    return DOCUMENT_TYPE_LABELS[normalized] ?? 'Khác hoặc chưa rõ';
}

function formatRelationType(value: string | null | undefined) {
    return RELATION_OPTIONS.find((item) => item.value === value)?.label ?? 'Quan hệ văn bản';
}

function statusTone(value: string) {
    if (value === 'active') return 'good';
    if (value === 'suspended' || value === 'annulled') return 'danger';
    return 'warn';
}

function statusLabel(value: string) {
    return {
        active: 'Đang công bố',
        suspended: 'Tạm ngừng',
        expired: 'Hết hiệu lực',
        replaced: 'Được thay thế',
        annulled: 'Bị bãi bỏ',
    }[value] ?? value;
}

function relationReviewTone(value: string) {
    return value === 'approved' ? 'good' : 'warn';
}

function visibilityLabel(status: string) {
    return status === 'active' ? 'Có' : 'Không';
}

function formatDocumentRole(value: string | null | undefined) {
    const normalized = normalizeDocumentRole(value);
    if (!normalized) return 'Chưa phân loại';
    return {
        primary: 'Văn bản chính để trả lời',
        amendment: 'Văn bản sửa đổi hoặc bổ sung',
        replacement: 'Văn bản thay thế hoặc ban hành mới',
        guidance: 'Văn bản hướng dẫn thi hành',
        foundation: 'Văn bản căn cứ để đối chiếu',
        reference: 'Tài liệu tham khảo bổ sung',
        technical: 'Quy chuẩn hoặc tài liệu kỹ thuật',
    }[normalized] ?? 'Chưa phân loại';
}

function formatHistoryEntity(value: string) {
    return value === 'document' ? 'Văn bản' : 'Hồ sơ xử lý';
}

function formatReviewDecision(value: string) {
    return {
        approved: 'Đã duyệt',
        rejected: 'Từ chối',
        published: 'Đã công bố',
        publish: 'Đã công bố',
        suspended: 'Tạm ngừng công bố',
        unsuspended: 'Khôi phục công bố',
        updated: 'Đã cập nhật',
        created: 'Đã tạo',
    }[value] ?? value;
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

function createMetadataDraft(detail: PublishedDocumentDetailResponse): MetadataDraft {
    return {
        title: detail.document.title ?? '',
        documentNumber: detail.document.document_number ?? '',
        documentType: normalizeDocumentType(detail.document.document_type),
        issuingAuthority: detail.document.issuing_authority ?? '',
        issuedDate: detail.document.issued_date ?? '',
        effectiveDate: detail.document.effective_date ?? '',
        expiryDate: detail.document.expiry_date ?? '',
        sourceUrl: detail.revision.source_url ?? '',
        sourceDownloadedAt: detail.revision.source_downloaded_at ?? '',
        sourceNote: detail.revision.source_note ?? '',
        summary: standardSummaryContent(detail),
        documentRole: normalizeDocumentRole(String(detail.document.metadata_json?.document_role ?? '')),
    };
}

function createReplacementDraft(detail: PublishedDocumentDetailResponse): ReplacementDraft {
    const metadataDraft = createMetadataDraft(detail);
    const original = {
        title: metadataDraft.title,
        documentNumber: metadataDraft.documentNumber,
        documentType: metadataDraft.documentType,
        documentRole: metadataDraft.documentRole,
        issuingAuthority: metadataDraft.issuingAuthority,
        issuedDate: metadataDraft.issuedDate,
        effectiveDate: metadataDraft.effectiveDate,
        expiryDate: metadataDraft.expiryDate,
        sourceUrl: metadataDraft.sourceUrl,
        sourceDownloadedAt: metadataDraft.sourceDownloadedAt,
        sourceNote: metadataDraft.sourceNote,
    };
    return {
        documentId: detail.document.document_id,
        title: metadataDraft.title,
        documentNumber: metadataDraft.documentNumber,
        documentType: metadataDraft.documentType,
        documentRole: metadataDraft.documentRole,
        issuingAuthority: metadataDraft.issuingAuthority,
        issuedDate: metadataDraft.issuedDate,
        effectiveDate: metadataDraft.effectiveDate,
        expiryDate: metadataDraft.expiryDate,
        sourceUrl: metadataDraft.sourceUrl,
        sourceDownloadedAt: new Date().toISOString().slice(0, 10),
        sourceNote: metadataDraft.sourceNote || 'Thay file nguồn sau khi đối chiếu bản mới.',
        file: null,
        confirmedDocumentNumber: false,
        confirmedRelationReview: false,
        original,
    };
}

function replacementMaterialChanges(draft: ReplacementDraft) {
    const comparableFields: Array<keyof ReplacementDraft['original']> = [
        'title',
        'documentNumber',
        'documentType',
        'documentRole',
        'issuingAuthority',
        'issuedDate',
        'effectiveDate',
        'expiryDate',
    ];
    return comparableFields.filter((field) => draft[field].trim() !== draft.original[field].trim());
}

function standardSummaryContent(detail: PublishedDocumentDetailResponse) {
    return detail.summary?.content ?? '';
}

function sourceDownloadPath(detail: PublishedDocumentDetailResponse) {
    return `/api/v1/admin/kb-v2/revisions/${detail.revision.revision_id}/source`;
}

function relationDisplayText(
    relation: PublishedDocumentDetailResponse['relations'][number],
    options: PublishedDocumentListItem[],
    documentId: string,
) {
    const counterpartId = relation.source_document_id === documentId
        ? relation.target_document_id
        : relation.source_document_id;
    const counterpart = options.find((item) => item.document_id === counterpartId);
    const counterpartLabel = counterpart?.document_number || counterpart?.title || counterpartId;
    const direction = relation.source_document_id === documentId ? 'Quan hệ đi' : 'Quan hệ đến';
    return `${direction}: ${formatRelationType(relation.relation_type)} với ${counterpartLabel}`;
}

function sortReviewEventsByNewest(detail: PublishedDocumentDetailResponse) {
    return [...detail.review_events].sort((left, right) => {
        const leftTime = left.created_at ? new Date(left.created_at).getTime() : 0;
        const rightTime = right.created_at ? new Date(right.created_at).getTime() : 0;
        return rightTime - leftTime;
    });
}

export default function ViewKB({ activeView }: { activeView: string }) {
    const [query, setQuery] = React.useState('');
    const deferredQuery = React.useDeferredValue(query);
    const [statusFilter, setStatusFilter] = React.useState<StatusFilter>('');
    const [page, setPage] = React.useState(1);
    const [documents, setDocuments] = React.useState<PublishedDocumentListResponse | null>(null);
    const [allDocuments, setAllDocuments] = React.useState<PublishedDocumentListItem[]>([]);
    const [loading, setLoading] = React.useState(false);
    const [slowLoading, setSlowLoading] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);
    const [expandedDocumentId, setExpandedDocumentId] = React.useState<string | null>(null);
    const [details, setDetails] = React.useState<Record<string, PublishedDocumentDetailResponse>>({});
    const [detailLoadingId, setDetailLoadingId] = React.useState<string | null>(null);
    const [detailErrors, setDetailErrors] = React.useState<Record<string, string>>({});
    const [metadataDrafts, setMetadataDrafts] = React.useState<Record<string, MetadataDraft>>({});
    const [relationDrafts, setRelationDrafts] = React.useState<Record<string, Record<string, RelationDraft>>>({});
    const [newRelationDrafts, setNewRelationDrafts] = React.useState<Record<string, RelationDraft>>({});
    const [savingMetadataId, setSavingMetadataId] = React.useState<string | null>(null);
    const [savingRelationKey, setSavingRelationKey] = React.useState<string | null>(null);
    const [changingStatusId, setChangingStatusId] = React.useState<string | null>(null);
    const [actionErrors, setActionErrors] = React.useState<Record<string, string>>({});
    const [downloadDetail, setDownloadDetail] = React.useState<PublishedDocumentDetailResponse | null>(null);
    const [replacementDraft, setReplacementDraft] = React.useState<ReplacementDraft | null>(null);
    const [replacementUploading, setReplacementUploading] = React.useState(false);
    const [replacementUploadPhase, setReplacementUploadPhase] = React.useState<ReplacementUploadPhase>('idle');
    const [replacementMessage, setReplacementMessage] = React.useState<string | null>(null);
    const [pendingConfirmation, setPendingConfirmation] = React.useState<PendingConfirmation | null>(null);
    const [reviewEventPages, setReviewEventPages] = React.useState<Record<string, number>>({});
    const statusCounts = React.useMemo(() => (
        STATUS_ACTIONS.reduce<Record<Exclude<StatusFilter, ''>, number>>((accumulator, item) => {
            accumulator[item.value] = allDocuments.filter((doc) => doc.display_status === item.value).length;
            return accumulator;
        }, {
            active: 0,
            suspended: 0,
            expired: 0,
            replaced: 0,
            annulled: 0,
        })
    ), [allDocuments]);

    const loadDocuments = React.useCallback(async (nextPage = 1) => {
        setLoading(true);
        setError(null);
        try {
            const [paged, options] = await Promise.all([
                fetchPublishedDocuments({
                    q: deferredQuery || undefined,
                    status: statusFilter || undefined,
                    page: nextPage,
                    page_size: 10,
                }),
                fetchPublishedDocuments({
                    page: 1,
                    page_size: 200,
                }),
            ]);
            setDocuments(paged);
            setAllDocuments(options.items);
            setPage(nextPage);
            setExpandedDocumentId((current) => (
                current && paged.items.some((item) => item.document_id === current) ? current : null
            ));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Không thể tải danh sách văn bản trong kho.');
        } finally {
            setLoading(false);
        }
    }, [deferredQuery, statusFilter]);

    React.useEffect(() => {
        if (!loading) {
            setSlowLoading(false);
            return;
        }
        const timer = window.setTimeout(() => setSlowLoading(true), SLOW_LOADING_THRESHOLD_MS);
        return () => window.clearTimeout(timer);
    }, [loading]);

    React.useEffect(() => {
        if (!replacementUploading) {
            setReplacementUploadPhase('idle');
            return;
        }
        setReplacementUploadPhase('uploading');
        const phases: ReplacementUploadPhase[] = ['uploading', 'parsing', 'proposals'];
        let index = 0;
        const timer = window.setInterval(() => {
            index = Math.min(index + 1, phases.length - 1);
            setReplacementUploadPhase(phases[index]);
        }, 950);
        return () => window.clearInterval(timer);
    }, [replacementUploading]);

    React.useEffect(() => {
        if (activeView !== 'view-kb') return;
        void loadDocuments(1);
    }, [activeView, loadDocuments]);

    async function loadDetail(documentId: string) {
        if (details[documentId] || detailLoadingId === documentId) return;
        setDetailLoadingId(documentId);
        setDetailErrors((current) => ({ ...current, [documentId]: '' }));
        try {
            const detail = await fetchPublishedDocumentDetail(documentId);
            setDetails((current) => ({ ...current, [documentId]: detail }));
            setMetadataDrafts((current) => ({ ...current, [documentId]: createMetadataDraft(detail) }));
            setReviewEventPages((current) => ({ ...current, [documentId]: 1 }));
            setRelationDrafts((current) => ({
                ...current,
                [documentId]: Object.fromEntries(detail.relations.map((relation) => [
                    relation.relation_id,
                    {
                        targetDocumentId: relation.target_document_id,
                        relationType: relation.relation_type as RelationType,
                        sourceLocator: relation.source_locator ?? '',
                        targetLocator: relation.target_locator ?? '',
                        note: String(relation.metadata_json?.review_note || relation.metadata_json?.note || ''),
                    },
                ])),
            }));
            setNewRelationDrafts((current) => ({ ...current, [documentId]: emptyRelationDraft() }));
        } catch (err) {
            setDetailErrors((current) => ({
                ...current,
                [documentId]: err instanceof Error ? err.message : 'Không thể tải chi tiết văn bản.',
            }));
        } finally {
            setDetailLoadingId((current) => (current === documentId ? null : current));
        }
    }

    async function toggleDocument(documentId: string) {
        if (expandedDocumentId === documentId) {
            setExpandedDocumentId(null);
            return;
        }
        setExpandedDocumentId(documentId);
        await loadDetail(documentId);
    }

    function openReviewWorkspace(searchTitle?: string, revisionId?: string) {
        try {
            if (revisionId) {
                sessionStorage.setItem(HITL_REVIEW_REVISION_KEY, revisionId);
            }
            if (searchTitle) {
                sessionStorage.setItem(HITL_REVIEW_SEARCH_KEY, searchTitle);
            }
        } catch {
            // Ignore storage issues.
        }
        if (revisionId) {
            window.dispatchEvent(new CustomEvent('app:open-review-revision', { detail: revisionId }));
        }
        window.dispatchEvent(new CustomEvent('app:navigate', { detail: 'view-hitl' }));
    }

    function openReplacementDialog(detail: PublishedDocumentDetailResponse) {
        setReplacementDraft(createReplacementDraft(detail));
        setReplacementMessage(null);
    }

    function updateReplacementDraft(patch: Partial<ReplacementDraft>) {
        setReplacementDraft((current) => {
            if (!current) return current;
            const next = { ...current, ...patch };
            if (patch.documentNumber !== undefined && patch.documentNumber !== current.documentNumber) {
                next.confirmedDocumentNumber = false;
            }
            if (
                Object.keys(patch).some((field) => (
                    ['title', 'documentNumber', 'documentType', 'documentRole', 'issuingAuthority', 'issuedDate', 'effectiveDate', 'expiryDate']
                        .includes(field)
                ))
            ) {
                next.confirmedRelationReview = false;
            }
            return next;
        });
    }

    async function handleReplacementUpload(event: React.FormEvent) {
        event.preventDefault();
        if (!replacementDraft) return;
        if (!replacementDraft.file) {
            setReplacementMessage('Cần chọn file DOCX mới trước khi tạo hồ sơ thay file nguồn.');
            return;
        }
        if (!replacementDraft.confirmedDocumentNumber) {
            setReplacementMessage('Cần xác nhận số hiệu để tránh gắn file mới vào nhầm văn bản.');
            return;
        }
        const materialChanges = replacementMaterialChanges(replacementDraft);
        if (materialChanges.length > 0 && !replacementDraft.confirmedRelationReview) {
            setReplacementMessage('Thông tin văn bản đã thay đổi. Cần xác nhận sẽ rà lại quan hệ trong hồ sơ mới.');
            return;
        }
        setReplacementUploading(true);
        setReplacementMessage(null);
        try {
            const response = await uploadKbV2ReplacementRevision(replacementDraft.documentId, {
                file: replacementDraft.file,
                title: replacementDraft.title,
                source_url: replacementDraft.sourceUrl,
                source_downloaded_at: replacementDraft.sourceDownloadedAt,
                source_note: replacementDraft.sourceNote,
                document_number: replacementDraft.documentNumber || undefined,
                document_type: normalizeDocumentType(replacementDraft.documentType) || undefined,
                document_role: normalizeDocumentRole(replacementDraft.documentRole) || undefined,
                issuing_authority: replacementDraft.issuingAuthority || undefined,
                issued_date: replacementDraft.issuedDate || undefined,
                effective_date: replacementDraft.effectiveDate || undefined,
                expiry_date: replacementDraft.expiryDate || undefined,
            });
            setReplacementUploadPhase('opening');
            setReplacementDraft(null);
            setReplacementMessage(null);
            await loadDocuments(page);
            openReviewWorkspace(undefined, response.revision.revision_id);
        } catch (err) {
            if (err instanceof KbV2DuplicateSourceError && err.revisionId) {
                setReplacementMessage(`${err.message} Hệ thống sẽ mở hồ sơ đã có trong Duyệt văn bản để bạn kiểm tra tiếp.`);
                openReviewWorkspace(undefined, err.revisionId);
                return;
            }
            setReplacementMessage(err instanceof Error ? err.message : 'Không thể tạo hồ sơ thay file nguồn.');
        } finally {
            setReplacementUploading(false);
        }
    }

    async function refreshSingleDocument(documentId: string) {
        const detail = await fetchPublishedDocumentDetail(documentId);
        setDetails((current) => ({ ...current, [documentId]: detail }));
        setMetadataDrafts((current) => ({ ...current, [documentId]: createMetadataDraft(detail) }));
        setReviewEventPages((current) => ({ ...current, [documentId]: 1 }));
        setRelationDrafts((current) => ({
            ...current,
            [documentId]: Object.fromEntries(detail.relations.map((relation) => [
                relation.relation_id,
                {
                    targetDocumentId: relation.target_document_id,
                    relationType: relation.relation_type as RelationType,
                    sourceLocator: relation.source_locator ?? '',
                    targetLocator: relation.target_locator ?? '',
                    note: String(relation.metadata_json?.review_note || relation.metadata_json?.note || ''),
                },
            ])),
        }));
    }

    async function handleSaveMetadata(documentId: string) {
        const draft = metadataDrafts[documentId];
        if (!draft) return;
        const currentDetail = details[documentId];
        setSavingMetadataId(documentId);
        setActionErrors((current) => ({ ...current, [documentId]: '' }));
        try {
            await updatePublishedDocument(documentId, {
                title: draft.title,
                document_number: draft.documentNumber || null,
                document_type: normalizeDocumentType(draft.documentType) || null,
                issuing_authority: draft.issuingAuthority || null,
                issued_date: draft.issuedDate || null,
                effective_date: draft.effectiveDate || null,
                expiry_date: draft.expiryDate || null,
                source_url: draft.sourceUrl || null,
                source_downloaded_at: draft.sourceDownloadedAt || null,
                source_note: draft.sourceNote || null,
                document_role: normalizeDocumentRole(draft.documentRole) || null,
            });
            if (
                currentDetail?.summary?.summary_id
                && draft.summary.trim() !== standardSummaryContent(currentDetail).trim()
            ) {
                await reviewKbV2Summary(currentDetail.summary.summary_id, {
                    decision: 'approved',
                    content: draft.summary.trim(),
                });
            }
            await refreshSingleDocument(documentId);
            await loadDocuments(page);
        } catch (err) {
            setActionErrors((current) => ({
                ...current,
                [documentId]: err instanceof Error ? err.message : 'Không thể lưu thông tin văn bản.',
            }));
        } finally {
            setSavingMetadataId((current) => (current === documentId ? null : current));
        }
    }

    async function handleChangeStatus(
        documentId: string,
        status: Exclude<StatusFilter, ''>,
        note: string,
        replacementDocumentId?: string,
    ) {
        setChangingStatusId(documentId);
        setActionErrors((current) => ({ ...current, [documentId]: '' }));
        try {
            await updatePublishedDocumentStatus(documentId, {
                status,
                note,
                replacement_document_id: replacementDocumentId || undefined,
            });
            await refreshSingleDocument(documentId);
            await loadDocuments(page);
        } catch (err) {
            setActionErrors((current) => ({
                ...current,
                [documentId]: err instanceof Error ? err.message : 'Không thể đổi trạng thái văn bản.',
            }));
        } finally {
            setChangingStatusId((current) => (current === documentId ? null : current));
        }
    }

    async function handleSaveRelation(documentId: string, relationId: string) {
        const draft = relationDrafts[documentId]?.[relationId];
        if (!draft) return;
        setSavingRelationKey(relationId);
        setActionErrors((current) => ({ ...current, [documentId]: '' }));
        try {
            await updateDocumentRelation(relationId, {
                target_document_id: draft.targetDocumentId,
                relation_type: draft.relationType,
                source_locator: draft.sourceLocator || undefined,
                target_locator: draft.targetLocator || undefined,
                note: draft.note || undefined,
            });
            await reviewDocumentRelation(relationId, 'approved', 'Đã cập nhật trực tiếp từ Kho văn bản.');
            await refreshSingleDocument(documentId);
        } catch (err) {
            setActionErrors((current) => ({
                ...current,
                [documentId]: err instanceof Error ? err.message : 'Không thể lưu quan hệ văn bản.',
            }));
        } finally {
            setSavingRelationKey((current) => (current === relationId ? null : current));
        }
    }

    async function handleCreateRelation(documentId: string, revisionId: string) {
        const draft = newRelationDrafts[documentId];
        if (!draft?.targetDocumentId) {
            setActionErrors((current) => ({ ...current, [documentId]: 'Hãy chọn văn bản liên quan trước khi thêm quan hệ.' }));
            return;
        }
        setSavingRelationKey(`new:${documentId}`);
        setActionErrors((current) => ({ ...current, [documentId]: '' }));
        try {
            const relation = await createDocumentRelationProposal(revisionId, {
                target_document_id: draft.targetDocumentId,
                relation_type: draft.relationType,
                source_locator: draft.sourceLocator || undefined,
                target_locator: draft.targetLocator || undefined,
                note: draft.note || undefined,
            });
            await reviewDocumentRelation(relation.relation_id, 'approved', 'Đã thêm trực tiếp từ Kho văn bản.');
            setNewRelationDrafts((current) => ({ ...current, [documentId]: emptyRelationDraft() }));
            await refreshSingleDocument(documentId);
        } catch (err) {
            setActionErrors((current) => ({
                ...current,
                [documentId]: err instanceof Error ? err.message : 'Không thể thêm quan hệ văn bản.',
            }));
        } finally {
            setSavingRelationKey((current) => (current === `new:${documentId}` ? null : current));
        }
    }

    async function handleDeleteRelation(documentId: string, relationId: string) {
        setSavingRelationKey(`delete:${relationId}`);
        setActionErrors((current) => ({ ...current, [documentId]: '' }));
        try {
            await deleteDocumentRelation(relationId);
            await refreshSingleDocument(documentId);
            await loadDocuments(page);
        } catch (err) {
            setActionErrors((current) => ({
                ...current,
                [documentId]: err instanceof Error ? err.message : 'Không thể loại bỏ quan hệ văn bản.',
            }));
        } finally {
            setSavingRelationKey((current) => (current === `delete:${relationId}` ? null : current));
        }
    }

    function requestSaveMetadata(documentId: string) {
        setPendingConfirmation({ kind: 'metadata', documentId });
    }

    function requestChangeStatus(
        documentId: string,
        status: Exclude<StatusFilter, ''>,
        replacementDocumentId?: string,
    ) {
        setPendingConfirmation({ kind: 'status', documentId, status, replacementDocumentId, note: '' });
    }

    function requestSaveRelation(documentId: string, relationId: string) {
        setPendingConfirmation({ kind: 'relation-save', documentId, relationId });
    }

    function requestDeleteRelation(documentId: string, relationId: string) {
        setPendingConfirmation({ kind: 'relation-delete', documentId, relationId });
    }

    function requestCreateRelation(documentId: string, revisionId: string) {
        const draft = newRelationDrafts[documentId];
        if (!draft?.targetDocumentId) {
            setActionErrors((current) => ({ ...current, [documentId]: 'Hãy chọn văn bản liên quan trước khi thêm quan hệ.' }));
            return;
        }
        setPendingConfirmation({ kind: 'relation-create', documentId, revisionId });
    }

    function confirmationCopy() {
        if (!pendingConfirmation) return null;

        const documentId = pendingConfirmation.documentId;
        const draft = metadataDrafts[documentId];
        const documentTitle = draft?.title || documents?.items.find((item) => item.document_id === documentId)?.title || 'văn bản này';

        if (pendingConfirmation.kind === 'metadata') {
            return {
                title: 'Lưu thông tin văn bản?',
                description: `Thông tin mới của "${documentTitle}" sẽ được cập nhật ngay trong kho văn bản.`,
                confirmLabel: 'Lưu thông tin',
            };
        }

        if (pendingConfirmation.kind === 'status') {
            const action = STATUS_ACTIONS.find((item) => item.value === pendingConfirmation.status);
            return {
                title: 'Đổi trạng thái công bố?',
                description: `Văn bản "${documentTitle}" sẽ chuyển sang trạng thái "${action?.label || pendingConfirmation.status}".`,
                confirmLabel: 'Xác nhận đổi trạng thái',
            };
        }

        if (pendingConfirmation.kind === 'relation-save') {
            return {
                title: 'Lưu quan hệ văn bản?',
                description: `Các thay đổi quan hệ của "${documentTitle}" sẽ được áp dụng ngay trong kho văn bản.`,
                confirmLabel: 'Lưu quan hệ',
            };
        }

        if (pendingConfirmation.kind === 'relation-delete') {
            return {
                title: 'Loại bỏ quan hệ văn bản?',
                description: `Quan hệ của "${documentTitle}" sẽ bị loại bỏ và thao tác được ghi vào lịch sử xử lý.`,
                confirmLabel: 'Loại bỏ quan hệ',
            };
        }

        return {
            title: 'Thêm quan hệ văn bản?',
            description: `Quan hệ mới của "${documentTitle}" sẽ được thêm ngay trong kho văn bản.`,
            confirmLabel: 'Thêm quan hệ',
        };
    }

    async function handleConfirmAction() {
        if (!pendingConfirmation) return;
        const action = pendingConfirmation;
        setPendingConfirmation(null);

        if (action.kind === 'metadata') {
            await handleSaveMetadata(action.documentId);
            return;
        }

        if (action.kind === 'status') {
            await handleChangeStatus(action.documentId, action.status, action.note, action.replacementDocumentId);
            return;
        }

        if (action.kind === 'relation-save') {
            await handleSaveRelation(action.documentId, action.relationId);
            return;
        }

        if (action.kind === 'relation-delete') {
            await handleDeleteRelation(action.documentId, action.relationId);
            return;
        }

        await handleCreateRelation(action.documentId, action.revisionId);
    }

    const totalPages = documents ? Math.max(1, Math.ceil(documents.total / documents.page_size)) : 1;
    const confirmDialog = confirmationCopy();
    const replacementChangedFields = replacementDraft ? replacementMaterialChanges(replacementDraft) : [];
    const replacementPhaseIndex = REPLACEMENT_UPLOAD_PHASES.findIndex(
        (phase) => phase.value === replacementUploadPhase,
    );

    return (
        <PageFrame
            id="view-kb"
            active={activeView === 'view-kb'}
            icon={Book}
            title="Kho văn bản"
        >
            <section className="kb-hero kb-hero-compact kb-hero-single">
                <div className="kb-hero-body">
                    <p className="kb-kicker">Kho văn bản</p>
                    <h2>Quản lý văn bản trong kho</h2>
                    <p className="kb-subtle">
                        Tra cứu và cập nhật thông tin, quan hệ, trạng thái công bố cùng file nguồn của từng văn bản.
                        File thay thế sẽ được chuyển sang Duyệt văn bản để kiểm tra trước khi áp dụng.
                    </p>
                </div>
                <div className="kb-status-strip kb-status-strip-embedded" aria-label="Tổng quan trạng thái">
                    {STATUS_ACTIONS.map((item) => (
                        <button
                            key={item.value}
                            className={`kb-status-pill ${statusTone(item.value)} ${statusFilter === item.value ? 'active' : ''}`}
                            type="button"
                            aria-pressed={statusFilter === item.value}
                            data-testid={`kb-status-${item.value}`}
                            onClick={() => setStatusFilter((current) => (current === item.value ? '' : item.value))}
                        >
                            <span>{item.label}</span>
                            <strong>{statusCounts[item.value]}</strong>
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
                        placeholder="Tìm theo tiêu đề, số hiệu hoặc cơ quan ban hành"
                    />
                </label>
                <button className="btn-secondary kb-filter-toggle" type="button" onClick={() => void loadDocuments(1)} disabled={loading}>
                    <ArrowCounterClockwise size={18} />
                    Làm mới
                </button>
            </section>

            <section className="kb-list-panel kb-list-panel-expanded">
                <div className="kb-list-header">
                    <div>
                        <h3>Danh sách văn bản trong kho</h3>
                        <p>Chỉ hiển thị văn bản đã hoặc đang được dùng trong kho. Hồ sơ đang xử lý nằm ở màn Duyệt văn bản.</p>
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
                    <div className="kb-record-list kb-list-skeleton" aria-label="Đang tải danh sách văn bản">
                        {[0, 1, 2].map((index) => (
                            <div className="kb-record kb-record-accordion skeleton-panel !mt-0 !h-28" key={index} />
                        ))}
                    </div>
                ) : documents && documents.items.length > 0 ? (
                    <>
                        <div className="kb-record-list">
                            {documents.items.map((item) => {
                                const expanded = expandedDocumentId === item.document_id;
                                const detail = details[item.document_id];
                                const metadataDraft = metadataDrafts[item.document_id];
                                const relationDraftById = relationDrafts[item.document_id] ?? {};
                                const newRelationDraft = newRelationDrafts[item.document_id] ?? emptyRelationDraft();
                                const actionError = actionErrors[item.document_id];
                                const detailError = detailErrors[item.document_id];
                                const sortedReviewEvents = detail ? sortReviewEventsByNewest(detail) : [];
                                const reviewEventPage = reviewEventPages[item.document_id] ?? 1;
                                const reviewEventTotalPages = Math.max(1, Math.ceil(sortedReviewEvents.length / REVIEW_EVENTS_PAGE_SIZE));
                                const boundedReviewEventPage = Math.min(reviewEventPage, reviewEventTotalPages);
                                const pagedReviewEvents = sortedReviewEvents.slice(
                                    (boundedReviewEventPage - 1) * REVIEW_EVENTS_PAGE_SIZE,
                                    boundedReviewEventPage * REVIEW_EVENTS_PAGE_SIZE,
                                );
                                return (
                                    <article className={`kb-record kb-record-accordion ${expanded ? 'active' : ''}`} key={item.document_id}>
                                        <div className="kb-record-header">
                                            <button className="kb-record-toggle" type="button" onClick={() => void toggleDocument(item.document_id)}>
                                                <div className="kb-record-main">
                                                    <div className="kb-record-topline">
                                                        <span className={`badge ${statusTone(item.display_status)}`}>{statusLabel(item.display_status)}</span>
                                                        <span className="kb-mini-flag">{formatDocType(item.document_type)}</span>
                                                        {item.document_number ? <span className="kb-mini-flag">{item.document_number}</span> : null}
                                                        {item.relation_count > 0 ? <span className="kb-mini-flag">Quan hệ: {item.relation_count}</span> : null}
                                                    </div>
                                                    <h4>{item.title || 'Chưa có tiêu đề'}</h4>
                                                    <div className="kb-record-meta">
                                                        <span>{item.issuing_authority || 'Chưa cập nhật cơ quan ban hành'}</span>
                                                        <span>{formatDate(item.effective_date)}</span>
                                                    </div>
                                                </div>
                                                <span className={`kb-expand-indicator ${expanded ? 'open' : ''}`} aria-hidden="true">
                                                    <CaretDown size={18} />
                                                </span>
                                            </button>
                                        </div>

                                        {expanded ? (
                                            <div className="kb-inline-detail">
                                                {detailLoadingId === item.document_id && !detail ? (
                                                    <div className="empty-state">
                                                        <strong>Đang tải chi tiết văn bản</strong>
                                                        <p>Hệ thống đang mở thông tin đầy đủ của văn bản này.</p>
                                                    </div>
                                                ) : null}

                                                {detailError ? <p className="kb-inline-error">{detailError}</p> : null}

                                                {detail && metadataDraft ? (
                                                    <>
                                                        <div className="kb-detail-grid">
                                                            <details className="kb-detail-accordion" open>
                                                                <summary className="kb-detail-summary">
                                                                    <div>
                                                                        <strong>Thông tin văn bản</strong>
                                                                        <span>{formatDocType(metadataDraft.documentType)} · {formatDocumentRole(metadataDraft.documentRole)}</span>
                                                                    </div>
                                                                    <CaretDown size={18} />
                                                                </summary>
                                                                <section className="review-section review-field-span">
                                                                    <div className="review-compact-grid">
                                                                        <label>
                                                                            <span>Tiêu đề</span>
                                                                            <input
                                                                                value={metadataDraft.title}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, title: event.target.value },
                                                                                }))}
                                                                            />
                                                                        </label>
                                                                        <label>
                                                                            <span>Số hiệu</span>
                                                                            <input
                                                                                value={metadataDraft.documentNumber}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, documentNumber: event.target.value },
                                                                                }))}
                                                                            />
                                                                        </label>
                                                                        <label>
                                                                            <span>Loại văn bản</span>
                                                                            <select
                                                                                value={metadataDraft.documentType}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, documentType: event.target.value },
                                                                                }))}
                                                                            >
                                                                                <option value="">Chọn loại văn bản</option>
                                                                                {DOCUMENT_TYPE_OPTIONS.map((option) => (
                                                                                    <option key={option.value} value={option.value}>{option.label}</option>
                                                                                ))}
                                                                            </select>
                                                                        </label>
                                                                        <label>
                                                                            <span>Cơ quan ban hành</span>
                                                                            <input
                                                                                value={metadataDraft.issuingAuthority}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, issuingAuthority: event.target.value },
                                                                                }))}
                                                                            />
                                                                        </label>
                                                                        <label>
                                                                            <span>Ngày ban hành</span>
                                                                        <DateInput
                                                                            value={metadataDraft.issuedDate}
                                                                            onChange={(value) => setMetadataDrafts((current) => ({
                                                                                ...current,
                                                                                [item.document_id]: { ...metadataDraft, issuedDate: value },
                                                                            }))}
                                                                        />
                                                                            <small className="text-xs text-slate-500">Nhập theo thứ tự ngày, tháng, năm để dễ đối chiếu với văn bản gốc.</small>
                                                                        </label>
                                                                        <label>
                                                                            <span>Hiệu lực từ</span>
                                                                        <DateInput
                                                                            value={metadataDraft.effectiveDate}
                                                                            onChange={(value) => setMetadataDrafts((current) => ({
                                                                                ...current,
                                                                                [item.document_id]: { ...metadataDraft, effectiveDate: value },
                                                                            }))}
                                                                        />
                                                                            <small className="text-xs text-slate-500">Có thể để trống nếu văn bản chưa ghi rõ ngày bắt đầu có hiệu lực.</small>
                                                                        </label>
                                                                        <label>
                                                                            <span>Hết hiệu lực</span>
                                                                        <DateInput
                                                                            value={metadataDraft.expiryDate}
                                                                            onChange={(value) => setMetadataDrafts((current) => ({
                                                                                ...current,
                                                                                [item.document_id]: { ...metadataDraft, expiryDate: value },
                                                                            }))}
                                                                        />
                                                                            <small className="text-xs text-slate-500">Chỉ nhập khi đã có thông tin hết hiệu lực chính thức.</small>
                                                                        </label>
                                                                        <label>
                                                                            <span>Vai trò văn bản</span>
                                                                            <select
                                                                                value={metadataDraft.documentRole}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, documentRole: event.target.value },
                                                                                }))}
                                                                            >
                                                                                <option value="">Chọn vai trò</option>
                                                                                {DOCUMENT_ROLE_OPTIONS.map((option) => (
                                                                                    <option key={option.value} value={option.value}>{option.label}</option>
                                                                                ))}
                                                                            </select>
                                                                        </label>
                                                                        <label className="review-field-span">
                                                                            <span>Đường dẫn nguồn</span>
                                                                            <input
                                                                                value={metadataDraft.sourceUrl}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, sourceUrl: event.target.value },
                                                                                }))}
                                                                            />
                                                                        </label>
                                                                        <label>
                                                                            <span>Ngày lấy nguồn</span>
                                                                        <DateInput
                                                                            value={metadataDraft.sourceDownloadedAt}
                                                                            onChange={(value) => setMetadataDrafts((current) => ({
                                                                                ...current,
                                                                                [item.document_id]: { ...metadataDraft, sourceDownloadedAt: value },
                                                                            }))}
                                                                        />
                                                                        </label>
                                                                        <label className="review-field-span">
                                                                            <span>Tóm tắt</span>
                                                                            <textarea
                                                                                value={metadataDraft.summary}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, summary: event.target.value },
                                                                                }))}
                                                                                rows={4}
                                                                            />
                                                                        </label>
                                                                        <label className="review-field-span">
                                                                            <span>Ghi chú nguồn</span>
                                                                            <textarea
                                                                                value={metadataDraft.sourceNote}
                                                                                onChange={(event) => setMetadataDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...metadataDraft, sourceNote: event.target.value },
                                                                                }))}
                                                                                rows={3}
                                                                            />
                                                                        </label>
                                                                    </div>
                                                                    <div className="kb-action-buttons">
                                                                        <button
                                                                            className="btn-primary"
                                                                            type="button"
                                                                            onClick={() => requestSaveMetadata(item.document_id)}
                                                                            disabled={savingMetadataId === item.document_id}
                                                                        >
                                                                            <NotePencil size={18} />
                                                                            {savingMetadataId === item.document_id ? 'Đang lưu' : 'Lưu thông tin'}
                                                                        </button>
                                                                        <button className="btn-secondary" type="button" onClick={() => openReplacementDialog(detail)}>
                                                                            <FileArrowUp size={18} />
                                                                            Thay file nguồn
                                                                        </button>
                                                                        <button className="btn-secondary" type="button" onClick={() => setDownloadDetail(detail)}>
                                                                            <DownloadSimple size={18} />
                                                                            Tải file nguồn
                                                                        </button>
                                                                    </div>
                                                                </section>
                                                            </details>

                                                            <details className="kb-detail-accordion">
                                                                <summary className="kb-detail-summary">
                                                                    <div>
                                                                        <strong>Trạng thái công bố</strong>
                                                                        <span>{statusLabel(item.display_status)} · {visibilityLabel(item.display_status)} trên trang tra cứu</span>
                                                                    </div>
                                                                    <CaretDown size={18} />
                                                                </summary>
                                                                <section className="review-section review-field-span">
                                                                    <div className="kb-relation-suggestion-list">
                                                                        {STATUS_ACTIONS.map((action) => (
                                                                            <article className="kb-relation-suggestion" key={action.value}>
                                                                                <div>
                                                                                    <strong>{action.label}</strong>
                                                                                    <span>{action.helper}</span>
                                                                                </div>
                                                                                <button
                                                                                    className="btn-secondary"
                                                                                    type="button"
                                                                                    disabled={changingStatusId === item.document_id}
                                                                                    onClick={() => requestChangeStatus(
                                                                                        item.document_id,
                                                                                        action.value,
                                                                                        action.value === 'replaced'
                                                                                            ? relationDraftById[Object.keys(relationDraftById)[0] || '']?.targetDocumentId
                                                                                            : undefined,
                                                                                    )}
                                                                                >
                                                                                    Áp dụng
                                                                                </button>
                                                                            </article>
                                                                        ))}
                                                                    </div>
                                                                </section>
                                                            </details>

                                                            <details className="kb-detail-accordion">
                                                                <summary className="kb-detail-summary">
                                                                    <div>
                                                                        <strong>Quan hệ văn bản</strong>
                                                                        <span>{detail.relations.length} quan hệ đang hiển thị</span>
                                                                    </div>
                                                                    <CaretDown size={18} />
                                                                </summary>
                                                                <section className="review-section review-field-span">
                                                                    {detail.relations.length === 0 ? (
                                                                        <div className="empty-state">
                                                                            <strong>Chưa có quan hệ văn bản</strong>
                                                                            <p>Hãy thêm quan hệ nếu văn bản này sửa đổi, thay thế, hướng dẫn hoặc cần văn bản nền để đối chiếu.</p>
                                                                        </div>
                                                                    ) : (
                                                                        <div className="kb-record-list">
                                                                            {detail.relations.map((relation) => {
                                                                                const draft = relationDraftById[relation.relation_id];
                                                                                if (!draft) return null;
                                                                                const incoming = relation.target_document_id === item.document_id;
                                                                                if (incoming) {
                                                                                    return (
                                                                                        <article className="kb-relation-editor-shell" key={relation.relation_id}>
                                                                                            <div className="kb-record-topline">
                                                                                                <span className={`badge ${relationReviewTone(relation.review_status)}`}>{relation.review_status === 'approved' ? 'Đã lưu' : 'Cần kiểm tra tại văn bản nguồn'}</span>
                                                                                                <span className="kb-mini-flag">{relationDisplayText(relation, allDocuments, item.document_id)}</span>
                                                                                            </div>
                                                                                            <p className="text-sm text-slate-500">Quan hệ này được quản lý tại văn bản nguồn nên chỉ hiển thị để đối chiếu tại đây.</p>
                                                                                        </article>
                                                                                    );
                                                                                }
                                                                                return (
                                                                                    <article className="kb-relation-editor-shell" key={relation.relation_id}>
                                                                                        <div className="kb-record-topline">
                                                                                            <span className={`badge ${relationReviewTone(relation.review_status)}`}>{relation.review_status === 'approved' ? 'Đã lưu' : 'Cần kiểm tra lại'}</span>
                                                                                            <span className="kb-mini-flag">{relationDisplayText(relation, allDocuments, item.document_id)}</span>
                                                                                        </div>
                                                                                        <div className="kb-relation-form-grid">
                                                                                            <label className="filter-group">
                                                                                                <span>Văn bản liên quan</span>
                                                                                                <select
                                                                                                    value={draft.targetDocumentId}
                                                                                                    onChange={(event) => setRelationDrafts((current) => ({
                                                                                                        ...current,
                                                                                                        [item.document_id]: {
                                                                                                            ...relationDraftById,
                                                                                                            [relation.relation_id]: { ...draft, targetDocumentId: event.target.value },
                                                                                                        },
                                                                                                    }))}
                                                                                                >
                                                                                                    <option value="">Chọn văn bản liên quan</option>
                                                                                                    {allDocuments
                                                                                                        .filter((option) => option.document_id !== item.document_id)
                                                                                                        .map((option) => (
                                                                                                            <option key={option.document_id} value={option.document_id}>
                                                                                                                {option.document_number || option.title || option.document_id}
                                                                                                            </option>
                                                                                                        ))}
                                                                                                </select>
                                                                                            </label>
                                                                                            <label className="filter-group">
                                                                                                <span>Loại quan hệ</span>
                                                                                                <select
                                                                                                    value={draft.relationType}
                                                                                                    onChange={(event) => setRelationDrafts((current) => ({
                                                                                                        ...current,
                                                                                                        [item.document_id]: {
                                                                                                            ...relationDraftById,
                                                                                                            [relation.relation_id]: { ...draft, relationType: event.target.value as RelationType },
                                                                                                        },
                                                                                                    }))}
                                                                                                >
                                                                                                    {RELATION_OPTIONS.map((option) => (
                                                                                                        <option key={option.value} value={option.value}>{option.label}</option>
                                                                                                    ))}
                                                                                                </select>
                                                                                            </label>
                                                                                            <label className="filter-group">
                                                                                                <span>Vị trí trong văn bản này</span>
                                                                                                <input
                                                                                                    value={draft.sourceLocator}
                                                                                                    onChange={(event) => setRelationDrafts((current) => ({
                                                                                                        ...current,
                                                                                                        [item.document_id]: {
                                                                                                            ...relationDraftById,
                                                                                                            [relation.relation_id]: { ...draft, sourceLocator: event.target.value },
                                                                                                        },
                                                                                                    }))}
                                                                                                />
                                                                                            </label>
                                                                                            <label className="filter-group">
                                                                                                <span>Vị trí trong văn bản liên quan</span>
                                                                                                <input
                                                                                                    value={draft.targetLocator}
                                                                                                    onChange={(event) => setRelationDrafts((current) => ({
                                                                                                        ...current,
                                                                                                        [item.document_id]: {
                                                                                                            ...relationDraftById,
                                                                                                            [relation.relation_id]: { ...draft, targetLocator: event.target.value },
                                                                                                        },
                                                                                                    }))}
                                                                                                />
                                                                                            </label>
                                                                                        </div>
                                                                                        <label className="filter-group">
                                                                                            <span>Ghi chú</span>
                                                                                            <textarea
                                                                                                value={draft.note}
                                                                                                onChange={(event) => setRelationDrafts((current) => ({
                                                                                                    ...current,
                                                                                                    [item.document_id]: {
                                                                                                        ...relationDraftById,
                                                                                                        [relation.relation_id]: { ...draft, note: event.target.value },
                                                                                                    },
                                                                                                }))}
                                                                                                rows={2}
                                                                                            />
                                                                                        </label>
                                                                                        <p className="text-sm text-slate-500">
                                                                                            {RELATION_OPTIONS.find((option) => option.value === draft.relationType)?.helper}
                                                                                        </p>
                                                                                        <div className="kb-action-buttons">
                                                                                            <button
                                                                                                className="btn-secondary"
                                                                                                type="button"
                                                                                                onClick={() => requestSaveRelation(item.document_id, relation.relation_id)}
                                                                                                disabled={savingRelationKey === relation.relation_id}
                                                                                            >
                                                                                                <Link size={18} />
                                                                                                {savingRelationKey === relation.relation_id ? 'Đang lưu' : 'Lưu quan hệ'}
                                                                                            </button>
                                                                                            <button
                                                                                                className="btn-secondary"
                                                                                                type="button"
                                                                                                onClick={() => requestDeleteRelation(item.document_id, relation.relation_id)}
                                                                                                disabled={Boolean(savingRelationKey)}
                                                                                            >
                                                                                                Loại bỏ
                                                                                            </button>
                                                                                        </div>
                                                                                    </article>
                                                                                );
                                                                            })}
                                                                        </div>
                                                                    )}

                                                                    <article className="kb-relation-editor-shell">
                                                                        <div className="kb-record-topline">
                                                                            <span className="kb-mini-flag">Thêm quan hệ mới</span>
                                                                        </div>
                                                                        <div className="kb-relation-form-grid">
                                                                            <label className="filter-group">
                                                                                <span>Văn bản liên quan</span>
                                                                                <select
                                                                                    value={newRelationDraft.targetDocumentId}
                                                                                    onChange={(event) => setNewRelationDrafts((current) => ({
                                                                                        ...current,
                                                                                        [item.document_id]: { ...newRelationDraft, targetDocumentId: event.target.value },
                                                                                    }))}
                                                                                >
                                                                                    <option value="">Chọn văn bản liên quan</option>
                                                                                    {allDocuments
                                                                                        .filter((option) => option.document_id !== item.document_id)
                                                                                        .map((option) => (
                                                                                            <option key={option.document_id} value={option.document_id}>
                                                                                                {option.document_number || option.title || option.document_id}
                                                                                            </option>
                                                                                        ))}
                                                                                </select>
                                                                            </label>
                                                                            <label className="filter-group">
                                                                                <span>Loại quan hệ</span>
                                                                                <select
                                                                                    value={newRelationDraft.relationType}
                                                                                    onChange={(event) => setNewRelationDrafts((current) => ({
                                                                                        ...current,
                                                                                        [item.document_id]: { ...newRelationDraft, relationType: event.target.value as RelationType },
                                                                                    }))}
                                                                                >
                                                                                    {RELATION_OPTIONS.map((option) => (
                                                                                        <option key={option.value} value={option.value}>{option.label}</option>
                                                                                    ))}
                                                                                </select>
                                                                            </label>
                                                                            <label className="filter-group">
                                                                                <span>Vị trí trong văn bản này</span>
                                                                                <input
                                                                                    value={newRelationDraft.sourceLocator}
                                                                                    onChange={(event) => setNewRelationDrafts((current) => ({
                                                                                        ...current,
                                                                                        [item.document_id]: { ...newRelationDraft, sourceLocator: event.target.value },
                                                                                    }))}
                                                                                />
                                                                            </label>
                                                                            <label className="filter-group">
                                                                                <span>Vị trí trong văn bản liên quan</span>
                                                                                <input
                                                                                    value={newRelationDraft.targetLocator}
                                                                                    onChange={(event) => setNewRelationDrafts((current) => ({
                                                                                        ...current,
                                                                                        [item.document_id]: { ...newRelationDraft, targetLocator: event.target.value },
                                                                                    }))}
                                                                                />
                                                                            </label>
                                                                        </div>
                                                                        <label className="filter-group">
                                                                            <span>Ghi chú</span>
                                                                            <textarea
                                                                                value={newRelationDraft.note}
                                                                                onChange={(event) => setNewRelationDrafts((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: { ...newRelationDraft, note: event.target.value },
                                                                                }))}
                                                                                rows={2}
                                                                            />
                                                                        </label>
                                                                        <div className="kb-action-buttons">
                                                                            <button
                                                                                className="btn-secondary"
                                                                                type="button"
                                                                                onClick={() => requestCreateRelation(item.document_id, detail.revision.revision_id)}
                                                                                disabled={savingRelationKey === `new:${item.document_id}`}
                                                                            >
                                                                                <Link size={18} />
                                                                                {savingRelationKey === `new:${item.document_id}` ? 'Đang thêm' : 'Thêm quan hệ'}
                                                                            </button>
                                                                        </div>
                                                                    </article>
                                                                </section>
                                                            </details>

                                                            <details className="kb-detail-accordion">
                                                                <summary className="kb-detail-summary">
                                                                    <div>
                                                                        <strong>Lịch sử xử lý</strong>
                                                                        <span>{detail.review_events.length} mốc xử lý đã ghi nhận</span>
                                                                    </div>
                                                                    <CaretDown size={18} />
                                                                </summary>
                                                                <section className="review-section review-field-span">
                                                                    <div className="kb-history-list">
                                                                        {detail.review_events.length === 0 ? (
                                                                            <article className="kb-history-card">
                                                                                <p>Chưa có lịch sử xử lý hiển thị cho văn bản này.</p>
                                                                            </article>
                                                                        ) : pagedReviewEvents.map((event) => (
                                                                            <article className="kb-history-card" key={event.review_event_id}>
                                                                                <div className="kb-history-top">
                                                                                    <strong>{formatHistoryEntity(event.entity_type)}</strong>
                                                                                    <span>{formatDateTime(event.created_at)}</span>
                                                                                </div>
                                                                                <p>Thao tác: {formatReviewDecision(event.decision)}</p>
                                                                            </article>
                                                                        ))}
                                                                    </div>
                                                                    {detail.review_events.length > REVIEW_EVENTS_PAGE_SIZE ? (
                                                                        <div className="pagination">
                                                                            <button
                                                                                className="btn-secondary"
                                                                                type="button"
                                                                                disabled={boundedReviewEventPage <= 1}
                                                                                onClick={() => setReviewEventPages((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: Math.max(1, boundedReviewEventPage - 1),
                                                                                }))}
                                                                            >
                                                                                Trước
                                                                            </button>
                                                                            <span>Trang {boundedReviewEventPage} / {reviewEventTotalPages}</span>
                                                                            <button
                                                                                className="btn-secondary"
                                                                                type="button"
                                                                                disabled={boundedReviewEventPage >= reviewEventTotalPages}
                                                                                onClick={() => setReviewEventPages((current) => ({
                                                                                    ...current,
                                                                                    [item.document_id]: Math.min(reviewEventTotalPages, boundedReviewEventPage + 1),
                                                                                }))}
                                                                            >
                                                                                Sau
                                                                            </button>
                                                                        </div>
                                                                    ) : null}
                                                                </section>
                                                            </details>
                                                        </div>

                                                        {actionError ? <p className="kb-inline-error">{actionError}</p> : null}
                                                    </>
                                                ) : null}
                                            </div>
                                        ) : null}
                                    </article>
                                );
                            })}
                        </div>

                        <div className="pagination">
                            <button className="btn-secondary" type="button" disabled={page <= 1 || loading} onClick={() => void loadDocuments(page - 1)}>
                                Trước
                            </button>
                            <span>Trang {page} / {totalPages}</span>
                            <button className="btn-secondary" type="button" disabled={page >= totalPages || loading} onClick={() => void loadDocuments(page + 1)}>
                                Sau
                            </button>
                        </div>
                    </>
                ) : (
                    <div className="empty-state">
                        <span className="empty-state-icon"><FileText size={30} weight="duotone" /></span>
                        <strong>Chưa có văn bản phù hợp</strong>
                        <p>Hãy đổi từ khóa tìm kiếm, bộ lọc trạng thái hoặc chuyển sang Duyệt văn bản để công bố thêm văn bản mới.</p>
                    </div>
                )}
            </section>

            {replacementDraft ? (
                <div
                    className="admin-modal-backdrop replacement-dialog-backdrop"
                    role="presentation"
                    onClick={() => {
                        if (!replacementUploading) setReplacementDraft(null);
                    }}
                >
                    <section
                        className="admin-modal replacement-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Thay file nguồn"
                        aria-busy={replacementUploading}
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head replacement-dialog-head">
                            <div className="review-editor-head-copy">
                                <p className="kb-kicker">Thay file nguồn</p>
                                <h3>{replacementDraft.documentNumber || replacementDraft.title}</h3>
                            </div>
                            <button
                                className="admin-modal-close"
                                type="button"
                                disabled={replacementUploading}
                                onClick={() => setReplacementDraft(null)}
                                aria-label="Đóng"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body replacement-dialog-body">
                            <section className="kb-warning-card">
                                <WarningCircle size={18} />
                                <div className="kb-warning-copy">
                                    <strong>Bản đang công bố vẫn được giữ nguyên</strong>
                                    <p>
                                        File mới sẽ tạo một hồ sơ xử lý trong Duyệt văn bản. Trang tra cứu và chatbot chỉ chuyển sang bản mới sau khi hồ sơ này được duyệt và đưa vào kho.
                                    </p>
                                </div>
                            </section>
                            <form
                                className={`replacement-form ${replacementUploading ? 'is-uploading' : ''}`}
                                onSubmit={handleReplacementUpload}
                            >
                                <label className="filter-group replacement-field-full" htmlFor="kb-replacement-file">
                                    <span>File DOCX mới</span>
                                    <input
                                        id="kb-replacement-file"
                                        type="file"
                                        accept=".docx"
                                        onChange={(event) => updateReplacementDraft({ file: event.target.files?.[0] ?? null })}
                                        required
                                    />
                                    <small>Chọn bản nguồn mới cần đưa qua luồng duyệt. Nếu file trùng bản đã có, hệ thống sẽ mở hồ sơ hiện có thay vì tạo bản lặp.</small>
                                </label>
                                <label className="filter-group replacement-field-full" htmlFor="kb-replacement-title">
                                    <span>Tiêu đề</span>
                                    <textarea
                                        id="kb-replacement-title"
                                        className="auto-resize-textarea"
                                        value={replacementDraft.title}
                                        onChange={(event) => updateReplacementDraft({ title: event.target.value })}
                                        required
                                    />
                                </label>
                                <label className="filter-group replacement-field-full" htmlFor="kb-replacement-source-url">
                                    <span>Đường dẫn nguồn</span>
                                    <input
                                        id="kb-replacement-source-url"
                                        value={replacementDraft.sourceUrl}
                                        onChange={(event) => updateReplacementDraft({ sourceUrl: event.target.value })}
                                        required
                                    />
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-downloaded-at">
                                    <span>Ngày lấy nguồn</span>
                                    <DateInput
                                        id="kb-replacement-downloaded-at"
                                        value={replacementDraft.sourceDownloadedAt}
                                        onChange={(value) => updateReplacementDraft({ sourceDownloadedAt: value })}
                                        required
                                    />
                                </label>
                                <label className="filter-group replacement-field-full" htmlFor="kb-replacement-note">
                                    <span>Ghi chú nguồn</span>
                                    <textarea
                                        id="kb-replacement-note"
                                        rows={2}
                                        value={replacementDraft.sourceNote}
                                        onChange={(event) => updateReplacementDraft({ sourceNote: event.target.value })}
                                        required
                                    />
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-number">
                                    <span>Số hiệu</span>
                                    <input
                                        id="kb-replacement-number"
                                        value={replacementDraft.documentNumber}
                                        onChange={(event) => updateReplacementDraft({ documentNumber: event.target.value })}
                                    />
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-type">
                                    <span>Loại văn bản</span>
                                    <select
                                        id="kb-replacement-type"
                                        value={replacementDraft.documentType}
                                        onChange={(event) => updateReplacementDraft({ documentType: event.target.value })}
                                    >
                                        <option value="">Chọn loại văn bản</option>
                                        {DOCUMENT_TYPE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-role">
                                    <span>Vai trò văn bản</span>
                                    <select
                                        id="kb-replacement-role"
                                        value={replacementDraft.documentRole}
                                        onChange={(event) => updateReplacementDraft({ documentRole: event.target.value })}
                                    >
                                        <option value="">Chọn vai trò</option>
                                        {DOCUMENT_ROLE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-issuer">
                                    <span>Cơ quan ban hành</span>
                                    <input
                                        id="kb-replacement-issuer"
                                        value={replacementDraft.issuingAuthority}
                                        onChange={(event) => updateReplacementDraft({ issuingAuthority: event.target.value })}
                                    />
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-issued-date">
                                    <span>Ngày ban hành</span>
                                    <DateInput
                                        id="kb-replacement-issued-date"
                                        value={replacementDraft.issuedDate}
                                        onChange={(value) => updateReplacementDraft({ issuedDate: value })}
                                    />
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-effective-date">
                                    <span>Ngày có hiệu lực</span>
                                    <DateInput
                                        id="kb-replacement-effective-date"
                                        value={replacementDraft.effectiveDate}
                                        onChange={(value) => updateReplacementDraft({ effectiveDate: value })}
                                    />
                                </label>
                                <label className="filter-group" htmlFor="kb-replacement-expiry-date">
                                    <span>Ngày hết hiệu lực</span>
                                    <DateInput
                                        id="kb-replacement-expiry-date"
                                        value={replacementDraft.expiryDate}
                                        onChange={(value) => updateReplacementDraft({ expiryDate: value })}
                                    />
                                </label>
                                <section className="replacement-verification replacement-field-full">
                                    <div>
                                        <strong>Xác nhận đúng văn bản</strong>
                                        <p>
                                            File mới sẽ được gắn vào số hiệu <b>{replacementDraft.documentNumber || 'chưa cập nhật'}</b>.
                                            Hãy kiểm tra kỹ trước khi tạo hồ sơ.
                                        </p>
                                    </div>
                                    <label>
                                        <input
                                            type="checkbox"
                                            checked={replacementDraft.confirmedDocumentNumber}
                                            onChange={(event) => updateReplacementDraft({ confirmedDocumentNumber: event.target.checked })}
                                        />
                                        <span>Tôi xác nhận đây là file mới của đúng văn bản trên.</span>
                                    </label>
                                    {replacementChangedFields.length > 0 ? (
                                        <label className="is-warning">
                                            <input
                                                type="checkbox"
                                                checked={replacementDraft.confirmedRelationReview}
                                                onChange={(event) => updateReplacementDraft({ confirmedRelationReview: event.target.checked })}
                                            />
                                            <span>
                                                Thông tin pháp lý đã thay đổi ở {replacementChangedFields.length} mục.
                                                Tôi sẽ rà lại quan hệ văn bản trong hồ sơ mới trước khi đưa vào kho.
                                            </span>
                                        </label>
                                    ) : null}
                                </section>
                                {replacementUploading ? (
                                    <section
                                        className="review-upload-progress replacement-field-full"
                                        aria-label="Tiến trình tạo hồ sơ thay file"
                                    >
                                        <div className="review-upload-progress-head">
                                            <strong>{REPLACEMENT_UPLOAD_PHASES[Math.max(replacementPhaseIndex, 0)]?.label ?? 'Đang xử lý'}</strong>
                                            <span>{REPLACEMENT_UPLOAD_PHASES[Math.max(replacementPhaseIndex, 0)]?.description ?? 'Vui lòng chờ trong giây lát.'}</span>
                                        </div>
                                        <div className="review-upload-progress-track" aria-hidden="true">
                                            <span style={{ width: `${Math.max(replacementPhaseIndex + 1, 1) / REPLACEMENT_UPLOAD_PHASES.length * 100}%` }} />
                                        </div>
                                        <div className="review-upload-progress-steps">
                                            {REPLACEMENT_UPLOAD_PHASES.map((phase, index) => (
                                                <span key={phase.value} className={index <= replacementPhaseIndex ? 'is-active' : ''}>{phase.label}</span>
                                            ))}
                                        </div>
                                    </section>
                                ) : null}
                                {replacementMessage ? <p className="kb-inline-error replacement-field-full">{replacementMessage}</p> : null}
                                <div className="replacement-dialog-footer replacement-field-full">
                                    <button className="btn-secondary" type="button" disabled={replacementUploading} onClick={() => setReplacementDraft(null)}>
                                        Hủy
                                    </button>
                                    <button className="btn-primary" type="submit" disabled={replacementUploading}>
                                        <FileArrowUp size={18} />
                                        {replacementUploading ? 'Đang tạo hồ sơ' : 'Tạo hồ sơ thay file'}
                                    </button>
                                </div>
                            </form>
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

            {confirmDialog ? (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setPendingConfirmation(null)}>
                    <section
                        className="admin-modal review-confirm-dialog"
                        role="alertdialog"
                        aria-modal="true"
                        aria-label={confirmDialog.title}
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <h3>{confirmDialog.title}</h3>
                            <button className="admin-modal-close" type="button" onClick={() => setPendingConfirmation(null)} aria-label="Đóng">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body">
                            <div className="kb-warning-card">
                                <WarningCircle size={18} />
                                <div className="kb-warning-copy">
                                    <strong>Xác nhận trước khi tiếp tục</strong>
                                    <p>{confirmDialog.description}</p>
                                </div>
                            </div>
                            {pendingConfirmation?.kind === 'status' ? (
                                <label className="filter-group" htmlFor="kb-status-change-note">
                                    <span>Ghi chú thay đổi trạng thái</span>
                                    <textarea
                                        id="kb-status-change-note"
                                        value={pendingConfirmation.note}
                                        onChange={(event) => setPendingConfirmation((current) => (
                                            current?.kind === 'status'
                                                ? { ...current, note: event.target.value }
                                                : current
                                        ))}
                                        placeholder="Có thể để trống nếu không cần ghi chú"
                                        rows={3}
                                    />
                                    <small>Ghi chú sẽ được lưu trong lịch sử xử lý của văn bản.</small>
                                </label>
                            ) : null}
                            <div className="mt-5 flex flex-wrap justify-end gap-2">
                                <button className="btn-secondary" type="button" onClick={() => setPendingConfirmation(null)}>
                                    Hủy
                                </button>
                                <button className="btn-primary" type="button" onClick={() => void handleConfirmAction()}>
                                    {confirmDialog.confirmLabel}
                                </button>
                            </div>
                        </div>
                    </section>
                </div>
            ) : null}
        </PageFrame>
    );
}
