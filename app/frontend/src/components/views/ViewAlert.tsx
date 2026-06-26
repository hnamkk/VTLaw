'use client';

import { useEffect, useMemo, useState } from 'react';
import { Bell, Book, Check, SignIn } from '@phosphor-icons/react';
import {
    fetchNotifications,
    getStoredAuth,
    markAllNotificationsRead,
    markNotificationRead,
    subscribeNotifications,
    type AuthSession,
    type NotificationItem,
} from '@/lib/api';
import { EmptyView, PageFrame } from '../ui';

function changeTypeLabel(value: string) {
    return {
        create: 'Văn bản mới',
        update: 'Cập nhật',
        repeal: 'Bãi bỏ/thay thế',
    }[value] || 'Cập nhật KB';
}

export default function ViewAlert({ activeView }: { activeView: string }) {
    const [session, setSession] = useState<AuthSession | null>(null);
    const [items, setItems] = useState<NotificationItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const unreadCount = useMemo(() => items.filter((item) => !item.is_read).length, [items]);

    const loadNotifications = async () => {
        if (!getStoredAuth()) {
            setItems([]);
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const response = await fetchNotifications(false);
            setItems(response.items);
        } catch (err) {
            console.error(err);
            setError('Không thể tải thông báo.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const refresh = () => {
            const next = getStoredAuth();
            setSession(next);
            if (next) void loadNotifications();
            else setItems([]);
        };
        refresh();
        window.addEventListener('legalai-auth-changed', refresh);
        return () => window.removeEventListener('legalai-auth-changed', refresh);
    }, []);

    useEffect(() => {
        if (!session) return;
        return subscribeNotifications(
            (notification) => {
                setItems((current) => [
                    notification,
                    ...current.filter((item) => item.notification_id !== notification.notification_id),
                ]);
            },
            (detail) => setError(detail),
        );
    }, [session]);

    const handleMarkRead = async (notificationId: string) => {
        setError(null);
        try {
            await markNotificationRead(notificationId);
            setItems((current) =>
                current.map((item) =>
                    item.notification_id === notificationId ? { ...item, is_read: true } : item,
                ),
            );
        } catch (err) {
            console.error(err);
            setError('Không thể đánh dấu đã đọc.');
        }
    };

    const handleMarkAllRead = async () => {
        setError(null);
        try {
            await markAllNotificationsRead();
            setItems((current) => current.map((item) => ({ ...item, is_read: true })));
        } catch (err) {
            console.error(err);
            setError('Không thể đánh dấu tất cả đã đọc.');
        }
    };

    const unreadItems = items.filter((item) => !item.is_read);
    const readItems = items.filter((item) => item.is_read);

    return (
        <PageFrame
            id="view-alert"
            active={activeView === 'view-alert'}
            icon={Bell}
            title="Thông báo pháp luật"
            description="Nhận realtime khi quản trị viên phê duyệt văn bản vào Kho văn bản."
        >
            {!session ? (
                <EmptyView
                    icon={SignIn}
                    title="Đăng nhập để nhận thông báo"
                    description="Bạn vẫn có thể tra cứu công khai. Khi đăng nhập, hệ thống sẽ báo ngay khi có văn bản được phê duyệt."
                />
            ) : loading ? (
                <div className="grid gap-3" aria-live="polite" aria-busy="true">
                    {[0, 1, 2].map((item) => (
                        <div className="alert-card animate-pulse" key={item}>
                            <div className="h-4 w-36 rounded-full bg-slate-200" />
                            <div className="mt-4 h-5 w-3/4 rounded-xl bg-slate-200" />
                            <div className="mt-3 h-12 rounded-xl bg-slate-200" />
                        </div>
                    ))}
                </div>
            ) : items.length === 0 ? (
                <EmptyView
                    icon={Bell}
                    title="Chưa có thông báo"
                    description="Khi admin duyệt văn bản mới hoặc cập nhật KB, thông báo sẽ xuất hiện tại đây ngay lập tức."
                />
            ) : (
                <>
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-navy-800/10 bg-white/80 p-4">
                        <div>
                            <strong className="text-navy-800">{unreadCount} thông báo chưa đọc</strong>
                            <p className="text-sm text-slate-500">Kết nối realtime đang bật khi bạn đăng nhập.</p>
                        </div>
                        <button className="btn-secondary" type="button" onClick={() => void handleMarkAllRead()} disabled={unreadCount === 0}>
                            <Check size={16} /> Đánh dấu tất cả đã đọc
                        </button>
                    </div>

                    {error && <div className="mb-4 rounded-2xl border border-red-600/15 bg-red-600/[0.06] p-3 text-sm text-red-700">{error}</div>}

                    <h2 className="mb-3 mt-6 text-xs font-bold uppercase tracking-widest text-slate-500">Chưa đọc</h2>
                    {unreadItems.length === 0 ? (
                        <p className="rounded-2xl border border-navy-800/10 bg-white/70 p-4 text-sm text-slate-500">
                            Bạn đã đọc hết thông báo mới.
                        </p>
                    ) : (
                        unreadItems.map((item) => (
                            <article className="alert-card new" key={item.notification_id}>
                                <div className="alert-header">
                                    <span className="badge new">Mới</span>
                                    <time>{new Date(item.created_at).toLocaleString('vi-VN')}</time>
                                    <span>{changeTypeLabel(item.change_type)}</span>
                                </div>
                                <h3 className="alert-title flex items-start gap-2">
                                    <Book size={20} className="mt-1 shrink-0 text-navy-800" />{item.title}
                                </h3>
                                <p className="alert-summary">{item.summary}</p>
                                <div className="alert-actions">
                                    <button className="btn-primary bg-emerald-700 hover:bg-emerald-800" type="button" onClick={() => void handleMarkRead(item.notification_id)}>
                                        <Check size={16} /> Đánh dấu đã đọc
                                    </button>
                                </div>
                            </article>
                        ))
                    )}

                    <h2 className="mb-3 mt-8 text-xs font-bold uppercase tracking-widest text-slate-500">Đã đọc</h2>
                    {readItems.map((item) => (
                        <article className="alert-card read" key={item.notification_id}>
                            <div className="alert-header">
                                <span className="badge bg-slate-100 text-slate-600">Đã đọc</span>
                                <time>{new Date(item.created_at).toLocaleString('vi-VN')}</time>
                                <span>{changeTypeLabel(item.change_type)}</span>
                            </div>
                            <h3 className="alert-title">{item.title}</h3>
                            <p className="alert-summary">{item.summary}</p>
                        </article>
                    ))}
                </>
            )}
        </PageFrame>
    );
}
