// ---- Types ----
export interface Citation {
  citation_id: string;
  chunk_id: string;
  doc_id: string;
  doc_title: string;
  doc_type: string;
  status: string;
  effective_date: string | null;
  article_num: number | null;
  clause_num: number | null;
  point_num: string | null;
  locator_type: string | null;
  locator_label: string | null;
  section_path: string[];
  section_number: string | null;
  sign_code: string | null;
  asset_ids: string[];
  text_snippet: string;
  verification_status: "verified" | "partial" | "unverified" | "blocked";
  confidence: number;
  source_url: string | null;
}

export type ChatAnswerMode =
  | 'direct'
  | 'summary'
  | 'historical'
  | 'clarification_needed'
  | 'multiple_possibilities'
  | 'insufficient_evidence'
  | 'out_of_scope';

export type ChatRiskLevel = 'low' | 'medium' | 'high';
export type ChatConfidenceLevel = 'low' | 'medium' | 'high';

export interface ChatConfidence {
  level: ChatConfidenceLevel;
  reason: string;
}

export interface ChatProvisionCitation {
  document_id: string;
  article_num: number | null;
  clause_num: number | null;
  point_num: string | null;
  effective_status: string;
  retrieval_unit_id: string;
}

export interface ChatDocumentSource {
  document_id: string;
  title: string | null;
  issuing_body: string | null;
  date: string | null;
  url: string | null;
}

export interface ChatHistoricalReference {
  document_id: string;
  title: string | null;
  article_num: number | null;
  clause_num: number | null;
  point_num: string | null;
  effective_from: string | null;
  effective_to: string | null;
  status: string | null;
  replaced_by: string | null;
}

export interface ChatResponseMetadata {
  risk_level?: ChatRiskLevel;
  answer_mode?: ChatAnswerMode;
  confidence?: ChatConfidence;
  provision_citations?: ChatProvisionCitation[];
  document_sources?: ChatDocumentSource[];
  historical_references?: ChatHistoricalReference[];
  clarification_question?: string | null;
}

export interface UserAccount {
  user_id: string;
  email: string;
  username: string | null;
  role: "USER" | "ADMIN";
  is_active: boolean;
}

export interface AuthSession {
  access_token: string;
  token_type: "bearer";
  user: UserAccount;
}

const ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX = '/api/v1/admin/kb-v2';

export class DocumentRepositoryDuplicateSourceError extends Error {
  code = 'KB_DUPLICATE_SOURCE';
  documentId?: string;
  revisionId?: string;
  sourceAssetId?: string;
  sha256?: string;

  constructor(message: string, detail: Record<string, unknown>) {
    super(message);
    this.name = 'DocumentRepositoryDuplicateSourceError';
    this.documentId = typeof detail.document_id === 'string' ? detail.document_id : undefined;
    this.revisionId = typeof detail.revision_id === 'string' ? detail.revision_id : undefined;
    this.sourceAssetId = typeof detail.source_asset_id === 'string' ? detail.source_asset_id : undefined;
    this.sha256 = typeof detail.sha256 === 'string' ? detail.sha256 : undefined;
  }
}

export const KbV2DuplicateSourceError = DocumentRepositoryDuplicateSourceError;

export interface ChatMessage extends ChatResponseMetadata {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  faithfulness_score?: number;
  is_out_of_scope?: boolean;
  timestamp: number;
}

export interface ChatSessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_bookmarked: boolean;
  bookmark_title: string | null;
  bookmarked_at: string | null;
}

export interface AdminUserAccount extends UserAccount {
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserListResponse {
  items: AdminUserAccount[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserFilters {
  q?: string;
  role?: 'USER' | 'ADMIN';
  is_active?: boolean;
  page?: number;
  page_size?: number;
}

export interface AdminUserCreatePayload {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
  role: 'USER' | 'ADMIN';
}

export interface AdminUserUpdatePayload {
  username?: string;
  email?: string;
  role?: 'USER' | 'ADMIN';
  is_active?: boolean;
}

export interface ChatSessionsResponse {
  items: ChatSessionSummary[];
}

export interface PersistedChatMessage extends ChatResponseMetadata {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  faithfulness_score: number | null;
  is_out_of_scope: boolean;
  created_at: string;
}

export interface ChatMessagesResponse {
  session: ChatSessionSummary;
  messages: PersistedChatMessage[];
}

export interface ChatSessionBookmarkResponse {
  session: ChatSessionSummary;
}

export interface DoneMeta extends ChatResponseMetadata {
  trace_id: string;
  session_id: string;
  content: string;
  citations: Citation[];
  faithfulness_score: number | null;
  is_out_of_scope: boolean;
  reranker_failed?: boolean;
  reranker_used?: boolean;
  reranker_error_code?: string | null;
  low_confidence?: boolean;
  retrieval_candidate_count?: number;
  rerank_top_score?: number | null;
  guardrail_triggered?: boolean;
  guardrail_stage?: string | null;
  guardrail_reason?: string | null;
}

export type QualityVerdictStatus = 'blocked' | 'needs_attention' | 'healthy' | 'unknown';

export interface QualityReleaseMetric {
  value: number | null;
  threshold: number;
  sample_size?: number | null;
  eligible_count?: number | null;
  minimum?: number | null;
  p10?: number | null;
  numerator?: number | null;
  denominator?: number | null;
}

export interface QualityReleaseCheck {
  run_id: string;
  status: 'passed' | 'failed' | 'invalid';
  dataset_version: string;
  executed: number;
  required: number;
  valid: number;
  skipped: number;
  invalid: number;
  evaluator_errors: number;
  execution_coverage: number;
  faithfulness: QualityReleaseMetric;
  citation_accuracy: QualityReleaseMetric;
  gate_failures: string[];
  generated_at: string;
}

export interface QualityOverview {
  verdict: {
    status: QualityVerdictStatus;
    title: string;
    reason: string;
    next_action: string;
  };
  as_of: string;
  period_days: number;
  data_quality: {
    status: 'complete' | 'partial' | 'empty';
    production_trace_coverage: { traced: number; total: number; rate: number };
    blind_spots: string[];
  };
  blockers: {
    open: number;
    active_filter_violations: number;
    disclaimer_missing: number;
    high_risk_unsupported_claims: number;
  };
  latest_release_check: QualityReleaseCheck | null;
  action_queue: {
    critical: number;
    needs_review: number;
    oldest_opened_at: string | null;
  };
  production: {
    total_requests: number;
    completed_requests: number;
    evaluated_responses: number;
    average_faithfulness: number | null;
    abstained_responses: number;
    failed_requests: number;
    p95_latency_ms: number | null;
  };
}

export interface QualityIssueItem {
  issue_id: string;
  trace_id: string;
  issue_type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'open' | 'reviewing' | 'resolved' | 'dismissed';
  title: string;
  summary: string;
  machine_reason: string | null;
  affected_count: number;
  first_seen_at: string;
  last_seen_at: string;
  next_action: string;
  created_at: string;
  updated_at: string;
}

export interface QualityIssueListResponse {
  items: QualityIssueItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface QualityIssueDetail extends QualityIssueItem {
  evidence: Record<string, unknown>;
  reviewer_conclusion: string | null;
  root_cause: string | null;
  reviewer_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  observation: {
    trace_id: string;
    environment: string;
    status: string;
    query_text: string;
    response_text: string | null;
    citations: Citation[];
    evidence: Array<Record<string, unknown>>;
    pipeline_metadata: {
      versions?: Record<string, string>;
      scope?: Record<string, unknown>;
      retrieval?: Record<string, unknown>;
      rerank?: Record<string, unknown>;
      verification?: Record<string, unknown>;
    };
    faithfulness_score: number | null;
    low_confidence: boolean;
    active_filter_violation: boolean;
    disclaimer_missing: boolean;
    guardrail_reason: string | null;
    first_token_latency_ms: number | null;
    latency_ms: number | null;
    error_summary: string | null;
    created_at: string;
  };
}

export interface QualityReleaseCheckListResponse {
  items: QualityReleaseCheck[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentItem {
  doc_id: string;
  title: string;
  document_number: string | null;
  doc_type: string;
  status: string;
  issued_date: string | null;
  effective_date: string;
  expiry_date: string | null;
  issuer: string;
  source_url: string | null;
  source_file_name: string | null;
  source_download_url: string | null;
  viewer_warning?: string | null;
  standard_summary_url?: string | null;
  current_revision_id?: string | null;
  relations?: PublicDocumentRelation[];
}

export interface PublicDocumentRelation {
  relation_id: string;
  relation_type: string;
  direction: 'outgoing' | 'incoming';
  source_locator: string | null;
  target_locator: string | null;
  counterpart_document_id: string;
  counterpart_title: string | null;
  counterpart_document_number: string | null;
  counterpart_legal_status: string | null;
}

export interface DocumentsResponse {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface KbV2HistoricalCitation {
  retrieval_unit_id: string;
  document_id: string;
  revision_id: string;
  title: string | null;
  document_number: string | null;
  citation_label: string | null;
  legal_status: string;
  publication_status: string;
  source_file_name: string | null;
  source_download_url: string | null;
  viewer_warning: string;
  historical: boolean;
}

export interface KbV2DocumentOut {
  document_id: string;
  title: string | null;
  document_number: string | null;
  document_type: string | null;
  issuing_authority: string | null;
  issued_date: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  legal_status: string;
  metadata_json: Record<string, unknown>;
}

export interface KbV2RevisionOut {
  revision_id: string;
  document_id: string;
  revision_number: number;
  ingestion_status: string;
  review_status: string;
  publication_status: string;
  checksum_sha256: string | null;
  source_url: string | null;
  source_downloaded_at: string | null;
  source_note: string | null;
  parser_version: string | null;
  uploaded_at: string;
}

export interface KbV2SourceAssetOut {
  asset_id: string;
  document_id: string;
  revision_id: string | null;
  asset_role: string;
  storage_uri: string;
  original_filename: string;
  mime_type: string;
  sha256: string;
  file_size_bytes: number | null;
  source_url: string | null;
  source_downloaded_at: string | null;
  source_note: string | null;
}

export interface KbV2CanonicalNodeOut {
  node_id: string;
  revision_id: string;
  parent_id: string | null;
  node_type: string;
  label: string | null;
  text: string | null;
  order_index: number;
  review_status: string;
  provenance: Record<string, unknown>;
  structured_content: Record<string, unknown>;
}

export interface KbV2MetadataProposalOut {
  proposal_id: string;
  document_id: string;
  revision_id: string;
  field_name: string;
  proposed_value: string;
  source_type: string;
  confidence: number | null;
  review_status: string;
  provenance: Record<string, unknown>;
  review_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string | null;
}

export interface KbV2DocumentRelationOut {
  relation_id: string;
  source_document_id: string;
  target_document_id: string;
  relation_type: string;
  source_locator: string | null;
  target_locator: string | null;
  review_status: string;
  metadata_json: Record<string, unknown>;
  created_at: string | null;
}

export interface KbV2StandardSummaryOut {
  summary_id: string;
  document_id: string;
  revision_id: string;
  content: string;
  review_status: string;
  approved_by: string | null;
  approved_at: string | null;
}

export interface KbV2RetrievalUnitOut {
  retrieval_unit_id: string;
  canonical_node_id: string;
  document_id: string;
  revision_id: string;
  answerable_status: string;
  citation_label: string | null;
  embedding_model: string | null;
  embedding_version: string | null;
  index_version: string | null;
}

export interface KbV2ReviewEventOut {
  review_event_id: string;
  document_id: string;
  revision_id: string | null;
  entity_type: string;
  entity_id: string;
  decision: string;
  actor_user_id: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
}

export interface KbV2RevisionDetailResponse {
  document: KbV2DocumentOut;
  revision: KbV2RevisionOut;
  source_asset: KbV2SourceAssetOut | null;
  canonical_nodes: KbV2CanonicalNodeOut[];
  metadata_proposals: KbV2MetadataProposalOut[];
  relations: KbV2DocumentRelationOut[];
  summary: KbV2StandardSummaryOut | null;
  retrieval_units: KbV2RetrievalUnitOut[];
  review_events: KbV2ReviewEventOut[];
  publish_blockers: string[];
  pending_metadata?: KbV2MetadataProposalOut[];
  pending_relations?: KbV2DocumentRelationOut[];
  pending_risky_nodes?: KbV2CanonicalNodeOut[];
  resolved_risky_nodes?: KbV2CanonicalNodeOut[];
  resolved_risky_count?: number;
  risky_reference_only_count?: number;
  risky_answerable_count?: number;
  is_ready_to_publish?: boolean;
}

export interface KbV2UploadResponse {
  document: KbV2DocumentOut;
  revision: KbV2RevisionOut;
  source_asset: KbV2SourceAssetOut;
  parser_confidence: number;
  parser_warnings: string[];
  canonical_nodes: KbV2CanonicalNodeOut[];
}

export interface KbV2RevisionListItem {
  revision_id: string;
  document_id: string;
  title: string | null;
  document_number: string | null;
  document_type: string | null;
  issuing_authority: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  review_status: string;
  publication_status: string;
  ingestion_status: string;
  legal_status: string;
  source_file_name: string | null;
  pending_metadata_count: number;
  pending_relations_count: number;
  pending_risky_nodes_count: number;
  summary_status: string | null;
  publish_blockers_count: number;
  is_ready_to_publish: boolean;
  relation_count: number;
  uploaded_at: string;
  updated_at: string | null;
}

export interface KbV2RevisionListResponse {
  items: KbV2RevisionListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface KbV2PublishedDocumentListItem {
  document_id: string;
  revision_id: string;
  title: string | null;
  document_number: string | null;
  document_type: string | null;
  issuing_authority: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  legal_status: string;
  publication_status: string;
  display_status: 'active' | 'suspended' | 'expired' | 'replaced' | 'annulled' | string;
  source_file_name: string | null;
  updated_at: string | null;
  relation_count: number;
}

export interface KbV2PublishedDocumentListResponse {
  items: KbV2PublishedDocumentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface KbV2RelationTargetItem {
  document_id: string;
  title: string | null;
  document_number: string | null;
}

export interface KbV2RelationTargetListResponse {
  items: KbV2RelationTargetItem[];
  total: number;
}

export type PublishedDocumentListItem = KbV2PublishedDocumentListItem;
export type PublishedDocumentListResponse = KbV2PublishedDocumentListResponse;
export type PublishedDocumentDetailResponse = KbV2RevisionDetailResponse;

export interface AdminDocumentItem extends DocumentItem {
  review_status: string;
  legal_status: string;
  valid_from: string | null;
  valid_to: string | null;
  chunk_count: number;
  indexed_chunk_count: number;
  pending_queue_count: number;
  source_file_name: string | null;
  source_download_url: string | null;
  created_at: string;
}

export interface AdminDocumentSummary {
  total: number;
  active: number;
  pending_review: number;
  future_effective: number;
  repealed: number;
  processing_failed: number;
}

export interface AdminDocumentChunk {
  chunk_id: string;
  chunk_type: string;
  article_num: number | null;
  clause_num: number | null;
  point_num: string | null;
  source_order: number | null;
  content_kind: string;
  text_content: string;
  display_path: string | null;
  parser_confidence: number | null;
  source_page: number | null;
  has_embedding: boolean;
}

export interface AdminDocumentHistoryItem {
  queue_id: string;
  change_type: string;
  review_status: string;
  processing_status: string;
  source_file_name: string | null;
  reviewer_note: string | null;
  reject_reason: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AdminDocumentDetail extends AdminDocumentItem {
  replaced_by_id: string | null;
  domain_tags: string[];
  warnings: string[];
  source_file_name: string | null;
  structure_summary: Record<string, number>;
  history: AdminDocumentHistoryItem[];
  chunks: AdminDocumentChunk[];
}

export interface AdminDocumentsResponse {
  items: AdminDocumentItem[];
  total: number;
  page: number;
  page_size: number;
  summary: AdminDocumentSummary;
}

export interface DuplicateCandidate {
  doc_id: string;
  title: string;
  doc_type: string;
  status: string;
  review_status: string;
  effective_date: string;
  issuer: string;
  source_url: string | null;
  reason?: string;
}

export interface TrafficSignAsset {
  asset_id: string;
  url: string;
  width: number | null;
  height: number | null;
  mime_type: string;
}

export interface TrafficSign {
  sign_code: string;
  sign_name: string;
  aliases: string[];
  sign_group: string | null;
  recognition_text: string | null;
  meaning_text: string;
  application_text: string | null;
  exception_text: string | null;
  source_locator: string;
  citation_chunk_id: string;
  primary_asset: TrafficSignAsset | null;
}

export interface TrafficSignListResponse {
  items: TrafficSign[];
  total: number;
}

export interface NotificationItem {
  notification_id: string;
  doc_id: string;
  queue_id: string | null;
  change_type: string;
  title: string;
  summary: string;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
}

const AUTH_STORAGE_KEY = 'legalai_auth';

export function getStoredAuth(): AuthSession | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function setStoredAuth(session: AuthSession | null): void {
  if (typeof window === 'undefined') return;
  if (session) {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  } else {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  window.dispatchEvent(new Event('legalai-auth-changed'));
}

export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const session = getStoredAuth();
  const headers = new Headers(init.headers);
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`);
  }
  return fetch(input, { ...init, headers });
}

async function parseAuthResponse(response: Response): Promise<AuthSession> {
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Đăng nhập không thành công: ${response.status}`));
  }
  const session = (await response.json()) as AuthSession;
  setStoredAuth(session);
  return session;
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return parseAuthResponse(response);
}

export async function register(
  email: string,
  password: string,
  confirmPassword: string,
  username?: string,
): Promise<AuthSession> {
  const response = await fetch('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      confirm_password: confirmPassword,
      username: username || undefined,
    }),
  });
  return parseAuthResponse(response);
}

export async function logout(): Promise<void> {
  try {
    await authFetch('/api/v1/auth/logout', { method: 'POST' });
  } finally {
    setStoredAuth(null);
  }
}

export async function fetchCurrentUser(): Promise<UserAccount> {
  const response = await authFetch('/api/v1/auth/me');
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải thông tin tài khoản: ${response.status}`));
  }
  const user = (await response.json()) as UserAccount;
  const current = getStoredAuth();
  if (current) {
    setStoredAuth({ ...current, user });
  }
  return user;
}

export async function updateProfile(email: string, username: string): Promise<UserAccount> {
  const response = await authFetch('/api/v1/auth/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể cập nhật thông tin tài khoản: ${response.status}`));
  }
  const user = (await response.json()) as UserAccount;
  const current = getStoredAuth();
  if (current) {
    setStoredAuth({ ...current, user });
  }
  return user;
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
  confirmPassword: string,
): Promise<void> {
  const response = await authFetch('/api/v1/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể đổi mật khẩu: ${response.status}`));
  }
}

function adminUserSearchParams(filters: AdminUserFilters, includePaging = true) {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.role) params.set('role', filters.role);
  if (filters.is_active !== undefined) params.set('is_active', String(filters.is_active));
  if (includePaging) {
    if (filters.page) params.set('page', String(filters.page));
    if (filters.page_size) params.set('page_size', String(filters.page_size));
  }
  return params;
}

export async function fetchAdminUsers(filters: AdminUserFilters): Promise<AdminUserListResponse> {
  const response = await authFetch(`/api/v1/admin/users?${adminUserSearchParams(filters)}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải danh sách người dùng: ${response.status}`));
  }
  return response.json();
}

export async function createAdminUser(payload: AdminUserCreatePayload): Promise<AdminUserAccount> {
  const response = await authFetch('/api/v1/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tạo người dùng: ${response.status}`));
  }
  return response.json();
}

export async function updateAdminUser(
  userId: string,
  payload: AdminUserUpdatePayload,
): Promise<AdminUserAccount> {
  const response = await authFetch(`/api/v1/admin/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể cập nhật người dùng: ${response.status}`));
  }
  return response.json();
}

export async function resetAdminUserPassword(
  userId: string,
  newPassword: string,
  confirmPassword: string,
): Promise<void> {
  const response = await authFetch(`/api/v1/admin/users/${userId}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể đặt lại mật khẩu: ${response.status}`));
  }
}

export async function exportAdminUsers(filters: AdminUserFilters): Promise<void> {
  const response = await authFetch(
    `/api/v1/admin/users/export?${adminUserSearchParams(filters, false)}`,
  );
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể xuất danh sách người dùng: ${response.status}`));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'vt-law-users.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function fetchNotifications(unreadOnly = false): Promise<NotificationListResponse> {
  const response = await authFetch(`/api/v1/notifications?unread_only=${unreadOnly ? 'true' : 'false'}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải thông báo: ${response.status}`));
  }
  return response.json();
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  const response = await authFetch(`/api/v1/notifications/${notificationId}/read`, { method: 'PATCH' });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể đánh dấu đã đọc thông báo: ${response.status}`));
  }
}

export async function markAllNotificationsRead(): Promise<void> {
  const response = await authFetch('/api/v1/notifications/read-all', { method: 'PATCH' });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể đánh dấu đã đọc tất cả thông báo: ${response.status}`));
  }
}

export function subscribeNotifications(
  onNotification: (notification: NotificationItem) => void,
  onError?: (detail: string) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await authFetch('/api/v1/notifications/stream', {
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(await parseApiError(response, `Không thể kết nối luồng thông báo: ${response.status}`));
      }
      if (!response.body) {
        throw new Error('Trình duyệt hiện không hỗ trợ nhận thông báo theo thời gian thực.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const raw = trimmed.slice(6);
          if (!raw || raw === '{}') continue;
          const payload = JSON.parse(raw);
          if (payload.type === 'notification' && payload.notification) {
            onNotification(payload.notification as NotificationItem);
          }
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      onError?.(error instanceof Error ? error.message : 'Không thể nhận thông báo theo thời gian thực.');
    }
  })();

  return () => controller.abort();
}

export async function fetchChatSessions(): Promise<ChatSessionsResponse> {
  const response = await authFetch('/api/v1/chat/sessions');
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải danh sách cuộc trò chuyện: ${response.status}`));
  }
  return response.json();
}

export async function fetchBookmarkedChatSessions(): Promise<ChatSessionsResponse> {
  const response = await authFetch('/api/v1/chat/bookmarks');
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải danh sách đã lưu: ${response.status}`));
  }
  return response.json();
}

export async function fetchChatSessionMessages(sessionId: string): Promise<ChatMessagesResponse> {
  const response = await authFetch(`/api/v1/chat/sessions/${sessionId}/messages`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải nội dung cuộc trò chuyện: ${response.status}`));
  }
  return response.json();
}

export async function bookmarkChatSession(
  sessionId: string,
  bookmarkTitle: string,
): Promise<ChatSessionSummary> {
  const response = await authFetch(`/api/v1/chat/sessions/${sessionId}/bookmark`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bookmark_title: bookmarkTitle }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể lưu cuộc trò chuyện: ${response.status}`));
  }
  const payload = (await response.json()) as ChatSessionBookmarkResponse;
  window.dispatchEvent(new Event('legalai-bookmarks-changed'));
  return payload.session;
}

export async function unbookmarkChatSession(sessionId: string): Promise<void> {
  const response = await authFetch(`/api/v1/chat/sessions/${sessionId}/bookmark`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể bỏ lưu cuộc trò chuyện: ${response.status}`));
  }
  window.dispatchEvent(new Event('legalai-bookmarks-changed'));
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await authFetch(`/api/v1/chat/sessions/${sessionId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể xóa cuộc trò chuyện: ${response.status}`));
  }
}

async function parseApiError(response: Response, fallback: string): Promise<string> {
  const raw = await response.text();
  return parseApiErrorText(raw, fallback);
}

function parseApiErrorText(raw: string, fallback: string): string {
  if (!raw) return fallback;

  try {
    const parsed = JSON.parse(raw) as {
      detail?: string | { message?: string; code?: string; blockers?: string[] } | Array<{ msg?: string }>;
    };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail;
    }
    if (
      parsed.detail &&
      !Array.isArray(parsed.detail) &&
      typeof parsed.detail === 'object' &&
      Array.isArray(parsed.detail.blockers) &&
      parsed.detail.blockers.length > 0
    ) {
      return parsed.detail.blockers.map(localizeApiBlocker).join('\n');
    }
    if (
      parsed.detail &&
      !Array.isArray(parsed.detail) &&
      typeof parsed.detail === 'object' &&
      typeof parsed.detail.message === 'string' &&
      parsed.detail.message.trim()
    ) {
      return parsed.detail.code ? `${parsed.detail.message} (${parsed.detail.code})` : parsed.detail.message;
    }
    if (Array.isArray(parsed.detail)) {
      const firstMessage = parsed.detail.find((item) => typeof item?.msg === 'string' && item.msg.trim())?.msg;
      if (firstMessage) return firstMessage;
    }
  } catch {
    return raw;
  }

  return raw || fallback;
}

function fileNameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const match = value.match(/filename="?([^";]+)"?/i);
  return match?.[1] || null;
}

export async function downloadAdminSource(url: string, fallbackName = 'source-document'): Promise<void> {
  const response = await authFetch(url);
  if (!response.ok) {
    throw new Error(await response.text() || `Không thể tải tệp nguồn: ${response.status}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fileNameFromDisposition(response.headers.get('content-disposition')) || fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

// ---- streamChat ----
// Uses fetch + ReadableStream to support POST body
export function streamChat(
  question: string,
  sessionId: string,
  onDone: (meta: DoneMeta) => void,
  onError: (detail: string) => void,
): () => void { // Returns abort function
  const controller = new AbortController();

  (async () => {
    try {
      const session = getStoredAuth();
      const headers = new Headers({
        'Content-Type': 'application/json',
      });
      if (session?.access_token) {
        headers.set('Authorization', `Bearer ${session.access_token}`);
      }

      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          question,
          session_id: sessionId || undefined,
          language: 'vi',
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response, `Không thể gửi câu hỏi: ${response.status}`));
      }

      if (!response.body) {
        throw new Error('Trình duyệt hiện không hỗ trợ nhận câu trả lời theo thời gian thực.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        // Keep the last partial line in the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;

          const jsonStr = trimmed.slice(6);
          try {
            const data = JSON.parse(jsonStr);
            if (data.type === 'done') {
              onDone({
                trace_id: data.trace_id,
                session_id: data.session_id,
                content: data.content || '',
                citations: data.citations || [],
                risk_level: data.risk_level,
                answer_mode: data.answer_mode,
                confidence: data.confidence,
                provision_citations: data.provision_citations || [],
                document_sources: data.document_sources || [],
                historical_references: data.historical_references || [],
                clarification_question: data.clarification_question ?? null,
                faithfulness_score: data.faithfulness_score ?? null,
                is_out_of_scope: data.is_out_of_scope || false,
                reranker_failed: data.reranker_failed || false,
                reranker_used: data.reranker_used || false,
                reranker_error_code: data.reranker_error_code ?? null,
                low_confidence: data.low_confidence || false,
                retrieval_candidate_count: data.retrieval_candidate_count ?? 0,
                rerank_top_score: data.rerank_top_score ?? null,
                guardrail_triggered: data.guardrail_triggered || false,
                guardrail_stage: data.guardrail_stage ?? null,
                guardrail_reason: data.guardrail_reason ?? null,
              });
            } else if (data.type === 'error') {
              onError(data.detail || 'Đã xảy ra lỗi khi nhận câu trả lời.');
            }
          } catch (e) {
            console.error('Error parsing SSE line:', line, e);
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        console.log('Chat stream aborted by client');
      } else {
        onError(err instanceof Error ? err.message : 'Đã xảy ra lỗi kết nối.');
      }
    }
  })();

  return () => {
    controller.abort();
  };
}

// ---- fetchDocuments ----
export interface DocumentSearchParams {
  q?: string;
  doc_type?: string;
  issuer?: string;
  year?: number;
  page?: number;
  page_size?: number;
}

export async function fetchDocuments(
  params: DocumentSearchParams
): Promise<DocumentsResponse> {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.append('q', params.q);
  if (params.doc_type) searchParams.append('doc_type', params.doc_type);
  if (params.issuer) searchParams.append('issuer', params.issuer);
  if (params.year) searchParams.append('year', params.year.toString());
  if (params.page) searchParams.append('page', params.page.toString());
  if (params.page_size) searchParams.append('page_size', params.page_size.toString());

  const response = await fetch(`/api/v1/documents?${searchParams.toString()}`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Không thể tải danh sách văn bản: ${response.status}`);
  }
  return response.json();
}

export async function fetchKbV2HistoricalCitation(retrievalUnitId: string): Promise<KbV2HistoricalCitation> {
  const response = await fetch(`/api/v1/documents/citations/${retrievalUnitId}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải trích dẫn lịch sử: ${response.status}`));
  }
  return response.json();
}

export async function fetchTrafficSigns(query: string, limit = 3): Promise<TrafficSignListResponse> {
  const searchParams = new URLSearchParams({ query, limit: String(limit) });
  const response = await fetch(`/api/v1/traffic-signs?${searchParams.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text() || `Không thể tải danh mục biển báo: ${response.status}`);
  }
  return response.json();
}

export interface AdminDocumentSearchParams extends DocumentSearchParams {
  status?: string;
}

function appendSearchParams(searchParams: URLSearchParams, params: Record<string, string | number | undefined>) {
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      searchParams.append(key, String(value));
    }
  });
}

export async function fetchAdminDocuments(
  params: AdminDocumentSearchParams
): Promise<AdminDocumentsResponse> {
  const searchParams = new URLSearchParams();
  appendSearchParams(searchParams, {
    q: params.q,
    doc_type: params.doc_type,
    issuer: params.issuer,
    year: params.year,
    status: params.status,
    page: params.page,
    page_size: params.page_size,
  });

  const response = await authFetch(`/api/v1/admin/documents?${searchParams.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text() || `Không thể tải danh sách văn bản quản trị: ${response.status}`);
  }
  return response.json();
}

export async function fetchAdminDocumentDetail(docId: string): Promise<AdminDocumentDetail> {
  const response = await authFetch(`/api/v1/admin/documents/${docId}`);
  if (!response.ok) {
    throw new Error(await response.text() || `Không thể tải chi tiết văn bản: ${response.status}`);
  }
  return response.json();
}

export async function fetchKbV2RevisionList(params: {
  q?: string;
  publication_status?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<KbV2RevisionListResponse> {
  const searchParams = new URLSearchParams();
  appendSearchParams(searchParams, params);
  const response = await authFetch(`/api/v1/admin/kb-v2/revisions?${searchParams.toString()}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải danh sách hồ sơ xử lý: ${response.status}`));
  }
  return response.json();
}

export async function fetchKbV2RevisionDetail(revisionId: string): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`/api/v1/admin/kb-v2/revisions/${revisionId}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải chi tiết hồ sơ xử lý: ${response.status}`));
  }
  return response.json();
}

export async function fetchKbV2PublishedDocuments(params: {
  q?: string;
  status?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<KbV2PublishedDocumentListResponse> {
  const searchParams = new URLSearchParams();
  appendSearchParams(searchParams, params);
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/documents?${searchParams.toString()}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải danh sách văn bản trong kho: ${response.status}`));
  }
  return response.json();
}

export async function fetchKbV2PublishedDocumentDetail(documentId: string): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/documents/${documentId}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tải chi tiết văn bản trong kho: ${response.status}`));
  }
  return response.json();
}

export async function updateKbV2PublishedDocument(
  documentId: string,
  payload: {
    title?: string | null;
    document_number?: string | null;
    document_type?: string | null;
    issuing_authority?: string | null;
    issued_date?: string | null;
    effective_date?: string | null;
    expiry_date?: string | null;
    source_url?: string | null;
    source_downloaded_at?: string | null;
    source_note?: string | null;
    source_file_name?: string | null;
    document_role?: string | null;
  },
): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/documents/${documentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể cập nhật thông tin văn bản: ${response.status}`));
  }
  return response.json();
}

export async function fetchKbV2RelationTargets(params: {
  q?: string;
  exclude_document_id?: string;
  limit?: number;
} = {}): Promise<KbV2RelationTargetListResponse> {
  const searchParams = new URLSearchParams();
  appendSearchParams(searchParams, params);
  const response = await authFetch(`/api/v1/admin/kb-v2/relation-targets?${searchParams.toString()}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tìm văn bản liên quan: ${response.status}`));
  }
  return response.json();
}

function localizeApiBlocker(value: string): string {
  const normalized = value.trim();
  const lower = normalized.toLowerCase();
  if (!normalized) return 'Hồ sơ còn điều kiện cần xử lý trước khi đưa vào kho.';
  if (lower.includes('no approved answerable canonical nodes')) {
    return 'Chưa có mục nội dung đã duyệt nào được dùng cho hỏi đáp. Hãy đánh dấu ít nhất một mục là dùng cho hỏi đáp trước khi đưa vào kho.';
  }
  if (lower.includes('revision parsing is incomplete') || lower.includes('parse')) {
    return 'Quá trình tách nội dung chưa hoàn tất hoặc bị lỗi. Vui lòng kiểm tra lại file nguồn.';
  }
  if (lower.includes('summary proposal is missing')) {
    return 'Hồ sơ chưa có tóm tắt được xác nhận.';
  }
  if (lower.includes('summary proposal is not approved')) {
    return 'Tóm tắt của hồ sơ chưa được duyệt.';
  }
  if (lower.includes('canonical nodes still need admin review')) {
    return 'Vẫn còn mục nội dung cần kiểm tra thủ công.';
  }
  if (lower.includes('approved table/form/appendix/image nodes need answerable')) {
    return 'Có bảng, mẫu, phụ lục hoặc hình ảnh đã duyệt nhưng chưa chọn dùng cho hỏi đáp hay chỉ để đối chiếu.';
  }
  if (lower.includes('required metadata field is not approved')) {
    return 'Thông tin văn bản còn trường bắt buộc chưa được xác nhận.';
  }
  if (lower.includes('metadata conflict is unresolved')) {
    return 'Thông tin văn bản còn đề xuất mâu thuẫn cần xử lý.';
  }
  if (lower.includes('amendment relation is unresolved')) {
    return 'Văn bản sửa đổi hoặc bổ sung cần có quan hệ văn bản đã được xác nhận.';
  }
  if (lower.includes('missing source asset checksum')) {
    return 'File nguồn chưa có mã kiểm tra toàn vẹn.';
  }
  if (lower.includes('object storage is required')) {
    return 'File nguồn chưa được lưu ở kho lưu trữ bắt buộc.';
  }
  return normalized;
}

export async function updateKbV2RevisionSource(
  revisionId: string,
  payload: {
    source_url?: string | null;
    source_downloaded_at?: string | null;
    source_note?: string | null;
    source_file_name?: string | null;
  },
): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/revisions/${revisionId}/source`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể cập nhật thông tin nguồn: ${response.status}`));
  }
  return response.json();
}

export async function updateKbV2PublishedDocumentStatus(
  documentId: string,
  payload: {
    status: 'active' | 'suspended' | 'expired' | 'replaced' | 'annulled';
    note?: string;
    replacement_document_id?: string;
  },
): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/documents/${documentId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể đổi trạng thái văn bản: ${response.status}`));
  }
  return response.json();
}

export async function uploadKbV2Revision(payload: {
  file: File;
  title: string;
  source_url: string;
  source_downloaded_at: string;
  source_note: string;
  document_number?: string;
  document_type?: string;
  document_role?: string;
  issuing_authority?: string;
  issued_date?: string;
  effective_date?: string;
  expiry_date?: string;
}): Promise<KbV2UploadResponse> {
  const formData = new FormData();
  formData.append('file', payload.file);
  formData.append('title', payload.title);
  formData.append('source_url', payload.source_url);
  formData.append('source_downloaded_at', payload.source_downloaded_at);
  formData.append('source_note', payload.source_note);
  if (payload.document_number) formData.append('document_number', payload.document_number);
  if (payload.document_type) formData.append('document_type', payload.document_type);
  if (payload.document_role) formData.append('document_role', payload.document_role);
  if (payload.issuing_authority) formData.append('issuing_authority', payload.issuing_authority);
  if (payload.issued_date) formData.append('issued_date', payload.issued_date);
  if (payload.effective_date) formData.append('effective_date', payload.effective_date);
  if (payload.expiry_date) formData.append('expiry_date', payload.expiry_date);

  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/revisions/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw) as { detail?: string | (Record<string, unknown> & { message?: string; code?: string }) };
      if (
        parsed.detail &&
        typeof parsed.detail === 'object' &&
        !Array.isArray(parsed.detail) &&
        parsed.detail.code === 'KB_DUPLICATE_SOURCE'
      ) {
        throw new DocumentRepositoryDuplicateSourceError(
          parsed.detail.message || 'Tệp DOCX này đã tồn tại trong kho dữ liệu hiện tại.',
          parsed.detail,
        );
      }
    } catch (err) {
      if (err instanceof DocumentRepositoryDuplicateSourceError) throw err;
    }
    throw new Error(parseApiErrorText(raw, `Không thể tạo hồ sơ xử lý mới: ${response.status}`));
  }
  return response.json();
}

export async function uploadKbV2ReplacementRevision(documentId: string, payload: {
  file: File;
  title: string;
  source_url: string;
  source_downloaded_at: string;
  source_note: string;
  document_number?: string;
  document_type?: string;
  document_role?: string;
  issuing_authority?: string;
  issued_date?: string;
  effective_date?: string;
  expiry_date?: string;
}): Promise<KbV2UploadResponse> {
  const formData = new FormData();
  formData.append('file', payload.file);
  formData.append('title', payload.title);
  formData.append('source_url', payload.source_url);
  formData.append('source_downloaded_at', payload.source_downloaded_at);
  formData.append('source_note', payload.source_note);
  if (payload.document_number) formData.append('document_number', payload.document_number);
  if (payload.document_type) formData.append('document_type', payload.document_type);
  if (payload.document_role) formData.append('document_role', payload.document_role);
  if (payload.issuing_authority) formData.append('issuing_authority', payload.issuing_authority);
  if (payload.issued_date) formData.append('issued_date', payload.issued_date);
  if (payload.effective_date) formData.append('effective_date', payload.effective_date);
  if (payload.expiry_date) formData.append('expiry_date', payload.expiry_date);

  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/documents/${documentId}/replacement-revisions/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw) as { detail?: string | (Record<string, unknown> & { message?: string; code?: string }) };
      if (
        parsed.detail &&
        typeof parsed.detail === 'object' &&
        !Array.isArray(parsed.detail) &&
        parsed.detail.code === 'KB_DUPLICATE_SOURCE'
      ) {
        throw new DocumentRepositoryDuplicateSourceError(
          parsed.detail.message || 'Tệp DOCX này đã tồn tại trong kho dữ liệu hiện tại.',
          parsed.detail,
        );
      }
    } catch (err) {
      if (err instanceof DocumentRepositoryDuplicateSourceError) throw err;
    }
    throw new Error(parseApiErrorText(raw, `Không thể tạo hồ sơ thay file nguồn: ${response.status}`));
  }
  return response.json();
}

export async function reviewKbV2Node(
  nodeId: string,
  decision: 'approved' | 'rejected',
  note?: string,
  answerable?: boolean,
) {
  const response = await authFetch(`/api/v1/admin/kb-v2/nodes/${nodeId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note, answerable }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể lưu quyết định cho mục nội dung: ${response.status}`));
  }
  return response.json();
}

export async function resetKbV2NodeReview(nodeId: string, note?: string) {
  const response = await authFetch(`/api/v1/admin/kb-v2/nodes/${nodeId}/reset-review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể đưa mục nội dung về trạng thái cần kiểm tra: ${response.status}`));
  }
  return response.json();
}

export async function bulkReviewKbV2RiskyNodes(
  revisionId: string,
  payload: {
    node_type: 'table' | 'appendix' | 'form' | 'image_caption';
    mode: 'answerable' | 'review_only' | 'reset' | 'rejected';
    note?: string;
  },
): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`/api/v1/admin/kb-v2/revisions/${revisionId}/risky-nodes/bulk-review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể xử lý hàng loạt nội dung cần kiểm tra kỹ: ${response.status}`));
  }
  return response.json();
}

export async function reviewKbV2MetadataProposal(
  proposalId: string,
  decision: 'approved' | 'rejected',
  note?: string,
  proposed_value?: string,
) {
  const response = await authFetch(`/api/v1/admin/kb-v2/metadata-proposals/${proposalId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note, proposed_value }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể lưu thông tin văn bản đã chỉnh: ${response.status}`));
  }
  return response.json();
}

export async function reviewKbV2Relation(relationId: string, decision: 'approved' | 'rejected', note?: string) {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/relations/${relationId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể lưu quyết định cho quan hệ văn bản: ${response.status}`));
  }
  return response.json();
}

export async function createKbV2RelationProposal(
  revisionId: string,
  payload: {
    target_document_id: string;
    relation_type: 'amends' | 'supplements' | 'replaces' | 'annuls' | 'guides' | 'depends_on';
    source_locator?: string;
    target_locator?: string;
    note?: string;
  },
): Promise<KbV2DocumentRelationOut> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/revisions/${revisionId}/relations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tạo quan hệ văn bản: ${response.status}`));
  }
  return response.json();
}

export async function updateKbV2Relation(
  relationId: string,
  payload: {
    target_document_id?: string;
    relation_type?: 'amends' | 'supplements' | 'replaces' | 'annuls' | 'guides' | 'depends_on';
    source_locator?: string;
    target_locator?: string;
    note?: string;
  },
): Promise<KbV2DocumentRelationOut> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/relations/${relationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể cập nhật quan hệ văn bản: ${response.status}`));
  }
  return response.json();
}

export async function reviewKbV2Summary(
  summaryId: string,
  payload: { decision: 'approved' | 'rejected'; content?: string },
) {
  const response = await authFetch(`/api/v1/admin/kb-v2/summaries/${summaryId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể lưu tóm tắt chuẩn: ${response.status}`));
  }
  return response.json();
}

export async function publishKbV2Revision(revisionId: string): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`/api/v1/admin/kb-v2/revisions/${revisionId}/publish`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể công bố hồ sơ xử lý: ${response.status}`));
  }
  return response.json();
}

export async function suspendKbV2Revision(revisionId: string, reason: string): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`/api/v1/admin/kb-v2/revisions/${revisionId}/suspend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tạm ngừng hồ sơ xử lý: ${response.status}`));
  }
  return response.json();
}

export async function unsuspendKbV2Revision(revisionId: string): Promise<KbV2RevisionDetailResponse> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/revisions/${revisionId}/unsuspend`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể khôi phục hồ sơ xử lý: ${response.status}`));
  }
  return response.json();
}

export async function deleteKbV2Relation(relationId: string): Promise<void> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/relations/${relationId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể loại bỏ quan hệ văn bản: ${response.status}`));
  }
}

export async function createKbV2MetadataProposal(
  revisionId: string,
  payload: {
    field_name:
      | 'title'
      | 'document_number'
      | 'document_type'
      | 'document_role'
      | 'issuing_authority'
      | 'issued_date'
      | 'effective_date'
      | 'expiry_date';
    proposed_value: string;
    note?: string;
  },
): Promise<KbV2MetadataProposalOut> {
  const response = await authFetch(`${ADMIN_DOCUMENT_REPOSITORY_ROUTE_PREFIX}/revisions/${revisionId}/metadata-proposals`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, `Không thể tạo đề xuất chỉnh thông tin văn bản: ${response.status}`));
  }
  return response.json();
}

export async function fetchPublishedDocuments(params: {
  q?: string;
  status?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<PublishedDocumentListResponse> {
  return fetchKbV2PublishedDocuments(params);
}

export async function fetchPublishedDocumentDetail(documentId: string): Promise<PublishedDocumentDetailResponse> {
  return fetchKbV2PublishedDocumentDetail(documentId);
}

export async function updatePublishedDocument(
  documentId: string,
  payload: Parameters<typeof updateKbV2PublishedDocument>[1],
): Promise<PublishedDocumentDetailResponse> {
  return updateKbV2PublishedDocument(documentId, payload);
}

export async function updatePublishedDocumentStatus(
  documentId: string,
  payload: Parameters<typeof updateKbV2PublishedDocumentStatus>[1],
): Promise<PublishedDocumentDetailResponse> {
  return updateKbV2PublishedDocumentStatus(documentId, payload);
}

export async function reviewDocumentRelation(
  relationId: string,
  decision: 'approved' | 'rejected',
  note?: string,
) {
  return reviewKbV2Relation(relationId, decision, note);
}

export async function createDocumentRelationProposal(
  revisionId: string,
  payload: Parameters<typeof createKbV2RelationProposal>[1],
) {
  return createKbV2RelationProposal(revisionId, payload);
}

export async function updateDocumentRelation(
  relationId: string,
  payload: Parameters<typeof updateKbV2Relation>[1],
) {
  return updateKbV2Relation(relationId, payload);
}

export async function deleteDocumentRelation(relationId: string) {
  return deleteKbV2Relation(relationId);
}

export async function fetchQualityOverview(periodDays = 7): Promise<QualityOverview> {
  const response = await authFetch(`/api/v1/admin/quality/overview?period_days=${periodDays}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, 'Không thể tải tình hình chất lượng AI.'));
  }
  return response.json();
}

export async function fetchQualityIssues(
  status: QualityIssueItem['status'] = 'open',
  page = 1,
  pageSize = 20,
): Promise<QualityIssueListResponse> {
  const params = new URLSearchParams({ status, page: String(page), page_size: String(pageSize) });
  const response = await authFetch(`/api/v1/admin/quality/issues?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, 'Không thể tải danh sách vấn đề.'));
  }
  return response.json();
}

export async function fetchQualityIssue(issueId: string): Promise<QualityIssueDetail> {
  const response = await authFetch(`/api/v1/admin/quality/issues/${issueId}`);
  if (!response.ok) {
    throw new Error(await parseApiError(response, 'Không thể tải bằng chứng của vấn đề.'));
  }
  return response.json();
}

export async function reviewQualityIssue(
  issueId: string,
  payload: {
    status: 'reviewing' | 'resolved' | 'dismissed';
    conclusion: 'confirmed' | 'false_positive' | 'kb_gap' | 'retrieval_miss';
    root_cause?: string;
    note: string;
  },
): Promise<QualityIssueDetail> {
  const response = await authFetch(`/api/v1/admin/quality/issues/${issueId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseApiError(response, 'Không thể lưu kết luận đánh giá.'));
  }
  return response.json();
}

export async function fetchQualityReleaseChecks(): Promise<QualityReleaseCheckListResponse> {
  const response = await authFetch('/api/v1/admin/quality/release-checks?page=1&page_size=5');
  if (!response.ok) {
    throw new Error(await parseApiError(response, 'Không thể tải lịch sử kiểm tra phát hành.'));
  }
  return response.json();
}
