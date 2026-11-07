import React from 'react';
import {
    BookmarkSimple,
    CaretLeft,
    CaretRight,
    Lightbulb,
    Link,
    Microphone,
    PencilSimple,
    PaperPlaneRight,
    Plus,
    Robot,
    Trash,
    WarningCircle,
    X,
} from '@phosphor-icons/react';
import {
    bookmarkChatSession,
    deleteChatSession,
    fetchLegalKbHistoricalCitation,
    fetchChatSessionMessages,
    fetchChatSessions,
    getStoredAuth,
    streamChat,
    unbookmarkChatSession,
    type AuthSession,
    type ChatMessage,
    type LegalKbHistoricalCitation,
} from '../../lib/api';

type ChatSessionItem = {
    sessionId: string;
    title: string;
    timestamp: number;
    isBookmarked: boolean;
    bookmarkTitle: string | null;
    bookmarkedAt: number | null;
};

type ParsedAnswer = {
    body: string;
    disclaimer: string | null;
};

const LOCAL_SESSIONS_KEY = 'chat_sessions';
const WELCOME_MESSAGE =
    'Xin chào bạn! Tôi là trợ lý AI tra cứu quy định pháp luật giao thông vận tải đường bộ Việt Nam. Tôi có thể giúp gì cho bạn hôm nay?';

function createSessionId(): string {
    return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15);
}

function createWelcomeMessages(): ChatMessage[] {
    return [
        {
            role: 'assistant',
            content: WELCOME_MESSAGE,
            timestamp: Date.now(),
        },
    ];
}

function parseAnswerContent(text: string): ParsedAnswer {
    const marker = 'LƯU Ý PHÁP LÝ:';
    const markerIndex = text.indexOf(marker);
    if (markerIndex === -1) {
        return { body: text, disclaimer: null };
    }

    return {
        body: text.slice(0, markerIndex).trim(),
        disclaimer: text.slice(markerIndex + marker.length).trim(),
    };
}

function toLocalMessage(message: {
    role: 'user' | 'assistant';
    content: string;
    citations?: ChatMessage['citations'];
    risk_level?: ChatMessage['risk_level'];
    answer_mode?: ChatMessage['answer_mode'];
    confidence?: ChatMessage['confidence'];
    provision_citations?: ChatMessage['provision_citations'];
    document_sources?: ChatMessage['document_sources'];
    historical_references?: ChatMessage['historical_references'];
    clarification_question?: ChatMessage['clarification_question'];
    faithfulness_score?: number | null;
    is_out_of_scope?: boolean;
    created_at?: string;
}): ChatMessage {
    return {
        role: message.role,
        content: message.content,
        citations: message.citations || [],
        risk_level: message.risk_level,
        answer_mode: message.answer_mode,
        confidence: message.confidence,
        provision_citations: message.provision_citations || [],
        document_sources: message.document_sources || [],
        historical_references: message.historical_references || [],
        clarification_question: message.clarification_question ?? null,
        faithfulness_score: message.faithfulness_score ?? undefined,
        is_out_of_scope: message.is_out_of_scope || false,
        timestamp: message.created_at ? new Date(message.created_at).getTime() : Date.now(),
    };
}

function formatPublicationStatus(status: string) {
    return {
        published: 'Đang công bố',
        suspended: 'Tạm ngừng công bố',
        archived: 'Lưu lịch sử',
        draft: 'Bản nháp',
    }[status] ?? status;
}

function formatEffectiveStatus(status?: string | null) {
    return {
        active: 'đang áp dụng',
        expired: 'hết hiệu lực',
        repealed: 'đã bị thay thế',
        annulled: 'đã bị bãi bỏ',
        future_effective: 'chưa có hiệu lực',
    }[status || 'active'] ?? 'cần kiểm tra hiệu lực';
}

function formatAnswerMode(mode?: ChatMessage['answer_mode']) {
    return {
        direct: 'Trả lời trực tiếp',
        summary: 'Tóm tắt / tổng quan',
        historical: 'Quy định lịch sử',
        clarification_needed: 'Cần làm rõ',
        multiple_possibilities: 'Nhiều khả năng áp dụng',
        insufficient_evidence: 'Chưa đủ căn cứ',
        out_of_scope: 'Ngoài phạm vi hỗ trợ',
    }[mode || 'direct'];
}

function formatRiskLevel(level?: ChatMessage['risk_level']) {
    return {
        low: 'Rủi ro thấp',
        medium: 'Rủi ro trung bình',
        high: 'Rủi ro cao',
    }[level || 'medium'];
}

function formatConfidence(confidence?: ChatMessage['confidence']) {
    if (!confidence) return 'Độ tin cậy: trung bình';
    return `Độ tin cậy: ${confidence.level === 'high' ? 'cao' : confidence.level === 'low' ? 'thấp' : 'trung bình'}`;
}

export default function ViewChat({ activeView }: { activeView: string }) {
    const [messages, setMessages] = React.useState<ChatMessage[]>(createWelcomeMessages);
    const [input, setInput] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [selectedMessageIndex, setSelectedMessageIndex] = React.useState<number | null>(null);
    const [sessions, setSessions] = React.useState<ChatSessionItem[]>([]);
    const [activeSessionId, setActiveSessionId] = React.useState(createSessionId);
    const [authSession, setAuthSession] = React.useState<AuthSession | null>(null);
    const [sessionToDelete, setSessionToDelete] = React.useState<ChatSessionItem | null>(null);
    const [sessionError, setSessionError] = React.useState<string | null>(null);
    const [bookmarkTarget, setBookmarkTarget] = React.useState<ChatSessionItem | null>(null);
    const [bookmarkTitle, setBookmarkTitle] = React.useState('');
    const [bookmarkError, setBookmarkError] = React.useState<string | null>(null);
    const [savingBookmark, setSavingBookmark] = React.useState(false);
    const [historyCollapsed, setHistoryCollapsed] = React.useState(false);
    const [historicalCitations, setHistoricalCitations] = React.useState<Record<string, LegalKbHistoricalCitation>>({});
    const [historicalCitationLoading, setHistoricalCitationLoading] = React.useState<string | null>(null);
    const [historicalCitationError, setHistoricalCitationError] = React.useState<string | null>(null);

    const activeSessionIdRef = React.useRef(activeSessionId);

    React.useEffect(() => {
        activeSessionIdRef.current = activeSessionId;
    }, [activeSessionId]);

    React.useEffect(() => {
        const refresh = () => setAuthSession(getStoredAuth());
        refresh();
        window.addEventListener('legalai-auth-changed', refresh);
        return () => window.removeEventListener('legalai-auth-changed', refresh);
    }, []);

    const loadLocalSessions = React.useCallback(() => {
        const storedSessions = localStorage.getItem(LOCAL_SESSIONS_KEY);
        if (!storedSessions) {
            setSessions([]);
            return;
        }
        try {
            setSessions(JSON.parse(storedSessions));
        } catch (error) {
            console.error(error);
            setSessions([]);
        }
    }, []);

    const loadRemoteSessions = React.useCallback(async () => {
        try {
            const response = await fetchChatSessions();
            setSessions(
                response.items.map((item) => ({
                    sessionId: item.session_id,
                    title: item.title,
                    timestamp: new Date(item.updated_at || item.created_at).getTime(),
                    isBookmarked: item.is_bookmarked,
                    bookmarkTitle: item.bookmark_title,
                    bookmarkedAt: item.bookmarked_at ? new Date(item.bookmarked_at).getTime() : null,
                })),
            );
            setSessionError(null);
        } catch (error) {
            console.error(error);
            setSessionError('Không thể tải lịch sử chat của tài khoản này.');
        }
    }, []);

    React.useEffect(() => {
        if (authSession) {
            void loadRemoteSessions();
            setMessages(createWelcomeMessages());
            setActiveSessionId(createSessionId());
            return;
        }

        loadLocalSessions();
        const storedMsgs = localStorage.getItem(`chat_session_messages_${activeSessionIdRef.current}`);
        if (storedMsgs) {
            try {
                setMessages(JSON.parse(storedMsgs));
                return;
            } catch (error) {
                console.error(error);
            }
        }
        setMessages(createWelcomeMessages());
    }, [authSession, loadLocalSessions, loadRemoteSessions]);

    React.useEffect(() => {
        if (authSession || messages.length === 0) return;
        localStorage.setItem(`chat_session_messages_${activeSessionId}`, JSON.stringify(messages));
    }, [activeSessionId, authSession, messages]);

    React.useEffect(() => {
        const chatContainer = document.getElementById('fullChatMessages');
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }, [messages, loading]);

    const handleNewChat = () => {
        setActiveSessionId(createSessionId());
        setMessages(createWelcomeMessages());
        setSelectedMessageIndex(null);
        setInput('');
        setSessionError(null);
    };

    const mapRemoteSession = (item: {
        session_id: string;
        title: string;
        updated_at: string;
        created_at: string;
        is_bookmarked: boolean;
        bookmark_title: string | null;
        bookmarked_at: string | null;
    }): ChatSessionItem => ({
        sessionId: item.session_id,
        title: item.title,
        timestamp: new Date(item.updated_at || item.created_at).getTime(),
        isBookmarked: item.is_bookmarked,
        bookmarkTitle: item.bookmark_title,
        bookmarkedAt: item.bookmarked_at ? new Date(item.bookmarked_at).getTime() : null,
    });

    const handleSelectSession = React.useCallback(async (sid: string) => {
        setActiveSessionId(sid);
        setSelectedMessageIndex(null);
        setInput('');
        setSessionError(null);

        if (authSession) {
            try {
                const response = await fetchChatSessionMessages(sid);
                const loadedMessages = response.messages.map(toLocalMessage);
                setMessages(loadedMessages.length > 0 ? loadedMessages : createWelcomeMessages());
            } catch (error) {
                console.error(error);
                setMessages(createWelcomeMessages());
                setSessionError('Không thể tải nội dung cuộc trò chuyện.');
            }
            return;
        }

        const storedMsgs = localStorage.getItem(`chat_session_messages_${sid}`);
        if (storedMsgs) {
            try {
                setMessages(JSON.parse(storedMsgs));
            } catch (error) {
                console.error(error);
                setMessages(createWelcomeMessages());
            }
        }
    }, [authSession]);

    const upsertLocalSession = (question: string, sessionId: string) => {
        const title = question.slice(0, 30) + (question.length > 30 ? '...' : '');
        const nextSession = {
            sessionId,
            title,
            timestamp: Date.now(),
            isBookmarked: false,
            bookmarkTitle: null,
            bookmarkedAt: null,
        };
        const nextSessions = [nextSession, ...sessions.filter((session) => session.sessionId !== sessionId)];
        setSessions(nextSessions);
        localStorage.setItem(LOCAL_SESSIONS_KEY, JSON.stringify(nextSessions));
    };

    React.useEffect(() => {
        if (activeView !== 'view-chat') return;
        const targetSessionId = sessionStorage.getItem('legalai_open_chat_session');
        if (!targetSessionId) return;
        sessionStorage.removeItem('legalai_open_chat_session');
        void handleSelectSession(targetSessionId);
    }, [activeView, handleSelectSession]);

    const handleSend = async () => {
        if (!input.trim() || loading) return;
        const question = input.trim();
        const sessionId = activeSessionIdRef.current;
        setInput('');

        const userMsg: ChatMessage = {
            role: 'user',
            content: question,
            timestamp: Date.now(),
        };
        const updatedMsgs = [...messages, userMsg];
        setMessages(updatedMsgs);
        setLoading(true);
        setSessionError(null);

        const isFirstQuestion = updatedMsgs.filter((message) => message.role === 'user').length === 1;
        if (!authSession && isFirstQuestion) {
            upsertLocalSession(question, sessionId);
        }

        streamChat(
            question,
            sessionId,
            (meta) => {
                setLoading(false);
                const botMsg: ChatMessage = {
                    role: 'assistant',
                    content: meta.content,
                    citations: meta.citations,
                    risk_level: meta.risk_level,
                    answer_mode: meta.answer_mode,
                    confidence: meta.confidence,
                    provision_citations: meta.provision_citations || [],
                    document_sources: meta.document_sources || [],
                    historical_references: meta.historical_references || [],
                    clarification_question: meta.clarification_question ?? null,
                    faithfulness_score: meta.faithfulness_score ?? undefined,
                    is_out_of_scope: meta.is_out_of_scope,
                    timestamp: Date.now(),
                };
                setMessages((previous) => [...previous, botMsg]);
                if (authSession) {
                    void loadRemoteSessions();
                }
            },
            (errDetail) => {
                setLoading(false);
                const errorMsg: ChatMessage = {
                    role: 'assistant',
                    content: `Đã xảy ra lỗi: ${errDetail}`,
                    timestamp: Date.now(),
                };
                setMessages((previous) => [...previous, errorMsg]);
            },
        );
    };

    const handleHistoricalCitation = React.useCallback(async (retrievalUnitId: string) => {
        if (historicalCitations[retrievalUnitId]) return;
        setHistoricalCitationLoading(retrievalUnitId);
        setHistoricalCitationError(null);
        try {
            const result = await fetchLegalKbHistoricalCitation(retrievalUnitId);
            setHistoricalCitations((current) => ({ ...current, [retrievalUnitId]: result }));
        } catch (error) {
            setHistoricalCitationError(
                error instanceof Error ? error.message : 'Không thể tải trích dẫn lịch sử.',
            );
        } finally {
            setHistoricalCitationLoading(null);
        }
    }, [historicalCitations]);

    const handleConfirmDeleteSession = async () => {
        if (!sessionToDelete || loading) return;
        const deletedSessionId = sessionToDelete.sessionId;

        try {
            if (authSession) {
                await deleteChatSession(deletedSessionId);
                await loadRemoteSessions();
            } else {
                const nextSessions = sessions.filter((session) => session.sessionId !== deletedSessionId);
                setSessions(nextSessions);
                localStorage.setItem(LOCAL_SESSIONS_KEY, JSON.stringify(nextSessions));
                localStorage.removeItem(`chat_session_messages_${deletedSessionId}`);
            }

            if (activeSessionIdRef.current === deletedSessionId) {
                handleNewChat();
            }
            setSessionToDelete(null);
        } catch (error) {
            console.error(error);
            setSessionError('Không thể xóa cuộc trò chuyện. Vui lòng thử lại.');
        }
    };

    const openBookmarkDialog = (session: ChatSessionItem) => {
        if (!authSession) {
            setSessionError('Vui lòng đăng nhập để lưu cuộc trò chuyện.');
            return;
        }
        setBookmarkTarget(session);
        setBookmarkTitle(session.bookmarkTitle || session.title);
        setBookmarkError(null);
    };

    const handleSaveBookmark = async () => {
        if (!bookmarkTarget || savingBookmark) return;
        const title = bookmarkTitle.trim().replace(/\s+/g, ' ');
        if (title.length < 2) {
            setBookmarkError('Tên đã lưu cần có ít nhất 2 ký tự.');
            return;
        }

        setSavingBookmark(true);
        setBookmarkError(null);
        try {
            const updated = await bookmarkChatSession(bookmarkTarget.sessionId, title);
            const mapped = mapRemoteSession(updated);
            setSessions((current) => [
                mapped,
                ...current.filter((session) => session.sessionId !== mapped.sessionId),
            ]);
            setBookmarkTarget(null);
            setBookmarkTitle('');
        } catch (error) {
            setBookmarkError(error instanceof Error ? error.message : 'Không thể lưu cuộc trò chuyện.');
        } finally {
            setSavingBookmark(false);
        }
    };

    const handleRemoveBookmark = async (session: ChatSessionItem) => {
        if (!authSession || savingBookmark) return;
        setSavingBookmark(true);
        setSessionError(null);
        try {
            await unbookmarkChatSession(session.sessionId);
            setSessions((current) =>
                current.map((item) =>
                    item.sessionId === session.sessionId
                        ? { ...item, isBookmarked: false, bookmarkTitle: null, bookmarkedAt: null }
                        : item,
                ),
            );
        } catch (error) {
            setSessionError(error instanceof Error ? error.message : 'Không thể bỏ lưu cuộc trò chuyện.');
        } finally {
            setSavingBookmark(false);
        }
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void handleSend();
        }
    };

    const activeMsg =
        selectedMessageIndex !== null
            ? messages[selectedMessageIndex]
            : [...messages].reverse().find((message) => message.role === 'assistant');
    const displayCitations = activeMsg?.citations || [];
    const provisionCitations = activeMsg?.provision_citations || [];
    const documentSources = activeMsg?.document_sources || [];
    const historicalReferences = activeMsg?.historical_references || [];
    const activeClarification =
        activeMsg?.answer_mode === 'clarification_needed'
            ? activeMsg.clarification_question || activeMsg.content
            : null;
    const activeSession = sessions.find((session) => session.sessionId === activeSessionId);

    const renderContent = (text: string) => {
        const parsed = parseAnswerContent(text);
        const lines = (parsed.body || text).split('\n').map((line, index) => {
            const parts = line.split('**');
            const renderedLine = parts.map((part, partIndex) => {
                if (partIndex % 2 === 1) {
                    return <strong key={partIndex}>{part}</strong>;
                }
                return part;
            });
            return (
                <React.Fragment key={index}>
                    {renderedLine}
                    <br />
                </React.Fragment>
            );
        });

        return (
            <>
                <div>{lines}</div>
                {parsed.disclaimer && (
                    <aside className="legal-disclaimer-note">
                        <span>Lưu ý pháp lý</span>
                        <p>{parsed.disclaimer}</p>
                    </aside>
                )}
            </>
        );
    };

    return (
        <>
            <div id="view-chat" className={`view-section ${activeView === 'view-chat' ? 'active' : ''}`.trim()}>
                <div className={`chat-grid-container ${historyCollapsed ? 'history-collapsed' : ''}`}>
                    <div className={`chat-sidebar ${historyCollapsed ? 'collapsed' : ''}`}>
                        <div className="chat-panel-header">
                            {!historyCollapsed && <span>Lịch sử chat</span>}
                            <div className="chat-history-controls">
                                {!historyCollapsed && (
                                    <button
                                        onClick={handleNewChat}
                                        aria-label="Tạo cuộc trò chuyện mới"
                                        title="Cuộc trò chuyện mới"
                                        type="button"
                                    >
                                        <Plus size={16} weight="bold" />
                                    </button>
                                )}
                                <button
                                    onClick={() => setHistoryCollapsed((value) => !value)}
                                    aria-label={historyCollapsed ? 'Mở lịch sử chat' : 'Thu gọn lịch sử chat'}
                                    title={historyCollapsed ? 'Mở lịch sử chat' : 'Thu gọn lịch sử chat'}
                                    type="button"
                                >
                                    {historyCollapsed ? <CaretRight size={16} /> : <CaretLeft size={16} />}
                                </button>
                            </div>
                        </div>
                        <div className="chat-sidebar-list">
                            {sessionError && (
                                <div className="mb-2 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-800">
                                    {sessionError}
                                </div>
                            )}
                            {!authSession && (
                                <div className="mb-2 rounded-xl border border-navy-800/10 bg-navy-800/[0.04] p-3 text-xs text-slate-500">
                                    Đăng nhập để lịch sử chat được lưu riêng theo tài khoản.
                                </div>
                            )}
                            {sessions.length === 0 ? (
                                <div className="p-4 text-center text-sm text-slate-500">Không có cuộc trò chuyện nào</div>
                            ) : (
                                sessions.map((session) => (
                                    <div
                                        key={session.sessionId}
                                        className={`chat-history-item ${activeSessionId === session.sessionId ? 'active' : ''} ${session.isBookmarked ? 'saved' : ''}`.trim()}
                                    >
                                        <button
                                            type="button"
                                            onClick={() => {
                                                void handleSelectSession(session.sessionId);
                                            }}
                                            className="min-w-0 flex-1 text-left"
                                        >
                                            <div className="mb-1 flex items-center gap-1.5 truncate font-semibold">
                                                {session.isBookmarked && <BookmarkSimple size={13} weight="fill" />}
                                                <span className="truncate">{session.bookmarkTitle || session.title}</span>
                                            </div>
                                            <div className="text-xs text-slate-500">
                                                {new Date(session.timestamp).toLocaleDateString('vi-VN')}
                                            </div>
                                        </button>
                                        {authSession && (
                                            <button
                                                type="button"
                                                className="chat-session-bookmark"
                                                onClick={(event) => {
                                                    event.stopPropagation();
                                                    if (session.isBookmarked) {
                                                        void handleRemoveBookmark(session);
                                                        return;
                                                    }
                                                    openBookmarkDialog(session);
                                                }}
                                                aria-label={session.isBookmarked ? `Bỏ lưu ${session.bookmarkTitle || session.title}` : `Lưu ${session.title}`}
                                                disabled={loading || savingBookmark}
                                            >
                                                <BookmarkSimple size={15} weight={session.isBookmarked ? 'fill' : 'regular'} />
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            className="chat-session-delete"
                                            onClick={(event) => {
                                                event.stopPropagation();
                                                setSessionToDelete(session);
                                            }}
                                            aria-label={`Xóa cuộc trò chuyện ${session.title}`}
                                            disabled={loading}
                                        >
                                            <Trash size={15} />
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>

                    <div className="chat-main-area">
                        <div className="chat-active-toolbar">
                            <div className="min-w-0">
                                <span>Cuộc trò chuyện</span>
                                <strong>{activeSession?.bookmarkTitle || activeSession?.title || 'Cuộc trò chuyện mới'}</strong>
                            </div>
                            {authSession && activeSession && (
                                <button
                                    className="btn-secondary chat-save-btn"
                                    type="button"
                                    onClick={() => openBookmarkDialog(activeSession)}
                                    disabled={loading || savingBookmark}
                                >
                                    {activeSession.isBookmarked ? <PencilSimple size={16} /> : <BookmarkSimple size={16} />}
                                    {activeSession.isBookmarked ? 'Đổi tên lưu' : 'Lưu cuộc trò chuyện'}
                                </button>
                            )}
                        </div>
                        <div className="chat-messages" id="fullChatMessages">
                            {messages.map((msg, index) => (
                                <div
                                    key={`${msg.timestamp}-${index}`}
                                    className={`message-wrapper ${msg.role === 'user' ? 'user' : 'bot'}`}
                                    onClick={() => msg.role === 'assistant' && setSelectedMessageIndex(index)}
                                    role={msg.role === 'assistant' ? 'button' : undefined}
                                    tabIndex={msg.role === 'assistant' ? 0 : undefined}
                                >
                                    <div className="message">
                                        {msg.role === 'assistant' && (
                                            <div className="bot-header">
                                                <Robot size={18} /> TRỢ LÝ TRA CỨU QUY ĐỊNH
                                            </div>
                                        )}
                                        {renderContent(msg.content)}

                                        {msg.role === 'assistant' && msg.answer_mode && (
                                            <div className="mt-3 flex flex-wrap gap-2 text-xs">
                                                <span className="rounded-full bg-navy-800/[0.06] px-2.5 py-1 font-semibold text-navy-800">
                                                    {formatAnswerMode(msg.answer_mode)}
                                                </span>
                                                {msg.risk_level && (
                                                    <span
                                                        className={`rounded-full px-2.5 py-1 font-semibold ${
                                                            msg.risk_level === 'high'
                                                                ? 'bg-red-600/[0.08] text-red-800'
                                                                : msg.risk_level === 'low'
                                                                    ? 'bg-emerald-600/[0.08] text-emerald-800'
                                                                    : 'bg-amber-500/[0.12] text-amber-900'
                                                        }`}
                                                    >
                                                        {formatRiskLevel(msg.risk_level)}
                                                    </span>
                                                )}
                                            </div>
                                        )}

                                        {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                                            <div className="citation-list">
                                                {msg.citations.map((citation, citationIndex) => {
                                                    const label = `${citation.doc_type === 'LUAT' ? 'Luật' : 'NĐ'} ${
                                                        citation.doc_title.split('/')[0]
                                                    } - Đ. ${citation.article_num || ''}${
                                                        citation.clause_num ? `, K. ${citation.clause_num}` : ''
                                                    }`;
                                                    return (
                                                        <span
                                                            key={`${citation.chunk_id}-${citationIndex}`}
                                                            className={`citation status-${citation.verification_status}`}
                                                        >
                                                            {label}
                                                        </span>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}

                            {loading && (
                                <div className="typing-indicator">
                                    <div className="typing-dot"></div>
                                    <div className="typing-dot"></div>
                                    <div className="typing-dot"></div>
                                </div>
                            )}
                        </div>

                        <div className="chat-input-wrapper">
                            <div className="input-container">
                                <textarea
                                    className="chat-input"
                                    id="fullChatInput"
                                    placeholder="Nhập câu hỏi của bạn..."
                                    rows={1}
                                    value={input}
                                    onChange={(event) => setInput(event.target.value)}
                                    onKeyDown={handleKeyDown}
                                    disabled={loading}
                                ></textarea>
                                <button className="icon-btn" title="Ghi âm giọng nói" type="button">
                                    <Microphone size={20} />
                                </button>
                                <button
                                    className="icon-btn send-btn"
                                    id="fullSendChatBtn"
                                    onClick={() => {
                                        void handleSend();
                                    }}
                                    disabled={loading}
                                    type="button"
                                >
                                    <PaperPlaneRight size={20} weight="fill" />
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="chat-info-panel">
                        <div className="chat-panel-header">
                            <span>Thông tin bổ sung</span>
                        </div>
                        <div className="chat-info-content">
                            {activeMsg?.role === 'assistant' && (
                                <div className="mb-4 rounded-2xl border border-navy-800/10 bg-white/75 p-4 text-sm text-slate-700 shadow-sm">
                                    <div className="mb-3 flex flex-wrap gap-2">
                                        <span className="rounded-full bg-navy-800/[0.06] px-2.5 py-1 text-xs font-semibold text-navy-800">
                                            {formatAnswerMode(activeMsg.answer_mode)}
                                        </span>
                                        <span
                                            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                                                activeMsg.risk_level === 'high'
                                                    ? 'bg-red-600/[0.08] text-red-800'
                                                    : activeMsg.risk_level === 'low'
                                                        ? 'bg-emerald-600/[0.08] text-emerald-800'
                                                        : 'bg-amber-500/[0.12] text-amber-900'
                                            }`}
                                        >
                                            {formatRiskLevel(activeMsg.risk_level)}
                                        </span>
                                    </div>
                                    <p className="text-xs font-semibold text-slate-500">
                                        {formatConfidence(activeMsg.confidence)}
                                    </p>
                                    {activeMsg.answer_mode === 'historical' && (
                                        <p className="mt-2 text-xs leading-relaxed text-amber-900">
                                            Đây là thông tin lịch sử, không phải căn cứ pháp lý đang áp dụng hiện hành.
                                        </p>
                                    )}
                                    {activeMsg.risk_level === 'high' && (
                                        <p className="mt-2 text-xs leading-relaxed text-red-800">
                                            Câu hỏi có rủi ro cao; hệ thống chỉ cung cấp quy định, thủ tục hoặc checklist khách quan.
                                        </p>
                                    )}
                                </div>
                            )}

                            {displayCitations.length === 0 && provisionCitations.length === 0 && documentSources.length === 0 && historicalReferences.length === 0 ? (
                                <>
                                    {activeClarification && (
                                        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-900">
                                            <div className="mb-2 flex items-center gap-2 font-semibold">
                                                <WarningCircle size={18} weight="fill" />
                                                <span>Cần làm rõ trước khi tra cứu</span>
                                            </div>
                                            <p className="leading-relaxed">{activeClarification}</p>
                                        </div>
                                    )}
                                    <p>Các tài liệu được trích dẫn sẽ hiển thị ở đây để bạn tiện tra cứu sâu hơn.</p>
                                    <div className="mt-4 rounded-xl border border-navy-800/10 bg-navy-800/[0.05] p-3">
                                        <h4 className="mb-2 flex items-center gap-1.5 font-semibold text-navy-800">
                                            <Lightbulb size={18} weight="fill" /> Mẹo tra cứu
                                        </h4>
                                        <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed">
                                            <li>Nêu rõ tình huống cụ thể, ví dụ: vượt đèn đỏ</li>
                                            <li>Chỉ định rõ phương tiện: xe máy, ô tô, xe tải</li>
                                            <li>Đối chiếu kỹ các điều khoản được trích dẫn</li>
                                        </ul>
                                    </div>
                                </>
                            ) : (
                                <div className="flex flex-col gap-4">
                                    {provisionCitations.length > 0 && (
                                        <section className="rounded-2xl border border-emerald-700/15 bg-emerald-700/[0.06] p-4">
                                            <p className="mb-3 text-sm font-semibold text-emerald-900">
                                                Căn cứ Điều/Khoản đang áp dụng:
                                            </p>
                                            <div className="flex flex-col gap-2">
                                                {provisionCitations.map((citation, index) => (
                                                    <div
                                                        key={`${citation.retrieval_unit_id}-${index}`}
                                                        className="rounded-xl bg-white/70 px-3 py-2 text-xs text-slate-700"
                                                    >
                                                        <strong>{`Căn cứ ${index + 1}`}</strong>
                                                        <span>
                                                            {' '}
                                                            {citation.article_num ? `Điều ${citation.article_num}` : ''}
                                                            {citation.clause_num ? `, Khoản ${citation.clause_num}` : ''}
                                                            {citation.point_num ? `, Điểm ${citation.point_num}` : ''}
                                                        </span>
                                                        <span className="ml-1 text-emerald-800">
                                                            ({formatEffectiveStatus(citation.effective_status)})
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        </section>
                                    )}

                                    {documentSources.length > 0 && (
                                        <section className="rounded-2xl border border-navy-800/10 bg-navy-800/[0.04] p-4">
                                            <p className="mb-3 text-sm font-semibold text-navy-800">Nguồn văn bản tổng quan:</p>
                                            <div className="flex flex-col gap-2">
                                                {documentSources.map((source, index) => (
                                                    <div key={`${source.document_id}-${index}`} className="rounded-xl bg-white/70 px-3 py-2 text-xs text-slate-700">
                                                        <strong>{source.title || source.document_id}</strong>
                                                        <p className="mt-1 text-slate-500">
                                                            {[source.issuing_body, source.date].filter(Boolean).join(' · ') || 'Nguồn metadata văn bản'}
                                                        </p>
                                                        {source.url && (
                                                            <a
                                                                href={source.url}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="mt-1 inline-flex items-center gap-1 font-semibold text-blue-700 hover:underline"
                                                            >
                                                                Mở nguồn <Link size={14} />
                                                            </a>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </section>
                                    )}

                                    {historicalReferences.length > 0 && (
                                        <section className="rounded-2xl border border-amber-600/20 bg-amber-500/[0.1] p-4">
                                            <p className="mb-2 text-sm font-semibold text-amber-950">
                                                Tham chiếu quy định lịch sử:
                                            </p>
                                            <p className="mb-3 text-xs leading-relaxed text-amber-900">
                                                Các mục dưới đây không phải căn cứ pháp lý hiện hành.
                                            </p>
                                            <div className="flex flex-col gap-2">
                                                {historicalReferences.map((reference, index) => (
                                                    <div key={`${reference.document_id}-${index}`} className="rounded-xl bg-white/70 px-3 py-2 text-xs text-slate-700">
                                                        <strong>{reference.title || reference.document_id}</strong>
                                                        <p className="mt-1">
                                                            {reference.article_num ? `Điều ${reference.article_num}` : ''}
                                                            {reference.clause_num ? `, Khoản ${reference.clause_num}` : ''}
                                                            {reference.point_num ? `, Điểm ${reference.point_num}` : ''}
                                                        </p>
                                                        <p className="mt-1 text-slate-500">
                                                            {[reference.effective_from, reference.effective_to].filter(Boolean).join(' -> ') || 'Chưa có đủ mốc hiệu lực'}
                                                            {reference.status ? ` · ${formatEffectiveStatus(reference.status)}` : ''}
                                                        </p>
                                                        {reference.replaced_by && (
                                                            <p className="mt-1 text-slate-500">Văn bản thay thế: {reference.replaced_by}</p>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </section>
                                    )}

                                    {displayCitations.length > 0 && (
                                        <>
                                    <p className="text-sm font-semibold text-slate-500">
                                        Tài liệu trích dẫn từ câu trả lời:
                                    </p>
                                    {displayCitations.map((citation, index) => (
                                        <article
                                            key={`${citation.chunk_id}-${index}`}
                                            className="rounded-2xl border border-navy-800/10 bg-white/70 p-4 shadow-sm"
                                        >
                                            <div className="mb-2 flex items-center justify-between gap-2">
                                                <span className="badge active">
                                                    {citation.doc_type === 'LUAT' ? 'LUẬT' : 'NGHỊ ĐỊNH'}
                                                </span>
                                                <span
                                                    className={`text-xs font-bold ${
                                                        citation.verification_status === 'verified'
                                                            ? 'text-emerald-700'
                                                            : citation.verification_status === 'partial'
                                                                ? 'text-amber-700'
                                                                : 'text-red-700'
                                                    }`}
                                                >
                                                    {citation.verification_status === 'verified'
                                                        ? 'Đã đối chiếu'
                                                        : citation.verification_status === 'partial'
                                                            ? 'Nên đọc thêm nguồn'
                                                            : 'Chưa đủ căn cứ'}
                                                </span>
                                            </div>
                                            <h4 className="mb-1.5 text-sm font-bold text-slate-900">
                                                {citation.doc_title}
                                            </h4>
                                            <p className="mb-2 text-xs text-slate-500">
                                                {citation.article_num ? `Điều ${citation.article_num}` : ''}{' '}
                                                {citation.clause_num ? `Khoản ${citation.clause_num}` : ''}{' '}
                                                {citation.point_num ? `Điểm ${citation.point_num}` : ''}
                                            </p>
                                            <div className="mb-3 grid gap-1 text-xs text-slate-500">
                                                <p>
                                                    {citation.status === 'active' ? 'Đang có hiệu lực' : 'Cần kiểm tra hiệu lực'}
                                                    {citation.effective_date ? ` từ ${citation.effective_date}` : ''}
                                                </p>
                                                {(citation.sign_code || citation.section_number || citation.locator_label) && (
                                                    <p>
                                                        Vị trí trong văn bản:{' '}
                                                        {[citation.sign_code, citation.section_number, citation.locator_label]
                                                            .filter(Boolean)
                                                            .join(' / ')}
                                                    </p>
                                                )}
                                                {citation.section_path?.length > 0 && (
                                                    <p>Mục liên quan: {citation.section_path.join(' › ')}</p>
                                                )}
                                            </div>
                                            <p className="mb-1 text-xs font-semibold text-slate-500">Đoạn làm căn cứ</p>
                                            <blockquote className="rounded-lg border-l-3 border-navy-800 bg-slate-50 px-3 py-2.5 text-sm text-slate-700">
                                                "{citation.text_snippet}"
                                            </blockquote>
                                            {citation.source_url && (
                                                <a
                                                    href={citation.source_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline"
                                                >
                                                    Xem nguồn văn bản <Link size={14} />
                                                </a>
                                            )}
                                            <div className="mt-3 flex flex-col gap-2">
                                                <button
                                                    type="button"
                                                    className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 hover:underline"
                                                    onClick={() => {
                                                        void handleHistoricalCitation(citation.chunk_id);
                                                    }}
                                                >
                                                    {historicalCitationLoading === citation.chunk_id
                                                        ? 'Đang tải trích dẫn lịch sử'
                                                        : 'Xem trích dẫn lịch sử'}
                                                    <Link size={14} />
                                                </button>
                                                {historicalCitations[citation.chunk_id] && (
                                                    <div className="rounded-xl border border-navy-800/10 bg-navy-800/[0.04] p-3 text-xs text-slate-600">
                                                        <p className="font-semibold text-slate-800">
                                                            {historicalCitations[citation.chunk_id].title || 'Trích dẫn lịch sử'}
                                                        </p>
                                                        <p>
                                                            {historicalCitations[citation.chunk_id].citation_label || 'Chưa có vị trí trích dẫn'} · {formatPublicationStatus(historicalCitations[citation.chunk_id].publication_status)}
                                                        </p>
                                                        <p>{historicalCitations[citation.chunk_id].viewer_warning}</p>
                                                        {historicalCitations[citation.chunk_id].source_download_url && (
                                                            <a
                                                                href={historicalCitations[citation.chunk_id].source_download_url || '#'}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="mt-2 inline-flex items-center gap-1 font-semibold text-blue-700 hover:underline"
                                                            >
                                                                Mở file nguồn lịch sử <Link size={14} />
                                                            </a>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </article>
                                    ))}
                                    {historicalCitationError && (
                                        <p className="text-xs text-red-700">{historicalCitationError}</p>
                                    )}
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {sessionToDelete && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setSessionToDelete(null)}>
                    <div
                        className="admin-modal review-confirm-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="delete-chat-session-title"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <h3 id="delete-chat-session-title">Xóa cuộc trò chuyện?</h3>
                            <button
                                className="admin-modal-close"
                                type="button"
                                onClick={() => setSessionToDelete(null)}
                                aria-label="Đóng"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body">
                            <div className="flex items-start gap-3 rounded-2xl border border-red-600/15 bg-red-600/[0.06] p-4 text-sm text-slate-700">
                                <WarningCircle className="mt-0.5 shrink-0 text-red-700" size={22} weight="fill" />
                                <p>
                                    Cuộc trò chuyện <strong>{sessionToDelete.title}</strong> sẽ bị xóa khỏi lịch sử của
                                    bạn. Hành động này không thể hoàn tác.
                                </p>
                            </div>
                            <div className="mt-5 flex flex-wrap justify-end gap-2">
                                <button className="btn-secondary" type="button" onClick={() => setSessionToDelete(null)}>
                                    Hủy
                                </button>
                                <button
                                    className="btn-primary border-red-700 bg-red-700 hover:border-red-800 hover:bg-red-800"
                                    type="button"
                                    onClick={() => {
                                        void handleConfirmDeleteSession();
                                    }}
                                    disabled={loading}
                                >
                                    Xóa cuộc trò chuyện
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {bookmarkTarget && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setBookmarkTarget(null)}>
                    <div
                        className="admin-modal review-confirm-dialog"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="bookmark-chat-session-title"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <h3 id="bookmark-chat-session-title">
                                {bookmarkTarget.isBookmarked ? 'Đổi tên đã lưu' : 'Lưu cuộc trò chuyện'}
                            </h3>
                            <button
                                className="admin-modal-close"
                                type="button"
                                onClick={() => setBookmarkTarget(null)}
                                aria-label="Đóng"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="admin-modal-body">
                            <label className="auth-field">
                                <span>Tên hiển thị trong Đã lưu</span>
                                <input
                                    className="filter-input"
                                    value={bookmarkTitle}
                                    onChange={(event) => {
                                        setBookmarkTitle(event.target.value);
                                        setBookmarkError(null);
                                    }}
                                    placeholder="Ví dụ: Mức phạt quá tải xe tải"
                                    maxLength={120}
                                    autoFocus
                                />
                                {bookmarkError && <p className="auth-error">{bookmarkError}</p>}
                            </label>
                            <div className="mt-5 flex flex-wrap justify-end gap-2">
                                <button className="btn-secondary" type="button" onClick={() => setBookmarkTarget(null)}>
                                    Hủy
                                </button>
                                <button
                                    className="btn-primary"
                                    type="button"
                                    onClick={() => {
                                        void handleSaveBookmark();
                                    }}
                                    disabled={savingBookmark}
                                >
                                    {savingBookmark ? 'Đang lưu...' : 'Lưu'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
