import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { userAuthApi } from '../api/userAuth'
import { ErrorBox, Loading, TopBar } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { useAction, useAsync } from '../lib/hooks'
import { useUserAuth } from '../lib/userAuth'
import '../styles/account.css'

export function AccountPage() {
  const { slug, club } = useClub()
  const auth = useUserAuth()
  const [params] = useSearchParams()
  const { busy, run } = useAction()

  const logout = () => run(async () => { await auth.logout(); return true }, '로그아웃했어요')
  return (
    <>
      <TopBar title="내 계정" back={`/c/${slug}`} />
      <main className="page account-page">
        {auth.loading ? <Loading rows={2} /> : auth.error ? <ErrorBox error={auth.error} onRetry={auth.refresh} /> : !auth.user ? (
          <section className="card stack account-intro">
            <h2>카카오로 로그인</h2>
            <p className="muted">{club?.clubName ?? '우리 팀'}의 선수 기록을 내 계정에 연결하세요. 승인 후 참석한 일정의 경기 진행과 골 기록을 할 수 있어요.</p>
            {params.get('login') === 'failed' ? <p className="notice warn" role="alert">로그인을 완료하지 못했어요. 다시 시도해 주세요.</p> : null}
            {auth.configured ? (
              <a className="btn kakao-login" href={userAuthApi.loginUrl(slug)}><KakaoIcon />카카오 로그인</a>
            ) : <p className="notice gray">카카오 로그인을 준비 중입니다.</p>}
            <p className="small muted">로그인하지 않아도 경기와 기사, 선수 기록을 볼 수 있어요.</p>
          </section>
        ) : (
          <>
            <section className="card account-user">
              <div><span className="small muted">카카오 계정</span><h2>{auth.user.nickname || '회원'}</h2></div>
              <button type="button" className="btn sm" disabled={busy} onClick={() => { void logout() }}>로그아웃</button>
            </section>
            <AccountConnection key={`${slug}-${auth.user.userId}`} userId={auth.user.userId} />
          </>
        )}
      </main>
    </>
  )
}

function AccountConnection({ userId }: { userId: number }) {
  const { api, slug } = useClub()
  const auth = useUserAuth()
  const account = useAsync(() => userAuthApi.account(slug), [slug, userId])
  const players = useAsync(() => api.members(true), [api])
  const { busy, run } = useAction()
  const [memberId, setMemberId] = useState('')

  useClubEvent((m) => {
    if (m.type === 'ACCOUNT_UPDATED' || m.type === 'RECONNECTED') account.reload()
  })

  const request = async () => {
    if (!memberId || busy) return
    const done = await run(async () => { await userAuthApi.requestLink(slug, Number(memberId)); return true }, '선수 연결을 요청했어요')
    if (done) { setMemberId(''); account.reload() }
  }
  const cancel = async () => {
    if (await run(async () => { await userAuthApi.cancelRequest(slug); return true }, '요청을 취소했어요')) account.reload()
  }

  if (account.error) return <ErrorBox error={account.error} onRetry={account.reload} />
  if (!account.data) return <Loading rows={2} />
  const d = account.data
  if (!d.user || d.user.userId !== userId) return (
    <section className="card stack"><p>로그인 정보를 다시 확인해 주세요.</p><button type="button" className="btn" onClick={() => { void auth.refresh() }}>다시 확인</button></section>
  )
  if (d.link) return (
    <section className="card stack" aria-label="연결된 선수">
      <span className="tag green account-tag">선수 연결 완료</span>
      <h2>{d.link.name}</h2>
      <p className="small muted">참석 명단에 등록된 일정에서 골 기록과 경기 진행을 할 수 있어요. 첫 경기 시작과 기록 확정은 관리자가 합니다.</p>
      <Link className="btn" to={`/c/${slug}/members/${d.link.memberId}`}>내 선수 기록 보기</Link>
      <p className="small muted">다른 선수로 연결해야 한다면 관리자에게 연결 해제를 요청해 주세요.</p>
    </section>
  )
  if (d.request?.status === 'PENDING') return (
    <section className="card stack" aria-label="선수 연결 승인 대기" role="status">
      <span className="tag gold account-tag">승인 대기</span>
      <h2>{d.request.name}</h2>
      <p className="small muted">관리자가 본인 확인 후 선수 기록을 연결해 줍니다. 승인 전에는 경기 조작을 할 수 없어요.</p>
      <div className="account-actions">
        <button type="button" className="btn" disabled={busy} onClick={account.reload}>승인 상태 확인</button>
        <button type="button" className="btn" disabled={busy} onClick={() => { void cancel() }}>요청 취소</button>
      </div>
    </section>
  )
  return (
    <section className="card stack" aria-label="선수 연결 요청">
      <h2>내 선수 기록 연결</h2>
      {d.request?.status === 'REJECTED' ? <p className="notice warn">이전 연결 요청이 승인되지 않았어요. 본인 이름을 다시 확인해 주세요.</p>
        : d.request?.status === 'REVOKED' ? <p className="notice gray">이전 선수 연결이 해제되었습니다.</p> : null}
      <p className="small muted">선수단에서 본인을 선택해 주세요. 관리자가 승인하면 기존 경기 기록이 내 계정에 연결됩니다.</p>
      {players.error ? <ErrorBox error={players.error} onRetry={players.reload} /> : !players.data ? <Loading rows={1} /> : !players.data.length ? (
        <p className="notice gray">등록된 선수가 없어요. 관리자에게 선수 등록을 요청해 주세요.</p>
      ) : (
        <>
          <label className="field">내 이름
            <select className="input" value={memberId} disabled={busy} onChange={(e) => setMemberId(e.target.value)}>
              <option value="">선수를 선택하세요</option>
              {players.data.filter((p) => !p.deleted).map((p) => (
                <option key={p.memberId} value={p.memberId}>{p.name}{p.jerseyNumber != null ? ` · ${p.jerseyNumber}번` : ''}{p.birthYear ? ` · ${p.birthYear}년생` : ''}{!p.active ? ' · 비활성' : ''}</option>
              ))}
            </select>
          </label>
          <button type="button" className="btn primary" disabled={busy || !memberId} onClick={() => { void request() }}>{busy ? '요청 중…' : '선수 연결 요청'}</button>
          <p className="small muted">이름이 없다면 관리자에게 선수 등록을 요청해 주세요.</p>
        </>
      )}
    </section>
  )
}

function KakaoIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3C6.5 3 2 6.4 2 10.6c0 2.7 1.9 5.1 4.7 6.4l-1 3.6c-.1.3.2.5.5.3l4.2-2.8 1.6.1c5.5 0 10-3.4 10-7.6S17.5 3 12 3Z" /></svg>
}
