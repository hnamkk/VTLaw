'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
    CaretDown,
    Gavel,
    Key,
    List,
    SignOut,
    UserCircle,
    UserGear,
} from '@phosphor-icons/react';
import {
    normalizeDisplayName,
    normalizeEmail,
    validateDisplayName,
    validateEmail,
    validatePasswordConfirmation,
    validatePasswordStrength,
    type AuthFieldErrors,
} from '@/lib/auth-validation';
import {
    changePassword,
    getStoredAuth,
    logout,
    updateProfile,
    type AuthSession,
} from '@/lib/api';

type ProfileField = 'username' | 'email';
type PasswordField = 'currentPassword' | 'newPassword' | 'confirmPassword';

function getAvatarLabel(name: string) {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return 'U';
    if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
    return `${parts[0][0] ?? ''}${parts[parts.length - 1][0] ?? ''}`.toUpperCase();
}

export default function Header({ onMenuClick }: { onMenuClick: () => void }) {
    const [session, setSession] = useState<AuthSession | null>(null);
    const [menuOpen, setMenuOpen] = useState(false);
    const [profileOpen, setProfileOpen] = useState(false);
    const [username, setUsername] = useState('');
    const [email, setEmail] = useState('');
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [profileErrors, setProfileErrors] = useState<AuthFieldErrors<ProfileField>>({});
    const [passwordErrors, setPasswordErrors] = useState<AuthFieldErrors<PasswordField>>({});
    const [profileError, setProfileError] = useState<string | null>(null);
    const [passwordError, setPasswordError] = useState<string | null>(null);
    const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
    const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
    const [savingProfile, setSavingProfile] = useState(false);
    const [savingPassword, setSavingPassword] = useState(false);
    const menuRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const refresh = () => {
            const next = getStoredAuth();
            setSession(next);
            setUsername(next?.user.username || '');
            setEmail(next?.user.email || '');
        };
        refresh();
        window.addEventListener('legalai-auth-changed', refresh);
        return () => window.removeEventListener('legalai-auth-changed', refresh);
    }, []);

    useEffect(() => {
        if (!menuOpen) return;
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [menuOpen]);

    const displayName = useMemo(
        () => session?.user.username?.trim() || session?.user.email || '',
        [session],
    );

    const avatarLabel = useMemo(() => getAvatarLabel(displayName), [displayName]);

    const navigate = (target: string) => {
        window.dispatchEvent(new CustomEvent('app:navigate', { detail: target }));
    };

    const signOut = async () => {
        await logout();
        setSession(null);
        setMenuOpen(false);
        setProfileOpen(false);
        navigate('view-search');
    };

    const validateProfile = (): AuthFieldErrors<ProfileField> => {
        const nextErrors: AuthFieldErrors<ProfileField> = {};
        const usernameError = validateDisplayName(username, 'Họ và tên');
        const emailError = validateEmail(email);

        if (usernameError) nextErrors.username = usernameError;
        if (emailError) nextErrors.email = emailError;

        return nextErrors;
    };

    const validatePassword = (): AuthFieldErrors<PasswordField> => {
        const nextErrors: AuthFieldErrors<PasswordField> = {};

        if (!currentPassword) nextErrors.currentPassword = 'Vui lòng nhập mật khẩu hiện tại.';

        const newPasswordError = validatePasswordStrength(newPassword, 'Mật khẩu mới');
        if (newPasswordError) nextErrors.newPassword = newPasswordError;

        const confirmPasswordError = validatePasswordConfirmation(
            newPassword,
            confirmPassword,
            'Xác nhận mật khẩu mới',
        );
        if (confirmPasswordError) nextErrors.confirmPassword = confirmPasswordError;

        if (!nextErrors.newPassword && currentPassword && currentPassword === newPassword) {
            nextErrors.newPassword = 'Mật khẩu mới phải khác mật khẩu hiện tại.';
        }

        return nextErrors;
    };

    const clearProfileFieldError = (field: ProfileField) => {
        setProfileErrors((current) => {
            if (!current[field]) return current;
            const next = { ...current };
            delete next[field];
            return next;
        });
        if (profileError) setProfileError(null);
    };

    const clearPasswordFieldError = (field: PasswordField, value: string) => {
        setPasswordErrors((current) => {
            if (!current[field] && !(field === 'newPassword' && current.confirmPassword)) return current;
            const next = { ...current };
            delete next[field];
            if (field === 'newPassword') {
                const confirmPasswordError = validatePasswordConfirmation(value, confirmPassword, 'Xác nhận mật khẩu mới');
                if (confirmPasswordError) next.confirmPassword = confirmPasswordError;
                else delete next.confirmPassword;
            }
            return next;
        });
        if (passwordError) setPasswordError(null);
    };

    const handleProfileSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const nextErrors = validateProfile();
        if (Object.keys(nextErrors).length > 0) {
            setProfileErrors(nextErrors);
            setProfileError(null);
            setProfileSuccess(null);
            return;
        }

        setSavingProfile(true);
        setProfileError(null);
        setProfileSuccess(null);
        try {
            const updatedUser = await updateProfile(normalizeEmail(email), normalizeDisplayName(username));
            setUsername(updatedUser.username || '');
            setEmail(updatedUser.email);
            setProfileSuccess('Đã cập nhật thông tin cá nhân.');
        } catch (error) {
            setProfileError(error instanceof Error ? error.message : 'Không thể cập nhật thông tin.');
        } finally {
            setSavingProfile(false);
        }
    };

    const handlePasswordSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const nextErrors = validatePassword();
        if (Object.keys(nextErrors).length > 0) {
            setPasswordErrors(nextErrors);
            setPasswordError(null);
            setPasswordSuccess(null);
            return;
        }

        setSavingPassword(true);
        setPasswordError(null);
        setPasswordSuccess(null);
        try {
            await changePassword(currentPassword, newPassword, confirmPassword);
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
            setPasswordSuccess('Đã đổi mật khẩu.');
        } catch (error) {
            setPasswordError(error instanceof Error ? error.message : 'Không thể đổi mật khẩu.');
        } finally {
            setSavingPassword(false);
        }
    };

    return (
        <>
            <header className="top-header">
                <div className="header-brand">
                    <button
                        className="mobile-menu-btn"
                        type="button"
                        onClick={onMenuClick}
                        aria-label="Mở điều hướng"
                    >
                        <List size={22} />
                    </button>
                    <div className="header-title">
                        <span className="header-mark"><Gavel size={20} weight="fill" /></span>
                        <span>
                            <strong>VT Law</strong>
                            <small>Tra cứu & tuân thủ giao thông</small>
                        </span>
                    </div>
                </div>

                <div className="header-auth">
                    {session ? (
                        <div className="header-user-menu" ref={menuRef}>
                            <button
                                className="header-user-trigger"
                                type="button"
                                aria-expanded={menuOpen}
                                onClick={() => setMenuOpen((open) => !open)}
                            >
                                <span className="header-avatar" aria-hidden="true">{avatarLabel}</span>
                                <span className="header-auth-name">{displayName}</span>
                                <CaretDown size={14} className={`header-user-caret ${menuOpen ? 'open' : ''}`} />
                            </button>

                            {menuOpen && (
                                <div className="header-user-dropdown">
                                    <button
                                        className="header-dropdown-item"
                                        type="button"
                                        onClick={() => {
                                            setProfileOpen(true);
                                            setMenuOpen(false);
                                            setProfileErrors({});
                                            setPasswordErrors({});
                                            setProfileError(null);
                                            setPasswordError(null);
                                            setProfileSuccess(null);
                                            setPasswordSuccess(null);
                                        }}
                                    >
                                        <UserGear size={16} /> Thông tin cá nhân
                                    </button>
                                    <button className="header-dropdown-item" type="button" onClick={() => void signOut()}>
                                        <SignOut size={16} /> Đăng xuất
                                    </button>
                                </div>
                            )}
                        </div>
                    ) : (
                        <>
                            <button className="header-register-link" type="button" onClick={() => navigate('view-register')}>
                                Đăng ký
                            </button>
                            <button className="header-login-btn" type="button" onClick={() => navigate('view-login')}>
                                Đăng nhập
                            </button>
                        </>
                    )}
                </div>
            </header>

            {profileOpen && (
                <div className="admin-modal-backdrop" role="presentation" onClick={() => setProfileOpen(false)}>
                    <section
                        className="admin-modal header-profile-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Thông tin cá nhân"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="admin-modal-head">
                            <div>
                                <h3>Thông tin cá nhân</h3>
                                <p className="header-profile-subtitle">Cập nhật tên hiển thị, email và mật khẩu đăng nhập.</p>
                            </div>
                            <button
                                className="admin-modal-close"
                                type="button"
                                aria-label="Đóng"
                                onClick={() => setProfileOpen(false)}
                            >
                                ×
                            </button>
                        </div>

                        <div className="admin-modal-body header-profile-body">
                            <form className="header-profile-form" onSubmit={handleProfileSubmit} noValidate>
                                <div className="header-profile-section">
                                    <div className="header-profile-section-head">
                                        <UserCircle size={18} />
                                        <strong>Thông tin cơ bản</strong>
                                    </div>
                                    <label className="auth-field">
                                        <span>Họ và tên</span>
                                        <input
                                            className="filter-input"
                                            value={username}
                                            onChange={(event) => {
                                                setUsername(event.target.value);
                                                clearProfileFieldError('username');
                                            }}
                                            placeholder="Nguyễn Văn A"
                                            autoComplete="name"
                                            aria-invalid={Boolean(profileErrors.username)}
                                        />
                                        {profileErrors.username && <p className="auth-error">{profileErrors.username}</p>}
                                    </label>
                                    <label className="auth-field">
                                        <span>Email</span>
                                        <input
                                            className="filter-input"
                                            type="email"
                                            value={email}
                                            onChange={(event) => {
                                                setEmail(event.target.value);
                                                clearProfileFieldError('email');
                                            }}
                                            placeholder="you@example.com"
                                            autoComplete="email"
                                            aria-invalid={Boolean(profileErrors.email)}
                                        />
                                        {profileErrors.email && <p className="auth-error">{profileErrors.email}</p>}
                                    </label>
                                    {profileError && <p className="auth-error">{profileError}</p>}
                                    {profileSuccess && <p className="auth-success">{profileSuccess}</p>}
                                    <button type="submit" className="btn-primary header-profile-submit" disabled={savingProfile}>
                                        {savingProfile ? 'Đang lưu...' : 'Lưu thông tin'}
                                    </button>
                                </div>
                            </form>

                            <form className="header-profile-form" onSubmit={handlePasswordSubmit} noValidate>
                                <div className="header-profile-section">
                                    <div className="header-profile-section-head">
                                        <Key size={18} />
                                        <strong>Đổi mật khẩu</strong>
                                    </div>
                                    <label className="auth-field">
                                        <span>Mật khẩu hiện tại</span>
                                        <input
                                            className="filter-input"
                                            type="password"
                                            value={currentPassword}
                                            onChange={(event) => {
                                                setCurrentPassword(event.target.value);
                                                clearPasswordFieldError('currentPassword', event.target.value);
                                            }}
                                            autoComplete="current-password"
                                            aria-invalid={Boolean(passwordErrors.currentPassword)}
                                        />
                                        {passwordErrors.currentPassword && <p className="auth-error">{passwordErrors.currentPassword}</p>}
                                    </label>
                                    <label className="auth-field">
                                        <span>Mật khẩu mới</span>
                                        <input
                                            className="filter-input"
                                            type="password"
                                            value={newPassword}
                                            onChange={(event) => {
                                                setNewPassword(event.target.value);
                                                clearPasswordFieldError('newPassword', event.target.value);
                                            }}
                                            autoComplete="new-password"
                                            aria-invalid={Boolean(passwordErrors.newPassword)}
                                        />
                                        {passwordErrors.newPassword && <p className="auth-error">{passwordErrors.newPassword}</p>}
                                    </label>
                                    <label className="auth-field">
                                        <span>Xác nhận mật khẩu mới</span>
                                        <input
                                            className="filter-input"
                                            type="password"
                                            value={confirmPassword}
                                            onChange={(event) => {
                                                setConfirmPassword(event.target.value);
                                                clearPasswordFieldError('confirmPassword', event.target.value);
                                            }}
                                            autoComplete="new-password"
                                            aria-invalid={Boolean(passwordErrors.confirmPassword)}
                                        />
                                        {passwordErrors.confirmPassword && <p className="auth-error">{passwordErrors.confirmPassword}</p>}
                                    </label>
                                    {passwordError && <p className="auth-error">{passwordError}</p>}
                                    {passwordSuccess && <p className="auth-success">{passwordSuccess}</p>}
                                    <button type="submit" className="btn-primary header-profile-submit" disabled={savingPassword}>
                                        {savingPassword ? 'Đang đổi...' : 'Đổi mật khẩu'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </section>
                </div>
            )}
        </>
    );
}
