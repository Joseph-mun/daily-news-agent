'use client';

import { useState, useEffect } from 'react';
import type { Comment } from '@/lib/types';

interface CommentSectionProps {
  date: string;
}

export default function CommentSection({ date }: CommentSectionProps) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [nickname, setNickname] = useState('');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchComments();
  }, [date]);

  async function fetchComments() {
    try {
      const res = await fetch(`/api/comments?date=${date}`);
      if (res.ok) {
        const data = await res.json();
        setComments(data.comments ?? []);
      }
    } catch {
      // silently fail for comments
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    if (content.length > 500) {
      setError('댓글은 500자 이내로 작성해주세요.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/comments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date,
          nickname: nickname.trim() || '익명',
          content: content.trim(),
        }),
      });

      if (res.ok) {
        setContent('');
        fetchComments();
      } else {
        const data = await res.json();
        setError(data.error ?? '댓글 등록에 실패했습니다.');
      }
    } catch {
      setError('네트워크 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2 className="text-center text-sm font-semibold text-gray-400 tracking-widest uppercase mb-6">
        댓글 ({comments.length})
      </h2>

      {/* 댓글 목록 */}
      {comments.length > 0 && (
        <div className="space-y-3 mb-6">
          {comments.map((comment) => (
            <div
              key={comment.id}
              className="bg-white rounded-xl border border-gray-100 p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">
                  {comment.nickname}
                </span>
                <span className="text-xs text-gray-400">
                  {comment.created_at.slice(0, 16).replace('T', ' ')}
                </span>
              </div>
              <p className="text-sm text-gray-600 whitespace-pre-wrap">
                {comment.content}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* 댓글 입력 */}
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-xl border border-gray-100 p-4 space-y-3"
      >
        <input
          type="text"
          placeholder="닉네임 (선택)"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          maxLength={20}
          className="w-full text-sm px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
        <textarea
          placeholder="댓글을 작성해주세요 (최대 500자)"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          maxLength={500}
          rows={3}
          className="w-full text-sm px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 resize-none"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">{content.length}/500</span>
          <button
            type="submit"
            disabled={loading || !content.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '등록 중...' : '댓글 등록'}
          </button>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
      </form>
    </div>
  );
}
