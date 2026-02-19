import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '금융보안 데일리 브리핑',
  description: '매일 AI가 큐레이션한 금융권 보안 뉴스 브리핑',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-gray-50">
        <header className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
            <a href="/" className="text-lg font-bold text-gray-900 hover:text-blue-600 transition-colors">
              정보보호 뉴스
            </a>
            <a
              href="/archive"
              className="text-sm text-gray-500 hover:text-gray-900 transition-colors"
            >
              아카이브
            </a>
          </div>
        </header>
        <main className="max-w-4xl mx-auto px-4 py-8">{children}</main>
        <footer className="border-t border-gray-200 mt-16">
          <div className="max-w-4xl mx-auto px-4 py-6 text-center text-xs text-gray-400">
            금융보안 데일리 브리핑 &middot; AI 큐레이션 뉴스
          </div>
        </footer>
      </body>
    </html>
  );
}
