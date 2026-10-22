// S01 홈 · 와이어: LIVE 배너, 이번·지난 일정, 두 일정의 최근 기사(지난 기사는 기록 탭)

import { Link } from 'react-router-dom'
import type { Api } from '../api/endpoints'
import type { Article, LiveMatch, SessionListItem } from '../api/types'
import { ArticleCard } from '../components/ArticleCard'
import { Icon } from '../components/Icon'
import { AdminButton, Empty, ErrorBox, Loading, TeamBadge } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtClock, fmtDate, SESSION_STATUS_LABEL } from '../lib/format'
import { useAsync, useMatchClock } from '../lib/hooks'

/** 와이어에 바로 보이는 기사 수. 나머지는 [기사 더보기] → 기록 탭 */
const WIRE_ARTICLES = 3

export function HomePage() {
  const { api, club, slug, isAdmin } = useClub()
  const live = useAsync(() => api.live(), [api])
  const sessions = useAsync(() => api.sessions(10), [api])
  const picked = pickWireSessions(sessions.data ?? [])
  const pickedIds = picked.map((p) => p.s.sessionId)
  const articles = useAsync(() => loadWireArticles(api, pickedIds), [api, pickedIds.join(',')])

  useClubEvent((m) => {
    if (m.type === 'MATCH_UPDATED') live.reload()
    if (m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED') sessions.reload()
    if (m.type === 'ARTICLE_UPDATED') articles.reload()
  })

  // 일정 목록을 받기 전, 또는 고른 일정이 바뀌어 다시 불러오는 중이면 로딩 표시
  const articlesLoading = (sessions.loading && !sessions.data) || (articles.loading && !articles.data?.length)
  const shown = (articles.data ?? []).slice(0, WIRE_ARTICLES)

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
          <Loading rows={2} />
        ) : (
          <>
            {picked[0]?.label !== '이번 일정' ? (
              <div className="card flat row between">
                <span className="muted" style={{ fontSize: 14 }}>예정된 일정이 없어요</span>
                {isAdmin ? <Link className="btn sm primary" to={`/c/${slug}/admin/sessions/new`}>새 일정</Link> : null}
              </div>
            ) : null}
            {picked.map(({ s, label }) => (
              <SessionCard key={s.sessionId} s={s} slug={slug} label={label} />
            ))}
          </>
        )}

        <section className="section" aria-labelledby="wire-title">
          <div className="section-head">
            <h2 id="wire-title" className="big">The Wire</h2>
            <span className="small muted">{picked.length > 1 ? '이번·지난 일정 기사' : '최근 일정 기사'}</span>
          </div>
          {articles.error ? (
            <ErrorBox error={articles.error} onRetry={articles.reload} />
          ) : articlesLoading ? (
            <Loading />
          ) : shown.length === 0 ? (
            <Empty>아직 게시된 기사가 없어요.<br />[일정확정] 때 프리뷰, [일정마감] 때 마감 기사가 나옵니다.</Empty>
          ) : (
            shown.map((a, i) => <ArticleCard key={a.articleId} a={a} slug={slug} lead={i === 0} />)
          )}
          <Link to={`/c/${slug}/records?tab=articles`} className="link-btn" style={{ alignSelf: 'flex-end', display: 'inline-flex', alignItems: 'center' }}>
            기사 더보기 <Icon name="chevron" size={16} />
          </Link>
        </section>
      </main>
    </>
  )
}

type WireSession = { s: SessionListItem; label: '이번 일정' | '지난 일정' | '그 전 일정' }

/** 와이어에 보일 일정: 예정·진행 중 1개(가장 가까운 것) + 바로 직전 일정 1개. 예정이 없으면 최근 일정 2개 */
function pickWireSessions(list: SessionListItem[]): WireSession[] {
  const valid = list.filter((s) => s.status !== 'CANCELLED')
  const recent = [...valid].sort((a, b) => b.sessionDate.localeCompare(a.sessionDate) || b.sessionId - a.sessionId)
  const current = pickCurrentSession(valid)
  if (!current) {
    return recent.slice(0, 2).map((s, i) => ({ s, label: i === 0 ? '지난 일정' : '그 전 일정' }))
  }
  const prev = recent.find((s) => s.sessionDate.localeCompare(current.sessionDate) < 0
    || (s.sessionDate === current.sessionDate && s.sessionId < current.sessionId))
  return [{ s: current, label: '이번 일정' }, ...(prev ? [{ s: prev, label: '지난 일정' as const }] : [])]
}

function pickCurrentSession(list: SessionListItem[]): SessionListItem | null {
  const open = list
    .filter((s) => ['OPEN', 'CONFIRMED', 'IN_PROGRESS'].includes(s.status))
    .sort((a, b) => a.sessionDate.localeCompare(b.sessionDate) || a.sessionId - b.sessionId)
  return open[0] ?? null
}

/** 고른 일정들의 게시 기사(최신 게시 순). 일정마다 프리뷰·마감 기사가 1건씩이라 일정당 10건이면 충분 */
async function loadWireArticles(api: Api, sessionIds: number[]): Promise<Article[]> {
  const lists = await Promise.all(sessionIds.map((sessionId) => api.articles({ sessionId, limit: 10 })))
  return lists.flat().sort((a, b) => (b.publishedAt ?? '').localeCompare(a.publishedAt ?? '') || b.articleId - a.articleId)
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

function SessionCard({ s, slug, label }: { s: SessionListItem; slug: string; label: WireSession['label'] }) {
  const [, m, d] = s.sessionDate.split('-').map(Number)
  const past = label !== '이번 일정'
  return (
    <Link to={`/c/${slug}/sessions/${s.sessionId}`} className="card link row" style={{ gap: 14 }}>
      <div style={{ width: 52, height: 56, borderRadius: 12, background: past ? 'var(--soft)' : 'var(--green-soft)', color: past ? 'var(--ink-3)' : 'var(--green)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600 }}>{m}월</span>
        <span style={{ fontFamily: 'var(--display)', fontSize: 24, lineHeight: 1 }}>{d}</span>
      </div>
      <div className="stack" style={{ flex: 1, gap: 3, minWidth: 0 }}>
        <span className="eyebrow" style={past ? { color: 'var(--muted)' } : undefined}>{label}</span>
        <div className="row">
          <b style={{ fontSize: 15 }}>{s.title}</b>
          <span className={`status-badge ${s.status === 'IN_PROGRESS' ? 'green' : ''}`}>{SESSION_STATUS_LABEL[s.status]}</span>
        </div>
        <span className="small muted">
          {s.location ? `${s.location} · ` : ''}참석 {s.attendeeCount}명{s.guestCount ? ` · 게스트 ${s.guestCount}명` : ''}
          {s.teamCount ? ` · ${s.teamCount}팀` : ''}
        </span>
        {s.status === 'CLOSED' ? <SessionResult sessionId={s.sessionId} /> : null}
      </div>
      <Icon name="chevron" />
    </Link>
  )
}

/** 마감된 일정의 결과 한 줄: 팀별 승·무·패 + 득점 1위 (일정 요약 API) */
function SessionResult({ sessionId }: { sessionId: number }) {
  const { api } = useClub()
  const sum = useAsync(() => api.sessionSummary(sessionId), [api, sessionId])
  if (!sum.data) return null
  const teams = [...sum.data.teamRecords].sort((a, b) => a.teamCode.localeCompare(b.teamCode))
  const best = sum.data.topScorers[0]?.count ?? 0
  const scorers = sum.data.topScorers.filter((p) => p.count === best).map((p) => p.name)
  return (
    <span className="small" style={{ color: 'var(--ink-3)', lineHeight: 1.5 }}>
      {teams.map((t) => `${t.teamCode} ${t.wins}승 ${t.draws}무 ${t.losses}패`).join(' · ')}
      {best > 0 ? <><br />득점 1위 {scorers.join('·')} {best}골</> : null}
    </span>
  )
}
