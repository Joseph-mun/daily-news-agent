import path from 'path';
import fs from 'fs';
import type { Article, DailyBriefing, DailyData } from './types';
import type { Database } from 'sql.js';
import initSqlJs from 'sql.js';

let cachedDb: Database | null = null;

async function getDb(): Promise<Database | null> {
  if (cachedDb) return cachedDb;

  const dbPath = path.join(process.cwd(), 'data', 'news.db');
  if (!fs.existsSync(dbPath)) {
    return null;
  }

  const SQL = await initSqlJs();
  const buffer = fs.readFileSync(dbPath);
  const db = new SQL.Database(buffer);
  cachedDb = db;
  return db;
}

async function queryAll<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const db = await getDb();
  if (!db) return [];

  const stmt = db.prepare(sql);
  if (params.length > 0) {
    stmt.bind(params);
  }

  const results: T[] = [];
  while (stmt.step()) {
    results.push(stmt.getAsObject() as T);
  }
  stmt.free();
  return results;
}

async function queryOne<T>(sql: string, params: unknown[] = []): Promise<T | null> {
  const results = await queryAll<T>(sql, params);
  return results.length > 0 ? results[0] : null;
}

export async function getAllDates(): Promise<string[]> {
  const rows = await queryAll<{ date: string }>(
    'SELECT DISTINCT date FROM articles ORDER BY date DESC'
  );
  return rows.map((r) => r.date);
}

export async function getLatestDate(): Promise<string | null> {
  const dates = await getAllDates();
  return dates.length > 0 ? dates[0] : null;
}

export async function getDailyData(date: string): Promise<DailyData> {
  const briefing = await queryOne<DailyBriefing>(
    'SELECT * FROM daily_briefings WHERE date = ?',
    [date]
  );

  const articles = await queryAll<Article>(
    'SELECT * FROM articles WHERE date = ? ORDER BY id ASC',
    [date]
  );

  const prevRow = await queryOne<{ date: string }>(
    'SELECT date FROM articles WHERE date < ? GROUP BY date ORDER BY date DESC LIMIT 1',
    [date]
  );

  const nextRow = await queryOne<{ date: string }>(
    'SELECT date FROM articles WHERE date > ? GROUP BY date ORDER BY date ASC LIMIT 1',
    [date]
  );

  return {
    briefing: briefing ?? null,
    articles,
    prevDate: prevRow?.date ?? null,
    nextDate: nextRow?.date ?? null,
  };
}

export async function getDatesByMonth(): Promise<Record<string, string[]>> {
  const dates = await getAllDates();
  const grouped: Record<string, string[]> = {};
  for (const d of dates) {
    const month = d.slice(0, 7);
    if (!grouped[month]) grouped[month] = [];
    grouped[month].push(d);
  }
  return grouped;
}
