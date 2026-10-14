// S05 선수 기록 (+ 수상 이력)

import { Link, useParams } from 'react-router-dom'
import type { Award } from '../api/types'
import { ErrorBox, Loading, TopBar } from '../components/ui'
import { useClub } from '../lib/club'
import { fmtShortDate, initials, pct, RESULT_LABEL } from '../lib/format'
import { useAsync } from '../lib/hooks'

export function PlayerPage() {
  const { memberId } = useParams()
  const id = Number(memberId)
  const { api, slug } = useClub()
  const detail = useAsync(() => api.memberDetail(id), [api, id])
  const awards = useAsync(() => api.awards({ memberId: id }), [api, id])

  if (detail.error) return <><TopBar title="선수 기록" back /><ErrorBox error={detail.error} onRetry={detail.reload} /></>
  const d = detail.data
  if (!d) return <><TopBar title="선수 기록" back /><div className="page"><Loading /></div></>
  const s = d.summary
  const streak = leadingWins(d.recentForm.map((r) => r.result))
  const titleCounts = countTitles(awards.data ?? [])

  return (
    <>
      <TopBar title="선수 기록" back />
      <header className="stack" style={{ gap: 12, padding: '16px 16px 18px', background: 'var(--card)', borderBottom: '1px solid var(--line)' }}>
        <div className="row" style={{ gap: 14 }}>
          <span className="avatar" style={{ width: 64, height: 64, fontSize: 18 }}>{initials(s.name)}</span>
          <div className="stack" style={{ gap: 6 }}>
            <h1 className="club-name">{s.name}</h1>
            <div className="tags">
              {titleCounts.map(([name, n]) => <span key={name} className="tag gold">{name} ×{n}</span>)}
              {streak >= 2 ? <span className="tag green">{streak}연승 중</span> : null}
              {!s.active ? <span className="tag">비활성</span> : null}
            </div>
          </div>
        </div>
      </header>

      <main className="page">
        <div className="grid3">
          <Stat label="경기" value={s.games} />
          <Stat label="승률" value={pct(s.winRate)} />
          <Stat label="승 무 패" value={`${s.wins}·${s.draws}·${s.losses}`} />
          <Stat label="골" value={s.goals} />
          <Stat label="도움" value={s.assists} />
          <Stat label="출전 일정" value={s.sessionsAttended} />
        </div>

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>최근 {d.recentForm.length || 5}경기</h2>
          {d.recentForm.length === 0 ? <p className="small muted">확정된 경기가 아직 없어요.</p> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 6 }}>
              {d.recentForm.map((r) => (
                <div key={r.matchId} className={`form-cell ${r.result}`} title={`${r.sessionDate} ${r.gameNo}경기`}>
                  <b>{RESULT_LABEL[r.result]}</b>
                  <span>{[r.goals ? `${r.goals}골` : '', r.assists ? `${r.assists}도움` : ''].filter(Boolean).join(' ') || '-'}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>수상 이력</h2>
          {(awards.data ?? []).length === 0 ? <p className="small muted">아직 받은 타이틀이 없어요.</p> : (
            (awards.data ?? []).slice(0, 10).map((a) => (
              <div key={a.memberTitleId} className="list-row">
                <span className="row"><span className="tag gold">{a.titleName}</span></span>
                <span className="small muted">
                  {fmtShortDate(a.periodStart)}–{fmtShortDate(a.periodEnd)}{a.facts?.value ? ` · ${a.facts.value}${a.facts.metric === 'assists' ? '도움' : a.facts.metric === 'wins' ? '승' : '골'}` : ''}
                </span>
              </div>
            ))
          )}
        </section>

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>자주 같은 팀이 된 선수</h2>
          {d.frequentTeammates.length === 0 ? <p className="small muted">기록이 쌓이면 보여요.</p> : d.frequentTeammates.map((p) => (
            <Link key={p.memberId} to={`/c/${slug}/members/${p.memberId}`} className="list-row">
              <b>{p.name}</b>
              <span className="muted">{p.matches}경기 · 함께 승률 {pct(p.winRate)}</span>
            </Link>
          ))}
        </section>

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>자주 맞붙은 선수</h2>
          {d.frequentOpponents.length === 0 ? <p className="small muted">기록이 쌓이면 보여요.</p> : d.frequentOpponents.map((p) => (
            <Link key={p.memberId} to={`/c/${slug}/members/${p.memberId}`} className="list-row">
              <b>{p.name}</b>
              <span className="muted">{p.matches}경기 · {p.wins}승 {p.draws}무 {p.losses}패</span>
            </Link>
          ))}
        </section>
      </main>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  )
}

function leadingWins(results: string[]): number {
  let n = 0
  for (const r of results) {
    if (r === 'W') n++
    else break
  }
  return n
}

function countTitles(awards: Award[]): [string, number][] {
  const m = new Map<string, number>()
  awards.forEach((a) => m.set(a.titleName, (m.get(a.titleName) ?? 0) + 1))
  return [...m.entries()]
}
