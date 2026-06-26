import React from 'react';
import type { Icon } from '@phosphor-icons/react';

type IconComponent = Icon;

export function PageFrame({
    id,
    active,
    icon: Icon,
    title,
    description,
    children,
}: {
    id: string;
    active: boolean;
    icon: IconComponent;
    title: string;
    description?: string;
    children: React.ReactNode;
}) {
    return (
        <section id={id} className={`view-section ${active ? 'active' : ''}`.trim()}>
            <div className="mockup-container">
                <header className="mb-6">
                    <div className="view-header mb-1">
                        <Icon size={24} weight="fill" />
                        <h1>{title}</h1>
                    </div>
                    {description && <p className="text-sm text-slate-500">{description}</p>}
                </header>
                {children}
            </div>
        </section>
    );
}

export function Panel({
    title,
    children,
    className = '',
}: {
    title?: string;
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <section className={`content-section ${className}`.trim()}>
            {title && (
                <h2 className="mb-4 border-b border-navy-800/10 pb-3 text-sm font-bold text-navy-800">
                    {title}
                </h2>
            )}
            {children}
        </section>
    );
}

export function MetricCard({
    icon: Icon,
    label,
    value,
    status,
}: {
    icon: IconComponent;
    label: string;
    value: string;
    status?: string;
}) {
    return (
        <article className="dash-card">
            <div className="dash-card-title"><Icon size={18} /> {label}</div>
            <div className="dash-card-value">{value}</div>
            {status && <div className="dash-card-status good">{status}</div>}
        </article>
    );
}

export function EmptyView({
    icon,
    title,
    description,
}: {
    icon: IconComponent;
    title: string;
    description: string;
}) {
    const Icon = icon;
    return (
        <div className="empty-state min-h-[360px]">
            <span className="empty-state-icon"><Icon size={30} weight="duotone" /></span>
            <strong>{title}</strong>
            <p className="max-w-md">{description}</p>
        </div>
    );
}

export function TableShell({ children }: { children: React.ReactNode }) {
    return <div className="overflow-x-auto rounded-2xl">{children}</div>;
}
