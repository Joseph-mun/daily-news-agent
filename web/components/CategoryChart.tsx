interface CategoryChartProps {
  domestic: number;
  overseas: number;
}

export default function CategoryChart({ domestic, overseas }: CategoryChartProps) {
  const total = domestic + overseas;
  if (total === 0) return null;

  const domesticPct = Math.round((domestic / total) * 100);
  const overseasPct = 100 - domesticPct;

  return (
    <div className="flex items-center gap-4">
      <div className="flex-1 h-3 rounded-full bg-gray-100 overflow-hidden flex">
        <div
          className="bg-blue-500 transition-all"
          style={{ width: `${domesticPct}%` }}
        />
        <div
          className="bg-emerald-500 transition-all"
          style={{ width: `${overseasPct}%` }}
        />
      </div>
      <div className="flex items-center gap-3 text-xs text-gray-500 flex-shrink-0">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          국내 {domestic}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          해외 {overseas}
        </span>
      </div>
    </div>
  );
}
