import type { Metadata } from 'next';
import '@fontsource/be-vietnam-pro/400.css';
import '@fontsource/be-vietnam-pro/500.css';
import '@fontsource/be-vietnam-pro/600.css';
import '@fontsource/be-vietnam-pro/700.css';
import '@fontsource/be-vietnam-pro/800.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'Hệ Thống Tra Cứu Văn Bản Pháp Luật | VT Law AI',
  description: 'Tra cứu văn bản pháp luật, chính sách, nghị định, thông tư mới nhất. Hỗ trợ bởi AI.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
