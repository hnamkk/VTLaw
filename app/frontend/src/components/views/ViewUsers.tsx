import React from 'react';
import {
    DownloadSimple,
    Key,
    LockKey,
    LockKeyOpen,
    MagnifyingGlass,
    PencilSimple,
    Plus,
    Users,
    X,
} from '@phosphor-icons/react';
import { PageFrame, TableShell } from '../ui';
import {
    type AdminUserAccount,
    createAdminUser,
    exportAdminUsers,
    fetchAdminUsers,
    getStoredAuth,
    resetAdminUserPassword,
    setStoredAuth,
    updateAdminUser,
} from '../../lib/api';

type UserForm = {
    username: string;
    email: string;
    role: 'USER' | 'ADMIN';
    password: string;
    confirmPassword: string;
};

const EMPTY_FORM: UserForm = {
    username: '',
    email: '',
    role: 'USER',
    password: '',
    confirmPassword: '',
};

function formatDate(value: string | null) {
    if (!value) return 'Chưa có';
    return new Date(value).toLocaleString('vi-VN', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function initials(user: AdminUserAccount) {
    const source = user.username?.trim() || user.email;
    return source
        .split(/\s+/)
        .slice(-2)
        .map((part) => part[0])
        .join('')
        .toUpperCase();
}

function validateForm(form: UserForm, mode: 'create' | 'edit') {
    const username = form.username.trim().replace(/\s+/g, ' ');
    const email = form.email.trim().toLowerCase();
    if (username.length < 2 || username.length > 50) return 'Họ và tên phải có từ 2 đến 50 ký tự.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Email không hợp lệ.';
    if (mode === 'create' || form.password || form.confirmPassword) {
        if (form.password.length < 8 || form.password.length > 128) return 'Mật khẩu phải có từ 8 đến 128 ký tự.';
        if (/\s/.test(form.password) || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) {
            return 'Mật khẩu phải có chữ cái, chữ số và không chứa khoảng trắng.';
        }
        if (form.password !== form.confirmPassword) return 'Xác nhận mật khẩu chưa khớp.';
    }
    return null;
}

export default function ViewUsers({ activeView }: { activeView: string }) {
    const [query, setQuery] = React.useState('');
    const deferredQuery = React.useDeferredValue(query);
    const [roleFilter, setRoleFilter] = React.useState<'' | 'USER' | 'ADMIN'>('');
    const [statusFilter, setStatusFilter] = React.useState<'' | 'active' | 'locked'>('');
    const [users, setUsers] = React.useState<AdminUserAccount[]>([]);
    const [total, setTotal] = React.useState(0);
    const [page, setPage] = React.useState(1);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);
    const [editor, setEditor] = React.useState<{ mode: 'create' | 'edit'; user?: AdminUserAccount } | null>(null);
    const [form, setForm] = React.useState<UserForm>(EMPTY_FORM);
    const [formError, setFormError] = React.useState<string | null>(null);
    const [saving, setSaving] = React.useState(false);
    const [statusTarget, setStatusTarget] = React.useState<AdminUserAccount | null>(null);
    const [statusSaving, setStatusSaving] = React.useState(false);
    const [exporting, setExporting] = React.useState(false);
    const [currentUserId, setCurrentUserId] = React.useState<string | null>(null);
    const pageSize = 20;

    const loadUsers = React.useCallback(async (nextPage: number) => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetchAdminUsers({
                q: deferredQuery.trim() || undefined,
                role: roleFilter || undefined,
                is_active: statusFilter ? statusFilter === 'active' : undefined,
                page: nextPage,
                page_size: pageSize,
            });
            setUsers(response.items);
            setTotal(response.total);
            setPage(response.page);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Không thể tải danh sách người dùng.');
        } finally {
            setLoading(false);
        }
    }, [deferredQuery, roleFilter, statusFilter]);

    React.useEffect(() => {
        if (activeView !== 'view-users') return;
        setCurrentUserId(getStoredAuth()?.user.user_id ?? null);
        void loadUsers(1);
    }, [activeView, loadUsers]);

    React.useEffect(() => {
        if (!editor && !statusTarget) return;
        function handleEscape(event: KeyboardEvent) {
            if (event.key !== 'Escape' || saving || statusSaving) return;
            setEditor(null);
            setStatusTarget(null);
        }
        window.addEventListener('keydown', handleEscape);
        return () => window.removeEventListener('keydown', handleEscape);
    }, [editor, saving, statusSaving, statusTarget]);

    function openCreate() {
        setForm(EMPTY_FORM);
        setFormError(null);
        setEditor({ mode: 'create' });
    }

    function openEdit(user: AdminUserAccount) {
        setForm({
            username: user.username || '',
            email: user.email,
            role: user.role,
            password: '',
            confirmPassword: '',
        });
        setFormError(null);
        setEditor({ mode: 'edit', user });
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!editor) return;
        const validationError = validateForm(form, editor.mode);
        if (validationError) {
            setFormError(validationError);
            return;
        }
        setSaving(true);
        setFormError(null);
        try {
            if (editor.mode === 'create') {
                await createAdminUser({
                    username: form.username,
                    email: form.email,
                    password: form.password,
                    confirm_password: form.confirmPassword,
                    role: form.role,
                });
            } else if (editor.user) {
                const updated = await updateAdminUser(editor.user.user_id, {
                    username: form.username,
                    email: form.email,
                    role: form.role,
                });
                if (updated.user_id === currentUserId) {
                    const session = getStoredAuth();
                    if (session) setStoredAuth({ ...session, user: updated });
                }
                if (form.password || form.confirmPassword) {
                    await resetAdminUserPassword(
                        editor.user.user_id,
                        form.password,
                        form.confirmPassword,
                    );
                }
            }
            setEditor(null);
            await loadUsers(editor.mode === 'create' ? 1 : page);
        } catch (err: unknown) {
            setFormError(err instanceof Error ? err.message : 'Không thể lưu tài khoản.');
        } finally {
            setSaving(false);
        }
    }

    async function handleToggleStatus() {
        if (!statusTarget) return;
        setStatusSaving(true);
        setError(null);
        try {
            await updateAdminUser(statusTarget.user_id, { is_active: !statusTarget.is_active });
            setStatusTarget(null);
            await loadUsers(page);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Không thể cập nhật trạng thái tài khoản.');
            setStatusTarget(null);
        } finally {
            setStatusSaving(false);
        }
    }

    async function handleExport() {
        setExporting(true);
        setError(null);
        try {
            await exportAdminUsers({
                q: deferredQuery.trim() || undefined,
                role: roleFilter || undefined,
                is_active: statusFilter ? statusFilter === 'active' : undefined,
            });
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Không thể xuất danh sách người dùng.');
        } finally {
            setExporting(false);
        }
    }

    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    const actions = (user: AdminUserAccount) => (
        <div className="user-actions">
            <button className="user-icon-button" type="button" onClick={() => openEdit(user)} title="Sửa tài khoản" aria-label={`Sửa ${user.username || user.email}`}>
                <PencilSimple size={17} />
            </button>
            <button
                className={`user-icon-button ${user.is_active ? 'danger' : 'success'}`}
                type="button"
                onClick={() => setStatusTarget(user)}
                disabled={user.user_id === currentUserId && user.is_active}
                title={user.is_active ? 'Khóa tài khoản' : 'Mở khóa tài khoản'}
                aria-label={`${user.is_active ? 'Khóa' : 'Mở khóa'} ${user.username || user.email}`}
            >
                {user.is_active ? <LockKey size={17} /> : <LockKeyOpen size={17} />}
            </button>
        </div>
    );

    return (
        <PageFrame
            id="view-users"
            active={activeView === 'view-users'}
            icon={Users}
            title="Quản lý người dùng"
        >
            <section className="user-toolbar" aria-label="Công cụ quản lý người dùng">
                <label className="user-search">
                    <MagnifyingGlass size={19} />
                    <input
                        type="search"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="Tìm theo tên hoặc email"
                        aria-label="Tìm theo tên hoặc email"
                    />
                </label>
                <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value as '' | 'USER' | 'ADMIN')} aria-label="Lọc vai trò">
                    <option value="">Vai trò: Tất cả</option>
                    <option value="USER">Người dùng</option>
                    <option value="ADMIN">Quản trị viên</option>
                </select>
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as '' | 'active' | 'locked')} aria-label="Lọc trạng thái">
                    <option value="">Trạng thái: Tất cả</option>
                    <option value="active">Đang hoạt động</option>
                    <option value="locked">Đã khóa</option>
                </select>
                <button className="btn-primary" type="button" onClick={openCreate}>
                    <Plus size={17} /> Thêm người dùng
                </button>
                <button className="btn-secondary" type="button" onClick={() => void handleExport()} disabled={exporting}>
                    <DownloadSimple size={17} /> {exporting ? 'Đang xuất' : 'Xuất danh sách'}
                </button>
            </section>

            {error && (
                <div className="error-state user-error" role="alert">
                    <strong>Không thể hoàn tất thao tác</strong>
                    <span>{error}</span>
                    <button className="btn-secondary" type="button" onClick={() => void loadUsers(page)}>Thử lại</button>
                </div>
            )}

            <section className="user-list-panel">
                <div className="user-list-heading">
                    <h2>Danh sách tài khoản</h2>
                    <span>{loading ? 'Đang tải...' : `${total.toLocaleString('vi-VN')} tài khoản`}</span>
                </div>

                {loading && users.length === 0 ? (
                    <div className="user-skeleton-list" aria-hidden="true">
                        {Array.from({ length: 5 }).map((_, index) => <div className="skeleton-panel !mt-0 !h-16" key={index} />)}
                    </div>
                ) : users.length === 0 ? (
                    <div className="empty-state user-empty">
                        <span className="empty-state-icon"><Users size={30} weight="duotone" /></span>
                        <strong>Không tìm thấy tài khoản</strong>
                        <p>Hãy đổi từ khóa, bộ lọc hoặc thêm người dùng mới.</p>
                    </div>
                ) : (
                    <>
                        <div className="user-desktop-table">
                            <TableShell>
                                <table className="data-table user-table">
                                    <thead><tr><th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th><th>Đăng nhập gần nhất</th><th aria-label="Hành động" /></tr></thead>
                                    <tbody>
                                        {users.map((user) => (
                                            <tr key={user.user_id}>
                                                <td>
                                                    <div className="user-identity">
                                                        <span className="user-avatar">{initials(user)}</span>
                                                        <span><strong>{user.username || 'Chưa đặt tên'}</strong><small>{user.email}</small></span>
                                                    </div>
                                                </td>
                                                <td><span className={`badge ${user.role === 'ADMIN' ? 'user-admin-badge' : ''}`}>{user.role === 'ADMIN' ? 'Quản trị viên' : 'Người dùng'}</span></td>
                                                <td><span className={`badge ${user.is_active ? 'active' : 'expired'}`}>{user.is_active ? 'Hoạt động' : 'Đã khóa'}</span></td>
                                                <td><span className="user-date">{formatDate(user.last_login_at)}</span></td>
                                                <td>{actions(user)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </TableShell>
                        </div>
                        <div className="user-mobile-list">
                            {users.map((user) => (
                                <article className="user-mobile-card" key={user.user_id}>
                                    <div className="user-identity">
                                        <span className="user-avatar">{initials(user)}</span>
                                        <span><strong>{user.username || 'Chưa đặt tên'}</strong><small>{user.email}</small></span>
                                    </div>
                                    <div className="user-mobile-meta">
                                        <span className={`badge ${user.role === 'ADMIN' ? 'user-admin-badge' : ''}`}>{user.role === 'ADMIN' ? 'Quản trị viên' : 'Người dùng'}</span>
                                        <span className={`badge ${user.is_active ? 'active' : 'expired'}`}>{user.is_active ? 'Hoạt động' : 'Đã khóa'}</span>
                                    </div>
                                    <p>Đăng nhập gần nhất: {formatDate(user.last_login_at)}</p>
                                    {actions(user)}
                                </article>
                            ))}
                        </div>
                    </>
                )}
            </section>

            {totalPages > 1 && (
                <div className="pagination">
                    <button className="btn-secondary" type="button" disabled={page <= 1 || loading} onClick={() => void loadUsers(page - 1)}>Trước</button>
                    <span>Trang {page} / {totalPages}</span>
                    <button className="btn-secondary" type="button" disabled={page >= totalPages || loading} onClick={() => void loadUsers(page + 1)}>Sau</button>
                </div>
            )}

            {editor && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => !saving && setEditor(null)}>
                    <section className="admin-modal user-editor-dialog" role="dialog" aria-modal="true" aria-label={editor.mode === 'create' ? 'Thêm người dùng' : 'Sửa người dùng'} onClick={(event) => event.stopPropagation()}>
                        <div className="admin-modal-head">
                            <div><p className="kb-kicker">Tài khoản</p><h3>{editor.mode === 'create' ? 'Thêm người dùng' : 'Sửa người dùng'}</h3></div>
                            <button className="admin-modal-close" type="button" onClick={() => setEditor(null)} disabled={saving} aria-label="Đóng"><X size={18} /></button>
                        </div>
                        <form className="admin-modal-body user-editor-form" onSubmit={handleSubmit}>
                            <div className="user-form-grid">
                                <label><span>Họ và tên</span><input value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} minLength={2} maxLength={50} required /></label>
                                <label><span>Email</span><input type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} maxLength={100} required /></label>
                                <label><span>Vai trò</span><select value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value as 'USER' | 'ADMIN' }))} disabled={editor.user?.user_id === currentUserId}><option value="USER">Người dùng</option><option value="ADMIN">Quản trị viên</option></select></label>
                                <span className="user-form-note">{editor.mode === 'edit' ? 'Để trống mật khẩu nếu không cần đặt lại.' : 'Mật khẩu cần có chữ cái và chữ số.'}</span>
                                <label><span>{editor.mode === 'create' ? 'Mật khẩu' : 'Mật khẩu mới'}</span><input type="password" value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} minLength={editor.mode === 'create' ? 8 : undefined} maxLength={128} required={editor.mode === 'create'} autoComplete="new-password" /></label>
                                <label><span>Xác nhận mật khẩu</span><input type="password" value={form.confirmPassword} onChange={(event) => setForm((current) => ({ ...current, confirmPassword: event.target.value }))} maxLength={128} required={editor.mode === 'create' || Boolean(form.password)} autoComplete="new-password" /></label>
                            </div>
                            {formError && <p className="kb-inline-error" role="alert">{formError}</p>}
                            <div className="review-action-buttons review-action-buttons-inline">
                                <button className="btn-secondary" type="button" onClick={() => setEditor(null)} disabled={saving}>Hủy</button>
                                <button className="btn-primary" type="submit" disabled={saving}>{editor.mode === 'edit' && <Key size={17} />}{saving ? 'Đang lưu' : 'Lưu tài khoản'}</button>
                            </div>
                        </form>
                    </section>
                </div>
            )}

            {statusTarget && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => !statusSaving && setStatusTarget(null)}>
                    <section className="admin-modal user-status-dialog" role="dialog" aria-modal="true" aria-label={statusTarget.is_active ? 'Khóa tài khoản' : 'Mở khóa tài khoản'} onClick={(event) => event.stopPropagation()}>
                        <div className="admin-modal-head">
                            <div><p className="kb-kicker">Xác nhận</p><h3>{statusTarget.is_active ? 'Khóa tài khoản?' : 'Mở khóa tài khoản?'}</h3></div>
                            <button className="admin-modal-close" type="button" onClick={() => setStatusTarget(null)} disabled={statusSaving} aria-label="Đóng"><X size={18} /></button>
                        </div>
                        <div className="admin-modal-body">
                            <p className="user-status-copy">{statusTarget.username || statusTarget.email} {statusTarget.is_active ? 'sẽ không thể đăng nhập hoặc sử dụng các phiên hiện tại.' : 'sẽ có thể đăng nhập và sử dụng hệ thống trở lại.'}</p>
                            <div className="review-action-buttons review-action-buttons-inline">
                                <button className="btn-secondary" type="button" onClick={() => setStatusTarget(null)} disabled={statusSaving}>Hủy</button>
                                <button className={statusTarget.is_active ? 'user-danger-button' : 'btn-primary'} type="button" onClick={() => void handleToggleStatus()} disabled={statusSaving}>{statusSaving ? 'Đang cập nhật' : statusTarget.is_active ? 'Khóa tài khoản' : 'Mở khóa'}</button>
                            </div>
                        </div>
                    </section>
                </div>
            )}
        </PageFrame>
    );
}
