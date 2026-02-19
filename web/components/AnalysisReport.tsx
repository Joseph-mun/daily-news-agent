import type { Article } from '@/lib/types';

interface AnalysisReportProps {
  markdown: string;
  articles?: Article[];
}

function RefBadge({ num, article }: { num: string; article?: Article }) {
  const className =
    'inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-blue-100 text-blue-700 rounded mx-0.5 hover:bg-blue-200 transition-colors cursor-pointer';

  if (article?.url) {
    return (
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        title={article.title}
        className={className}
      >
        {num}
      </a>
    );
  }

  return (
    <span className="inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-blue-100 text-blue-700 rounded mx-0.5">
      {num}
    </span>
  );
}

function renderLineWithBadges(text: string, articles: Article[], keyPrefix: string) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const idx = parseInt(match[1], 10) - 1;
      return <RefBadge key={`${keyPrefix}-${i}`} num={match[1]} article={articles[idx]} />;
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

export default function AnalysisReport({ markdown, articles = [] }: AnalysisReportProps) {
  const lines = markdown.split('\n');

  return (
    <div className="text-sm text-gray-800 leading-relaxed">
      {lines.map((line, i) => {
        // ### 헤딩 → 볼드체
        const headingMatch = line.match(/^#{1,3}\s+(.+)$/);
        if (headingMatch) {
          return (
            <p key={i} className="font-bold text-gray-900 mt-4 mb-1">
              {renderLineWithBadges(headingMatch[1], articles, `h-${i}`)}
            </p>
          );
        }

        // 빈 줄
        if (line.trim() === '') {
          return <br key={i} />;
        }

        // 일반 텍스트
        return (
          <p key={i} className="mb-0.5">
            {renderLineWithBadges(line, articles, `l-${i}`)}
          </p>
        );
      })}
    </div>
  );
}
