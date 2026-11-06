// 기록 탭 '원정' → 상대 팀 하나: 그 팀과의 원정 일정 · 경기 점수(최근 순) + 그 팀 상대 우리 선수 골 · 도움 기록. 내부 기록과 따로 집계

import { Link, useParams } from 'react-router-dom'
import { AwayMemberTable } from '../components/AwayMemberTable'
import { Empty, ErrorBox, Loading, TeamBadge, TopBar } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDate, RESULT_LABEL } from '../lib/format'
import { useAsync } from '../lib/hooks'

export function AwayOpponentPage() {
  const { api, slug, club } = useClub()
  const id = Number(useParams().opponentId)
  const detail = useAsync(() => api.awayOpponent(id), [api, id])
  useClubEvent((m) => {
    if (m.type === 'SESSION_UPDATED' || m.type === 'OPPONENTS_UPDATED') detail.reload()
  })
  const back = `/c/${slug}/records?tab=away`
  if (detail.error) return <><TopBar title="원정 상대" back={back} /><main className="page"><ErrorBox error={detail.error} onRetry={detail.reload} /></main></>
  if (!detail.data) return <><TopBar title="원정 상대" back={back} /><main className="page"><Loading /></main></>
  const { opponent, summary, sessions, members } = detail.data
  const ours = club?.clubName ?? '우리 팀'

  return (
    <>
      <TopBar title={`vs ${opponent.name}`} sub="원정 맞대결 기록" back={back} />
      <main className="page">
        <section className="card stack" style={{ gap: 6 }}>
          <div className="row between">
            <h2 className="row" style={{ fontSize: 15, fontWeight: 700, gap: 8, minWidth: 0 }}>
              <TeamBadge code={opponent.name.trim()[0]} size={26} opponent />
              <span style={{ overflowWrap: 'anywhere' }}>{opponent.name}</span>
            </h2>
            <span className="row" style={{ gap: 6 }}>
              {!opponent.active ? <span className="tag dark">숨긴 팀</span> : null}
              <span className="tag away">원정</span>
            </span>
          </div>
          {summary.matches === 0 ? (
            <span className="small muted">아직 확정된 맞대결이 없어요.</span>
          ) : (
            <>
              <b className="num" style={{ fontSize: 22 }}>{summary.wins}승 {summary.draws}무 {summary.losses}패</b>
              <span className="small muted">{summary.sessions}번의 원정 · {summary.matches}경기 · {summary.goalsFor}득점 {summary.goalsAgainst}실점</span>
            </>
          )}
        </section>

        {summary.matches === 0 ? (
          <Empty>이 팀과의 원정 일정을 마치고 경기를 확정하면 여기에 기록이 쌓여요.</Empty>
        ) : (
          <>
            <section className="section">
              <h2 style={{ fontSize: 15, fontWeight: 700 }}>맞대결 일정</h2>
              {sessions.map((s) => (
                <div key={s.sessionId} className="card flat away-session">
                  <Link to={`/c/${slug}/sessions/${s.sessionId}`} className="away-session-head">
                    <span className="stack" style={{ gap: 0, minWidth: 0 }}>
                      <b>{fmtDate(s.sessionDate)}</b>
                      <span className="small muted" style={{ overflowWrap: 'anywhere' }}>{[s.title, s.location].filter(Boolean).join(' · ')}</span>
                    </span>
                    <span className="small" style={{ whiteSpace: 'nowrap' }}>
                      <b>{s.wins}승 {s.draws}무 {s.losses}패</b> <span className="muted mono">{s.goalsFor}:{s.goalsAgainst}</span>
                    </span>
                  </Link>
                  {s.matches.map((g) => (
                    <Link key={g.matchId} to={`/c/${slug}/matches/${g.matchId}`} className="away-game"
                      aria-label={`${g.gameNo}경기 ${ours} ${g.scoreFor} 대 ${g.scoreAgainst} ${opponent.name} ${RESULT_LABEL[g.result]}`}>
                      <span className="small muted">{g.gameNo}경기</span>
                      <span className="away-score">{g.scoreFor} : {g.scoreAgainst}</span>
                      <b className={`form-sq ${g.result}`}>{RESULT_LABEL[g.result]}</b>
                    </Link>
                  ))}
                </div>
              ))}
            </section>

            <section className="section">
              <div className="section-head">
                <h2 style={{ fontSize: 15, fontWeight: 700 }}>이 팀 상대 선수 기록</h2>
                <span className="small muted">{opponent.name}전만</span>
              </div>
              {members.length ? <AwayMemberTable slug={slug} members={members} /> : <p className="small muted">출전 기록이 없어요.</p>}
            </section>
          </>
        )}
      </main>
    </>
  )
}
