// 기사 카드: 와이어(홈) 최근 기사 · 기록 탭 지난 기사에서 같이 쓴다

import { Link } from 'react-router-dom'
import type { Article } from '../api/types'
import { fmtDateTime } from '../lib/format'
import { Tags, type FromState } from './ui'

export function ArticleCard({ a, slug, lead, from }: {
  a: Article
  slug: string
  lead: boolean
  /** 상세에서 [뒤로]·하단 탭이 돌아갈 곳(없으면 와이어) */
  from?: FromState['from']
}) {
  return (
    <Link to={`/c/${slug}/articles/${a.articleId}`} state={from ? { from } : undefined} className="card link stack" style={{ gap: 8 }}>
      <Tags tags={a.tags} />
      {lead ? (
        <div className="headline" style={{ fontSize: 22 }}>{a.title}</div>
      ) : (
        <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.4 }}>{a.title}</div>
      )}
      {lead && a.summary ? <p style={{ fontSize: 14, color: 'var(--ink-3)', lineHeight: 1.55 }}>{a.summary}</p> : null}
      <span className="small muted">
        {fmtDateTime(a.publishedAt ?? a.createdAt)} · {a.articleType === 'PRE_MATCH' ? '프리뷰' : '마감 기사'}
      </span>
    </Link>
  )
}
