'use client';

import React, { useEffect, useState } from 'react';
import type { Icon } from '@phosphor-icons/react';
import {
    MagnifyingGlass,
    ChatCircle,
    Bookmark,
    Bell,
    Book,
    CheckSquareOffset,
    ChartLineUp,
    Users,
    Shield,
} from '@phosphor-icons/react';
import { getStoredAuth, type AuthSession } from '@/lib/api';

type SidebarProps = {
    activeView: string;
    handleNavClick: (id: string) => void;
    open: boolean;
    onClose: () => void;
};

const navItems = [
    { id: 'view-search', label: 'Tra cứu văn bản', icon: MagnifyingGlass },
    { id: 'view-chat', label: 'Hỏi đáp pháp luật', icon: ChatCircle },
    { id: 'view-alert', label: 'Thông báo', icon: Bell },
    { id: 'view-bookmarks', label: 'Đã lưu', icon: Bookmark },
];

const adminItems = [
    { id: 'view-kb', label: 'Kho văn bản', icon: Book },
    { id: 'view-hitl', label: 'Duyệt văn bản', icon: CheckSquareOffset },
    { id: 'view-dashboard', label: 'Chất lượng AI', icon: ChartLineUp },
    { id: 'view-users', label: 'Người dùng', icon: Users },
];

export default function Sidebar({ activeView, handleNavClick, open, onClose }: SidebarProps) {
    const [session, setSession] = useState<AuthSession | null>(null);
    const isAdmin = session?.user.role === 'ADMIN';

    useEffect(() => {
        const refresh = () => setSession(getStoredAuth());
        refresh();
        window.addEventListener('legalai-auth-changed', refresh);
        return () => window.removeEventListener('legalai-auth-changed', refresh);
    }, []);

    const renderItem = (item: { id: string; label: string; icon: Icon; badge?: string }) => {
        const Icon = item.icon;
        const active = activeView === item.id;
        return (
            <button
                key={item.id}
                type="button"
                className={`nav-item ${active ? 'active' : ''}`}
                onClick={() => handleNavClick(item.id)}
                aria-current={active ? 'page' : undefined}
            >
                <Icon size={19} weight={active ? 'fill' : 'regular'} />
                <span>{item.label}</span>
                {item.badge && <span className="notification-badge">{item.badge}</span>}
            </button>
        );
    };

    return (
        <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Điều hướng chính">
            <div className="sidebar-header">
                <span className="logo-flag"><Shield size={23} weight="fill" /></span>
                <span>
                    <strong>Cổng pháp luật</strong>
                    <small>Giao thông vận tải</small>
                </span>
                <button className="sidebar-close" type="button" onClick={onClose} aria-label="Đóng menu">×</button>
            </div>
            <nav className="sidebar-nav">
                <div className="sidebar-section">Công cụ chính</div>
                {navItems.map(renderItem)}
                {isAdmin && <div className="sidebar-section">Quản trị</div>}
                {isAdmin && adminItems.map(renderItem)}
                <div className="sidebar-footer">
                    <p>Public có thể tra cứu và hỏi đáp; đăng nhập để dùng Thông báo, Đã lưu và khu vực quản trị nếu có quyền.</p>
                </div>
            </nav>
        </aside>
    );
}
