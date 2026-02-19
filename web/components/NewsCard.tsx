import type { Article } from '@/lib/types';

interface NewsCardProps {
  article: Article;
  index: number;
}

export default function NewsCard({ article, index }: NewsCardProps) {
  const isOverseas = article.category.includes('해외');

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-3">
        {/* 번호 배지 */}
        <span className="flex-shrink-0 w-7 h-7 rounded-full bg-gray-100 text-gray-600 text-sm font-bold flex items-center justify-center">
          {index}
        </span>

        <div className="flex-1 min-w-0">
          {/* 카테고리 + 제목 */}
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                isOverseas
                  ? 'bg-emerald-50 text-emerald-700'
                  : 'bg-blue-50 text-blue-700'
              }`}
            >
              {isOverseas ? '해외' : '국내'}
            </span>
          </div>

          <h3 className="text-base font-semibold text-gray-900 leading-snug mb-1">
            {article.title}
          </h3>

          {/* 해외 기사 원문 제목 */}
          {isOverseas && article.title_original && (
            <p className="text-sm italic text-gray-400 mb-2">
              {article.title_original}
            </p>
          )}

          {/* AI 요약 (3줄) */}
          {article.summary && (
            <p className="text-sm text-gray-600 mb-1 whitespace-pre-line">
              {article.summary}
            </p>
          )}

          {/* 링크 */}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-2 text-xs text-blue-500 hover:text-blue-700 truncate max-w-full"
          >
            {article.url}
          </a>
        </div>
      </div>
    </div>
  );
}
