import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import { Loading, TeamBadge } from './ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDate, teamLabel, teamMark } from '../lib/format'
import { useAsync } from '../lib/hooks'
import '../styles/home-fixture.css'

/** 확정된 다음 일정만 표시. 부모에서 일정별 key를 주어 이전 명단이 남지 않게 한다. */
export function HomeFixture({ sessionId }: { sessionId: number }) {
  const { api, slug } = useClub()
  const session = useAsync(() => api.session(sessionId), [api, sessionId])
  useClubEvent((m) => {
    if ((m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED') && m.sessionId === sessionId) {
      session.reload()
    }
  })

  const d = session.data
  return (
    <section className="panel home-fixture" aria-label="이번 일정 팀 편성">
      <header className="panel-head home-fixture-head">
        <span className="label"><span className="en">NEXT FIXTURE</span><span className="ko">팀 편성</span></span>
        <span className="tag green"><Icon name="check" size={12} />편성 확정</span>
      </header>
      {session.error ? (
        <div className="home-fixture-feedback" role="status">
          <span>팀 편성을 불러오지 못했어요.</span>
          <button type="button" className="btn sm" onClick={session.reload}>다시 시도</button>
        </div>
      ) : !d ? (
        <div className="home-fixture-body"><Loading rows={2} /></div>
      ) : d.deletedAt || !['CONFIRMED', 'IN_PROGRESS'].includes(d.status) ? (
        <p className="home-fixture-feedback">일정 상태가 변경되었습니다.</p>
      ) : (
        <Link to={`/c/${slug}/sessions/${sessionId}`} className="home-fixture-body">
          <div className="home-fixture-meta">
            <strong>{fmtDate(d.sessionDate)}</strong>
            <span>{d.title}</span>
            {d.status === 'IN_PROGRESS' ? <span className="tag">진행 중</span> : null}
          </div>
          {d.location ? <p className="home-fixture-location">장소 · {d.location}</p> : null}
          <div className="home-fixture-teams" style={{ gridTemplateColumns: `repeat(${Math.min(d.teams.length || 1, 3)}, minmax(0, 1fr))` }}>
            {d.teams.map((t) => (
              <section className="home-fixture-team" key={t.sessionTeamId} aria-label={teamLabel(t)}>
                <header>
                  <TeamBadge code={teamMark(t)} size={20} opponent={t.opponent} />
                  <b>{teamLabel(t)}</b>
                  <span>{t.opponent ? '상대' : `${t.headcount}명`}</span>
                </header>
                {t.opponent ? <p className="home-fixture-opponent">원정 상대팀</p> : (
                  <ul>
                    {t.members.map((m) => <li key={`m-${m.memberId}`}>{m.name}</li>)}
                    {t.guests.map((g) => <li key={`g-${g.guestId}`} className="muted">{g.name}<span className="sr-only"> (게스트)</span></li>)}
                  </ul>
                )}
              </section>
            ))}
          </div>
          {!d.teams.length ? <p className="small muted">등록된 팀 편성이 없어요.</p> : null}
          {!d.away && d.balanceLabel ? (
            <p className="home-fixture-balance"><Icon name="scale" size={14} />{d.balanceLabel}</p>
          ) : null}
          <span className="home-fixture-more">팀 편성 자세히 보기 <Icon name="chevron" size={14} /></span>
        </Link>
      )}
    </section>
  )
}
