import React from 'react';
import {
    ArrowClockwise,
    ArrowRight,
    ChartLineUp,
    CheckCircle,
    ClockCounterClockwise,
    Database,
    MagnifyingGlass,
    ShieldWarning,
    Warning,
    XCircle,
} from '@phosphor-icons/react';
import {
    fetchQualityIssue,
    fetchQualityIssues,
    fetchQualityOverview,
    fetchQualityReleaseChecks,
    reviewQualityIssue,
    type QualityIssueDetail,
    type QualityIssueItem,
    type QualityOverview,
    type QualityReleaseCheck,
    type QualityVerdictStatus,
} from '../../lib/api';
import { EmptyView, PageFrame } from '../ui';

const verdictIcons = {
    blocked: XCircle,
    needs_attention: Warning,
    healthy: CheckCircle,
    unknown: MagnifyingGlass,
} satisfies Record<QualityVerdictStatus, typeof XCircle>;

const severityLabels: Record<QualityIssueItem['severity'], string> = {
    critical: 'Chặn phát hành',
    high: 'Ưu tiên cao',
    medium: 'Cần xem',
    low: 'Theo dõi',
};

function humanizeQualityText(value: string | null | undefined) {
    if (!value) return 'Chưa có';
    return value
        .replaceAll('FAILED', 'Chưa đạt')
        .replaceAll('Faithfulness', 'Độ bám căn cứ')
        .replaceAll('faithfulness', 'độ bám căn cứ')
        .replaceAll('Observation', 'Ghi nhận')
        .replaceAll('observation', 'ghi nhận')
        .replaceAll('answerable', 'dùng để trả lời');
}

function formatReleaseStatus(value: QualityReleaseCheck['status']) {
    return {
        passed: 'Đạt',
        failed: 'Chưa đạt',
        invalid: 'Không hợp lệ',
    }[value] ?? humanizeQualityText(value);
}

function formatPercent(value: number | null | undefined) {
    return value == null ? 'Chưa có' : `${(value * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`;
}

function formatDate(value: string | null | undefined) {
    if (!value) return 'Chưa có';
    return new Intl.DateTimeFormat('vi-VN', {
        dateStyle: 'short',
        timeStyle: 'short',
    }).format(new Date(value));
}

function evidenceValue(item: Record<string, unknown>, key: string) {
    const value = item[key];
    return typeof value === 'string' || typeof value === 'number' ? String(value) : 'Chưa có';
}

function pipelineValue(value: unknown) {
    if (typeof value === 'boolean') return value ? 'Có' : 'Không';
    if (typeof value === 'number') return value.toLocaleString('vi-VN', { maximumFractionDigits: 3 });
    return typeof value === 'string' && value ? value : 'Chưa có';
}

function DashboardSkeleton() {
    return (
        <div className="quality-skeleton" aria-label="Đang tải dữ liệu chất lượng">
            <div className="skeleton-panel h-44" />
            <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
                <div className="skeleton-panel h-80" />
                <div className="skeleton-panel h-80" />
            </div>
        </div>
    );
}

function ReleaseEvidence({ release }: { release: QualityReleaseCheck | null }) {
    if (!release) {
        return (
            <div className="quality-empty-compact">
                <Database size={22} />
                <div>
                    <strong>Chưa có lần kiểm tra phát hành hợp lệ</strong>
                    <p>Chạy bộ kiểm thử chuẩn sau khi hoàn tất cập nhật để có bằng chứng phát hành.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="quality-release-evidence">
            <div className="quality-release-heading">
                <div>
                    <span className={`quality-status-tag ${release.status}`}>{formatReleaseStatus(release.status)}</span>
                    <strong>Kết quả lúc {formatDate(release.generated_at)}</strong>
                </div>
                <span className="font-mono text-xs text-slate-500">{release.dataset_version}</span>
            </div>
            <dl className="quality-release-metrics">
                <div>
                    <dt>Mức bao phủ</dt>
                    <dd>{release.executed}/{release.required} tình huống</dd>
                    <small>{release.skipped} bỏ qua · {release.invalid} không hợp lệ · {release.evaluator_errors} lỗi chấm điểm</small>
                </div>
                <div>
                    <dt>Độ bám căn cứ</dt>
                    <dd>{formatPercent(release.faithfulness.value)}</dd>
                    <small>{release.faithfulness.sample_size ?? 0}/{release.faithfulness.eligible_count ?? 0} tình huống có điểm</small>
                </div>
                <div>
                    <dt>P10 / thấp nhất</dt>
                    <dd>{formatPercent(release.faithfulness.p10)} / {formatPercent(release.faithfulness.minimum)}</dd>
                    <small>Ngưỡng trung bình {formatPercent(release.faithfulness.threshold)} · sàn 80%</small>
                </div>
                <div>
                    <dt>Trích dẫn chính xác</dt>
                    <dd>{formatPercent(release.citation_accuracy.value)}</dd>
                    <small>{release.citation_accuracy.numerator ?? 0}/{release.citation_accuracy.denominator ?? 0} tình huống · ngưỡng {formatPercent(release.citation_accuracy.threshold)}</small>
                </div>
            </dl>
            {release.gate_failures.length > 0 && (
                <p className="quality-gate-failures">
                    Chưa đạt: {release.gate_failures.map((item) => humanizeQualityText(item)).join(', ')}
                </p>
            )}
        </div>
    );
}

export default function ViewDashboard({ activeView }: { activeView: string }) {
    const [overview, setOverview] = React.useState<QualityOverview | null>(null);
    const [issues, setIssues] = React.useState<QualityIssueItem[]>([]);
    const [releaseChecks, setReleaseChecks] = React.useState<QualityReleaseCheck[]>([]);
    const [selectedIssue, setSelectedIssue] = React.useState<QualityIssueDetail | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [detailLoading, setDetailLoading] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);
    const [reviewNote, setReviewNote] = React.useState('');
    const [reviewError, setReviewError] = React.useState<string | null>(null);
    const [reviewing, setReviewing] = React.useState(false);

    const loadDashboard = React.useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [overviewData, openIssues, reviewingIssues, releases] = await Promise.all([
                fetchQualityOverview(7),
                fetchQualityIssues('open', 1, 20),
                fetchQualityIssues('reviewing', 1, 20),
                fetchQualityReleaseChecks(),
            ]);
            setOverview(overviewData);
            setIssues([...openIssues.items, ...reviewingIssues.items]);
            setReleaseChecks(releases.items);
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : 'Không thể tải dữ liệu chất lượng.');
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        if (activeView === 'view-dashboard') void loadDashboard();
    }, [activeView, loadDashboard]);

    async function openIssue(issueId: string) {
        setDetailLoading(true);
        setReviewError(null);
        try {
            setSelectedIssue(await fetchQualityIssue(issueId));
            setReviewNote('');
        } catch (detailError) {
            setReviewError(detailError instanceof Error ? detailError.message : 'Không thể tải bằng chứng.');
        } finally {
            setDetailLoading(false);
        }
    }

    async function submitReview(
        conclusion: 'confirmed' | 'false_positive' | 'kb_gap' | 'retrieval_miss',
        status: 'resolved' | 'dismissed',
    ) {
        if (!selectedIssue) return;
        if (reviewNote.trim().length < 3) {
            setReviewError('Ghi chú cần ít nhất 3 ký tự để lưu lại quyết định.');
            return;
        }
        setReviewing(true);
        setReviewError(null);
        try {
            const rootCauses = {
                confirmed: 'confirmed_quality_defect',
                false_positive: 'evaluator_false_positive',
                kb_gap: 'missing_knowledge',
                retrieval_miss: 'retrieval_miss',
            } as const;
            await reviewQualityIssue(selectedIssue.issue_id, {
                status,
                conclusion,
                root_cause: rootCauses[conclusion],
                note: reviewNote.trim(),
            });
            setSelectedIssue(null);
            await loadDashboard();
        } catch (reviewRequestError) {
            setReviewError(reviewRequestError instanceof Error ? reviewRequestError.message : 'Không thể lưu kết luận.');
        } finally {
            setReviewing(false);
        }
    }

    const VerdictIcon = overview ? verdictIcons[overview.verdict.status] : MagnifyingGlass;
    const coverage = overview?.data_quality.production_trace_coverage;

    return (
        <PageFrame
            id="view-dashboard"
            active={activeView === 'view-dashboard'}
            icon={ChartLineUp}
            title="Chất lượng AI"
            description="Kết luận vận hành từ lần kiểm tra phát hành và dữ liệu sử dụng 7 ngày gần nhất"
        >
            {loading && <DashboardSkeleton />}

            {!loading && error && (
                <section className="quality-error" role="alert">
                    <XCircle size={24} />
                    <div>
                        <strong>Không tải được tình hình chatbot</strong>
                        <p>{error}</p>
                    </div>
                    <button className="btn-secondary" type="button" onClick={() => void loadDashboard()}>
                        <ArrowClockwise size={16} /> Thử lại
                    </button>
                </section>
            )}

            {!loading && !error && overview && (
                <>
                    <section className={`quality-verdict ${overview.verdict.status}`}>
                        <div className="quality-verdict-icon"><VerdictIcon size={28} weight="fill" /></div>
                        <div className="quality-verdict-copy">
                            <span>Tình hình hiện tại · cập nhật {formatDate(overview.as_of)}</span>
                            <h2>{overview.verdict.title}</h2>
                            <p>{humanizeQualityText(overview.verdict.reason)}</p>
                            <strong>{humanizeQualityText(overview.verdict.next_action)}</strong>
                        </div>
                        <button
                            className="btn-secondary"
                            type="button"
                            disabled={issues.length === 0}
                            onClick={() => issues[0] && void openIssue(issues[0].issue_id)}
                        >
                            Xem việc ưu tiên <ArrowRight size={16} />
                        </button>
                    </section>

                    <dl className="quality-signal-strip">
                        <div>
                            <dt>Mức bao phủ vận hành</dt>
                            <dd>{coverage?.traced ?? 0}/{coverage?.total ?? 0}</dd>
                            <small>{formatPercent(coverage?.rate)} yêu cầu có đủ dữ liệu theo dõi</small>
                        </div>
                        <div>
                            <dt>Vấn đề chặn phát hành</dt>
                            <dd>{overview.blockers.open}</dd>
                            <small>{overview.blockers.high_risk_unsupported_claims} nhận định thiếu căn cứ</small>
                        </div>
                        <div>
                            <dt>Lượt trả lời đã được chấm</dt>
                            <dd>{overview.production.evaluated_responses}/{overview.production.total_requests}</dd>
                            <small>Chỉ phản ánh mức bao phủ; quyết định phát hành dùng bộ kiểm thử chuẩn</small>
                        </div>
                        <div>
                            <dt>Độ trễ P95</dt>
                            <dd>{overview.production.p95_latency_ms == null ? 'Chưa có' : `${overview.production.p95_latency_ms.toLocaleString('vi-VN')} ms`}</dd>
                            <small>{overview.production.failed_requests} yêu cầu lỗi trong kỳ</small>
                        </div>
                    </dl>

                    {overview.data_quality.blind_spots.length > 0 && (
                        <section className="quality-blind-spots">
                            <ShieldWarning size={20} />
                            <div>
                                <strong>Không nên suy rộng quá dữ liệu hiện có</strong>
                                {overview.data_quality.blind_spots.map((item) => <p key={item}>{humanizeQualityText(item)}</p>)}
                            </div>
                        </section>
                    )}

                    <div className="quality-workbench">
                        <section className="quality-work-queue">
                            <header>
                                <div>
                                    <span>Việc cần xử lý</span>
                                    <h2>{issues.length > 0 ? `${issues.length} vấn đề đang mở` : 'Không có vấn đề đang mở'}</h2>
                                </div>
                                <button className="btn-secondary" type="button" onClick={() => void loadDashboard()}>
                                    <ArrowClockwise size={16} /> Làm mới
                                </button>
                            </header>
                            {issues.length === 0 ? (
                                <EmptyView
                                    icon={CheckCircle}
                                    title="Hàng đợi đang trống"
                                    description="Không có vấn đề nào cần quản trị viên xem thêm trong dữ liệu hiện tại."
                                />
                            ) : (
                                <ol className="quality-issue-list">
                                    {issues.map((issue) => (
                                        <li key={issue.issue_id}>
                                            <button type="button" onClick={() => void openIssue(issue.issue_id)}>
                                                <span className={`quality-severity ${issue.severity}`}>
                                                    {severityLabels[issue.severity]}
                                                </span>
                                                <strong>{humanizeQualityText(issue.title)}</strong>
                                                <p>{humanizeQualityText(issue.summary)}</p>
                                                <p><strong>Tiếp theo:</strong> {humanizeQualityText(issue.next_action)}</p>
                                                <small>{formatDate(issue.first_seen_at)} · {issue.affected_count} lượt trả lời</small>
                                                <ArrowRight className="quality-issue-arrow" size={18} />
                                            </button>
                                        </li>
                                    ))}
                                </ol>
                            )}
                        </section>

                        <aside className="quality-release-panel">
                            <header>
                                <span>Bằng chứng phát hành</span>
                                <h2>Lần kiểm tra gần nhất</h2>
                            </header>
                            <ReleaseEvidence release={overview.latest_release_check} />
                        </aside>
                    </div>

                    <section className="quality-history">
                        <header>
                            <ClockCounterClockwise size={20} />
                            <div>
                                <span>Lịch sử kiểm tra</span>
                                <h2>Nhận biết sai lệch giữa các lần phát hành</h2>
                            </div>
                        </header>
                        {releaseChecks.length === 0 ? (
                            <p className="quality-muted">Chưa có lịch sử kiểm tra được lưu trong cơ sở dữ liệu.</p>
                        ) : (
                            <div className="quality-history-list">
                                {releaseChecks.map((release) => (
                                    <div key={release.run_id}>
                                        <span className={`quality-status-tag ${release.status}`}>{formatReleaseStatus(release.status)}</span>
                                        <strong>{formatDate(release.generated_at)}</strong>
                                        <span>{release.executed}/{release.required} tình huống</span>
                                        <span>{release.skipped} bỏ qua · {release.invalid} không hợp lệ</span>
                                        <span>Độ bám căn cứ {formatPercent(release.faithfulness.value)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                </>
            )}

            {(detailLoading || selectedIssue) && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => !reviewing && setSelectedIssue(null)}>
                    <section className="admin-modal quality-detail-dialog" onClick={(event) => event.stopPropagation()}>
                        {detailLoading && <div className="skeleton-panel h-[32rem]" />}
                        {!detailLoading && selectedIssue && (
                            <>
                                <header className="quality-detail-header">
                                    <div>
                                        <span className={`quality-severity ${selectedIssue.severity}`}>
                                            {severityLabels[selectedIssue.severity]}
                                        </span>
                                        <h2>{humanizeQualityText(selectedIssue.title)}</h2>
                                        <p>{humanizeQualityText(selectedIssue.summary)}</p>
                                    </div>
                                    <button className="admin-modal-close" type="button" onClick={() => setSelectedIssue(null)} aria-label="Đóng">
                                        <XCircle size={24} />
                                    </button>
                                </header>
                                <div className="quality-evidence-grid">
                                    <article>
                                        <span>Câu hỏi đã ẩn thông tin nhạy cảm</span>
                                        <p>{selectedIssue.observation.query_text}</p>
                                    </article>
                                    <article>
                                        <span>Câu trả lời của chatbot</span>
                                        <p className="whitespace-pre-wrap">{selectedIssue.observation.response_text || selectedIssue.observation.error_summary || 'Chưa có nội dung trả lời hoàn chỉnh.'}</p>
                                    </article>
                                </div>
                                <dl className="quality-detail-facts">
                                    <div><dt>Độ bám căn cứ</dt><dd>{formatPercent(selectedIssue.observation.faithfulness_score)}</dd></div>
                                    <div><dt>Số trích dẫn</dt><dd>{selectedIssue.observation.citations.length}</dd></div>
                                    <div><dt>Điều kiện an toàn</dt><dd>{selectedIssue.observation.guardrail_reason || 'Không kích hoạt'}</dd></div>
                                    <div><dt>Token đầu / tổng thời gian</dt><dd>{selectedIssue.observation.first_token_latency_ms == null ? 'Chưa có' : `${selectedIssue.observation.first_token_latency_ms} ms`} / {selectedIssue.observation.latency_ms == null ? 'Chưa có' : `${selectedIssue.observation.latency_ms} ms`}</dd></div>
                                </dl>
                                <section className="quality-evidence-section">
                                    <span>Hành động đề xuất</span>
                                    <p>{humanizeQualityText(selectedIssue.next_action)}</p>
                                </section>
                                <section className="quality-evidence-section">
                                    <span>Trích dẫn chatbot đã dùng</span>
                                    {selectedIssue.observation.citations.length === 0 ? (
                                        <p>Không có trích dẫn trong lượt trả lời này.</p>
                                    ) : (
                                        <ol>
                                            {selectedIssue.observation.citations.map((citation) => (
                                                <li key={citation.citation_id}>
                                                    <strong>{citation.doc_title}</strong>
                                                    <p>{citation.locator_label || `Điều ${citation.article_num ?? '?'}`}</p>
                                                    <small>{citation.verification_status} · độ tin cậy {formatPercent(citation.confidence)}</small>
                                                </li>
                                            ))}
                                        </ol>
                                    )}
                                </section>
                                <section className="quality-evidence-section">
                                    <span>Đoạn nguồn thực tế</span>
                                    {selectedIssue.observation.evidence.length === 0 ? (
                                        <p>Không có căn cứ nào được đưa vào phần tạo câu trả lời.</p>
                                    ) : (
                                        <ol>
                                            {selectedIssue.observation.evidence.map((item, index) => (
                                                <li key={`${evidenceValue(item, 'chunk_id')}-${index}`}>
                                                    <strong>{evidenceValue(item, 'doc_title')}</strong>
                                                    <p>{evidenceValue(item, 'locator_label')} · trạng thái {evidenceValue(item, 'status')}</p>
                                                    <small>{evidenceValue(item, 'text_snippet')}</small>
                                                </li>
                                            ))}
                                        </ol>
                                    )}
                                </section>
                                <section className="quality-evidence-section">
                                    <span>Thông tin đường xử lý và phiên bản</span>
                                    <div className="quality-pipeline-grid">
                                        {Object.entries(selectedIssue.observation.pipeline_metadata).map(([stage, values]) => (
                                            <article key={stage}>
                                                <strong>{stage}</strong>
                                                {Object.entries(values || {}).map(([key, value]) => (
                                                    <p key={key}><span>{key}</span><b>{pipelineValue(value)}</b></p>
                                                ))}
                                            </article>
                                        ))}
                                    </div>
                                </section>
                                <section className="quality-review-form">
                                    <label htmlFor="quality-review-note">Kết luận người duyệt</label>
                                    <textarea
                                        id="quality-review-note"
                                        value={reviewNote}
                                        onChange={(event) => setReviewNote(event.target.value)}
                                        placeholder="Nêu bằng chứng và lý do cho quyết định này"
                                        rows={4}
                                    />
                                    {reviewError && <p className="form-error" role="alert">{reviewError}</p>}
                                    <div className="quality-review-actions">
                                        <button className="btn-primary" type="button" disabled={reviewing} onClick={() => void submitReview('confirmed', 'resolved')}>
                                            Xác nhận lỗi
                                        </button>
                                        <button className="btn-secondary" type="button" disabled={reviewing} onClick={() => void submitReview('kb_gap', 'resolved')}>
                                            Xác nhận thiếu dữ liệu
                                        </button>
                                        <button className="btn-secondary" type="button" disabled={reviewing} onClick={() => void submitReview('retrieval_miss', 'resolved')}>
                                            Xác nhận bỏ sót căn cứ
                                        </button>
                                        <button className="btn-secondary" type="button" disabled={reviewing} onClick={() => void submitReview('false_positive', 'dismissed')}>
                                            Đánh dấu báo động giả
                                        </button>
                                    </div>
                                </section>
                            </>
                        )}
                    </section>
                </div>
            )}
        </PageFrame>
    );
}
