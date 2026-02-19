'use client';

interface DateNavigationProps {
  currentDate: string;
  prevDate: string | null;
  nextDate: string | null;
}

export default function DateNavigation({ currentDate, prevDate, nextDate }: DateNavigationProps) {
  const btnBase = 'w-9 h-9 flex items-center justify-center rounded-full text-lg transition-colors';

  return (
    <div className="flex items-center justify-center gap-4">
      {prevDate ? (
        <a
          href={`/daily/${prevDate}`}
          className={`${btnBase} bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-600`}
          title={prevDate}
        >
          &lsaquo;
        </a>
      ) : (
        <span className={`${btnBase} bg-gray-50 text-gray-300 cursor-default`}>
          &lsaquo;
        </span>
      )}

      <h1 className="text-xl font-bold text-gray-900">
        {currentDate} 정보보호 뉴스
      </h1>

      {nextDate ? (
        <a
          href={`/daily/${nextDate}`}
          className={`${btnBase} bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-600`}
          title={nextDate}
        >
          &rsaquo;
        </a>
      ) : (
        <span className={`${btnBase} bg-gray-50 text-gray-300 cursor-default`}>
          &rsaquo;
        </span>
      )}
    </div>
  );
}
