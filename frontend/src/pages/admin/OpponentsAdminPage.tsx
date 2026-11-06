// 원정팀 관리: 추가 / 이름 수정(지난 원정 일정 표시도 새 이름) / 숨기기(고르는 목록에서만 빠짐, 지난 전적 유지) · 복원

import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Opponent } from '../../api/types'
import { Empty, ErrorBox, Loading, TeamBadge, TopBar } from '../../components/ui'
import { useClub, useClubEvent } from '../../lib/club'
import { useAction, useAsync } from '../../lib/hooks'
import { useToast } from '../../lib/toast'

type Tab = 'active' | 'hidden'

export function OpponentsAdminPage() {
  const { api, slug } = useClub()
  const list = useAsync(() => api.opponents(true), [api])
  const { busy, run } = useAction()
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('active')
  const [name, setName] = useState('')
  useClubEvent((m) => {
    if (m.type === 'OPPONENTS_UPDATED') list.reload()
  })

  const all = list.data ?? []
  const active = all.filter((o) => o.active !== false)
  const hidden = all.filter((o) => o.active === false)

  const add = async () => {
    const clean = name.trim()
    if (!clean || busy) return
    const before = new Set(active.map((o) => o.opponentId))
    const o = await run(() => api.createOpponent(clean))
    if (!o) return
    // 같은 이름(공백 · 대소문자 무시)이 이미 있으면 새로 만들지 않고 그 팀(숨긴 팀이면 다시 보이게)
    toast.show(before.has(o.opponentId) ? `이미 있는 원정팀이에요: ${o.name}` : `${o.name} 추가했어요`)
    setName('')
    list.reload()
  }

  const setActive = async (o: Opponent, value: boolean) => {
    if (busy) return
    const msg = value ? `${o.name} 복원했어요` : `${o.name} 숨겼어요`
    if (await run(() => api.updateOpponent(o.opponentId, { active: value }), msg)) list.reload()
  }

  return (
    <>
      <TopBar title="원정팀 관리" back={`/c/${slug}/admin`} />
      <div className="tabs" role="tablist" aria-label="원정팀 구분">
        <button type="button" role="tab" aria-selected={tab === 'active'} onClick={() => setTab('active')}>
          원정팀 {list.data ? active.length : ''}
        </button>
        <button type="button" role="tab" aria-selected={tab === 'hidden'} onClick={() => setTab('hidden')}>
          숨긴 팀 {list.data ? hidden.length : ''}
        </button>
      </div>
      {tab === 'active' ? (
        <main className="page">
          <section className="card stack" style={{ gap: 10 }}>
            <label className="field">새 원정팀
              <input className="input" value={name} maxLength={50} placeholder="예: 한강FC" disabled={busy}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void add() }} />
            </label>
            <button type="button" className="btn primary" disabled={busy || !name.trim()} onClick={() => { void add() }}>추가</button>
            <p className="small muted">
              팀 편성에서 원정 경기 상대는 이 목록에서만 골라요. 이름은 띄어쓰기 · 대소문자를 무시하고 비교해서
              ‘한강FC’와 ‘한강 fc’는 같은 팀이에요(같은 상대 전적이 둘로 갈리지 않게).
            </p>
          </section>

          {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : !list.data ? <Loading /> : active.length === 0 ? (
            <Empty>아직 등록된 원정팀이 없어요.</Empty>
          ) : (
            <section className="section">
              <p className="small muted">
                이름을 바꾸면 이 팀과의 지난 원정 일정 · 경기 화면 · 원정 기록도 새 이름으로 보여요(이미 쓴 기사는 그대로).
                더 이상 만나지 않는 팀은 [숨기기]하세요. 고르는 목록에서만 빠지고 지난 전적은 기록실에 그대로 남아요.
              </p>
              {active.map((o) => (
                <OpponentRow key={`${o.opponentId}-${o.name}`} o={o} onSaved={list.reload}
                  onHide={() => { void setActive(o, false) }} hideBusy={busy} />
              ))}
            </section>
          )}
        </main>
      ) : (
        <main className="page">
          <p className="small muted">
            숨긴 팀은 팀 편성의 원정팀 목록에 나오지 않아요. 지난 원정 일정 · 전적은 그대로 보여요.
            [복원]하거나 같은 이름으로 [직접추가]하면 다시 고를 수 있어요.
          </p>
          {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : !list.data ? <Loading />
            : hidden.length === 0 ? <Empty>숨긴 원정팀이 없어요.</Empty> : (
              <section className="section">
                {hidden.map((o) => (
                  <div key={o.opponentId} className="list-row opponent-hidden-row">
                    <span className="row" style={{ gap: 8, minWidth: 0 }}>
                      <TeamBadge code={o.name.trim()[0]} size={24} opponent />
                      <span className="stack" style={{ gap: 0, minWidth: 0 }}>
                        <b style={{ overflowWrap: 'anywhere' }}>{o.name}</b>
                        <span className="small muted">원정 {o.sessions ?? 0}번</span>
                      </span>
                    </span>
                    <button type="button" className="btn sm" disabled={busy} onClick={() => { void setActive(o, true) }}>복원</button>
                  </div>
                ))}
              </section>
            )}
        </main>
      )}
    </>
  )
}

function OpponentRow({ o, onSaved, onHide, hideBusy }: { o: Opponent; onSaved: () => void; onHide: () => void; hideBusy: boolean }) {
  const { api, slug } = useClub()
  const { busy, run } = useAction()
  const [name, setName] = useState(o.name)
  const clean = name.trim().split(/\s+/).join(' ')
  const nameBad = clean.length === 0
  const dirty = clean !== o.name
  const save = async () => {
    if (busy || nameBad || !dirty) return
    if (await run(() => api.updateOpponent(o.opponentId, { name: clean }), '이름을 바꿨어요')) onSaved()
  }

  return (
    <div className="list-row opponent-admin-row">
      <div className="row" style={{ gap: 10 }}>
        <TeamBadge code={(clean || o.name)[0]} size={28} opponent />
        <label className="field" style={{ flex: 1, minWidth: 0 }}>이름
          <input className="input" aria-label={`${o.name} 이름`} value={name} disabled={busy} maxLength={50}
            aria-invalid={nameBad} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void save() }} />
        </label>
      </div>
      <div className="row between opponent-admin-actions">
        <span className="row" style={{ gap: 8 }}>
          {dirty ? (
            <>
              <button type="button" className="btn sm primary" disabled={busy || nameBad} onClick={() => { void save() }}>{busy ? '저장 중…' : '저장'}</button>
              <button type="button" className="btn sm" disabled={busy} onClick={() => setName(o.name)}>되돌리기</button>
            </>
          ) : o.sessions ? (
            <Link to={`/c/${slug}/records/away/${o.opponentId}`} className="small">원정 {o.sessions}번 · 기록 보기</Link>
          ) : (
            <span className="small muted">아직 원정 일정 없음</span>
          )}
        </span>
        <button type="button" className="btn sm" disabled={busy || hideBusy} onClick={onHide}>숨기기</button>
      </div>
    </div>
  )
}
