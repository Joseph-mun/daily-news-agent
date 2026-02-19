import { NextRequest, NextResponse } from 'next/server';
import { getTursoClient } from '@/lib/turso';
import crypto from 'crypto';

// Rate limiting: simple in-memory store
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 5; // max requests per window
const RATE_WINDOW = 60_000; // 1 minute

function getIpHash(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  const ip = forwarded?.split(',')[0]?.trim() ?? 'unknown';
  return crypto.createHash('sha256').update(ip).digest('hex').slice(0, 16);
}

function checkRateLimit(ipHash: string): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(ipHash);

  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(ipHash, { count: 1, resetAt: now + RATE_WINDOW });
    return true;
  }

  if (entry.count >= RATE_LIMIT) {
    return false;
  }

  entry.count++;
  return true;
}

export async function GET(req: NextRequest) {
  const date = req.nextUrl.searchParams.get('date');
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: '유효하지 않은 날짜입니다.' }, { status: 400 });
  }

  try {
    const client = getTursoClient();
    const result = await client.execute({
      sql: 'SELECT id, date, nickname, content, created_at FROM comments WHERE date = ? ORDER BY created_at ASC',
      args: [date],
    });

    const comments = result.rows.map((row) => ({
      id: row.id,
      date: row.date,
      nickname: row.nickname,
      content: row.content,
      created_at: row.created_at,
    }));

    return NextResponse.json({ comments });
  } catch {
    return NextResponse.json({ comments: [] });
  }
}

export async function POST(req: NextRequest) {
  const ipHash = getIpHash(req);

  if (!checkRateLimit(ipHash)) {
    return NextResponse.json(
      { error: '너무 많은 요청입니다. 잠시 후 다시 시도해주세요.' },
      { status: 429 }
    );
  }

  let body: { date?: string; nickname?: string; content?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: '잘못된 요청입니다.' }, { status: 400 });
  }

  const { date, nickname, content } = body;

  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: '유효하지 않은 날짜입니다.' }, { status: 400 });
  }

  if (!content || content.trim().length === 0) {
    return NextResponse.json({ error: '댓글 내용을 입력해주세요.' }, { status: 400 });
  }

  if (content.length > 500) {
    return NextResponse.json({ error: '댓글은 500자 이내로 작성해주세요.' }, { status: 400 });
  }

  const safeNickname = (nickname?.trim() || '익명').slice(0, 20);
  const safeContent = content.trim();
  const createdAt = new Date().toISOString();

  try {
    const client = getTursoClient();

    // Ensure table exists
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

    await client.execute({
      sql: 'INSERT INTO comments (date, nickname, content, ip_hash, created_at) VALUES (?, ?, ?, ?, ?)',
      args: [date, safeNickname, safeContent, ipHash, createdAt],
    });

    return NextResponse.json({ success: true }, { status: 201 });
  } catch {
    return NextResponse.json({ error: '댓글 등록에 실패했습니다.' }, { status: 500 });
  }
}
