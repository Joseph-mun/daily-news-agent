import { getDatesByMonth } from '@/lib/db';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '아카이브 | 금융보안 데일리 브리핑',
  description: '과거 금융권 보안 뉴스 브리핑 아카이브',
};

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

function CalendarMonth({ year, month, activeDates }: { year: number; month: number; activeDates: Set<string> }) {
  const firstDay = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-3 text-center">
        {year}년 {month}월
      </h2>
      <div className="grid grid-cols-7 gap-1">
        {WEEKDAYS.map((wd) => (
          <div key={wd} className="text-center text-xs font-medium text-gray-400 py-1">
            {wd}
          </div>
        ))}
        {cells.map((day, i) => {
          if (day === null) {
            return <div key={`empty-${i}`} />;
          }

          const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const hasData = activeDates.has(dateStr);

          if (hasData) {
            return (
              <a
                key={dateStr}
                href={`/daily/${dateStr}`}
                className="flex items-center justify-center h-9 rounded-lg text-sm font-medium bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 transition-colors"
              >
                {day}
              </a>
            );
          }

          return (
            <div
              key={dateStr}
              className="flex items-center justify-center h-9 rounded-lg text-sm text-gray-300"
            >
              {day}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default async function ArchivePage() {
  const datesByMonth = await getDatesByMonth();
  const months = Object.keys(datesByMonth).sort().reverse();

  if (months.length === 0) {
    return (
      <div className="text-center py-20">
        <h1 className="text-2xl font-bold text-gray-700 mb-4">아카이브</h1>
        <p className="text-gray-500">아직 등록된 뉴스가 없습니다.</p>
      </div>
    );
  }

  // 모든 날짜를 Set으로 모아두기
  const allDates = new Set<string>();
  for (const dates of Object.values(datesByMonth)) {
    for (const d of dates) allDates.add(d);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">아카이브</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {months.map((month) => {
          const [y, m] = month.split('-');
          return (
            <CalendarMonth
              key={month}
              year={parseInt(y)}
              month={parseInt(m)}
              activeDates={allDates}
            />
          );
        })}
      </div>
    </div>
  );
}
