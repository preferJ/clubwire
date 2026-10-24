// S03 일정 상세 (+ 관리자 운영 버튼)

import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { SessionDetail, SessionMatch } from '../api/types'
import { Icon } from '../components/Icon'
import { NextMatchSheet } from '../components/NextMatchSheet'
import { AdminButton, ErrorBox, Loading, TopBar } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDate, teamColor } from '../lib/format'
import { useAction, useAsync } from '../lib/hooks'

const STEPS: { key: string; label: string }[] = [
  { key: 'OPEN', label: '모집' },
  { key: 'CONFIRMED', label: '일정확정' },
  { key: 'IN_PROGRESS', label: '진행 중' },
  { key: 'CLOSED', label: '마감' },
]

export function SessionPage() {
  const { sessionId } = useParams()
  const id = Number(sessionId)
  const { api, slug, isAdmin } = useClub()
  const s = useAsync(() => api.session(id), [api, id, isAdmin])
  useClubEvent((m) => {
    if ((m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED' || m.type === 'MATCH_UPDATED') && m.sessionId === id) s.reload()
  })

  const d = s.data
  return (
    <>
      <TopBar
        back={`/c/${slug}/sessions`}
        title={d ? `${fmtDate(d.sessionDate)} ${d.title}` : '일정'}
        sub={d ? `${d.location ? `${d.location} · ` : ''}참석 ${d.attendees.length}명${d.guests.length ? ` · 게스트 ${d.guests.length}명` : ''}` : undefined}
        right={<AdminButton />}
      />
      {s.error ? (
        <ErrorBox error={s.error} onRetry={s.reload} />
      ) : !d ? (
        <div className="page"><Loading /></div>
      ) : (
        <>
          <main className="page">
            {d.status === 'CANCELLED' ? (
              <div className="notice gray">취소된 일정입니다.</div>
            ) : (
              <ol className="stepper-line" aria-label="일정 진행 단계">
                {STEPS.map((st, i) => {
                  const cur = STEPS.findIndex((x) => x.key === d.status)
                  return (
                    <li key={st.key} className={i < cur ? 'done' : i === cur ? 'current' : ''} aria-current={i === cur ? 'step' : undefined}>
                      {st.label}
                    </li>
                  )
                })}
              </ol>
            )}

            {d.balanceLabel ? (
              <div className="notice green" style={{ fontSize: 14, fontWeight: 600, alignItems: 'center' }}>
                <Icon name="scale" />{d.balanceLabel}
              </div>
            ) : null}

            {d.teams.length ? <Teams d={d} /> : <Attendees d={d} />}

            {d.matches.length ? (
              <section className="section">
                <h2 style={{ fontSize: 15, fontWeight: 700 }}>경기</h2>
                {d.matches.map((m) => <MatchRow key={m.matchId} m={m} slug={slug} />)}
              </section>
            ) : null}
          </main>
          {isAdmin ? <AdminActions d={d} reload={s.reload} /> : null}
        </>
      )}
    </>
  )
}

function Attendees({ d }: { d: SessionDetail }) {
  return (
    <section className="section">
      <h2 style={{ fontSize: 15, fontWeight: 700 }}>참석 예정 {d.attendees.length + d.guests.length}명</h2>
      <div className="row wrap" style={{ gap: 6 }}>
        {d.attendees.map((a) => <span key={a.memberId} className="name-chip" style={{ background: 'var(--card)' }}>{a.name}</span>)}
        {d.guests.map((g) => <span key={g.guestId} className="name-chip guest">{g.name}</span>)}
      </div>
      {d.status === 'OPEN' ? <p className="small muted">팀은 운영진이 [일정확정]하면 공개돼요.</p> : null}
    </section>
  )
}

function Teams({ d }: { d: SessionDetail }) {
  const cols = Math.min(d.teams.length, 3)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 8 }}>
      {d.teams.map((t) => (
        <section key={t.sessionTeamId} className="team-card" aria-label={`TEAM ${t.teamCode}`}>
          <header style={{ background: teamColor(t.teamCode) }}>
            <strong>TEAM {t.teamCode}</strong>
            <span className="small">{t.headcount}명</span>
          </header>
          <ul>
            {t.members.map((m) => <li key={m.memberId}>{m.name}</li>)}
            {t.guests.map((g) => <li key={g.guestId} className="muted">{g.name}</li>)}
          </ul>
        </section>
      ))}
    </div>
  )
}

function MatchRow({ m, slug }: { m: SessionMatch; slug: string }) {
  const live = m.status === 'RUNNING' || m.status === 'PAUSED'
  const right =
    m.status === 'READY' ? <span className="status-badge gold">대기</span>
      : live ? <span className="live-badge">{m.status === 'PAUSED' ? '정지' : 'LIVE'}</span>
        : m.status === 'CANCELLED' ? <span className="small muted">취소</span>
          : m.finalized ? <span className="small" style={{ color: 'var(--green)', fontWeight: 600 }}>확정</span>
            : <span className="small" style={{ color: 'var(--warn-ink)', fontWeight: 600 }}>검토 중</span>
  return (
    <Link to={`/c/${slug}/matches/${m.matchId}`} className={`list-row ${live ? 'dark' : ''}`}
      style={m.status === 'CANCELLED' ? { opacity: 0.6 } : undefined}>
      <span className={live ? '' : 'muted'} style={{ width: 44, color: live ? 'var(--night-muted)' : undefined }}>{m.gameNo}경기</span>
      <span style={{ flex: 1, textAlign: 'center' }}>
        TEAM {m.teamA.teamCode} <b className="mono" style={{ padding: '0 6px' }}>{m.status === 'READY' ? 'vs' : `${m.teamA.score} : ${m.teamB.score}`}</b> TEAM {m.teamB.teamCode}
      </span>
      {right}
    </Link>
  )
}

function AdminActions({ d, reload }: { d: SessionDetail; reload: () => void }) {
  const { api, slug } = useClub()
  const nav = useNavigate()
  const { busy, run } = useAction()
  const [nextOpen, setNextOpen] = useState(false)
  const active = d.matches.find((m) => ['READY', 'RUNNING', 'PAUSED'].includes(m.status))

  if (d.status === 'CLOSED' || d.status === 'CANCELLED') {
    return (
      <div className="bar-actions">
        <p className="small muted center">{d.status === 'CLOSED' ? '마감된 일정은 고칠 수 없어요.' : '취소된 일정입니다.'}</p>
      </div>
    )
  }

  if (d.status === 'OPEN') {
    const cancel = async () => {
      if (!window.confirm('이 일정을 취소할까요?')) return
      if (await run(() => api.cancelSession(d.sessionId), '일정을 취소했어요')) reload()
    }
    return (
      <div className="bar-actions">
        <div className="grid2">
          <Link className="btn" to={`/c/${slug}/admin/sessions/${d.sessionId}/attendance`}>참석자 수정</Link>
          <Link className="btn primary" to={`/c/${slug}/admin/sessions/${d.sessionId}/teams`}>팀 편성</Link>
        </div>
        <button type="button" className="link-btn" style={{ color: 'var(--warn-ink)' }} disabled={busy} onClick={cancel}>일정 취소</button>
      </div>
    )
  }

  return (
    <div className="bar-actions">
      {active ? (
        <button type="button" className="btn dark lg block" onClick={() => nav(`/c/${slug}/matches/${active.matchId}`)}>
          {active.gameNo}경기 {active.status === 'READY' ? '시작하러 가기' : '진행 화면으로'}
        </button>
      ) : (
        <button type="button" className="btn primary lg block" onClick={() => setNextOpen(true)}>
          <Icon name="plus" size={18} stroke={2} />다음 경기 만들기
        </button>
      )}
      <Link className="btn block" to={`/c/${slug}/admin/articles?sessionId=${d.sessionId}&articleType=PRE_MATCH`}>
        프리뷰 기사 올리기
      </Link>
      <div className="grid2">
        <Link className="btn sm" to={`/c/${slug}/admin/sessions/${d.sessionId}/teams`}>팀 수동 변경</Link>
        <Link className="btn sm" to={`/c/${slug}/admin/sessions/${d.sessionId}/close`}>일정마감</Link>
      </div>
      <NextMatchSheet sessionId={d.sessionId} open={nextOpen} onClose={() => setNextOpen(false)} />
    </div>
  )
}
