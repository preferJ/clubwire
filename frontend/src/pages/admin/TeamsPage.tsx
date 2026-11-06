// A03 팀 자동 편성 → [일정확정] / 확정 후 수동 변경(지각 추가 · 이동 · 제외)
// 1팀 = 원정 경기: 참석자 전원이 우리 팀, 상대는 원정팀 목록에서만 고른다(없으면 같은 화면 [직접추가]). 경기마다 출전 선수 선택

import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { Generation, Opponent, SessionDetail } from '../../api/types'
import { Icon } from '../../components/Icon'
import { OpponentPicker } from '../../components/OpponentPicker'
import { ErrorBox, Loading, Sheet, TeamBadge, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { fmtDate, fmtDateTime, teamColor, teamLabel } from '../../lib/format'
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
  const { api, slug, club } = useClub()
  const nav = useNavigate()
  const toast = useToast()
  const { busy, run } = useAction()
  const headcount = d.attendees.length + d.guests.length
  const [count, setCount] = useState(headcount >= 15 ? 3 : 2)
  const [opponent, setOpponent] = useState<Opponent | null>(null)
  const [gen, setGen] = useState<Generation | null>(null)
  const away = count === 1
  const canGenerate = away ? d.attendees.length >= 1 && opponent !== null : headcount >= count * 2

  const generate = async () => {
    const g = await run(() => api.generateTeams(d.sessionId, count, away ? opponent?.opponentId : undefined))
    if (g) setGen(g)
  }
  const confirm = async () => {
    if (!gen) return
    const r = await run(() => api.confirmTeams(d.sessionId, gen.generationId))
    if (r) {
      toast.show('일정을 확정했어요. 프리뷰를 검토한 뒤 게시해 주세요')
      nav(`/c/${slug}/admin/articles?sessionId=${d.sessionId}&articleType=PRE_MATCH&articleId=${r.articleIds?.[0] ?? ''}`)
    }
  }
  const sizes = gen ? gen.teams.map((t) => t.headcount).join(' · ') : splitSizes(headcount, count).join(' · ')

  return (
    <>
      <TopBar title={`팀 편성 · ${fmtDate(d.sessionDate, false)}`} back={`/c/${slug}/sessions/${d.sessionId}`}
        right={<span className="admin-pill">관리자 모드</span>} />
      <main className="page">
        <div className="segmented" role="group" aria-label="팀 수" style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))' }}>
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <button key={n} type="button" aria-pressed={count === n} disabled={n === 1 ? d.attendees.length < 1 : headcount < n * 2}
              onClick={() => { setCount(n); setGen(null) }}>{n === 1 ? '원정' : `${n}팀`}</button>
          ))}
        </div>
        {away ? (
          <>
            <OpponentPicker value={opponent?.opponentId ?? null} onChange={(o) => { setOpponent(o); setGen(null) }} />
            <div className="notice green" style={{ flexDirection: 'column', gap: 4 }}>
              <b style={{ fontSize: 15 }}>{club?.clubName ?? '우리 팀'} {headcount}명 vs {opponent?.name ?? '원정팀을 골라 주세요'}</b>
              <span>참석자 전원이 한 팀이 되고, 경기마다 출전 선수를 골라요. 원정팀 골은 점수만 기록하고, 원정 기록은 개인 기록 · 실력 점수 · 타이틀과 따로 쌓여요.</span>
            </div>
          </>
        ) : (
          <div className="notice green" style={{ flexDirection: 'column', gap: 4 }}>
            <b style={{ fontSize: 15 }}>{headcount}명 → {sizes}명</b>
            <span>{gen ? `${gen.balanceLabel} 최근 자주 같은 팀이었던 조합은 나눴어요.` : '참석자 전원이 팀에 들어가고, 팀별 인원 차이는 최대 1명이에요.'}</span>
          </div>
        )}

        {gen && gen.teamCount === 1 ? (
          <>
            {gen.teams.map((t) => (
              <section key={t.teamCode} className="card flat stack" style={{ gap: 8 }}>
                <div className="row"><TeamBadge code={t.teamCode} /><b>{club?.clubName ?? '우리 팀'}</b><span className="small muted">{t.headcount}명</span></div>
                <div className="row wrap" style={{ gap: 6 }}>
                  {t.members.map((m) => <span key={m.memberId} className="name-chip">{m.name}</span>)}
                  {t.guests.map((g) => <span key={g.guestId} className="name-chip guest">{g.name}</span>)}
                </div>
              </section>
            ))}
            <section className="card flat row" style={{ gap: 8 }}>
              <TeamBadge code={gen.opponentName?.trim()[0]} opponent /><b>{gen.opponentName}</b>
              <span className="small muted">원정팀 · 점수만 기록</span>
            </section>
          </>
        ) : gen ? (
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
        ) : away ? null : (
          <p className="small muted center">Rating 균형을 맞추면서, 최근 자주 같은 팀이었던 조합은 피해서 편성합니다.</p>
        )}
      </main>
      <div className="bar-actions">
        {gen ? (
          <>
            {gen.teamCount === 1 ? (
              <button type="button" className="btn primary lg block" disabled={busy} onClick={confirm}>원정 경기로 일정확정</button>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 8 }}>
                <button type="button" className="btn" disabled={busy} onClick={generate}><Icon name="shuffle" size={18} />다시 섞기</button>
                <button type="button" className="btn primary lg" disabled={busy} onClick={confirm}>일정확정</button>
              </div>
            )}
            <span className="small muted center">확정하면 팀이 공개되고, 프리뷰 기사 검토 화면으로 이동해요</span>
          </>
        ) : (
          <button type="button" className="btn primary lg block" disabled={busy || !canGenerate} onClick={generate}>
            <Icon name={away ? 'users' : 'shuffle'} size={18} />{away ? '원정 팀 만들기' : '팀 만들기'}
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
  const teams = d.teams.filter((t) => !t.opponent)  // 원정팀에는 선수를 배정하지 않는다
  const [lateTeam, setLateTeam] = useState<number>(teams[0]?.sessionTeamId ?? 0)
  const [reason, setReason] = useState('')
  const [opponent, setOpponent] = useState<Opponent | null>(null)  // 바꿀 원정팀(목록에서)

  const onTeam = new Set(teams.flatMap((t) => t.members.map((m) => m.memberId)))
  const candidates = (members.data ?? []).filter((m) => !onTeam.has(m.memberId))
  const teamName = (tid: number | null) => teamLabel(d.teams.find((t) => t.sessionTeamId === tid)) ?? '-'
  const nameOf = (mid: number | null) => (members.data ?? []).find((m) => m.memberId === mid)?.name
  const changeOpponent = async () => {
    if (!opponent) return
    if (await run(() => api.updateSession(d.sessionId, { opponentId: opponent.opponentId }), '원정팀을 바꿨어요')) {
      setOpponent(null)
      reload()
    }
  }

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
        {d.away ? (
          <section className="card stack" style={{ gap: 10 }}>
            <div className="row between"><b>원정팀</b><span className="row" style={{ gap: 6 }}><span className="tag away">원정</span>vs {d.opponentName}</span></div>
            <OpponentPicker label="바꿀 원정팀" value={opponent?.opponentId ?? d.opponentId}
              onChange={(o) => setOpponent(o.opponentId === d.opponentId ? null : o)} />
            <button type="button" className="btn" disabled={busy || !opponent} onClick={changeOpponent}>
              {opponent ? `원정팀 바꾸기 → ${opponent.name}` : '바꿀 원정팀을 고르세요'}
            </button>
          </section>
        ) : null}
        <p className="small muted">{d.away ? '선수를 누르면 팀에서 뺄 수 있어요. 경기별 출전 선수는 경기 화면에서 골라요.' : '선수를 누르면 다른 팀으로 옮기거나 팀에서 뺄 수 있어요.'}</p>
        {teams.map((t) => (
          <section key={t.sessionTeamId} className="card flat stack" style={{ gap: 8 }}>
            <div className="row"><TeamBadge code={t.teamCode} /><b>{teamLabel(t)}</b><span className="small muted">{t.headcount}명</span></div>
            <div className="row wrap" style={{ gap: 6 }}>
              {t.members.map((m) => (
                <button key={m.memberId} type="button" className="name-chip"
                  style={m.assignType === 'MANUAL' ? { outline: '1px dashed var(--accent-ink)' } : undefined}
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
          {teams.length > 1 ? (
            <div className="segmented" role="group" aria-label="들어갈 팀" style={{ gridTemplateColumns: `repeat(${teams.length}, minmax(0, 1fr))` }}>
              {teams.map((t) => (
                <button key={t.sessionTeamId} type="button" aria-pressed={lateTeam === t.sessionTeamId} onClick={() => setLateTeam(t.sessionTeamId)}>
                  {teamLabel(t)}
                </button>
              ))}
            </div>
          ) : null}
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
                {l.action === 'ADD' ? `→ ${teamName(l.toTeamId)} 추가` : l.action === 'MOVE' ? `${teamName(l.fromTeamId)} → ${teamName(l.toTeamId)}` : `${teamName(l.fromTeamId)}에서 제외`}
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
              {teams.filter((t) => t.sessionTeamId !== target.teamId).map((t) => (
                <button key={t.sessionTeamId} type="button" className="btn block" disabled={busy}
                  style={{ borderColor: teamColor(t.teamCode) }}
                  onClick={() => change(target.kind === 'member'
                    ? { action: 'MOVE', memberId: target.id, toTeamId: t.sessionTeamId }
                    : { action: 'MOVE', guestId: target.id, toTeamId: t.sessionTeamId }, `${teamLabel(t)}로 옮겼어요`)}>
                  {teamLabel(t)}로 이동
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
