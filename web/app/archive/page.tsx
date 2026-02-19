import { getDatesByMonth } from '@/lib/db';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '아카이브 | 금융보안 데일리 브리핑',
  description: '과거 금융권 보안 뉴스 브리핑 아카이브',
};

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

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">아카이브</h1>
      <div className="space-y-8">
        {months.map((month) => {
          const [year, mon] = month.split('-');
          const label = `${year}년 ${parseInt(mon)}월`;
          const dates = datesByMonth[month];

          return (
            <div key={month}>
              <h2 className="text-lg font-semibold text-gray-700 mb-3">
                {label}
              </h2>
              <div className="flex flex-wrap gap-2">
                {dates.map((date) => {
                  const day = parseInt(date.split('-')[2]);
                  return (
                    <a
                      key={date}
                      href={`/daily/${date}`}
                      className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-white border border-gray-200 text-sm font-medium text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
                    >
                      {day}
                    </a>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
