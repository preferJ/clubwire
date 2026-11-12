// S03 일정 상세 (+ 관리자 운영 버튼)

import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { SessionDetail, SessionMatch } from '../api/types'
import { Icon } from '../components/Icon'
import { NextMatchSheet } from '../components/NextMatchSheet'
import { SessionNotice } from '../components/SessionNotice'
import { AdminButton, ErrorBox, Loading, ResultTeam, Sheet, TopBar } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDate, fmtDateTime, OPPONENT_COLOR, teamColor, teamLabel, winSide } from '../lib/format'
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
            {d.deletedAt ? (
              <div className="notice gray">삭제한 일정입니다. {fmtDateTime(d.deletedAt)} · 기록은 보관되며 수정할 수 없어요.</div>
            ) : d.status === 'CANCELLED' ? (
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

            {d.away ? (
              <div className="away-banner" aria-label="원정 경기">
                <span className="tag away">원정</span>
                <b>vs {d.opponentName}</b>
                {d.opponentId ? <Link to={`/c/${slug}/records/away/${d.opponentId}`} style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 600 }}>상대 전적 →</Link> : null}
                <span className="small muted">경기마다 출전 선수를 정하고, 원정 기록은 따로 쌓여요</span>
              </div>
            ) : null}

            {/* 일정별 공지: 팀 밸런스 안내 위. 관리자는 마감 전까지 쓰기 · 수정 · 지우기 */}
            <NoticeBlock d={d} editable={isAdmin && !d.deletedAt && ['OPEN', 'CONFIRMED', 'IN_PROGRESS'].includes(d.status)} onSaved={s.reload} />

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
          {isAdmin ? <AdminActions d={d} /> : null}
        </>
      )}
    </>
  )
}

const NOTICE_LIMIT = 500

/** 일정별 공지 표시 + (관리자) 쓰기 · 수정 · 지우기 시트 */
function NoticeBlock({ d, editable, onSaved }: { d: SessionDetail; editable: boolean; onSaved: () => void }) {
  const { api } = useClub()
  const { busy, run } = useAction()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const start = () => {
    setText(d.notice ?? '')
    setOpen(true)
  }
  const close = () => {
    if (!busy) setOpen(false)
  }
  const save = async (value: string) => {
    if (busy) return
    const done = await run(() => api.updateSession(d.sessionId, { notice: value }),
      value.trim() ? '일정 공지를 저장했어요' : '일정 공지를 지웠어요')
    if (done) {
      setOpen(false)
      onSaved()
    }
  }
  if (!d.notice && !editable) return null
  return (
    <>
      {d.notice ? (
        <div className="session-notice-row">
          <SessionNotice text={d.notice} />
          {editable ? <button type="button" className="btn sm" onClick={start}>공지 수정</button> : null}
        </div>
      ) : (
        <button type="button" className="btn block" style={{ borderStyle: 'dashed', color: 'var(--muted)', fontWeight: 500 }} onClick={start}>
          + 일정 공지 쓰기
        </button>
      )}
      <Sheet open={open} onClose={close} labelledBy="session-notice-title">
        <div className="stack">
          <h2 id="session-notice-title">일정 공지</h2>
          <p className="small muted">
            이 일정에만 보이는 공지예요(상단에 흐르는 상시 공지와 별개). 일정 화면과 메인 화면에서 팀 밸런스 안내 위에 표시돼요.
          </p>
          <textarea className="session-notice-input" aria-label="일정 공지 내용" maxLength={NOTICE_LIMIT} value={text} disabled={busy}
            onChange={(e) => setText(e.target.value)} placeholder="예: 9시 50분까지 집합, 흰색 상의 지참" />
          <p className="small muted" style={{ margin: 0, textAlign: 'right' }}>{text.length} / {NOTICE_LIMIT}자</p>
          <div className="grid2">
            {d.notice
              ? <button type="button" className="btn danger" disabled={busy} onClick={() => { void save('') }}>공지 지우기</button>
              : <button type="button" className="btn" disabled={busy} onClick={close}>취소</button>}
            <button type="button" className="btn primary" disabled={busy || !text.trim() || text.trim() === (d.notice ?? '')}
              onClick={() => { void save(text) }}>{busy ? '저장 중…' : '저장'}</button>
          </div>
        </div>
      </Sheet>
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
        <section key={t.sessionTeamId} className="team-card" aria-label={teamLabel(t)}>
          <header style={{ background: t.opponent ? OPPONENT_COLOR : teamColor(t.teamCode) }}>
            <strong>{teamLabel(t)}</strong>
            <span className="small">{t.opponent ? '원정팀' : `${t.headcount}명`}</span>
          </header>
          {t.opponent ? (
            <p className="small muted" style={{ padding: '10px 12px', margin: 0 }}>선수 명단 없이 점수만 기록해요.</p>
          ) : (
            <ul>
              {t.members.map((m) => <li key={m.memberId}>{m.name}</li>)}
              {t.guests.map((g) => <li key={g.guestId} className="muted">{g.name}</li>)}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}

function MatchRow({ m, slug }: { m: SessionMatch; slug: string }) {
  const live = m.status === 'RUNNING' || m.status === 'PAUSED'
  const win = winSide(m)
  const right =
    m.status === 'READY' ? <span className="status-badge gold">대기</span>
      : live ? <span className="live-badge">{m.status === 'PAUSED' ? '정지' : 'LIVE'}</span>
        : m.status === 'CANCELLED' ? <span className="small muted">취소</span>
          : m.finalized ? <span className="small" style={{ color: 'var(--green-dark)', fontWeight: 600 }}>확정</span>
            : <span className="small" style={{ color: 'var(--warn-ink)', fontWeight: 600 }}>검토 중</span>
  return (
    <Link to={`/c/${slug}/matches/${m.matchId}`} className={`list-row ${live ? 'dark' : ''}`}
      style={m.status === 'CANCELLED' ? { opacity: 0.6 } : undefined}>
      <span className={live ? '' : 'muted'} style={{ width: 44, color: live ? 'var(--sports-muted)' : undefined }}>{m.gameNo}경기</span>
      <span style={{ flex: 1, textAlign: 'center' }}>
        <ResultTeam name={teamLabel(m.teamA)} side="A" win={win === 'A'} /> <b className="mono" style={{ padding: '0 6px' }}>{m.status === 'READY' ? 'vs' : `${m.teamA.score} : ${m.teamB.score}`}</b> <ResultTeam name={teamLabel(m.teamB)} side="B" win={win === 'B'} />
      </span>
      {right}
    </Link>
  )
}

function AdminActions({ d }: { d: SessionDetail }) {
  const { api, slug } = useClub()
  const nav = useNavigate()
  const { busy, run } = useAction()
  const [nextOpen, setNextOpen] = useState(false)
  const active = d.matches.find((m) => ['READY', 'RUNNING', 'PAUSED'].includes(m.status))

  const deleteSession = async () => {
    if (!window.confirm('이 일정을 삭제할까요? 삭제한 일정에서 다시 볼 수 있고, 완료된 경기 기록과 통계는 보존됩니다.')) return
    if (await run(() => api.deleteSession(d.sessionId), '일정을 삭제했어요')) nav(`/c/${slug}/sessions?tab=deleted`)
  }
  const deleteButton = <button type="button" className="btn sm danger block" disabled={busy} onClick={deleteSession}>일정 삭제</button>

  if (d.deletedAt) return <div className="bar-actions"><Link className="btn block" to={`/c/${slug}/sessions?tab=deleted`}>삭제한 일정 목록으로</Link></div>

  if (d.status === 'CLOSED' || d.status === 'CANCELLED') {
    return (
      <div className="bar-actions">
        <p className="small muted center">{d.status === 'CLOSED' ? '마감된 일정은 고칠 수 없어요.' : '취소된 일정입니다.'}</p>
        {deleteButton}
      </div>
    )
  }

  if (d.status === 'OPEN') {
    return (
      <div className="bar-actions">
        <div className="grid2">
          <Link className="btn" to={`/c/${slug}/admin/sessions/${d.sessionId}/attendance`}>참석자 수정</Link>
          <Link className="btn primary" to={`/c/${slug}/admin/sessions/${d.sessionId}/teams`}>팀 편성</Link>
        </div>
        {deleteButton}
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
      {deleteButton}
      <NextMatchSheet sessionId={d.sessionId} open={nextOpen} onClose={() => setNextOpen(false)} />
    </div>
  )
}
