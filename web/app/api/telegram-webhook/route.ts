import { NextRequest, NextResponse } from 'next/server';

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || '';
const GITHUB_PAT = process.env.GH_PAT || '';
const GITHUB_REPO = process.env.GITHUB_REPO || 'Joseph-mun/daily-news-agent';
const WEBHOOK_SECRET = process.env.TELEGRAM_WEBHOOK_SECRET || '';

async function sendTelegramMessage(chatId: string, text: string) {
  await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: 'HTML',
    }),
  });
}

async function triggerGitHubWorkflow(analysis: string, date: string) {
  const res = await fetch(
    `https://api.github.com/repos/${GITHUB_REPO}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${GITHUB_PAT}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: 'update-analysis',
        client_payload: { analysis, date },
      }),
    }
  );
  return res.ok;
}

export async function POST(req: NextRequest) {
  // Optional: verify webhook secret via query param
  const secret = req.nextUrl.searchParams.get('secret');
  if (WEBHOOK_SECRET && secret !== WEBHOOK_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const message = body?.message;
  if (!message?.text) {
    return NextResponse.json({ ok: true });
  }

  const chatId = String(message.chat.id);
  const text: string = message.text;

  // Only accept messages from the authorized chat
  if (chatId !== TELEGRAM_CHAT_ID) {
    return NextResponse.json({ ok: true });
  }

  // Check for /분석 command
  if (!text.startsWith('/분석')) {
    return NextResponse.json({ ok: true });
  }

  const analysis = text.replace(/^\/분석\s*/, '').trim();

  if (!analysis) {
    await sendTelegramMessage(chatId, '사용법: /분석 [분석 내용]\n\n분석 내용을 함께 보내주세요.');
    return NextResponse.json({ ok: true });
  }

  // Use today's date in KST
  const now = new Date();
  const kstDate = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const date = kstDate.toISOString().split('T')[0];

  // Trigger GitHub Actions
  const success = await triggerGitHubWorkflow(analysis, date);

  if (success) {
    await sendTelegramMessage(
      chatId,
      `<b>${date} 분석 업데이트 요청 완료</b>\n\n웹사이트에 2~3분 내 반영됩니다.`
    );
  } else {
    await sendTelegramMessage(
      chatId,
      'GitHub Actions 트리거 실패. GH_PAT 환경변수를 확인해주세요.'
    );
  }

  return NextResponse.json({ ok: true });
}
