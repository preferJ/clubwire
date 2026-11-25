import { useState } from 'react'
import { userAuthApi } from '../../api/userAuth'
import { Empty, ErrorBox, Loading, Sheet, TopBar } from '../../components/ui'
import { useClub, useClubEvent } from '../../lib/club'
import { fmtDateTime } from '../../lib/format'
import { useAction, useAsync } from '../../lib/hooks'
import '../../styles/account.css'

type Decision = { kind: 'approve' | 'reject' | 'revoke'; id: number; nickname: string; name: string }

export function AccountsAdminPage() {
  const { slug } = useClub()
  const data = useAsync(() => userAuthApi.accounts(slug), [slug])
  const { busy, run } = useAction()
  const [decision, setDecision] = useState<Decision | null>(null)
  const [tab, setTab] = useState<'pending' | 'linked'>('pending')

  useClubEvent((m) => {
    if (m.type === 'ACCOUNT_UPDATED' || m.type === 'RECONNECTED') data.reload()
  })

  const submit = async () => {
    if (!decision || busy) return
    const target = decision
    const ok = await run(async () => {
      if (target.kind === 'approve') await userAuthApi.approve(slug, target.id)
      else if (target.kind === 'reject') await userAuthApi.reject(slug, target.id)
      else await userAuthApi.revoke(slug, target.id)
      return true
    }, target.kind === 'approve' ? '선수 연결을 승인했어요' : target.kind === 'reject' ? '요청을 반려했어요' : '선수 연결을 해제했어요')
    if (ok) { setDecision(null); data.reload() }
  }

  return (
    <>
      <TopBar title="회원 계정 연결" back={`/c/${slug}/admin`} />
      <div className="tabs" role="tablist" aria-label="계정 연결 상태">
        <button type="button" role="tab" aria-selected={tab === 'pending'} onClick={() => setTab('pending')}>승인 대기 {data.data?.requests.length ?? ''}</button>
        <button type="button" role="tab" aria-selected={tab === 'linked'} onClick={() => setTab('linked')}>연결된 계정 {data.data?.links.length ?? ''}</button>
      </div>
      <main className="page account-page">
        <p className="small muted">본인 요청인지 확인한 뒤 승인하세요. 연결된 회원은 참석한 일정의 경기 진행과 골 기록을 할 수 있습니다.</p>
        {data.error ? <ErrorBox error={data.error} onRetry={data.reload} /> : !data.data ? <Loading /> : tab === 'pending' ? (
          data.data.requests.length ? data.data.requests.map((r) => (
            <section className="card stack account-admin-card" key={r.requestId} aria-label={`${r.name} 선수 연결 요청`}>
              <div className="account-identity"><span className="small muted">카카오 닉네임 · 계정 #{r.userId}</span><b>{r.nickname || '회원'}</b></div>
              <div className="account-identity"><span className="small muted">연결 요청 선수</span><b>{r.name}</b></div>
              <span className="small muted">{fmtDateTime(r.createdAt)} 요청</span>
              <div className="account-actions">
                <button type="button" className="btn" disabled={busy} onClick={() => setDecision({ kind: 'reject', id: r.requestId, nickname: r.nickname, name: r.name })}>반려</button>
                <button type="button" className="btn primary" disabled={busy} onClick={() => setDecision({ kind: 'approve', id: r.requestId, nickname: r.nickname, name: r.name })}>연결 승인</button>
              </div>
            </section>
          )) : <Empty>승인을 기다리는 요청이 없어요.</Empty>
        ) : data.data.links.length ? data.data.links.map((l) => (
          <section className="card stack account-admin-card" key={l.linkId} aria-label={`${l.name} 연결된 계정`}>
            <div className="account-identity"><span className="small muted">선수</span><b>{l.name}</b></div>
            <div className="account-identity"><span className="small muted">카카오 닉네임 · 계정 #{l.userId}</span><b>{l.nickname || '회원'}</b></div>
            <div className="account-user"><span className="small muted">{fmtDateTime(l.approvedAt)} 연결</span>
              <button type="button" className="btn sm" disabled={busy} onClick={() => setDecision({ kind: 'revoke', id: l.linkId, nickname: l.nickname, name: l.name })}>연결 해제</button>
            </div>
          </section>
        )) : <Empty>연결된 계정이 없어요.</Empty>}
      </main>
      <Sheet open={decision !== null} onClose={() => { if (!busy) setDecision(null) }} labelledBy="account-decision-title">
        {decision ? <div className="stack">
          <h2 id="account-decision-title">{decision.kind === 'approve' ? '선수 연결을 승인할까요?' : decision.kind === 'reject' ? '연결 요청을 반려할까요?' : '선수 연결을 해제할까요?'}</h2>
          <p><b>{decision.nickname || '회원'}</b> 계정 · <b>{decision.name}</b> 선수</p>
          <p className="small muted">{decision.kind === 'approve' ? '승인하면 이 계정으로 참석한 일정의 경기 진행과 골 기록을 할 수 있어요.'
            : decision.kind === 'reject' ? '해당 요청으로는 선수 기록에 연결되지 않아요. 사용자가 다시 요청할 수 있습니다.'
              : '이 계정의 경기 조작 권한이 해제됩니다. 선수의 기존 기록은 보존됩니다.'}</p>
          <div className="grid2">
            <button type="button" className="btn" disabled={busy} onClick={() => setDecision(null)}>취소</button>
            <button type="button" className={`btn ${decision.kind === 'approve' ? 'primary' : 'danger'}`} disabled={busy} onClick={() => { void submit() }}>
              {busy ? '처리 중…' : decision.kind === 'approve' ? '승인' : decision.kind === 'reject' ? '반려' : '연결 해제'}
            </button>
          </div>
        </div> : null}
      </Sheet>
    </>
  )
}
