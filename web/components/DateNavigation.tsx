'use client';

interface DateNavigationProps {
  currentDate: string;
  prevDate: string | null;
  nextDate: string | null;
}

export default function DateNavigation({ currentDate, prevDate, nextDate }: DateNavigationProps) {
  return (
    <div className="flex items-center justify-center gap-4">
      {prevDate ? (
        <a
          href={`/daily/${prevDate}`}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-600 transition-colors text-lg"
          title={prevDate}
        >
          &lsaquo;
        </a>
      ) : (
        <span className="w-9 h-9" />
      )}

      <h1 className="text-xl font-bold text-gray-900">
        {currentDate} 정보보호 뉴스
      </h1>

      {nextDate ? (
        <a
          href={`/daily/${nextDate}`}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-600 transition-colors text-lg"
          title={nextDate}
        >
          &rsaquo;
        </a>
      ) : (
        <span className="w-9 h-9" />
      )}
    </div>
  );
}
