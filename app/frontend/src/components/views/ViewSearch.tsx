import React from 'react';
import Image from 'next/image';
import {
    ArrowCounterClockwise,
    CaretDown,
    DownloadSimple,
    Faders,
    FileText,
    MagnifyingGlass,
    X,
} from '@phosphor-icons/react';
import {
    type DocumentSearchParams,
    type DocumentsResponse,
    type TrafficSign,
    fetchDocuments,
    fetchTrafficSigns,
} from '../../lib/api';

const DOCUMENT_TYPES = [
    { value: '', label: 'Tất cả loại văn bản' },
    { value: 'LUAT', label: 'Luật' },
    { value: 'BO_LUAT', label: 'Bộ luật' },
    { value: 'NGHI_DINH', label: 'Nghị định' },
    { value: 'THONG_TU', label: 'Thông tư' },
    { value: 'QUYET_DINH', label: 'Quyết định' },
    { value: 'CONG_VAN', label: 'Công văn' },
    { value: 'QCVN', label: 'Quy chuẩn kỹ thuật' },
];

const EFFECTIVE_YEARS = ['', '2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019'];
const DOCUMENTS_PER_PAGE = 10;

type AppliedFilters = {
    query: string;
    docType: string;
    issuer: string;
    year: string;
};

const EMPTY_FILTERS: AppliedFilters = {
    query: '',
    docType: '',
    issuer: '',
    year: '',
};

function formatDate(value: string | null) {
    if (!value) return 'Chưa cập nhật';
    return new Date(value).toLocaleDateString('vi-VN');
}

function formatSourceLabel(sourceUrl: string | null) {
    return sourceUrl ? 'Thư viện pháp luật' : 'Chưa cập nhật';
}

function getDocumentTypeLabel(value: string) {
    return DOCUMENT_TYPES.find((item) => item.value === value)?.label ?? value;
}

function formatDocumentStatus(value: string) {
    return {
        active: 'Đang hiệu lực',
        future_effective: 'Sắp có hiệu lực',
        expired: 'Hết hiệu lực',
        suspended: 'Tạm ngừng công bố',
    }[value] ?? value;
}

function formatRelationType(value: string) {
    return {
        amends: 'Sửa đổi',
        supplements: 'Bổ sung',
        replaces: 'Thay thế',
        annuls: 'Bãi bỏ',
        guides: 'Hướng dẫn',
        depends_on: 'Căn cứ liên quan',
    }[value] ?? 'Quan hệ văn bản';
}

function formatRelationDirection(value: string) {
    return value === 'incoming' ? 'Văn bản khác liên quan đến văn bản này' : 'Văn bản này liên quan đến';
}

export default function ViewSearch({ activeView }: { activeView: string }) {
    const [query, setQuery] = React.useState('');
    const [docType, setDocType] = React.useState('');
    const [agency, setAgency] = React.useState('');
    const [year, setYear] = React.useState('');
    const [page, setPage] = React.useState(1);
    const [results, setResults] = React.useState<DocumentsResponse | null>(null);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);
    const [trafficSigns, setTrafficSigns] = React.useState<TrafficSign[]>([]);
    const [appliedFilters, setAppliedFilters] = React.useState<AppliedFilters>(EMPTY_FILTERS);
    const [filtersOpen, setFiltersOpen] = React.useState(false);
    const [expandedDocId, setExpandedDocId] = React.useState<string | null>(null);
    const [downloadWarningDoc, setDownloadWarningDoc] = React.useState<DocumentsResponse['items'][number] | null>(null);
    const resultsRef = React.useRef<HTMLElement>(null);

    const toggleExpandedDoc = React.useCallback((docId: string) => {
        setExpandedDocId((current) => (current === docId ? null : docId));
    }, []);

    const runSearch = React.useCallback(async (
        filters: AppliedFilters,
        targetPage: number,
        scrollToResults = false,
    ) => {
        setLoading(true);
        setError(null);
        try {
            const params: DocumentSearchParams = {
                q: filters.query || undefined,
                doc_type: filters.docType || undefined,
                issuer: filters.issuer || undefined,
                year: filters.year ? Number(filters.year) : undefined,
                page: targetPage,
                page_size: DOCUMENTS_PER_PAGE,
            };
            const [res, signResult] = await Promise.all([
                fetchDocuments(params),
                filters.query
                    ? fetchTrafficSigns(filters.query).catch(() => ({ items: [], total: 0 }))
                    : Promise.resolve({ items: [], total: 0 }),
            ]);
            setResults(res);
            setTrafficSigns(signResult.items);
            setAppliedFilters(filters);
            setPage(targetPage);
            setExpandedDocId(null);
            if (scrollToResults) {
                requestAnimationFrame(() => {
                    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
            }
        } catch (err: unknown) {
            console.error('Error fetching documents:', err);
            setError(err instanceof Error ? err.message : 'Không thể kết nối tới máy chủ.');
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        void runSearch(EMPTY_FILTERS, 1);
    }, [runSearch]);

    function getDraftFilters(): AppliedFilters {
        return {
            query: query.trim(),
            docType,
            issuer: agency.trim(),
            year,
        };
    }

    function handleSubmit(event: React.FormEvent) {
        event.preventDefault();
        void runSearch(getDraftFilters(), 1, true);
    }

    function handleReset() {
        setQuery('');
        setDocType('');
        setAgency('');
        setYear('');
        setExpandedDocId(null);
        void runSearch(EMPTY_FILTERS, 1, true);
    }

    function handleApplyFilters() {
        setFiltersOpen(false);
        setExpandedDocId(null);
        void runSearch(getDraftFilters(), 1, true);
    }

    function handlePageChange(newPage: number) {
        setExpandedDocId(null);
        void runSearch(appliedFilters, newPage, true);
    }

    function removeFilter(key: keyof AppliedFilters) {
        const next = { ...appliedFilters, [key]: '' };
        if (key === 'query') setQuery('');
        if (key === 'docType') setDocType('');
        if (key === 'issuer') setAgency('');
        if (key === 'year') setYear('');
        setExpandedDocId(null);
        void runSearch(next, 1, true);
    }

    const activeFilterEntries = [
        appliedFilters.query && { key: 'query' as const, label: `Từ khóa: ${appliedFilters.query}` },
        appliedFilters.docType && { key: 'docType' as const, label: getDocumentTypeLabel(appliedFilters.docType) },
        appliedFilters.issuer && { key: 'issuer' as const, label: `Cơ quan: ${appliedFilters.issuer}` },
        appliedFilters.year && { key: 'year' as const, label: `Hiệu lực: ${appliedFilters.year}` },
    ].filter(Boolean) as Array<{ key: keyof AppliedFilters; label: string }>;

    const advancedFilterCount = [appliedFilters.docType, appliedFilters.issuer, appliedFilters.year].filter(Boolean).length;

    return (
        <>
            <div id="view-search" className={`view-section ${activeView === 'view-search' ? 'active' : ''} scrollable-content`.trim()}>
                <section className="hero-search">
                    <h2>Tra cứu văn bản giao thông vận tải</h2>
                    <p className="subtitle">Tìm theo tên văn bản, số hiệu, cơ quan ban hành hoặc năm có hiệu lực.</p>
                    <form className="search-container" onSubmit={handleSubmit}>
                        <input
                            type="text"
                            id="searchInput"
                            placeholder="Nhập tên văn bản hoặc số hiệu"
                            aria-label="Tìm kiếm văn bản"
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                        />
                        <button id="searchBtn" type="submit" disabled={loading}>
                            <MagnifyingGlass size={20} weight="bold" />
                            {loading ? 'Đang tra cứu' : 'Tra cứu'}
                        </button>
                    </form>
                </section>

                <section className="results-layout">
                    <div className="results-toolbar">
                        <div>
                            <h3>Kết quả tra cứu</h3>
                            <p><span className="count" id="resultsCount">{results?.total || 0}</span> văn bản đang được hiển thị</p>
                        </div>
                        <button
                            type="button"
                            className={`filter-toggle ${filtersOpen ? 'open' : ''}`}
                            aria-expanded={filtersOpen}
                            aria-controls="documentFilters"
                            onClick={() => setFiltersOpen((open) => !open)}
                        >
                            <Faders size={18} />
                            Bộ lọc
                            {advancedFilterCount > 0 && <span>{advancedFilterCount}</span>}
                            <CaretDown size={15} className="filter-toggle-caret" />
                        </button>
                    </div>

                    {filtersOpen && (
                        <aside id="documentFilters" className="filter-panel" aria-label="Bộ lọc văn bản">
                            <div className="filter-panel-heading">
                                <h3>Lọc kết quả</h3>
                            </div>

                            <div className="filter-panel-body">
                                <div className="filter-fields">
                                    <div className="filter-group">
                                        <label htmlFor="typeFilter">Loại văn bản</label>
                                        <select id="typeFilter" value={docType} onChange={(event) => setDocType(event.target.value)}>
                                            {DOCUMENT_TYPES.map((item) => (
                                                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
                                            ))}
                                        </select>
                                    </div>

                                    <div className="filter-group">
                                        <label htmlFor="agencyFilter">Cơ quan ban hành</label>
                                        <input
                                            type="text"
                                            id="agencyFilter"
                                            value={agency}
                                            onChange={(event) => setAgency(event.target.value)}
                                            placeholder="Ví dụ: Chính phủ"
                                        />
                                    </div>

                                    <div className="filter-group">
                                        <label htmlFor="yearFilter">Năm hiệu lực</label>
                                        <select id="yearFilter" value={year} onChange={(event) => setYear(event.target.value)}>
                                            {EFFECTIVE_YEARS.map((value) => (
                                                <option key={value || 'all-years'} value={value}>
                                                    {value || 'Tất cả các năm'}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                <div className="filter-actions">
                                    <button type="button" className="btn-primary" onClick={handleApplyFilters} disabled={loading}>
                                        <MagnifyingGlass size={17} /> Áp dụng
                                    </button>
                                    <button id="resetFiltersBtn" type="button" className="reset-btn" onClick={handleReset}>
                                        <ArrowCounterClockwise size={17} /> Xóa lọc
                                    </button>
                                </div>
                            </div>
                        </aside>
                    )}

                    {activeFilterEntries.length > 0 && (
                        <div className="applied-filters" aria-label="Bộ lọc đang áp dụng">
                            {activeFilterEntries.map((item) => (
                                <button key={item.key} type="button" onClick={() => removeFilter(item.key)}>
                                    {item.label}<X size={13} />
                                </button>
                            ))}
                            <button type="button" className="clear-all-filters" onClick={handleReset}>Xóa tất cả</button>
                        </div>
                    )}

                    <section className="results-content" ref={resultsRef}>
                        <div id="resultsList" className="results-list">
                            {!loading && trafficSigns.length > 0 && (
                                <section className="traffic-sign-results" aria-labelledby="trafficSignHeading">
                                    <div className="traffic-sign-results-heading">
                                        <div>
                                            <span>Danh mục QCVN đã xác minh</span>
                                            <h3 id="trafficSignHeading">Biển báo phù hợp</h3>
                                        </div>
                                        <small>Tối đa 3 kết quả để tránh chọn nhầm biển gần nghĩa</small>
                                    </div>
                                    <div className="traffic-sign-grid">
                                        {trafficSigns.map((sign) => (
                                            <article className="traffic-sign-card" key={sign.sign_code}>
                                                <div className="traffic-sign-visual">
                                                    {sign.primary_asset ? (
                                                        <Image
                                                            src={sign.primary_asset.url}
                                                            width={sign.primary_asset.width ?? 320}
                                                            height={sign.primary_asset.height ?? 320}
                                                            alt={sign.recognition_text || `${sign.sign_code} - ${sign.sign_name}`}
                                                            unoptimized
                                                        />
                                                    ) : (
                                                        <div className="traffic-sign-no-image">
                                                            <FileText size={30} weight="duotone" />
                                                            <span>Chưa có ảnh đã xác minh</span>
                                                        </div>
                                                    )}
                                                </div>
                                                <div>
                                                    <span className="traffic-sign-code">{sign.sign_code}</span>
                                                    <h4>{sign.sign_name}</h4>
                                                    {sign.recognition_text && <p>{sign.recognition_text}</p>}
                                                    <p>{sign.meaning_text}</p>
                                                    <small>{sign.source_locator}</small>
                                                </div>
                                            </article>
                                        ))}
                                    </div>
                                </section>
                            )}

                            {error ? (
                                <div className="error-state" role="alert">
                                    <strong>Không thể tải dữ liệu</strong>
                                    <span>{error}</span>
                                    <button type="button" className="btn-secondary" onClick={() => void runSearch(appliedFilters, page)}>Thử lại</button>
                                </div>
                            ) : loading ? (
                                Array.from({ length: 3 }).map((_, idx) => (
                                    <div key={idx} className="document-card document-skeleton" aria-hidden="true">
                                        <div className="document-card-top">
                                            <div className="skeleton-line skeleton-badge" />
                                        </div>
                                        <div className="skeleton-line skeleton-document-title" />
                                        <div className="document-meta">
                                            <div className="skeleton-line skeleton-meta" />
                                            <div className="skeleton-line skeleton-meta" />
                                        </div>
                                    </div>
                                ))
                            ) : results?.items.length === 0 ? (
                                <div className="empty-state">
                                    <span className="empty-state-icon"><FileText size={30} weight="duotone" /></span>
                                    <strong>Không tìm thấy văn bản phù hợp</strong>
                                    <p>Hãy rút gọn từ khóa hoặc bớt bộ lọc để mở rộng kết quả.</p>
                                    <button type="button" className="btn-secondary" onClick={handleReset}>Xóa bộ lọc</button>
                                </div>
                            ) : (
                                results?.items.map((doc) => {
                                    const expanded = expandedDocId === doc.doc_id;
                                    return (
                                        <article key={doc.doc_id} className={`document-card document-card-accordion ${expanded ? 'active' : ''}`}>
                                            <div className="document-card-toggle">
                                                <button
                                                    type="button"
                                                    className="document-card-main-button"
                                                    aria-expanded={expanded}
                                                    onClick={() => toggleExpandedDoc(doc.doc_id)}
                                                >
                                                    <span className="document-card-main">
                                                        <span className="document-card-top">
                                                        <span className="badge document-type">{getDocumentTypeLabel(doc.doc_type)}</span>
                                                        <span className={`badge ${doc.status === 'active' ? 'active' : ''}`}>
                                                            {formatDocumentStatus(doc.status)}
                                                        </span>
                                                        </span>
                                                        <span className="document-title">{doc.title}</span>
                                                        <span className="document-meta">
                                                            <span className="meta-item">
                                                            <span><strong>{doc.issuer}</strong></span>
                                                            </span>
                                                            <span className="meta-item">
                                                            <span>Hiệu lực từ <strong>{formatDate(doc.effective_date)}</strong></span>
                                                            </span>
                                                            </span>
                                                    </span>
                                                </button>

                                                <span className="document-card-actions">
                                                    {doc.source_download_url ? (
                                                        <button
                                                            className="kb-icon-action"
                                                            aria-label="Tải file nguồn"
                                                            title="Tải file nguồn"
                                                            type="button"
                                                            onClick={() => {
                                                                if (doc.viewer_warning) {
                                                                    setDownloadWarningDoc(doc);
                                                                    return;
                                                                }
                                                                window.open(doc.source_download_url || '#', '_blank', 'noopener,noreferrer');
                                                            }}
                                                        >
                                                            <DownloadSimple size={18} />
                                                        </button>
                                                    ) : (
                                                        <span className="kb-icon-action is-disabled" aria-label="Chưa có file nguồn" title="Chưa có file nguồn">
                                                            <DownloadSimple size={18} />
                                                        </span>
                                                    )}
                                                    <button
                                                        type="button"
                                                        className={`kb-icon-action kb-expand-indicator ${expanded ? 'open' : ''}`}
                                                        aria-label={expanded ? 'Thu gọn thông tin văn bản' : 'Xem thông tin văn bản'}
                                                        title={expanded ? 'Thu gọn thông tin văn bản' : 'Xem thông tin văn bản'}
                                                        aria-expanded={expanded}
                                                        onClick={() => toggleExpandedDoc(doc.doc_id)}
                                                    >
                                                        <CaretDown size={18} />
                                                    </button>
                                                </span>
                                            </div>

                                            {expanded && (
                                                <div className="document-inline-detail">
                                                    <dl className="kb-meta-list kb-meta-list-compact document-public-meta">
                                                        <div><dt>Cơ quan ban hành</dt><dd>{doc.issuer}</dd></div>
                                                        <div><dt>Số hiệu</dt><dd>{doc.document_number ?? 'Chưa cập nhật'}</dd></div>
                                                        <div><dt>Nguồn gốc</dt><dd>{doc.source_url ? <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-navy-800 underline underline-offset-2 transition-colors hover:text-navy-900">{formatSourceLabel(doc.source_url)}</a> : formatSourceLabel(doc.source_url)}</dd></div>
                                                        <div><dt>Ngày ban hành</dt><dd>{formatDate(doc.issued_date ?? null)}</dd></div>
                                                        <div><dt>Hiệu lực từ</dt><dd>{formatDate(doc.effective_date)}</dd></div>
                                                        <div><dt>Hết hiệu lực</dt><dd>{formatDate(doc.expiry_date)}</dd></div>
                                                    </dl>

                                                    {doc.relations && doc.relations.length > 0 ? (
                                                        <section className="document-public-relations" aria-label="Quan hệ văn bản">
                                                            <div className="document-public-relations-head">
                                                                <strong>Quan hệ văn bản</strong>
                                                                <span>{doc.relations.length} quan hệ đang được công bố</span>
                                                            </div>
                                                            <div className="document-public-relation-list">
                                                                {doc.relations.map((relation) => (
                                                                    <article key={relation.relation_id} className="document-public-relation-item">
                                                                        <span className="badge document-type">{formatRelationType(relation.relation_type)}</span>
                                                                        <div>
                                                                            <small>{formatRelationDirection(relation.direction)}</small>
                                                                            <p>
                                                                                {relation.counterpart_document_number ? `${relation.counterpart_document_number} - ` : ''}
                                                                                {relation.counterpart_title || 'Văn bản liên quan'}
                                                                            </p>
                                                                        </div>
                                                                    </article>
                                                                ))}
                                                            </div>
                                                        </section>
                                                    ) : null}

                                                    {doc.viewer_warning && (
                                                        <div className="mt-4 flex flex-col gap-3">
                                                            <article className="kb-warning-card">
                                                                <span>{doc.viewer_warning}</span>
                                                            </article>
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </article>
                                    );
                                })
                            )}

                            {results && results.total > results.page_size && (
                                <nav className="pagination" aria-label="Phân trang kết quả">
                                    <button onClick={() => handlePageChange(page - 1)} disabled={page === 1} className="btn-secondary">
                                        Trước
                                    </button>
                                    <span>Trang {page} / {Math.ceil(results.total / results.page_size)}</span>
                                    <button
                                        onClick={() => handlePageChange(page + 1)}
                                        disabled={page >= Math.ceil(results.total / results.page_size)}
                                        className="btn-secondary"
                                    >
                                        Sau
                                    </button>
                                </nav>
                            )}
                        </div>
                    </section>
                </section>
            </div>

            {downloadWarningDoc && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setDownloadWarningDoc(null)}>
                    <div
                        className="admin-modal review-confirm-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="public-source-warning-title"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <h3 id="public-source-warning-title">Lưu ý khi tải file nguồn</h3>
                            <button className="admin-modal-close" type="button" onClick={() => setDownloadWarningDoc(null)} aria-label="Đóng">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body">
                            <article className="kb-warning-card">
                                <span>{downloadWarningDoc.viewer_warning || 'Vui lòng đối chiếu kỹ trước khi áp dụng.'}</span>
                            </article>
                            <div className="mt-5 flex flex-wrap justify-end gap-2">
                                <button className="btn-secondary" type="button" onClick={() => setDownloadWarningDoc(null)}>
                                    Quay lại
                                </button>
                                <button
                                    className="btn-primary"
                                    type="button"
                                    onClick={() => {
                                        window.open(downloadWarningDoc.source_download_url || '#', '_blank', 'noopener,noreferrer');
                                        setDownloadWarningDoc(null);
                                    }}
                                >
                                    Tải file
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
