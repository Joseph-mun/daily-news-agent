import { createClient } from '@libsql/client';

export function getTursoClient() {
  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;

  if (!url) {
    throw new Error('TURSO_DATABASE_URL is not set');
  }

  return createClient({
    url,
    authToken,
  });
}

export async function initCommentsTable() {
  const client = getTursoClient();
  await client.execute(`
    CREATE TABLE IF NOT EXISTS comments (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      date        TEXT NOT NULL,
      nickname    TEXT DEFAULT '익명',
      content     TEXT NOT NULL,
      ip_hash     TEXT,
      created_at  TEXT NOT NULL
    )
  `);
  await client.execute(`
    CREATE INDEX IF NOT EXISTS idx_comments_date ON comments(date)
  `);
}
