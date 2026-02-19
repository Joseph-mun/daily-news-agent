interface AnalysisReportProps {
  markdown: string;
}

export default function AnalysisReport({ markdown }: AnalysisReportProps) {
  // [N] 형식의 기사 참조를 배지로 변환
  const parts = markdown.split(/(\[\d+\])/g);

  return (
    <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
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
