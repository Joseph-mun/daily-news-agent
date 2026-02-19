import type { Article } from '@/lib/types';

interface AnalysisReportProps {
  markdown: string;
  articles?: Article[];
}

export default function AnalysisReport({ markdown, articles = [] }: AnalysisReportProps) {
  // [N] 형식의 기사 참조를 클릭 가능한 배지로 변환
  const parts = markdown.split(/(\[\d+\])/g);

  return (
    <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
          const idx = parseInt(match[1], 10) - 1;
          const article = articles[idx];

          if (article?.url) {
            return (
              <a
                key={i}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                title={article.title}
                className="inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-blue-100 text-blue-700 rounded mx-0.5 hover:bg-blue-200 transition-colors cursor-pointer"
              >
                {match[1]}
              </a>
            );
          }

          return (
            <span
              key={i}
              className="inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-blue-100 text-blue-700 rounded mx-0.5"
            >
              {match[1]}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </div>
  );
}
