'use client';

export type AuthFieldErrors<T extends string> = Partial<Record<T, string>>;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function normalizeDisplayName(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

export function validateEmail(value: string): string | null {
  const normalized = normalizeEmail(value);
  if (!normalized) return 'Vui lòng nhập email.';
  if (normalized.length < 3 || normalized.length > 100) return 'Email phải có từ 3 đến 100 ký tự.';
  if (normalized.includes(' ')) return 'Email không được chứa khoảng trắng.';
  if (normalized.split('@').length !== 2 || !EMAIL_PATTERN.test(normalized)) return 'Email không hợp lệ.';
  if (normalized.includes('..')) return 'Email không hợp lệ.';
  const [, domain = ''] = normalized.split('@');
  if (!domain || domain.startsWith('.') || domain.endsWith('.')) return 'Email không hợp lệ.';
  return null;
}

export function validateDisplayName(value: string, label = 'Họ và tên'): string | null {
  const normalized = normalizeDisplayName(value);
  if (!normalized) return `Vui lòng nhập ${label.toLowerCase()}.`;
  if (normalized.length < 2 || normalized.length > 50) return `${label} phải có từ 2 đến 50 ký tự.`;
  const letterCount = Array.from(normalized).filter((char) => /\p{L}/u.test(char)).length;
  if (letterCount < 2) return `${label} phải chứa ít nhất 2 chữ cái.`;
  return null;
}

export function validatePasswordStrength(value: string, label = 'Mật khẩu'): string | null {
  if (!value) return `Vui lòng nhập ${label.toLowerCase()}.`;
  if (value.length < 8 || value.length > 128) return `${label} phải có từ 8 đến 128 ký tự.`;
  if (/\s/.test(value)) return `${label} không được chứa khoảng trắng.`;
  if (!/[A-Za-z]/.test(value)) return `${label} phải có ít nhất 1 chữ cái.`;
  if (!/\d/.test(value)) return `${label} phải có ít nhất 1 chữ số.`;
  return null;
}

export function validatePasswordConfirmation(password: string, confirmPassword: string, label = 'Xác nhận mật khẩu'): string | null {
  if (!confirmPassword) return `Vui lòng nhập ${label.toLowerCase()}.`;
  if (password !== confirmPassword) return `${label} chưa khớp.`;
  return null;
}
