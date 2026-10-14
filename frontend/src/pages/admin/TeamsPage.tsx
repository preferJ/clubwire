// A03 팀 자동 편성 → [일정확정] / 확정 후 수동 변경(지각 추가 · 이동 · 제외)

import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { Generation, SessionDetail } from '../../api/types'
import { Icon } from '../../components/Icon'
import { ErrorBox, Loading, Sheet, TeamBadge, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { fmtDate, fmtDateTime, teamColor } from '../../lib/format'
import { useAction, useAsync } from '../../lib/hooks'
import { useToast } from '../../lib/toast'

export function TeamsPage() {
  const { sessionId } = useParams()
  const id = Number(sessionId)
  const { api } = useClub()
  const s = useAsync(() => api.session(id), [api, id])
  if (s.error) return <ErrorBox error={s.error} onRetry={s.reload} />
  if (!s.data) return <div className="page"><Loading /></div>
  return s.data.status === 'OPEN' ? <Generate d={s.data} /> : <ManualEdit d={s.data} reload={s.reload} />
}

function Generate({ d }: { d: SessionDetail }) {
  const { api, slug } = useClub()
  const nav = useNavigate()
  const toast = useToast()
  const { busy, run } = useAction()
  const headcount = d.attendees.length + d.guests.length
  const [count, setCount] = useState(headcount >= 15 ? 3 : 2)
  const [gen, setGen] = useState<Generation | null>(null)

  const generate = async () => {
    const g = await run(() => api.generateTeams(d.sessionId, count))
    if (g) setGen(g)
  }
  const confirm = async () => {
    if (!gen) return
    const r = await run(() => api.confirmTeams(d.sessionId, gen.generationId))
    if (r) {
      toast.show('일정확정! 프리뷰 기사를 만들고 있어요')
      nav(`/c/${slug}/sessions/${d.sessionId}`)
    }
  }
  const sizes = gen ? gen.teams.map((t) => t.headcount).join(' · ') : splitSizes(headcount, count).join(' · ')

  return (
    <>
      <TopBar title={`팀 편성 · ${fmtDate(d.sessionDate, false)}`} back={`/c/${slug}/sessions/${d.sessionId}`}
        right={<span className="admin-pill">관리자 모드</span>} />
      <main className="page">
        <div className="segmented" role="group" aria-label="팀 수" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
          {[2, 3, 4, 5, 6].map((n) => (
            <button key={n} type="button" aria-pressed={count === n} disabled={headcount < n * 2}
              onClick={() => { setCount(n); setGen(null) }}>{n}팀</button>
          ))}
        </div>
        <div className="notice green" style={{ flexDirection: 'column', gap: 4 }}>
          <b style={{ fontSize: 15 }}>{headcount}명 → {sizes}명</b>
          <span>{gen ? `${gen.balanceLabel} 최근 자주 같은 팀이었던 조합은 나눴어요.` : '참석자 전원이 팀에 들어가고, 팀별 인원 차이는 최대 1명이에요.'}</span>
        </div>

        {gen ? (
          <>
            <details className="card flat">
              <summary>관리자 상세 (비공개 수치)</summary>
              <div className="stack mono small muted" style={{ gap: 4 }}>
                <span>평균 Rating {gen.teams.map((t) => `${t.teamCode} ${t.avgRating.toFixed(1)}`).join(' · ')}</span>
                <span>편차 {gen.spreadPercent.toFixed(2)}% · 후보 {gen.candidateCount.toLocaleString()}개 중 {gen.validCandidateCount.toLocaleString()}개 통과{gen.toleranceFallback ? ' (허용 범위 초과 → 최소 차이 후보 사용)' : ''}</span>
                <span>Pair Penalty {gen.pairPenalty.toFixed(2)} · seed {gen.seed}</span>
              </div>
            </details>
            {gen.teams.map((t) => (
              <section key={t.teamCode} className="card flat stack" style={{ gap: 8 }}>
                <div className="row"><TeamBadge code={t.teamCode} /><b>TEAM {t.teamCode}</b><span className="small muted">{t.headcount}명</span></div>
                <div className="row wrap" style={{ gap: 6 }}>
                  {t.members.map((m) => <span key={m.memberId} className="name-chip">{m.name}</span>)}
                  {t.guests.map((g) => <span key={g.guestId} className="name-chip guest">{g.name}</span>)}
                </div>
              </section>
            ))}
          </>
        ) : (
          <p className="small muted center">Rating 균형을 맞추면서, 최근 자주 같은 팀이었던 조합은 피해서 편성합니다.</p>
        )}
      </main>
      <div className="bar-actions">
        {gen ? (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 8 }}>
              <button type="button" className="btn" disabled={busy} onClick={generate}><Icon name="shuffle" size={18} />다시 섞기</button>
              <button type="button" className="btn primary lg" disabled={busy} onClick={confirm}>일정확정</button>
            </div>
            <span className="small muted center">확정하면 프리뷰 기사가 만들어지고 멤버에게 팀이 공개돼요</span>
          </>
        ) : (
          <button type="button" className="btn primary lg block" disabled={busy || headcount < count * 2} onClick={generate}>
            <Icon name="shuffle" size={18} />팀 만들기
          </button>
        )}
      </div>
    </>
  )
}

type Target = { kind: 'member'; id: number; name: string; teamId: number } | { kind: 'guest'; id: number; name: string; teamId: number }

function ManualEdit({ d, reload }: { d: SessionDetail; reload: () => void }) {
  const { api, slug } = useClub()
  const { busy, run } = useAction()
  const members = useAsync(() => api.members(), [api])
  const logs = useAsync(() => api.assignmentLogs(d.sessionId), [api, d.sessionId])
  const [target, setTarget] = useState<Target | null>(null)
  const [lateMember, setLateMember] = useState<number | ''>('')
  const [lateTeam, setLateTeam] = useState<number>(d.teams[0]?.sessionTeamId ?? 0)
  const [reason, setReason] = useState('')

  const onTeam = new Set(d.teams.flatMap((t) => t.members.map((m) => m.memberId)))
  const candidates = (members.data ?? []).filter((m) => !onTeam.has(m.memberId))
  const teamCode = (tid: number | null) => d.teams.find((t) => t.sessionTeamId === tid)?.teamCode ?? '-'
  const nameOf = (mid: number | null) => (members.data ?? []).find((m) => m.memberId === mid)?.name

  const change = async (body: Parameters<typeof api.changeAssignment>[1], ok: string) => {
    if (await run(() => api.changeAssignment(d.sessionId, { ...body, reason: reason.trim() || undefined }), ok)) {
      setTarget(null)
      setReason('')
      reload()
      logs.reload()
    }
  }

  return (
    <>
      <TopBar title="팀 수동 변경" sub="다음에 시작하는 경기부터 반영돼요" back={`/c/${slug}/sessions/${d.sessionId}`}
        right={<span className="admin-pill">관리자 모드</span>} />
      <main className="page">
        <p className="small muted">선수를 누르면 다른 팀으로 옮기거나 팀에서 뺄 수 있어요.</p>
        {d.teams.map((t) => (
          <section key={t.sessionTeamId} className="card flat stack" style={{ gap: 8 }}>
            <div className="row"><TeamBadge code={t.teamCode} /><b>TEAM {t.teamCode}</b><span className="small muted">{t.headcount}명</span></div>
            <div className="row wrap" style={{ gap: 6 }}>
              {t.members.map((m) => (
                <button key={m.memberId} type="button" className="name-chip"
                  style={m.assignType === 'MANUAL' ? { outline: '1px dashed var(--green)' } : undefined}
                  onClick={() => setTarget({ kind: 'member', id: m.memberId, name: m.name, teamId: t.sessionTeamId })}>
                  {m.name}
                </button>
              ))}
              {t.guests.map((g) => (
                <button key={g.guestId} type="button" className="name-chip guest"
                  onClick={() => setTarget({ kind: 'guest', id: g.guestId, name: g.name, teamId: t.sessionTeamId })}>
                  {g.name}
                </button>
              ))}
            </div>
          </section>
        ))}

        <section className="card stack" style={{ gap: 10 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>늦게 온 사람 추가</h2>
          <label className="field">멤버
            <select className="select" value={lateMember} onChange={(e) => setLateMember(e.target.value ? Number(e.target.value) : '')}>
              <option value="">선택하세요</option>
              {candidates.map((m) => <option key={m.memberId} value={m.memberId}>{m.name}</option>)}
            </select>
          </label>
          <div className="segmented" role="group" aria-label="들어갈 팀" style={{ gridTemplateColumns: `repeat(${d.teams.length}, minmax(0, 1fr))` }}>
            {d.teams.map((t) => (
              <button key={t.sessionTeamId} type="button" aria-pressed={lateTeam === t.sessionTeamId} onClick={() => setLateTeam(t.sessionTeamId)}>
                TEAM {t.teamCode}
              </button>
            ))}
          </div>
          <div className="grid2">
            <button type="button" className="btn" disabled={busy || !lateMember}
              onClick={() => lateMember && change({ action: 'ADD', memberId: lateMember, toTeamId: lateTeam }, '멤버를 추가했어요')}>
              멤버 추가
            </button>
            <button type="button" className="btn" disabled={busy}
              onClick={() => change({ action: 'ADD', toTeamId: lateTeam }, '게스트를 추가했어요')}>
              게스트 추가
            </button>
          </div>
        </section>

        <details className="card flat">
          <summary>변경 이력 {logs.data?.length ? `(${logs.data.length})` : ''}</summary>
          <div className="stack small" style={{ gap: 6 }}>
            {(logs.data ?? []).length === 0 ? <span className="muted">아직 없어요.</span> : (logs.data ?? []).map((l) => (
              <span key={l.logId}>
                {fmtDateTime(l.createdAt)} · {nameOf(l.memberId) ?? (l.guestId ? '게스트' : '')}{' '}
                {l.action === 'ADD' ? `→ TEAM ${teamCode(l.toTeamId)} 추가` : l.action === 'MOVE' ? `TEAM ${teamCode(l.fromTeamId)} → ${teamCode(l.toTeamId)}` : `TEAM ${teamCode(l.fromTeamId)}에서 제외`}
                {l.reason ? ` (${l.reason})` : ''}
              </span>
            ))}
          </div>
        </details>
      </main>

      <Sheet open={!!target} onClose={() => setTarget(null)} labelledBy="move-title">
        {target ? (
          <>
            <h2 id="move-title">{target.name}</h2>
            <label className="field">사유(선택)<input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="예: 부상, 인원 맞추기" /></label>
            <div className="stack">
              {d.teams.filter((t) => t.sessionTeamId !== target.teamId).map((t) => (
                <button key={t.sessionTeamId} type="button" className="btn block" disabled={busy}
                  style={{ borderColor: teamColor(t.teamCode) }}
                  onClick={() => change(target.kind === 'member'
                    ? { action: 'MOVE', memberId: target.id, toTeamId: t.sessionTeamId }
                    : { action: 'MOVE', guestId: target.id, toTeamId: t.sessionTeamId }, `TEAM ${t.teamCode}로 옮겼어요`)}>
                  TEAM {t.teamCode}로 이동
                </button>
              ))}
              <button type="button" className="btn danger block" disabled={busy}
                onClick={() => change(target.kind === 'member'
                  ? { action: 'REMOVE', memberId: target.id }
                  : { action: 'REMOVE', guestId: target.id }, '팀에서 뺐어요')}>
                팀에서 빼기(조퇴 등)
              </button>
            </div>
          </>
        ) : null}
      </Sheet>
    </>
  )
}

function splitSizes(total: number, k: number): number[] {
  const base = Math.floor(total / k)
  const rem = total % k
  return Array.from({ length: k }, (_, i) => (i < rem ? base + 1 : base))
}
