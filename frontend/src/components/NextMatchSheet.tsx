// 다음 경기 대진: 매 경기 관리자가 두 팀을 고른다(가장 오래 쉰 두 팀이 미리 선택됨)
// 원정 경기: 우리 팀 vs 원정팀은 고정, 대신 이번 경기 출전 선수를 고른다(직전 경기 명단이 미리 선택됨)

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { NextSuggestion } from '../api/types'
import { useClub } from '../lib/club'
import { teamColor, teamLabel, teamMark } from '../lib/format'
import { useAction } from '../lib/hooks'
import { Loading, Sheet, TeamBadge } from './ui'

export function NextMatchSheet({ sessionId, open, onClose }: { sessionId: number; open: boolean; onClose: () => void }) {
  const { api, slug } = useClub()
  const nav = useNavigate()
  const { busy, run } = useAction()
  const [sug, setSug] = useState<NextSuggestion | null>(null)
  const [pick, setPick] = useState<[number | null, number | null]>([null, null])
  const [lineup, setLineup] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!open) return
    setSug(null)
    api.nextSuggestion(sessionId).then((s) => {
      setSug(s)
      setPick([s.suggestedTeamAId, s.suggestedTeamBId])
      setLineup(new Set(s.lineupMemberIds ?? []))
    }).catch(() => setSug(null))
  }, [open, api, sessionId])

  const choose = (slot: 0 | 1, teamId: number) =>
    setPick((p) => (slot === 0 ? [teamId, p[1] === teamId ? p[0] : p[1]] : [p[0] === teamId ? p[1] : p[0], teamId]))
  const toggle = (memberId: number) => setLineup((s) => {
    const next = new Set(s)
    if (next.has(memberId)) next.delete(memberId)
    else next.add(memberId)
    return next
  })

  const away = !!sug?.away
  const create = async () => {
    if (!pick[0] || !pick[1] || (away && lineup.size === 0)) return
    const m = await run(() => api.createNextMatch(sessionId, pick[0]!, pick[1]!, away ? [...lineup] : undefined))
    if (m) {
      onClose()
      nav(`/c/${slug}/matches/${m.matchId}`)
    }
  }

  const team = (id: number | null) => sug?.teams.find((t) => t.sessionTeamId === id)
  const roster = sug?.roster ?? []

  return (
    <Sheet open={open} onClose={onClose} labelledBy="next-title">
      <h2 id="next-title">{sug ? `${sug.nextGameNo}경기 ${away ? '출전 선수' : '대진'}` : '다음 경기'}</h2>
      {!sug ? (
        <Loading rows={2} />
      ) : sug.blockedByMatchId ? (
        <div className="notice warn">
          대기·진행 중인 경기가 있어요.&nbsp;
          <Link to={`/c/${slug}/matches/${sug.blockedByMatchId}`} onClick={onClose}>그 경기로 가기</Link>
        </div>
      ) : away ? (
        <>
          <div className="row" style={{ justifyContent: 'center', gap: 12, minHeight: 48, borderRadius: 12, border: '1px dashed var(--line-strong)', fontSize: 15 }}>
            <TeamBadge code={team(pick[0])?.teamCode} /> <b>{teamLabel(team(pick[0]))}</b>
            <span className="muted">vs</span>
            <b>{teamLabel(team(pick[1]))}</b> <TeamBadge code={teamMark(team(pick[1]))} opponent />
          </div>
          <section className="section">
            <div className="row between">
              <h3 className="small muted" style={{ fontWeight: 700 }}>이번 경기 출전 선수 {lineup.size}명</h3>
              <span className="row" style={{ gap: 6 }}>
                <button type="button" className="link-btn" onClick={() => setLineup(new Set(roster.map((m) => m.memberId)))}>전체</button>
                <button type="button" className="link-btn" onClick={() => setLineup(new Set())}>비우기</button>
              </span>
            </div>
            <div className="grid3" style={{ gap: 6 }}>
              {roster.map((m) => (
                <button key={m.memberId} type="button" className="pick" aria-pressed={lineup.has(m.memberId)} onClick={() => toggle(m.memberId)}>
                  {m.name}
                </button>
              ))}
            </div>
          </section>
          <p className="small muted center">
            {(sug.lineupMemberIds ?? []).length ? '직전 경기 출전 선수를 미리 골라 뒀어요. 바꿔도 됩니다.' : '이번 경기에 뛸 선수를 골라 주세요.'} 게스트는 함께 뛰는 것으로 셉니다.
          </p>
          <button type="button" className="btn primary lg block" disabled={busy || lineup.size === 0} onClick={create}>
            {busy ? '만드는 중…' : lineup.size === 0 ? '출전 선수를 골라 주세요' : `${lineup.size}명으로 경기 만들기`}
          </button>
        </>
      ) : (
        <>
          {([0, 1] as const).map((slot) => (
            <section key={slot} className="section">
              <h3 className="small muted" style={{ fontWeight: 700 }}>팀 {slot + 1}</h3>
              <div className="grid3">
                {sug.teams.map((t) => (
                  <button key={t.sessionTeamId} type="button" className="pick" aria-pressed={pick[slot] === t.sessionTeamId}
                    onClick={() => choose(slot, t.sessionTeamId)}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, minHeight: 64 }}>
                    <span style={{ fontWeight: 700, color: pick[slot] === t.sessionTeamId ? '#fff' : teamColor(t.teamCode) }}>{teamLabel(t)}</span>
                    <span style={{ fontSize: 11, opacity: 0.85 }}>오늘 {t.gamesPlayed}경기{t.consecutive ? ` · 연속 ${t.consecutive}` : ''}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
          <div className="row" style={{ justifyContent: 'center', gap: 12, minHeight: 48, borderRadius: 12, border: '1px dashed var(--line-strong)', fontSize: 15 }}>
            <TeamBadge code={team(pick[0])?.teamCode ?? '?'} /> <b>{teamLabel(team(pick[0]))}</b>
            <span className="muted">vs</span>
            <b>{teamLabel(team(pick[1]))}</b> <TeamBadge code={team(pick[1])?.teamCode ?? '?'} />
          </div>
          <p className="small muted center">가장 오래 쉰 두 팀을 미리 골라 뒀어요. 바꿔도 됩니다.</p>
          <button type="button" className="btn primary lg block" disabled={busy || !pick[0] || !pick[1]} onClick={create}>
            {busy ? '만드는 중…' : '경기 만들기'}
          </button>
        </>
      )}
    </Sheet>
  )
}
