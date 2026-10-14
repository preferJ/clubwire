// S01 홈 · 와이어: LIVE 배너, 다음/진행 중 일정, 기사 피드

import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Article, LiveMatch, SessionListItem } from '../api/types'
import { Icon } from '../components/Icon'
import { AdminButton, Empty, ErrorBox, Loading, Tags, TeamBadge } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtClock, fmtDate, fmtDateTime, SESSION_STATUS_LABEL } from '../lib/format'
import { useAsync, useMatchClock } from '../lib/hooks'

const TAGS = ['전체', '마감', '프리뷰', '복귀', '연승', '결승골', '역전', '타이틀']

export function HomePage() {
  const { api, club, slug, isAdmin } = useClub()
  const [tag, setTag] = useState('전체')
  const live = useAsync(() => api.live(), [api])
  const sessions = useAsync(() => api.sessions(10), [api])
  const articles = useAsync(() => api.articles({ tag: tag === '전체' ? undefined : tag, limit: 20 }), [api, tag])

  useClubEvent((m) => {
    if (m.type === 'MATCH_UPDATED') live.reload()
    if (m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED') sessions.reload()
    if (m.type === 'ARTICLE_UPDATED') articles.reload()
  })

  const current = pickCurrentSession(sessions.data ?? [])

  return (
    <>
      <header className="home-head">
        <div className="stack" style={{ gap: 2 }}>
          <span className="eyebrow">THE WIRE</span>
          <h1 className="club-name">{club?.clubName ?? ' '}</h1>
        </div>
        <AdminButton />
      </header>

      <main className="page">
        {(live.data ?? []).map((m) => (
          <LiveBanner key={m.matchId} m={m} slug={slug} />
        ))}

        {sessions.loading && !sessions.data ? (
          <Loading rows={1} />
        ) : current ? (
          <SessionCard s={current} slug={slug} />
        ) : (
          <div className="card flat row between">
            <span className="muted" style={{ fontSize: 14 }}>예정된 일정이 없어요</span>
            {isAdmin ? <Link className="btn sm primary" to={`/c/${slug}/admin/sessions/new`}>새 일정</Link> : null}
          </div>
        )}

        <section className="section" aria-labelledby="wire-title">
          <div className="section-head">
            <h2 id="wire-title" className="big">The Wire</h2>
            <span className="small muted">경기 기록으로 쓴 기사</span>
          </div>
          <div className="chips" role="group" aria-label="기사 태그">
            {TAGS.map((t) => (
              <button key={t} type="button" className="chip" aria-pressed={tag === t} onClick={() => setTag(t)}>
                {t}
              </button>
            ))}
          </div>
          {articles.error ? (
            <ErrorBox error={articles.error} onRetry={articles.reload} />
          ) : articles.loading && !articles.data ? (
            <Loading />
          ) : (articles.data ?? []).length === 0 ? (
            <Empty>아직 게시된 기사가 없어요.<br />[일정확정] 때 프리뷰, [일정마감] 때 마감 기사가 나옵니다.</Empty>
          ) : (
            (articles.data ?? []).map((a, i) => <ArticleCard key={a.articleId} a={a} slug={slug} lead={i === 0} />)
          )}
        </section>
      </main>
    </>
  )
}

function pickCurrentSession(list: SessionListItem[]): SessionListItem | null {
  const open = list
    .filter((s) => ['OPEN', 'CONFIRMED', 'IN_PROGRESS'].includes(s.status))
    .sort((a, b) => a.sessionDate.localeCompare(b.sessionDate) || a.sessionId - b.sessionId)
  return open[0] ?? null
}

function LiveBanner({ m, slug }: { m: LiveMatch; slug: string }) {
  const clock = useMatchClock(m)
  const label = m.status === 'READY' ? '곧 시작' : m.status === 'PAUSED' ? '일시정지' : fmtClock(clock.remaining)
  return (
    <Link to={`/c/${slug}/matches/${m.matchId}`} className="card link" style={{ background: 'var(--night)', borderColor: 'var(--night)', color: '#fff' }}>
      <div className="row between">
        <div className="row">
          {m.status === 'READY' ? <span className="status-badge gold">대기</span> : <span className="live-badge">LIVE</span>}
          <span className="small" style={{ color: 'var(--night-muted)' }}>{fmtDate(m.sessionDate, false)} · {m.gameNo}경기</span>
        </div>
        <span className="mono" style={{ fontWeight: 600 }}>{label}</span>
      </div>
      <div className="row between" style={{ marginTop: 10 }}>
        <div className="row"><TeamBadge code={m.teamA.teamCode} size={28} onDark /><b>TEAM {m.teamA.teamCode}</b></div>
        <span style={{ fontFamily: 'var(--display)', fontSize: 32 }}>{m.teamA.score} : {m.teamB.score}</span>
        <div className="row"><b>TEAM {m.teamB.teamCode}</b><TeamBadge code={m.teamB.teamCode} size={28} onDark /></div>
      </div>
    </Link>
  )
}

function SessionCard({ s, slug }: { s: SessionListItem; slug: string }) {
  const [, m, d] = s.sessionDate.split('-').map(Number)
  return (
    <Link to={`/c/${slug}/sessions/${s.sessionId}`} className="card link row" style={{ gap: 14 }}>
      <div style={{ width: 52, height: 56, borderRadius: 12, background: 'var(--green-soft)', color: 'var(--green)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600 }}>{m}월</span>
        <span style={{ fontFamily: 'var(--display)', fontSize: 24, lineHeight: 1 }}>{d}</span>
      </div>
      <div className="stack" style={{ flex: 1, gap: 3 }}>
        <div className="row">
          <b style={{ fontSize: 15 }}>{s.title}</b>
          <span className={`status-badge ${s.status === 'IN_PROGRESS' ? 'green' : ''}`}>{SESSION_STATUS_LABEL[s.status]}</span>
        </div>
        <span className="small muted">
          {s.location ? `${s.location} · ` : ''}참석 {s.attendeeCount}명{s.guestCount ? ` · 게스트 ${s.guestCount}명` : ''}
        </span>
        {s.teamCount ? <span className="small muted">{s.teamCount}팀</span> : null}
      </div>
      <Icon name="chevron" />
    </Link>
  )
}

function ArticleCard({ a, slug, lead }: { a: Article; slug: string; lead: boolean }) {
  return (
    <Link to={`/c/${slug}/articles/${a.articleId}`} className="card link stack" style={{ gap: 8 }}>
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
