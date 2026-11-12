import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import { SessionNotice } from './SessionNotice'
import { Loading } from './ui'
import { useClub, useClubEvent } from '../lib/club'
import { dday, fmtDate, OPPONENT_COLOR, teamColor, teamLabel } from '../lib/format'
import { useAsync } from '../lib/hooks'
import '../styles/home-fixture.css'

/**
 * 메인 화면의 확정 팀 편성 카드(2026-11 B 시안): 초록 '팀 편성 완료' 띠 + 팀 색 머리 카드(세로 명단) + 일정 공지 + 밸런스.
 * 확정된 다음 일정만 표시. 부모에서 일정별 key를 주어 이전 명단이 남지 않게 한다.
 */
export function HomeFixture({ sessionId }: { sessionId: number }) {
  const { api, slug } = useClub()
  const session = useAsync(() => api.session(sessionId), [api, sessionId])
  useClubEvent((m) => {
    if ((m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED') && m.sessionId === sessionId) {
      session.reload()
    }
    if (m.type === 'RECONNECTED') session.reload()  // 화면을 켜 둔 채 연결이 끊겼다 다시 붙으면 최신 편성으로
  })

  const d = session.data
  return (
    <section className="panel home-fixture" aria-label="이번 일정 팀 편성">
      <header className="home-fixture-done">
        <span className="home-fixture-done-label"><Icon name="check" size={16} stroke={2.4} />팀 편성 완료</span>
        {d ? (
          <span className="home-fixture-done-side">
            {d.status === 'IN_PROGRESS' ? <span className="home-fixture-live">진행 중</span> : null}
            <span className="home-fixture-dday">{dday(d.sessionDate)}</span>
          </span>
        ) : null}
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
            {d.location ? <span>· {d.location}</span> : null}
          </div>
          <div className="home-fixture-teams" style={{ gridTemplateColumns: `repeat(${Math.min(d.teams.length || 1, 3)}, minmax(0, 1fr))` }}>
            {d.teams.map((t) => (
              <section className="home-fixture-team" key={t.sessionTeamId} aria-label={teamLabel(t)}>
                <header style={{ background: t.opponent ? OPPONENT_COLOR : teamColor(t.teamCode) }}>
                  <b>{teamLabel(t)}</b>
                  <span>{t.opponent ? '상대' : `${t.headcount}명`}</span>
                </header>
                {t.opponent ? <p className="home-fixture-opponent">원정 상대팀</p> : (
                  <ul>
                    {t.members.map((m) => <li key={`m-${m.memberId}`}>{m.name}</li>)}
                    {t.guests.map((g) => <li key={`g-${g.guestId}`} className="guest">{g.name}<span className="sr-only"> (게스트)</span></li>)}
                  </ul>
                )}
              </section>
            ))}
          </div>
          {!d.teams.length ? <p className="small muted">등록된 팀 편성이 없어요.</p> : null}
          <SessionNotice text={d.notice} clamp />
          {!d.away && d.balanceLabel ? (
            <p className="home-fixture-balance"><Icon name="scale" size={14} />{d.balanceLabel}</p>
          ) : null}
          <span className="home-fixture-more">팀 편성 자세히 보기 <Icon name="chevron" size={14} /></span>
        </Link>
      )}
    </section>
  )
}
