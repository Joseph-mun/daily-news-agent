import { redirect } from 'next/navigation';
import { getLatestDate } from '@/lib/db';

export default async function Home() {
  const latestDate = await getLatestDate();

  if (latestDate) {
    redirect(`/daily/${latestDate}`);
  }

  return (
    <div className="text-center py-20">
      <h1 className="text-2xl font-bold text-gray-700 mb-4">
        금융보안 데일리 브리핑
      </h1>
      <p className="text-gray-500">
        아직 등록된 뉴스가 없습니다. GitHub Actions가 실행되면 자동으로 데이터가 추가됩니다.
      </p>
    </div>
  );
}
