'use client';

import dynamic from 'next/dynamic';
import React, { useEffect, useRef, useState } from 'react';
import BackgroundBlobs from '../components/layout/BackgroundBlobs';
import Sidebar from '../components/layout/Sidebar';
import Header from '../components/layout/Header';
import ViewSearch from '../components/views/ViewSearch';

function ViewLoading() {
    return (
        <div className="view-section active" aria-live="polite" aria-busy="true">
            <div className="mockup-container">
                <div className="view-loading">
                    <div className="skeleton-line skeleton-title" />
                    <div className="skeleton-line skeleton-copy" />
                    <div className="skeleton-panel" />
                </div>
            </div>
        </div>
    );
}

const dynamicView = (loader: () => Promise<{ default: React.ComponentType<{ activeView: string }> }>) =>
    dynamic(loader, { loading: ViewLoading });

const ViewChat = dynamicView(() => import('../components/views/ViewChat'));
const ViewAlert = dynamicView(() => import('../components/views/ViewAlert'));
const ViewKB = dynamicView(() => import('../components/views/ViewKB'));
const ViewHITL = dynamicView(() => import('../components/views/ViewHITL'));
const ViewDashboard = dynamicView(() => import('../components/views/ViewDashboard'));
const ViewUsers = dynamicView(() => import('../components/views/ViewUsers'));
const ViewBookmarks = dynamicView(() => import('../components/views/ViewBookmarks'));
const ViewAuth = dynamicView(() => import('../components/views/ViewAuth'));

const views = {
    'view-search': ViewSearch,
    'view-chat': ViewChat,
    'view-alert': ViewAlert,
    'view-kb': ViewKB,
    'view-hitl': ViewHITL,
    'view-dashboard': ViewDashboard,
    'view-users': ViewUsers,
    'view-bookmarks': ViewBookmarks,
    'view-login': ViewAuth,
    'view-register': ViewAuth,
};

const isAuthViewId = (view: string) => view === 'view-login' || view === 'view-register';

export default function Home() {
    const [mounted, setMounted] = useState(false);
    const [activeView, setActiveView] = useState('view-search');
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [authReturnView, setAuthReturnView] = useState('view-search');
    const activeViewRef = useRef(activeView);
    const authReturnViewRef = useRef(authReturnView);
    const ActiveView = views[activeView as keyof typeof views] ?? ViewSearch;
    const isAuthView = isAuthViewId(activeView);

    useEffect(() => {
        setMounted(true);
    }, []);

    useEffect(() => {
        activeViewRef.current = activeView;
    }, [activeView]);

    useEffect(() => {
        authReturnViewRef.current = authReturnView;
    }, [authReturnView]);

    useEffect(() => {
        setSidebarOpen(false);
    }, [activeView]);

    useEffect(() => {
        if (!sidebarOpen) return;
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setSidebarOpen(false);
        };
        document.addEventListener('keydown', closeOnEscape);
        return () => document.removeEventListener('keydown', closeOnEscape);
    }, [sidebarOpen]);

    useEffect(() => {
        const navigateToView = (event: Event) => {
            const customEvent = event as CustomEvent<string>;
            if (typeof customEvent.detail !== 'string') return;

            const nextView = customEvent.detail;
            const currentView = activeViewRef.current;

            if (isAuthViewId(nextView) && !isAuthViewId(currentView)) {
                setAuthReturnView(currentView);
            }

            setActiveView(nextView);
        };

        const leaveAuthView = () => {
            setActiveView(authReturnViewRef.current || 'view-search');
        };

        window.addEventListener('app:navigate', navigateToView);
        window.addEventListener('app:leave-auth', leaveAuthView);
        return () => {
            window.removeEventListener('app:navigate', navigateToView);
            window.removeEventListener('app:leave-auth', leaveAuthView);
        };
    }, []);

    const handleNavClick = (targetId: string) => {
        setActiveView(targetId);
    };

    if (!mounted) {
        return null;
    }

    return (
        <>
            <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
            <BackgroundBlobs />

            <div className="app-container">
                {!isAuthView && (
                    <Sidebar
                        activeView={activeView}
                        handleNavClick={handleNavClick}
                        open={sidebarOpen}
                        onClose={() => setSidebarOpen(false)}
                    />
                )}
                {sidebarOpen && !isAuthView && (
                    <button
                        className="sidebar-backdrop"
                        type="button"
                        aria-label="Đóng menu điều hướng"
                        onClick={() => setSidebarOpen(false)}
                    />
                )}

                <main id="main-content" className="main-content">
                    <Header onMenuClick={() => setSidebarOpen(true)} />
                    <ActiveView activeView={activeView} />
                </main>
            </div>
        </>
    );
}
