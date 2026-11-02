// 멤버 관리: 추가 / 이름·등번호 수정 / 비활성화 / 삭제(목록에서만 숨김, 기록은 보존) · 삭제한 선수 복원

import { useState } from 'react'
import { errorMessage } from '../../api/client'
import type { Member } from '../../api/types'
import { Empty, ErrorBox, Loading, Sheet, Switch, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAction, useAsync } from '../../lib/hooks'
import '../../styles/member-numbers.css'

/** "이영희 1081", "1\t이영희\t1081", "홍길동" 형태를 이름 + 시작 Rating으로 */
export function parseMembers(text: string): { name: string; rating?: number }[] {
  return text.split(/[\n,]/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const tokens = line.split(/\s+/)
    const isNum = (t: string) => /^\d+(\.\d+)?$/.test(t)
    if (tokens.length > 2 && isNum(tokens[0])) tokens.shift() // 앞 순위 번호
    const rating = tokens.length > 1 && isNum(tokens[tokens.length - 1]) ? Number(tokens.pop()) : undefined
    return { name: tokens.join(' '), rating }
  }).filter((x) => x.name)
}

type Tab = 'members' | 'deleted'

export function MembersAdminPage() {
  const { api, slug } = useClub()
  const list = useAsync(() => api.members(true), [api])
  const deleted = useAsync(() => api.deletedMembers(), [api])
  const { busy, run } = useAction()
  const [names, setNames] = useState('')
  const [tab, setTab] = useState<Tab>('members')
  const [removal, setRemoval] = useState<Member | null>(null)
  const [removeError, setRemoveError] = useState('')

  const reloadAll = () => {
    list.reload()
    deleted.reload()
  }

  const add = async () => {
    const items = parseMembers(names)
    if (!items.length) return
    const ok = await run(async () => {
      for (const it of items) await api.createMember(it.name, it.rating)
      return true
    }, `${items.length}명 추가했어요`)
    if (ok) {
      setNames('')
      list.reload()
    }
  }

  const askRemove = (m: Member) => {
    setRemoveError('')
    setRemoval(m)
  }
  const closeRemoval = () => {
    if (!busy) setRemoval(null)
  }
  const remove = async () => {
    if (!removal || busy) return
    setRemoveError('')
    const target = removal
    const done = await run(async () => {
      try { return await api.deleteMember(target.memberId) }
      catch (error) { setRemoveError(errorMessage(error)); throw error }
    }, `${target.name} 선수를 삭제했어요`)
    if (done) {
      setRemoval(null)
      reloadAll()
    }
  }
  const restore = async (m: Member) => {
    if (busy) return
    if (await run(() => api.restoreMember(m.memberId), `${m.name} 선수를 복원했어요`)) reloadAll()
  }

  return (
    <>
      <TopBar title="멤버 관리" back={`/c/${slug}/admin`} />
      <div className="tabs" role="tablist" aria-label="멤버 구분">
        <button type="button" role="tab" aria-selected={tab === 'members'} onClick={() => setTab('members')}>
          선수 {list.data ? list.data.length : ''}
        </button>
        <button type="button" role="tab" aria-selected={tab === 'deleted'} onClick={() => setTab('deleted')}>
          삭제한 선수 {deleted.data ? deleted.data.length : ''}
        </button>
      </div>
      {tab === 'members' ? (
        <main className="page">
          <section className="card stack" style={{ gap: 10 }}>
            <label className="field">새 멤버(여러 명은 쉼표나 줄바꿈으로)
              <textarea className="input" style={{ height: 84, padding: 10, resize: 'vertical' }} value={names}
                onChange={(e) => setNames(e.target.value)} placeholder={'홍길동, 김철수\n이영희 1081'} />
            </label>
            <button type="button" className="btn primary" disabled={busy || !names.trim()} onClick={add}>추가</button>
            <p className="small muted">
              이름 뒤에 숫자를 붙이면 그 값이 시작 Rating이 돼요(예: 이영희 1081). 순위표를 그대로 붙여 넣어도 앞의 순위 숫자는 무시해요.
              숫자가 없으면 기본 Rating에서 시작해요.
              등번호는 추가 후 아래 목록에서 입력할 수 있어요.
            </p>
          </section>

          {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : !list.data ? <Loading /> : (
            <section className="section">
              <h2 style={{ fontSize: 15, fontWeight: 700 }}>전체 {list.data.length}명 · 활동 {list.data.filter((m) => m.active).length}명</h2>
              <p className="small muted">
                등번호는 0~99로 입력하세요. 비우고 저장하면 미지정으로 바뀌어요.
                쉬는 선수는 활동을 끄고(비활성), 그만둔 선수는 [삭제]하세요. 삭제해도 지난 경기 · 기사 기록은 남아요.
              </p>
              {list.data.map((m) => (
                <MemberRow key={`${m.memberId}-${m.name}-${m.jerseyNumber}`} m={m} onSaved={list.reload} onRemove={() => askRemove(m)} />
              ))}
            </section>
          )}
        </main>
      ) : (
        <main className="page">
          <p className="small muted">
            삭제한 선수는 선수단 · 참석 선택 · 기록 순위 · 이달의 MVP 후보에 나오지 않아요. 지난 경기 · 기사 · 수상 기록 속 이름은 그대로 보여요.
            [복원]하면 삭제 전 상태(활동/비활성)로 돌아가요.
          </p>
          {deleted.error ? <ErrorBox error={deleted.error} onRetry={deleted.reload} /> : !deleted.data ? <Loading />
            : deleted.data.length === 0 ? <Empty>삭제한 선수가 없어요.</Empty> : (
              <section className="section">
                {deleted.data.map((m) => (
                  <div key={m.memberId} className="list-row member-deleted-row">
                    <span className="member-name-line">
                      {m.jerseyNumber != null ? <span className="member-jersey">{m.jerseyNumber}</span> : null}
                      <b>{m.name}</b>
                    </span>
                    <span className="row" style={{ gap: 8 }}>
                      <span className="small muted">{fmtDeletedAt(m.deletedAt)} 삭제</span>
                      <button type="button" className="btn sm" disabled={busy} onClick={() => { void restore(m) }}>복원</button>
                    </span>
                  </div>
                ))}
              </section>
            )}
        </main>
      )}

      <Sheet open={removal !== null} onClose={closeRemoval} labelledBy="member-remove-title">
        {removal ? (
          <div className="stack">
            <h2 id="member-remove-title">{removal.name} 선수를 삭제할까요?</h2>
            <p className="small muted">
              선수단 · 참석 선택 · 기록 순위 · 이달의 MVP 후보에서 사라져요.
              지난 경기 · 기사 · 수상 기록은 그대로 남고, ‘삭제한 선수’에서 언제든 복원할 수 있어요.
            </p>
            {removeError ? <p role="alert" className="small" style={{ color: 'var(--warn-ink)' }}>{removeError}</p> : null}
            <div className="grid2">
              <button type="button" className="btn" disabled={busy} onClick={closeRemoval}>취소</button>
              <button type="button" className="btn danger" disabled={busy} onClick={() => { void remove() }}>{busy ? '삭제 중…' : '삭제하기'}</button>
            </div>
          </div>
        ) : null}
      </Sheet>
    </>
  )
}

/** 삭제 시각(UTC ISO) → 내 화면 기준 'M/D' */
function fmtDeletedAt(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function MemberRow({ m, onSaved, onRemove }: { m: Member; onSaved: () => void; onRemove: () => void }) {
  const { api } = useClub()
  const { busy, run } = useAction()
  const [name, setName] = useState(m.name)
  const [jersey, setJersey] = useState(m.jerseyNumber != null ? String(m.jerseyNumber) : '')
  const jerseyNumber = jersey === '' ? null : Number(jersey)
  const jerseyBad = jersey !== '' && !/^\d{1,2}$/.test(jersey)
  const dirty = name.trim() !== m.name || jerseyNumber !== (m.jerseyNumber ?? null)
  const nameBad = name.trim().length === 0
  const save = async () => {
    if (busy || jerseyBad || nameBad) return
    if (await run(() => api.updateMember(m.memberId, { name: name.trim(), jerseyNumber }), '저장했어요')) onSaved()
  }

  return (
    <div className="list-row member-admin-row" style={{ opacity: m.active ? 1 : 0.6 }}>
      <div className="member-admin-fields">
        <label className="field">이름
          <input className="input" aria-label={`${m.name} 이름`} value={name} disabled={busy} maxLength={50}
            aria-invalid={nameBad} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">등번호
          <input className="input" aria-label={`${m.name} 등번호`} inputMode="numeric" pattern="[0-9]{1,2}"
            placeholder="미지정" value={jersey} disabled={busy} aria-invalid={jerseyBad} onChange={(e) => setJersey(e.target.value)} />
        </label>
      </div>
      {jerseyBad ? <span className="small" style={{ color: 'var(--danger-ink)' }}>등번호는 0~99 사이의 정수로 입력하세요.</span> : null}
      <div className="row between member-admin-actions">
        {dirty ? <button type="button" className="btn sm primary" disabled={busy || jerseyBad || nameBad} onClick={save}>{busy ? '저장 중…' : '저장'}</button> : <span />}
        <span className="row small muted" style={{ gap: 8 }}>
          {m.active ? '활동' : '비활성'}
          <Switch checked={m.active} label={`${m.name} 활동 여부`}
            onChange={async (v) => { if (!busy && await run(() => api.updateMember(m.memberId, { active: v }))) onSaved() }} />
          <button type="button" className="btn sm danger" aria-label={`${m.name} 삭제`} disabled={busy} onClick={onRemove}>삭제</button>
        </span>
      </div>
    </div>
  )
}
