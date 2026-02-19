'use client';

interface DateNavigationProps {
  currentDate: string;
  prevDate: string | null;
  nextDate: string | null;
}

export default function DateNavigation({ currentDate, prevDate, nextDate }: DateNavigationProps) {
  const isLatest = !nextDate;

  return (
    <div className="flex items-center justify-between">
      {prevDate ? (
        <a
          href={`/daily/${prevDate}`}
          className="text-sm text-gray-500 hover:text-blue-600 transition-colors"
        >
          &larr; {prevDate}
        </a>
      ) : (
        <span />
      )}

      <h1 className="text-xl font-bold text-gray-900">
        {currentDate} 보안 브리핑
      </h1>

      {isLatest ? (
        <span />
      ) : nextDate ? (
        <a
          href={`/daily/${nextDate}`}
          className="text-sm text-gray-500 hover:text-blue-600 transition-colors"
        >
          {nextDate} &rarr;
        </a>
      ) : (
        <span />
      )}
    </div>
  );
}
