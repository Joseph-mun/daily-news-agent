export interface Article {
  id: number;
  date: string;
  category: string;
  title: string;
  title_original: string | null;
  url: string;
  summary: string | null;
  insight: string | null;
  detected_date: string | null;
  created_at: string;
}

export interface DailyBriefing {
  date: string;
  analysis: string;
  created_at: string;
}

export interface Comment {
  id: number;
  date: string;
  nickname: string;
  content: string;
  created_at: string;
}

export interface DailyData {
  briefing: DailyBriefing | null;
  articles: Article[];
  prevDate: string | null;
  nextDate: string | null;
}
