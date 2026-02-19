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
        {/* 번호 + 카테고리 */}
        <div className="flex-shrink-0 flex flex-col items-center gap-0.5">
          <span className="w-7 h-7 rounded-full bg-gray-100 text-gray-600 text-sm font-bold flex items-center justify-center">
            {index}
          </span>
          <span
            className={`text-[10px] font-medium ${
              isOverseas ? 'text-emerald-600' : 'text-blue-600'
            }`}
          >
            {isOverseas ? '해외' : '국내'}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          {/* 제목 */}
          <h3 className="text-base font-semibold text-gray-900 leading-snug">
            {article.title}
          </h3>

          {/* 해외 기사 원문 제목 */}
          {isOverseas && article.title_original && (
            <p className="text-sm italic text-gray-400 mt-0.5">
              {article.title_original}
            </p>
          )}

          {/* AI 요약 (3줄) */}
          {article.summary && (
            <p className="text-sm text-gray-600 mt-1.5 whitespace-pre-line">
              {article.summary}
            </p>
          )}

          {/* 링크 */}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-1.5 text-xs text-blue-500 hover:text-blue-700 truncate max-w-full"
          >
            {article.url}
          </a>
        </div>
      </div>
    </div>
  );
}
