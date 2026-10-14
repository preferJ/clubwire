// 다음 경기 대진: 매 경기 관리자가 두 팀을 고른다(가장 오래 쉰 두 팀이 미리 선택됨)

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { NextSuggestion } from '../api/types'
import { useClub } from '../lib/club'
import { teamColor } from '../lib/format'
import { useAction } from '../lib/hooks'
import { Loading, Sheet, TeamBadge } from './ui'

export function NextMatchSheet({ sessionId, open, onClose }: { sessionId: number; open: boolean; onClose: () => void }) {
  const { api, slug } = useClub()
  const nav = useNavigate()
  const { busy, run } = useAction()
  const [sug, setSug] = useState<NextSuggestion | null>(null)
  const [pick, setPick] = useState<[number | null, number | null]>([null, null])

  useEffect(() => {
    if (!open) return
    setSug(null)
    api.nextSuggestion(sessionId).then((s) => {
      setSug(s)
      setPick([s.suggestedTeamAId, s.suggestedTeamBId])
    }).catch(() => setSug(null))
  }, [open, api, sessionId])

  const choose = (slot: 0 | 1, teamId: number) =>
    setPick((p) => (slot === 0 ? [teamId, p[1] === teamId ? p[0] : p[1]] : [p[0] === teamId ? p[1] : p[0], teamId]))

  const create = async () => {
    if (!pick[0] || !pick[1]) return
    const m = await run(() => api.createNextMatch(sessionId, pick[0]!, pick[1]!))
    if (m) {
      onClose()
      nav(`/c/${slug}/matches/${m.matchId}`)
    }
  }

  const code = (id: number | null) => sug?.teams.find((t) => t.sessionTeamId === id)?.teamCode ?? '?'

  return (
    <Sheet open={open} onClose={onClose} labelledBy="next-title">
      <h2 id="next-title">{sug ? `${sug.nextGameNo}경기 대진` : '다음 경기'}</h2>
      {!sug ? (
        <Loading rows={2} />
      ) : sug.blockedByMatchId ? (
        <div className="notice warn">
          대기·진행 중인 경기가 있어요.&nbsp;
          <Link to={`/c/${slug}/matches/${sug.blockedByMatchId}`} onClick={onClose}>그 경기로 가기</Link>
        </div>
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
                    <span style={{ fontWeight: 700, color: pick[slot] === t.sessionTeamId ? '#fff' : teamColor(t.teamCode) }}>TEAM {t.teamCode}</span>
                    <span style={{ fontSize: 11, opacity: 0.85 }}>오늘 {t.gamesPlayed}경기{t.consecutive ? ` · 연속 ${t.consecutive}` : ''}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
          <div className="row" style={{ justifyContent: 'center', gap: 12, minHeight: 48, borderRadius: 12, border: '1px dashed #b9bdb7', fontSize: 15 }}>
            <TeamBadge code={code(pick[0])} /> <b>TEAM {code(pick[0])}</b>
            <span className="muted">vs</span>
            <b>TEAM {code(pick[1])}</b> <TeamBadge code={code(pick[1])} />
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
