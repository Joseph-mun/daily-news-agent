import ReactMarkdown from 'react-markdown';

interface AnalysisReportProps {
  markdown: string;
}

export default function AnalysisReport({ markdown }: AnalysisReportProps) {
  // [N] 형식의 기사 참조를 배지로 변환
  const processedMarkdown = markdown.replace(
    /\[(\d+)\]/g,
    '<span class="ref-badge">$1</span>'
  );

  return (
    <div className="prose max-w-none">
      <ReactMarkdown
        components={{
          // HTML을 허용하여 ref-badge span 렌더링
          p: ({ children, ...props }) => {
            if (typeof children === 'string' || (Array.isArray(children) && children.some(c => typeof c === 'string'))) {
              const html = childrenToString(children).replace(
                /\[(\d+)\]/g,
                '<span class="inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-blue-100 text-blue-700 rounded mx-0.5">$1</span>'
              );
              return <p {...props} dangerouslySetInnerHTML={{ __html: html }} />;
            }
            return <p {...props}>{children}</p>;
          },
          li: ({ children, ...props }) => {
            if (typeof children === 'string' || (Array.isArray(children) && children.some(c => typeof c === 'string'))) {
              const html = childrenToString(children).replace(
                /\[(\d+)\]/g,
                '<span class="inline-flex items-center justify-center w-5 h-5 text-xs font-bold bg-blue-100 text-blue-700 rounded mx-0.5">$1</span>'
              );
              return <li {...props} dangerouslySetInnerHTML={{ __html: html }} />;
            }
            return <li {...props}>{children}</li>;
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function childrenToString(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(childrenToString).join('');
  return '';
}
