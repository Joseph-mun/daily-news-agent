import { notFound } from 'next/navigation';
import { getAllDates, getDailyData } from '@/lib/db';
import DateNavigation from '@/components/DateNavigation';
import CategoryChart from '@/components/CategoryChart';
import NewsCard from '@/components/NewsCard';
import AnalysisReport from '@/components/AnalysisReport';
import CommentSection from '@/components/CommentSection';
import type { Metadata } from 'next';

interface PageProps {
  params: Promise<{ date: string }>;
}

export async function generateStaticParams() {
  const dates = await getAllDates();
  return dates.map((date) => ({ date }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { date } = await params;
  return {
    title: `${date} 보안 브리핑 | 금융보안 데일리 브리핑`,
    description: `${date} 금융권 보안 뉴스 AI 큐레이션 브리핑`,
  };
}

export default async function DailyPage({ params }: PageProps) {
  const { date } = await params;

  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    notFound();
  }

  const data = await getDailyData(date);

  if (data.articles.length === 0) {
    notFound();
  }

  const domesticCount = data.articles.filter((a) => a.category.includes('국내')).length;
  const overseasCount = data.articles.filter((a) => a.category.includes('해외')).length;

  return (
    <div className="space-y-10">
      <DateNavigation
        currentDate={date}
        prevDate={data.prevDate}
        nextDate={data.nextDate}
      />

      {data.briefing?.analysis && (
        <section>
          <h2 className="text-center text-sm font-semibold text-gray-400 tracking-widest uppercase mb-6">
            전략적 분석
          </h2>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 md:p-8">
            <AnalysisReport markdown={data.briefing.analysis} articles={data.articles} />
          </div>
        </section>
      )}

      <CategoryChart domestic={domesticCount} overseas={overseasCount} />

      <section>
        <h2 className="text-center text-sm font-semibold text-gray-400 tracking-widest uppercase mb-6">
          참고 기사
        </h2>
        <div className="space-y-4">
          {data.articles.map((article, index) => (
            <NewsCard key={article.id} article={article} index={index + 1} />
          ))}
        </div>
      </section>

      <section>
        <CommentSection date={date} />
      </section>
    </div>
  );
}
