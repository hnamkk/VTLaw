'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Gavel } from '@phosphor-icons/react';
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
    getStoredAuth,
    login,
    register,
    type AuthSession,
} from '@/lib/api';

type AuthMode = 'login' | 'register';
type AuthField = 'fullName' | 'email' | 'password' | 'confirmPassword';

function navigate(target: string) {
    window.dispatchEvent(new CustomEvent('app:navigate', { detail: target }));
}

function leaveAuth() {
    window.dispatchEvent(new Event('app:leave-auth'));
}

export default function ViewAuth({ activeView }: { activeView: string }) {
    const mode: AuthMode = activeView === 'view-register' ? 'register' : 'login';
    const [session, setSession] = useState<AuthSession | null>(null);
    const [fullName, setFullName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [fieldErrors, setFieldErrors] = useState<AuthFieldErrors<AuthField>>({});
    const [formError, setFormError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        const refresh = () => setSession(getStoredAuth());
        refresh();
        window.addEventListener('legalai-auth-changed', refresh);
        return () => window.removeEventListener('legalai-auth-changed', refresh);
    }, []);

    useEffect(() => {
        setFieldErrors({});
        setFormError(null);
        setPassword('');
        setConfirmPassword('');
    }, [mode]);

    const validate = (): AuthFieldErrors<AuthField> => {
        const nextErrors: AuthFieldErrors<AuthField> = {};

        const emailError = validateEmail(email);
        if (emailError) nextErrors.email = emailError;

        if (mode === 'register') {
            const fullNameError = validateDisplayName(fullName);
            if (fullNameError) nextErrors.fullName = fullNameError;
        }

        const passwordError = mode === 'register'
            ? validatePasswordStrength(password)
            : (!password ? 'Vui lòng nhập mật khẩu.' : null);
        if (passwordError) nextErrors.password = passwordError;

        if (mode === 'register') {
            const confirmPasswordError = validatePasswordConfirmation(password, confirmPassword);
            if (confirmPasswordError) nextErrors.confirmPassword = confirmPasswordError;
        }

        return nextErrors;
    };

    const updateFieldError = (field: AuthField, value: string) => {
        setFieldErrors((current) => {
            if (!current[field]) return current;
            const next = { ...current };
            delete next[field];
            return next;
        });
        if (formError) setFormError(null);

        if (field === 'password' && mode === 'register' && confirmPassword) {
            const confirmPasswordError = validatePasswordConfirmation(value, confirmPassword);
            setFieldErrors((current) => ({
                ...current,
                confirmPassword: confirmPasswordError ?? undefined,
            }));
        }
    };

    const submit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const nextErrors = validate();
        if (Object.keys(nextErrors).length > 0) {
            setFieldErrors(nextErrors);
            setFormError(null);
            return;
        }

        setBusy(true);
        setFormError(null);
        try {
            const normalizedEmail = normalizeEmail(email);
            const normalizedName = normalizeDisplayName(fullName);
            const nextSession = mode === 'login'
                ? await login(normalizedEmail, password)
                : await register(normalizedEmail, password, confirmPassword, normalizedName);
            setSession(nextSession);
            setPassword('');
            setConfirmPassword('');
            navigate('view-search');
        } catch (err) {
            setFormError(err instanceof Error ? err.message : 'Xác thực thất bại.');
        } finally {
            setBusy(false);
        }
    };

    const isRegister = mode === 'register';
    const title = isRegister ? 'Đăng ký' : 'Đăng nhập';

    return (
        <section
            id={isRegister ? 'view-register' : 'view-login'}
            className={`view-section ${activeView === 'view-register' || activeView === 'view-login' ? 'active' : ''} auth-screen`.trim()}
        >
            <div className="mockup-container auth-shell">
                <button className="auth-back" type="button" onClick={leaveAuth}>
                    <ArrowLeft size={17} /> Quay lại
                </button>

                <div className="auth-stage">
                    <div className="auth-card">
                        <div className="auth-brand">
                            <span><Gavel size={22} weight="fill" /></span>
                            <strong>VT Law</strong>
                        </div>

                        <div className="auth-heading">
                            <h1>{title}</h1>
                            <p>
                                {isRegister
                                    ? 'Tạo tài khoản để lưu lịch sử tra cứu, đánh dấu văn bản và nhận thông báo phù hợp.'
                                    : 'Đăng nhập để tiếp tục với các chức năng cá nhân và đồng bộ phiên làm việc của bạn.'}
                            </p>
                        </div>

                        <form className="auth-form" onSubmit={submit} noValidate>
                            {isRegister && (
                                <label className="auth-field">
                                    <span>Họ và tên</span>
                                    <input
                                        className="filter-input"
                                        value={fullName}
                                        onChange={(event) => {
                                            setFullName(event.target.value);
                                            updateFieldError('fullName', event.target.value);
                                        }}
                                        placeholder="Nguyễn Văn A"
                                        autoComplete="name"
                                        aria-invalid={Boolean(fieldErrors.fullName)}
                                    />
                                    {fieldErrors.fullName && <p className="auth-error">{fieldErrors.fullName}</p>}
                                </label>
                            )}

                            <label className="auth-field">
                                <span>Email</span>
                                <input
                                    className="filter-input"
                                    type="email"
                                    value={email}
                                    onChange={(event) => {
                                        setEmail(event.target.value);
                                        updateFieldError('email', event.target.value);
                                    }}
                                    placeholder="you@example.com"
                                    autoComplete="email"
                                    aria-invalid={Boolean(fieldErrors.email)}
                                />
                                {fieldErrors.email && <p className="auth-error">{fieldErrors.email}</p>}
                            </label>

                            <label className="auth-field">
                                <span>Mật khẩu</span>
                                <input
                                    className="filter-input"
                                    type="password"
                                    value={password}
                                    onChange={(event) => {
                                        setPassword(event.target.value);
                                        updateFieldError('password', event.target.value);
                                    }}
                                    placeholder={isRegister ? 'Tối thiểu 8 ký tự, gồm chữ và số' : 'Nhập mật khẩu'}
                                    autoComplete={isRegister ? 'new-password' : 'current-password'}
                                    aria-invalid={Boolean(fieldErrors.password)}
                                />
                                {fieldErrors.password && <p className="auth-error">{fieldErrors.password}</p>}
                            </label>

                            {isRegister && (
                                <label className="auth-field">
                                    <span>Xác nhận mật khẩu</span>
                                    <input
                                        className="filter-input"
                                        type="password"
                                        value={confirmPassword}
                                        onChange={(event) => {
                                            setConfirmPassword(event.target.value);
                                            updateFieldError('confirmPassword', event.target.value);
                                        }}
                                        placeholder="Nhập lại mật khẩu"
                                        autoComplete="new-password"
                                        aria-invalid={Boolean(fieldErrors.confirmPassword)}
                                    />
                                    {fieldErrors.confirmPassword && <p className="auth-error">{fieldErrors.confirmPassword}</p>}
                                </label>
                            )}

                            {formError && <p className="auth-error">{formError}</p>}
                            {session && <p className="auth-success">Bạn đang đăng nhập bằng {session.user.email}.</p>}

                            <button type="submit" className="btn-primary auth-submit" disabled={busy}>
                                {busy ? 'Đang xử lý...' : title}
                            </button>
                        </form>

                        <button
                            className="auth-switch"
                            type="button"
                            onClick={() => navigate(isRegister ? 'view-login' : 'view-register')}
                        >
                            {isRegister ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký'}
                        </button>
                    </div>
                </div>
            </div>
        </section>
    );
}
