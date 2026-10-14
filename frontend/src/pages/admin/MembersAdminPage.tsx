// 멤버 관리: 추가 / 이름 수정 / 비활성화(삭제하지 않음)

import { useState } from 'react'
import type { Member } from '../../api/types'
import { ErrorBox, Loading, Switch, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAction, useAsync } from '../../lib/hooks'

export function MembersAdminPage() {
  const { api, slug } = useClub()
  const list = useAsync(() => api.members(true), [api])
  const { busy, run } = useAction()
  const [names, setNames] = useState('')

  const add = async () => {
    const items = names.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)
    if (!items.length) return
    const ok = await run(async () => {
      for (const n of items) await api.createMember(n)
      return true
    }, `${items.length}명 추가했어요`)
    if (ok) {
      setNames('')
      list.reload()
    }
  }

  return (
    <>
      <TopBar title="멤버 관리" back={`/c/${slug}/admin`} />
      <main className="page">
        <section className="card stack" style={{ gap: 10 }}>
          <label className="field">새 멤버(여러 명은 쉼표나 줄바꿈으로)
            <textarea className="input" style={{ height: 84, padding: 10, resize: 'vertical' }} value={names}
              onChange={(e) => setNames(e.target.value)} placeholder="김응철, 박민선" />
          </label>
          <button type="button" className="btn primary" disabled={busy || !names.trim()} onClick={add}>추가</button>
          <p className="small muted">새 멤버는 기본 Rating에서 시작하고, 경기 기록이 쌓이며 팀 편성에 반영돼요.</p>
        </section>

        {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : !list.data ? <Loading /> : (
          <section className="section">
            <h2 style={{ fontSize: 15, fontWeight: 700 }}>전체 {list.data.length}명 · 활동 {list.data.filter((m) => m.active).length}명</h2>
            {list.data.map((m) => <MemberRow key={m.memberId} m={m} onSaved={list.reload} />)}
          </section>
        )}
      </main>
    </>
  )
}

function MemberRow({ m, onSaved }: { m: Member; onSaved: () => void }) {
  const { api } = useClub()
  const { busy, run } = useAction()
  const [name, setName] = useState(m.name)
  const dirty = name.trim() !== m.name && name.trim().length > 0
  return (
    <div className="list-row" style={{ minHeight: 60, opacity: m.active ? 1 : 0.6 }}>
      <input className="input" aria-label={`${m.name} 이름`} value={name} onChange={(e) => setName(e.target.value)}
        style={{ height: 40, flex: 1, border: dirty ? '1px solid var(--green)' : '1px solid transparent', background: 'transparent' }} />
      {dirty ? (
        <button type="button" className="btn sm primary" disabled={busy}
          onClick={async () => { if (await run(() => api.updateMember(m.memberId, { name: name.trim() }), '저장했어요')) onSaved() }}>저장</button>
      ) : null}
      <span className="row small muted">
        {m.active ? '활동' : '비활성'}
        <Switch checked={m.active} label={`${m.name} 활동 여부`}
          onChange={async (v) => { if (await run(() => api.updateMember(m.memberId, { active: v }))) onSaved() }} />
      </span>
    </div>
  )
}
