// S04 LIVE 관전 + (관리자) A04 경기 진행 · A05 골 기록 · A06 기록 확정/다음 경기

import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { MatchDetail, MatchDetailTeam, MatchEventView, SessionDetail } from '../api/types'
import { Icon } from '../components/Icon'
import { NextMatchSheet } from '../components/NextMatchSheet'
import { AdminButton, ErrorBox, Loading, Sheet, Switch, TeamBadge } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtClock, GAME_STATUS_LABEL, newIdempotencyKey, teamColor } from '../lib/format'
import { useAction, useAsync, useMatchClock } from '../lib/hooks'
import { ThemeToggle } from '../lib/theme'

export function MatchPage() {
  const { matchId } = useParams()
  const id = Number(matchId)
  const { api, slug, isAdmin, connected } = useClub()
  const detail = useAsync(() => api.match(id), [api, id])
  const { busy, run } = useAction()
  const [goalTeam, setGoalTeam] = useState<number | null>(null)
  const [nextOpen, setNextOpen] = useState(false)
  const [rosterOpen, setRosterOpen] = useState(false)

  useClubEvent((msg) => {
    if (msg.type === 'MATCH_UPDATED' && msg.matchId === id && detail.data) {
      const m = msg.match
      detail.setData({ ...detail.data, ...m, teamA: { ...detail.data.teamA, ...m.teamA }, teamB: { ...detail.data.teamB, ...m.teamB } })
    }
    if (msg.type === 'MATCH_EVENT' && msg.matchId === id) detail.reload()
  })

  const d = detail.data
  const clock = useMatchClock(d)

  const act = async (action: 'start' | 'pause' | 'resume' | 'end' | 'cancel' | 'finalize' | 'unfinalize', ok?: string) => {
    if (action === 'cancel' && !window.confirm('이 경기를 취소할까요?')) return
    if (action === 'end' && !window.confirm('경기를 종료할까요?')) return
    if (await run(() => api.matchAction(id, action), ok)) detail.reload()
  }

  if (detail.error) return <ErrorBox error={detail.error} onRetry={detail.reload} />
  if (!d) return <div className="page"><Loading /></div>

  const live = d.status === 'RUNNING' || d.status === 'PAUSED'
  const editable = isAdmin && !d.finalized && d.status !== 'CANCELLED'
  const goals = d.events.filter((e) => e.eventType === 'GOAL').sort((a, b) => (b.elapsedSec ?? 0) - (a.elapsedSec ?? 0) || b.eventId - a.eventId)
  const teamOf = (tid: number | null) => (tid === d.teamA.sessionTeamId ? d.teamA : d.teamB)
  const winner = d.winTeamId ? teamOf(d.winTeamId) : null

  return (
    <>
      <section className="scoreboard" aria-label="점수판">
        <div className="row between">
          <Link to={`/c/${slug}/sessions/${d.sessionId}`} className="icon-btn" aria-label="일정으로" style={{ color: 'var(--sports-ink)', marginLeft: -10 }}>
            <Icon name="back" size={22} />
          </Link>
          <div className="row">
            {d.status === 'RUNNING' ? <span className="live-badge">LIVE</span>
              : <span className="status-badge" style={{ background: d.status === 'PAUSED' ? 'var(--gold)' : 'var(--sports-control)', color: d.status === 'PAUSED' ? 'var(--on-light)' : 'var(--sports-ink)' }}>
                {d.finalized ? '확정' : GAME_STATUS_LABEL[d.status]}
              </span>}
            <span className="small" style={{ color: 'var(--sports-muted)' }}>{d.gameNo}경기</span>
          </div>
          <div className="row" style={{ flexShrink: 0, gap: 4 }}><ThemeToggle /><AdminButton onDark /></div>
        </div>

        <div className="score-row">
          <TeamCol t={d.teamA} />
          <div className="score" aria-label={`${d.teamA.score} 대 ${d.teamB.score}`}>{d.teamA.score}:{d.teamB.score}</div>
          <TeamCol t={d.teamB} />
        </div>

        <div className="stack" style={{ alignItems: 'center', gap: 8 }}>
          {isAdmin && live ? (
            <div className="row between" style={{ width: '100%' }}>
              <button type="button" className="night-btn" disabled={busy}
                onClick={() => act(d.status === 'RUNNING' ? 'pause' : 'resume')}>
                <Icon name={d.status === 'RUNNING' ? 'pause' : 'play'} size={18} stroke={2} />
                {d.status === 'RUNNING' ? '일시정지' : '재개'}
              </button>
              <Clock d={d} clock={clock} />
              <button type="button" className="night-btn" disabled={busy} onClick={() => act('end')}>
                <Icon name="stop" size={16} stroke={2} />종료
              </button>
            </div>
          ) : (
            <Clock d={d} clock={clock} />
          )}
          <div className="progress" aria-hidden="true"><span style={{ width: `${clock.progress * 100}%` }} /></div>
          <div className="small" style={{ color: 'var(--sports-muted)' }}>
            {d.status === 'READY' ? `${Math.round(d.durationSec / 60)}분 경기 · 시작 전`
              : d.status === 'FINISHED' ? (winner ? `TEAM ${winner.teamCode} 승` : '무승부') + (d.endReason === 'TIME_UP' ? ' · 시간 종료' : d.endReason === 'EARLY_GOAL' ? ' · 조기 종료' : '')
                : `남은 시간 · ${d.autoEnd ? '0이 되면 자동 종료' : '관리자가 종료'}`}
          </div>
        </div>
      </section>

      <div className="row small muted" style={{ padding: '10px 16px', background: 'var(--card)', borderBottom: '1px solid var(--line)' }}>
        <span style={{ width: 8, height: 8, borderRadius: 4, background: connected ? 'var(--green)' : 'var(--line-strong)' }} />
        {connected ? '실시간 연결됨' : '연결 중…'}{!isAdmin ? ' · 경기 조작은 관리자만 할 수 있어요' : ''}
      </div>

      <main className="page">
        {isAdmin && d.status === 'READY' ? (
          <div className="stack">
            <button type="button" className="btn primary lg block" disabled={busy} onClick={() => act('start', '경기를 시작했어요')}>
              <Icon name="play" size={18} stroke={2} />경기 시작
            </button>
            <button type="button" className="link-btn" style={{ color: 'var(--warn-ink)' }} onClick={() => act('cancel')}>경기 취소</button>
          </div>
        ) : null}

        {isAdmin && live ? (
          <div className="grid2" style={{ gap: 10 }}>
            {[d.teamA, d.teamB].map((t) => (
              <button key={t.sessionTeamId} type="button" className="goal-btn" style={{ background: teamColor(t.teamCode) }}
                onClick={() => setGoalTeam(t.sessionTeamId)}>
                <Icon name="plus" size={30} stroke={2} />TEAM {t.teamCode} 골
              </button>
            ))}
          </div>
        ) : null}

        {isAdmin && d.status === 'FINISHED' && !d.finalized ? (
          <section className="card stack" style={{ gap: 10 }}>
            <div className="row between">
              <b>기록 검토</b>
              <span className="status-badge gold">확정 전</span>
            </div>
            <p className="small muted">골 기록이 맞는지 확인하고 확정하세요. 확정하면 승패 · 개인 기록 · 팀 밸런스 계산에 반영돼요.</p>
            <div className="grid2">
              {[d.teamA, d.teamB].map((t) => (
                <button key={t.sessionTeamId} type="button" className="btn sm" onClick={() => setGoalTeam(t.sessionTeamId)}>
                  TEAM {t.teamCode} 골 추가
                </button>
              ))}
            </div>
            <button type="button" className="btn dark lg block" disabled={busy} onClick={() => act('finalize', '기록을 확정했어요')}>
              <Icon name="check" size={20} stroke={2} />기록 확정
            </button>
            <button type="button" className="link-btn" style={{ color: 'var(--warn-ink)' }} onClick={() => act('cancel')}>이 경기 취소(기록 안 함)</button>
          </section>
        ) : null}

        {isAdmin && d.finalized ? (
          <section className="stack">
            <button type="button" className="btn primary lg block" onClick={() => setNextOpen(true)}>
              <Icon name="plus" size={18} stroke={2} />다음 경기 만들기
            </button>
            <div className="grid2">
              <Link className="btn sm" to={`/c/${slug}/admin/sessions/${d.sessionId}/close`}>오늘 끝내기(일정마감)</Link>
              <button type="button" className="btn sm" disabled={busy}
                onClick={() => window.confirm('확정을 해제하고 기록을 고칠까요?') && act('unfinalize', '확정을 해제했어요')}>
                확정 해제
              </button>
            </div>
          </section>
        ) : null}

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>타임라인</h2>
          {goals.length === 0 ? <p className="small muted">아직 골이 없어요.</p> : null}
          {goals.map((e) => (
            <GoalRow key={e.eventId} e={e} team={teamOf(e.teamId)} other={teamOf(e.teamId) === d.teamA ? d.teamB : d.teamA} canCancel={editable && !e.cancelled && d.status !== 'READY'}
              onCancel={async () => {
                if (!window.confirm('이 골을 취소할까요? (기록은 남고 점수만 빠집니다)')) return
                if (await run(() => api.cancelGoal(id, e.eventId), '골을 취소했어요')) detail.reload()
              }} />
          ))}
        </section>

        <section className="grid2">
          {[d.teamA, d.teamB].map((t) => (
            <div key={t.sessionTeamId} className="card flat stack" style={{ gap: 6 }}>
              <span className="small" style={{ fontWeight: 700, color: teamColor(t.teamCode) }}>
                TEAM {t.teamCode} 출전 {t.members.length + t.guestCount}
              </span>
              <span style={{ fontSize: 13, lineHeight: 1.6 }}>
                {[...t.members.map((m) => m.name), ...Array.from({ length: t.guestCount }, (_, i) => `게스트${t.guestCount > 1 ? i + 1 : ''}`)].join(' · ') || '경기 시작 시 확정'}
              </span>
            </div>
          ))}
        </section>
        {editable && d.status !== 'READY' ? (
          <button type="button" className="link-btn" onClick={() => setRosterOpen(true)}>출전 명단 수정(결장 · 교체 투입)</button>
        ) : null}
      </main>

      {goalTeam ? (
        <GoalSheet d={d} teamId={goalTeam} onClose={() => setGoalTeam(null)} onDone={() => { setGoalTeam(null); detail.reload() }} />
      ) : null}
      <NextMatchSheet sessionId={d.sessionId} open={nextOpen} onClose={() => setNextOpen(false)} />
      {rosterOpen ? <RosterSheet d={d} onClose={() => setRosterOpen(false)} onChanged={detail.reload} /> : null}
    </>
  )
}

function TeamCol({ t }: { t: MatchDetailTeam }) {
  return (
    <div className="score-team">
      <TeamBadge code={t.teamCode} size={46} onDark />
      TEAM {t.teamCode}
    </div>
  )
}

function Clock({ d, clock }: { d: MatchDetail; clock: ReturnType<typeof useMatchClock> }) {
  const over = clock.overtime > 0 && d.status !== 'FINISHED'
  return (
    <div className="clock" role="timer" aria-live="off" style={over ? { color: 'var(--gold)' } : undefined}>
      {d.status === 'FINISHED' ? fmtClock(clock.elapsed) : over ? `+${fmtClock(clock.overtime)}` : fmtClock(clock.remaining)}
    </div>
  )
}

function GoalRow({ e, team, other, canCancel, onCancel }: {
  e: MatchEventView
  team: MatchDetailTeam
  other: MatchDetailTeam
  canCancel: boolean
  onCancel: () => void
}) {
  const who = (e.guestGoal ? '게스트' : e.scorerName ?? '?') + (e.ownGoal ? ` (TEAM ${other.teamCode})` : '')
  return (
    <div className={`timeline-item ${e.cancelled ? 'cancelled' : ''}`}>
      <time>{fmtClock(e.elapsedSec ?? 0)}</time>
      <span className="mini-badge" style={{ background: e.cancelled ? 'var(--line-strong)' : teamColor(team.teamCode) }}>{team.teamCode}</span>
      <div className="stack" style={{ flex: 1, gap: 0 }}>
        <span className="who" style={{ fontWeight: 700 }}>{e.ownGoal ? `자책골 · ${who}` : `골 · ${who}`}</span>
        <span className="small muted">{e.cancelled ? '취소됨' : e.assistName ? `도움 ${e.assistName}` : '도움 없음'}</span>
      </div>
      {canCancel ? (
        <button type="button" className="btn sm" style={{ border: 0, background: 'var(--soft)', color: 'var(--warn-ink)' }} onClick={onCancel}>취소</button>
      ) : null}
    </div>
  )
}

/** A05 골 기록 시트 */
function GoalSheet({ d, teamId, onClose, onDone }: { d: MatchDetail; teamId: number; onClose: () => void; onDone: () => void }) {
  const { api } = useClub()
  const { busy, run } = useAction()
  const idemKey = useMemo(() => newIdempotencyKey(), [])
  const team = teamId === d.teamA.sessionTeamId ? d.teamA : d.teamB
  const other = teamId === d.teamA.sessionTeamId ? d.teamB : d.teamA
  const [own, setOwn] = useState(false)
  const [scorer, setScorer] = useState<number | 'guest' | null>(null)
  const [assist, setAssist] = useState<number | null>(null)
  const finished = d.status === 'FINISHED'
  const [minute, setMinute] = useState(() => Math.round(d.durationSec / 60))

  useEffect(() => {
    setScorer(null)
    setAssist(null)
  }, [own])

  const scorerTeam = own ? other : team
  const scorerOptions = [...scorerTeam.members.map((m) => ({ id: m.memberId as number | 'guest', name: m.name })),
    ...(scorerTeam.guestCount > 0 ? [{ id: 'guest' as const, name: '게스트' }] : [])]
  const assistOptions = team.members.filter((m) => m.memberId !== scorer)

  const submit = async () => {
    if (scorer === null) return
    const r = await run(() =>
      api.addGoal(d.matchId, {
        teamId,
        scorerMemberId: scorer === 'guest' ? null : scorer,
        guestGoal: scorer === 'guest',
        ownGoal: own,
        assistMemberId: own ? null : assist,
        elapsedSec: finished ? Math.max(0, Math.min(d.durationSec * 3, minute * 60)) : null,
        idempotencyKey: idemKey,
      }),
    )
    if (r) onDone()
  }

  return (
    <Sheet open onClose={onClose} labelledBy="goal-title">
      <div className="row between">
        <div className="row"><TeamBadge code={team.teamCode} size={32} /><h2 id="goal-title">TEAM {team.teamCode} 골 기록</h2></div>
      </div>

      <div className="row between" style={{ padding: '10px 12px', borderRadius: 12, background: 'var(--bg)' }}>
        <div className="stack" style={{ gap: 2 }}>
          <b style={{ fontSize: 14 }}>자책골</b>
          <span className="small muted">켜면 상대(TEAM {other.teamCode}) 선수 중에서 고릅니다</span>
        </div>
        <Switch checked={own} onChange={setOwn} label="자책골" />
      </div>

      <section className="section">
        <h3 className="small muted" style={{ fontWeight: 700 }}>{own ? `자책한 선수 (TEAM ${other.teamCode})` : '득점자'}</h3>
        <div className="grid3" style={{ gap: 6 }}>
          {scorerOptions.map((o) => (
            <button key={String(o.id)} type="button" className="pick" aria-pressed={scorer === o.id} onClick={() => setScorer(o.id)}>
              {o.name}
            </button>
          ))}
        </div>
      </section>

      {!own ? (
        <section className="section">
          <h3 className="small muted" style={{ fontWeight: 700 }}>도움 (선택)</h3>
          <div className="grid3" style={{ gap: 6 }}>
            <button type="button" className="pick alt" aria-pressed={assist === null} onClick={() => setAssist(null)}>없음</button>
            {assistOptions.map((m) => (
              <button key={m.memberId} type="button" className="pick alt" aria-pressed={assist === m.memberId} onClick={() => setAssist(m.memberId)}>
                {m.name}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {finished ? (
        <label className="field">
          득점 시각(경기 시작 후 몇 분)
          <input className="input" type="number" min={0} max={Math.round(d.durationSec / 60) * 3} value={minute}
            onChange={(e) => setMinute(Number(e.target.value))} />
        </label>
      ) : null}

      <button type="button" className="btn primary lg block" disabled={busy || scorer === null} onClick={submit}>
        {busy ? '기록 중…' : own ? '자책골 기록' : '골 기록'}
      </button>
    </Sheet>
  )
}

/** 출전 명단 수정: 결장(빼기) / 교체 투입(넣기) */
function RosterSheet({ d, onClose, onChanged }: { d: MatchDetail; onClose: () => void; onChanged: () => void }) {
  const { api } = useClub()
  const { busy, run } = useAction()
  const [session, setSession] = useState<SessionDetail | null>(null)
  useEffect(() => {
    api.session(d.sessionId).then(setSession).catch(() => setSession(null))
  }, [api, d.sessionId])

  const inMatch = new Set([...d.teamA.members, ...d.teamB.members].map((m) => m.memberId))
  const benchFor = (teamId: number) =>
    (session?.teams.find((t) => t.sessionTeamId === teamId)?.members ?? []).filter((m) => !inMatch.has(m.memberId))

  return (
    <Sheet open onClose={onClose} labelledBy="roster-title">
      <h2 id="roster-title">출전 명단 수정</h2>
      <p className="small muted">골/도움 기록이 있는 선수는 뺄 수 없어요.</p>
      {[d.teamA, d.teamB].map((t) => (
        <section key={t.sessionTeamId} className="section">
          <h3 className="small" style={{ fontWeight: 700, color: teamColor(t.teamCode) }}>TEAM {t.teamCode}</h3>
          <div className="row wrap" style={{ gap: 6 }}>
            {t.members.map((m) => (
              <button key={m.memberId} type="button" className="name-chip" disabled={busy}
                onClick={async () => { if (await run(() => api.removeMatchMember(d.matchId, m.memberId), `${m.name} 결장 처리`)) onChanged() }}>
                {m.name} ✕
              </button>
            ))}
          </div>
          {benchFor(t.sessionTeamId).length ? (
            <div className="row wrap" style={{ gap: 6 }}>
              {benchFor(t.sessionTeamId).map((m) => (
                <button key={m.memberId} type="button" className="name-chip guest" disabled={busy}
                  onClick={async () => { if (await run(() => api.addMatchMember(d.matchId, m.memberId, t.sessionTeamId), `${m.name} 투입`)) onChanged() }}>
                  + {m.name}
                </button>
              ))}
            </div>
          ) : null}
        </section>
      ))}
      <button type="button" className="btn block" onClick={onClose}>닫기</button>
    </Sheet>
  )
}
