'use client';

import { useEffect, useState } from 'react';
import { Bookmark, ChatCircle, ClockCounterClockwise, SignIn } from '@phosphor-icons/react';
import {
    fetchBookmarkedChatSessions,
    getStoredAuth,
    unbookmarkChatSession,
    type AuthSession,
    type ChatSessionSummary,
} from '@/lib/api';
import { EmptyView, PageFrame } from '../ui';

function openChatSession(sessionId: string) {
    sessionStorage.setItem('legalai_open_chat_session', sessionId);
    window.dispatchEvent(new CustomEvent('app:navigate', { detail: 'view-chat' }));
}

export default function ViewBookmarks({ activeView }: { activeView: string }) {
    const [session, setSession] = useState<AuthSession | null>(null);
    const [items, setItems] = useState<ChatSessionSummary[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadBookmarks = async () => {
        if (!getStoredAuth()) {
            setItems([]);
            return;
        }

        setLoading(true);
        setError(null);
        try {
            const response = await fetchBookmarkedChatSessions();
            setItems(response.items);
        } catch (err) {
            console.error(err);
            setError('Không thể tải danh sách đã lưu.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const refresh = () => {
            const next = getStoredAuth();
            setSession(next);
            if (next) void loadBookmarks();
            else setItems([]);
        };
        refresh();
        window.addEventListener('legalai-auth-changed', refresh);
        window.addEventListener('legalai-bookmarks-changed', refresh);
        return () => {
            window.removeEventListener('legalai-auth-changed', refresh);
            window.removeEventListener('legalai-bookmarks-changed', refresh);
        };
    }, []);

    const handleRemove = async (sessionId: string) => {
        setError(null);
        try {
            await unbookmarkChatSession(sessionId);
            setItems((current) => current.filter((item) => item.session_id !== sessionId));
        } catch (err) {
            console.error(err);
            setError('Không thể bỏ lưu cuộc trò chuyện.');
        }
    };

    return (
        <PageFrame
            id="view-bookmarks"
            active={activeView === 'view-bookmarks'}
            icon={Bookmark}
            title="Đã lưu"
            description="Các cuộc trò chuyện bạn đã bookmark và đặt tên để xem lại nhanh."
        >
            {!session ? (
                <EmptyView
                    icon={SignIn}
                    title="Đăng nhập để dùng Đã lưu"
                    description="Bạn vẫn có thể tra cứu công khai. Khi đăng nhập, các cuộc trò chuyện được bookmark sẽ xuất hiện tại đây."
                />
            ) : loading ? (
                <div className="saved-chat-grid" aria-live="polite" aria-busy="true">
                    {[0, 1, 2].map((item) => (
                        <div className="saved-chat-card saved-chat-skeleton" key={item}>
                            <span />
                            <strong />
                            <p />
                        </div>
                    ))}
                </div>
            ) : items.length === 0 ? (
                <EmptyView
                    icon={Bookmark}
                    title="Chưa có cuộc trò chuyện đã lưu"
                    description="Vào Hỏi đáp pháp luật, bấm Lưu cuộc trò chuyện và đặt tên để tạo thẻ ở đây."
                />
            ) : (
                <>
                    {error && <div className="mb-4 rounded-2xl border border-red-600/15 bg-red-600/[0.06] p-3 text-sm text-red-700">{error}</div>}
                    <div className="saved-chat-grid">
                        {items.map((item) => (
                            <article className="saved-chat-card" key={item.session_id}>
                                <button
                                    className="saved-chat-open"
                                    type="button"
                                    onClick={() => openChatSession(item.session_id)}
                                >
                                    <span className="saved-chat-icon">
                                        <ChatCircle size={21} weight="fill" />
                                    </span>
                                    <strong>{item.bookmark_title || item.title}</strong>
                                    <p>{item.title}</p>
                                    <small>
                                        <ClockCounterClockwise size={14} />
                                        Lưu ngày{' '}
                                        {new Date(item.bookmarked_at || item.updated_at).toLocaleDateString('vi-VN')}
                                    </small>
                                </button>
                                <button
                                    className="saved-chat-remove"
                                    type="button"
                                    onClick={() => {
                                        void handleRemove(item.session_id);
                                    }}
                                >
                                    Bỏ lưu
                                </button>
                            </article>
                        ))}
                    </div>
                </>
            )}
        </PageFrame>
    );
}
