// A07 일정마감: 오늘 요약 → [일정마감](수정 잠금 + 자동 타이틀 + 마감 기사). MVP 선정은 2026-10-22 제거

import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Icon } from '../../components/Icon'
import { ErrorBox, Loading, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { fmtDate, teamColor } from '../../lib/format'
import { useAction, useAsync } from '../../lib/hooks'

export function ClosePage() {
  const { sessionId } = useParams()
  const id = Number(sessionId)
  const { api, slug } = useClub()
  const nav = useNavigate()
  const { busy, run } = useAction()
  const summary = useAsync(() => api.sessionSummary(id), [api, id])
  const session = useAsync(() => api.session(id), [api, id])
  const titles = useAsync(() => api.titleTypes(), [api])

  const s = summary.data
  const d = session.data
  if (summary.error) return <ErrorBox error={summary.error} onRetry={summary.reload} />
  if (!s || !d) return <div className="page"><Loading /></div>
  const autoTitles = (titles.data ?? []).filter((t) => t.awardMethod === 'AUTO' && t.active)

  const close = async () => {
    if (!window.confirm('일정을 마감할까요? 마감 후에는 이 일정의 기록을 고칠 수 없어요.')) return
    const done = await run(() => api.closeSession(id), '일정을 마감했어요. 마감 기사를 만들고 있어요')
    if (done) nav(`/c/${slug}/admin/articles`)
  }

  const closed = d.status === 'CLOSED'
  return (
    <>
      <TopBar title={`일정마감 · ${fmtDate(d.sessionDate, false)}`} back={`/c/${slug}/sessions/${id}`} right={<span className="admin-pill">관리자 모드</span>} />
      <main className="page">
        <section className="card stack" style={{ gap: 10 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>오늘 기록</h2>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(3, s.teamRecords.length || 1)}, minmax(0, 1fr))`, gap: 6 }}>
            {s.teamRecords.map((r) => (
              <div key={r.sessionTeamId} className="stack center" style={{ gap: 2, padding: '10px 0', borderRadius: 10, background: 'var(--bg)' }}>
                <span className="small" style={{ color: teamColor(r.teamCode), fontWeight: 700 }}>TEAM {r.teamCode}</span>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{r.wins}승 {r.draws}무 {r.losses}패</span>
              </div>
            ))}
          </div>
          <span style={{ fontSize: 13 }} className="muted">
            {s.finishedCount}경기 · 총 {s.totalGoals}골
            {s.topScorers[0] ? ` · 최다 득점 ${s.topScorers[0].name} ${s.topScorers[0].count}골` : ''}
            {s.topAssists[0] ? ` · 최다 도움 ${s.topAssists[0].name} ${s.topAssists[0].count}도움` : ''}
          </span>
        </section>

        {s.activeCount > 0 ? (
          <div className="notice warn"><Icon name="warn" />진행 중인 경기가 있어요. 경기를 먼저 종료해야 마감할 수 있어요.</div>
        ) : null}

        <section className="card flat stack" style={{ gap: 6, fontSize: 13 }}>
          <h2 className="small muted" style={{ fontWeight: 700 }}>마감하면 자동으로</h2>
          {s.unfinalizedCount ? <Check>확정 안 된 {s.unfinalizedCount}경기를 확정합니다</Check> : null}
          {s.readyCount ? <Check>시작 안 한 대기 경기 {s.readyCount}개는 취소합니다</Check> : null}
          {autoTitles.length ? <Check>이번 주 {autoTitles.map((t) => t.titleName.replace('이주의 ', '')).join(' · ')}을 다시 집계합니다</Check> : null}
          <Check>마감 기사를 작성합니다{' '}(게시 방식은 설정을 따름)</Check>
        </section>

        <div className="notice warn" role="note">
          <Icon name="warn" />
          <span>마감 후에는 이 일정의 팀 · 경기 · 골 기록을 고칠 수 없어요. 앞선 일정이 열려 있으면 마감되지 않아요.</span>
        </div>
      </main>
      <div className="bar-actions">
        <button type="button" className="btn dark lg block" disabled={busy || closed || s.activeCount > 0} onClick={close}>
          {closed ? '이미 마감된 일정' : busy ? '마감 중…' : '일정마감'}
        </button>
      </div>
    </>
  )
}

function Check({ children }: { children: ReactNode }) {
  return (
    <div className="row" style={{ alignItems: 'flex-start' }}>
      <span style={{ color: 'var(--green)', marginTop: 2 }}><Icon name="check" size={16} stroke={2} /></span>
      <span>{children}</span>
    </div>
  )
}
