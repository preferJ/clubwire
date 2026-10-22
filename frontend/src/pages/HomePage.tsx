// S01 홈 · 와이어(E 시안: 매니저 게임형)
// 클럽 바(엠블럼 · 날짜 · 다음 일정) → 요약 줄 → LIVE → NEXT FIXTURE → LAST MATCHDAY → INBOX(이번·지난 일정 기사)

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Api } from '../api/endpoints'
import type { Article, LiveMatch, SessionListItem, SessionSummary } from '../api/types'
import { Icon } from '../components/Icon'
import { ClubBar, ErrorBox, Loading, TeamBadge } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { dday, fmtClock, fmtDate, fmtShortDate, fmtToday, SESSION_STATUS_LABEL } from '../lib/format'
import { useAsync, useMatchClock } from '../lib/hooks'
import { readArticleIds } from '../lib/readStore'

/** 소식함에 바로 보이는 기사 수. 나머지는 [소식 전체 보기] → 기록 탭 */
const WIRE_ARTICLES = 3

export function HomePage() {
  const { api, club, slug, isAdmin } = useClub()
  const live = useAsync(() => api.live(), [api])
  const sessions = useAsync(() => api.sessions(10), [api])
  const summary = useAsync(() => api.clubSummary(), [api])
  const picked = pickWireSessions(sessions.data ?? [])
  const pickedIds = picked.map((p) => p.s.sessionId)
  const articles = useAsync(() => loadWireArticles(api, pickedIds), [api, pickedIds.join(',')])

  useClubEvent((m) => {
    if (m.type === 'MATCH_UPDATED') live.reload()
    if (m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED') {
      sessions.reload()
      summary.reload()
    }
    if (m.type === 'ARTICLE_UPDATED') {
      articles.reload()
      summary.reload()
    }
  })

  const next = picked[0]?.label === '이번 일정' ? picked[0].s : null
  const last = picked.find((p) => p.label !== '이번 일정' && p.s.status === 'CLOSED')?.s ?? null
  const sessionsLoading = sessions.loading && !sessions.data
  // 일정 목록을 받기 전, 또는 고른 일정이 바뀌어 다시 불러오는 중이면 로딩 표시
  const articlesLoading = sessionsLoading || (articles.loading && !articles.data?.length)

  return (
    <>
      <ClubBar title={club?.clubName ?? ' '} sub="THE WIRE">
        <div className="action-row">
          <span className="date">{fmtToday()}</span>
          {next ? (
            <Link to={`/c/${slug}/sessions/${next.sessionId}`} className="go-btn">
              다음 일정 · {dday(next.sessionDate)} <Icon name="play" size={14} />
            </Link>
          ) : isAdmin ? (
            <Link to={`/c/${slug}/admin/sessions/new`} className="go-btn">새 일정 <Icon name="play" size={14} /></Link>
          ) : null}
        </div>
      </ClubBar>

      <div className="stat-ribbon" aria-label="클럽 요약">
        <div><b>{summary.data?.activeMembers ?? '–'}</b><span>멤버</span></div>
        <div><b>{summary.data?.sessions ?? '–'}</b><span>올해 일정</span></div>
        <div><b>{summary.data?.articles ?? '–'}</b><span>올해 기사</span></div>
      </div>

      <main className="page" style={{ gap: 12, padding: '12px 12px 24px' }}>
        {(live.data ?? []).map((m) => (
          <LiveBanner key={m.matchId} m={m} slug={slug} />
        ))}

        {sessionsLoading ? <Loading rows={2} /> : (
          <>
            <NextFixture s={next} slug={slug} members={summary.data?.activeMembers} isAdmin={isAdmin} />
            {last ? <LastMatchday s={last} slug={slug} /> : null}
          </>
        )}

        <Inbox slug={slug} loading={articlesLoading} error={articles.error} onRetry={articles.reload}
          items={(articles.data ?? []).slice(0, WIRE_ARTICLES)} />
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

function PanelHead({ en, ko, right }: { en: string; ko: string; right?: ReactNode }) {
  return (
    <div className="panel-head">
      <span className="label"><span className="en">{en}</span><span className="ko">{ko}</span></span>
      {right}
    </div>
  )
}

/** NEXT FIXTURE: 이번 일정의 상태 · 팀 편성 · 참석 인원 */
function NextFixture({ s, slug, members, isAdmin }: { s: SessionListItem | null; slug: string; members?: number; isAdmin: boolean }) {
  if (!s) {
    return (
      <section className="panel" aria-label="다음 일정">
        <PanelHead en="NEXT FIXTURE" ko="다음 일정" />
        <div className="panel-body row between" style={{ flexDirection: 'row' }}>
          <span className="muted" style={{ fontSize: 14 }}>예정된 일정이 없어요</span>
          {isAdmin ? <Link className="btn sm primary" to={`/c/${slug}/admin/sessions/new`}>새 일정</Link> : null}
        </div>
      </section>
    )
  }
  const total = members ?? 0
  const pct = total ? Math.min(100, Math.round((s.attendeeCount / total) * 100)) : 0
  return (
    <section className="panel" aria-label="다음 일정">
      <PanelHead en="NEXT FIXTURE" ko="다음 일정" right={<span className="badge">{dday(s.sessionDate)}</span>} />
      <Link to={`/c/${slug}/sessions/${s.sessionId}`} className="panel-body">
        <span className="row between" style={{ alignItems: 'baseline' }}>
          <b style={{ fontSize: 16 }}>{s.title}</b>
          <span style={{ fontSize: 14, fontWeight: 700 }}>{fmtDate(s.sessionDate)}</span>
        </span>
        <span className="kv">
          <span><span>상태</span><span>{SESSION_STATUS_LABEL[s.status]}</span></span>
          <span><span>팀 편성</span><span style={s.teamCount ? undefined : { color: 'var(--draw)' }}>{s.teamCount ? `${s.teamCount}팀 확정` : '미확정'}</span></span>
          {s.location ? <span style={{ gridColumn: '1 / -1' }}><span>장소</span><span>{s.location}</span></span> : null}
        </span>
        <span className="stack" style={{ gap: 6 }}>
          <span className="row between" style={{ fontSize: 13 }}>
            <span className="muted">참석</span>
            <span><b className="num" style={{ fontSize: 17 }}>{s.attendeeCount}</b>{total ? ` / ${total}` : '명'}{s.guestCount ? ` · 게스트 ${s.guestCount}` : ''}</span>
          </span>
          {total ? <span className="meter" aria-hidden="true"><span style={{ width: `${pct}%` }} /></span> : null}
        </span>
      </Link>
    </section>
  )
}

type FormMark = 'W' | 'D' | 'L'
const FORM_LABEL: Record<FormMark, string> = { W: '승', D: '무', L: '패' }

/** 팀별 하루 성적: 경기 · 승 · 무 · 패 · 득실 · 경기 순서대로의 흐름 */
function dayTable(sum: SessionSummary) {
  const finished = sum.matches.filter((m) => m.status === 'FINISHED').sort((a, b) => a.gameNo - b.gameNo)
  return [...sum.teamRecords].sort((a, b) => a.teamCode.localeCompare(b.teamCode)).map((t) => {
    let gf = 0
    let ga = 0
    const form: FormMark[] = []
    for (const m of finished) {
      const mine = m.teamA === t.teamCode ? m.scoreA : m.teamB === t.teamCode ? m.scoreB : null
      if (mine === null) continue
      const theirs = m.teamA === t.teamCode ? m.scoreB : m.scoreA
      gf += mine
      ga += theirs
      form.push(mine > theirs ? 'W' : mine === theirs ? 'D' : 'L')
    }
    return { ...t, games: form.length, gd: gf - ga, form }
  })
}

/** 1위(동점이면 '홍길동 외 1') */
function leader(list: { name: string; count: number }[]): { name: string; count: number } | null {
  if (!list.length) return null
  const ties = list.filter((p) => p.count === list[0].count).length
  return { name: ties > 1 ? `${list[0].name} 외 ${ties - 1}` : list[0].name, count: list[0].count }
}

/** LAST MATCHDAY: 지난 일정의 팀 성적 · 흐름 · 득점/도움 1위 · 총 골 */
function LastMatchday({ s, slug }: { s: SessionListItem; slug: string }) {
  const { api } = useClub()
  const sum = useAsync(() => api.sessionSummary(s.sessionId), [api, s.sessionId])
  const rows = sum.data ? dayTable(sum.data) : []
  const top = sum.data ? leader(sum.data.topScorers) : null
  const ast = sum.data ? leader(sum.data.topAssists) : null
  return (
    <section className="panel" aria-label="지난 일정 결과">
      <PanelHead en="LAST MATCHDAY" ko={`${fmtShortDate(s.sessionDate)} 결과`}
        right={<span className="num muted" style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em' }}>FINAL{sum.data ? ` · ${sum.data.finishedCount}경기` : ''}</span>} />
      <Link to={`/c/${slug}/sessions/${s.sessionId}`} className="panel-body" style={{ gap: 0, paddingTop: 4 }}>
        {sum.error ? <span className="muted small">결과를 불러오지 못했어요</span> : !sum.data ? <Loading rows={1} /> : (
          <>
            <span className="mday" role="table" aria-label="팀별 성적">
              <span className="mday-row head" role="row">
                <span role="columnheader">팀</span><span role="columnheader">경</span><span role="columnheader">승</span>
                <span role="columnheader">무</span><span role="columnheader">패</span><span role="columnheader">득실</span>
                <span role="columnheader">흐름</span>
              </span>
              {rows.map((r) => (
                <span key={r.sessionTeamId} className="mday-row" role="row">
                  <span className="mday-team" role="cell"><TeamBadge code={r.teamCode} size={20} />{r.teamCode}</span>
                  <span role="cell">{r.games}</span><span role="cell">{r.wins}</span><span role="cell">{r.draws}</span>
                  <span role="cell">{r.losses}</span>
                  <span role="cell" className={r.gd > 0 ? 'gd-up' : r.gd < 0 ? 'gd-down' : ''}>{r.gd > 0 ? `+${r.gd}` : r.gd}</span>
                  <span className="form" role="cell" aria-label={`흐름 ${r.form.map((f) => FORM_LABEL[f]).join(' ')}`}>
                    {r.form.slice(-6).map((f, i) => <span key={i} className={`form-sq ${f}`} aria-hidden="true">{FORM_LABEL[f]}</span>)}
                  </span>
                </span>
              ))}
            </span>
            <span className="leaders" style={{ paddingTop: 10 }}>
              <span>
                <span className="k">득점 1위</span>
                <span className="v"><b>{top?.name ?? '–'}</b><span className="num">{top?.count ?? 0}</span></span>
              </span>
              <span>
                <span className="k">도움 1위</span>
                <span className="v"><b>{ast?.name ?? '–'}</b><span className="num">{ast?.count ?? 0}</span></span>
              </span>
              <span>
                <span className="k">총 골</span>
                <span className="v"><b>{sum.data.finishedCount}경기</b><span className="num">{sum.data.totalGoals}</span></span>
              </span>
            </span>
          </>
        )}
      </Link>
    </section>
  )
}

/** INBOX: 이번·지난 일정 기사(최신 3건). 안 읽은 기사에 점, 첫 기사는 요약까지 */
function Inbox({ slug, items, loading, error, onRetry }: {
  slug: string
  items: Article[]
  loading: boolean
  error: unknown
  onRetry: () => void
}) {
  const read = readArticleIds(slug)
  const unread = items.filter((a) => !read.has(a.articleId)).length
  return (
    <section className="panel" aria-label="소식함">
      <PanelHead en="INBOX" ko="소식함 · The Wire" right={unread ? <span className="badge" style={{ fontFamily: 'var(--body)', fontSize: 11 }}>새 소식 {unread}</span> : null} />
      {error ? <ErrorBox error={error} onRetry={onRetry} /> : loading ? <div className="panel-body"><Loading rows={2} /></div> : items.length === 0 ? (
        <p className="panel-body muted" style={{ fontSize: 14 }}>아직 게시된 기사가 없어요. [일정확정] 때 프리뷰, [일정마감] 때 마감 기사가 들어와요.</p>
      ) : items.map((a, i) => {
        const isRead = read.has(a.articleId)
        const topic = a.tags.find((t) => t !== '마감' && t !== '프리뷰')
        return (
          <Link key={a.articleId} to={`/c/${slug}/articles/${a.articleId}`} className={`inbox-row${i === 0 ? ' open' : ''}${isRead ? ' read' : ''}`}>
            {isRead ? <span className="dot" aria-hidden="true" /> : <span className="dot on" role="img" aria-label="새 소식" />}
            <span className="stack" style={{ flex: 1, gap: 4, minWidth: 0 }}>
              <span className="meta">
                <span>The Wire · {a.articleType === 'PRE_MATCH' ? '프리뷰' : '마감 기사'}{topic ? ` · ${topic}` : ''}</span>
                <span>{fmtShortDate(a.sessionDate)}</span>
              </span>
              <span className="subject">{a.title}</span>
              {i === 0 && a.summary ? <span className="preview">{a.summary}</span> : null}
            </span>
          </Link>
        )
      })}
      <Link to={`/c/${slug}/records?tab=articles`} className="panel-foot">
        소식 전체 보기 <span style={{ color: 'var(--accent-ink)', display: 'inline-flex' }}><Icon name="play" size={12} /></span>
      </Link>
    </section>
  )
}

function LiveBanner({ m, slug }: { m: LiveMatch; slug: string }) {
  const clock = useMatchClock(m)
  const label = m.status === 'READY' ? '곧 시작' : m.status === 'PAUSED' ? '일시정지' : fmtClock(clock.remaining)
  return (
    <Link to={`/c/${slug}/matches/${m.matchId}`} className="panel" style={{ display: 'block', background: 'var(--night)', borderColor: 'var(--accent)', color: '#fff', padding: '12px 14px' }}>
      <div className="row between">
        <div className="row">
          {m.status === 'READY' ? <span className="status-badge gold">대기</span> : <span className="live-badge">LIVE</span>}
          <span className="small" style={{ color: 'var(--night-muted)' }}>{fmtDate(m.sessionDate, false)} · {m.gameNo}경기</span>
        </div>
        <span className="mono" style={{ fontWeight: 600 }}>{label}</span>
      </div>
      <div className="row between" style={{ marginTop: 10 }}>
        <div className="row"><TeamBadge code={m.teamA.teamCode} size={28} onDark /><b>TEAM {m.teamA.teamCode}</b></div>
        <span className="num" style={{ fontSize: 36, fontWeight: 800 }}>{m.teamA.score} : {m.teamB.score}</span>
        <div className="row"><b>TEAM {m.teamB.teamCode}</b><TeamBadge code={m.teamB.teamCode} size={28} onDark /></div>
      </div>
    </Link>
  )
}
