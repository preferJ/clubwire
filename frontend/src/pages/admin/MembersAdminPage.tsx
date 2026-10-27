// 멤버 관리: 추가 / 이름·등번호 수정 / 비활성화(삭제하지 않음)

import { useState } from 'react'
import type { Member } from '../../api/types'
import { ErrorBox, Loading, Switch, TopBar } from '../../components/ui'
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

export function MembersAdminPage() {
  const { api, slug } = useClub()
  const list = useAsync(() => api.members(true), [api])
  const { busy, run } = useAction()
  const [names, setNames] = useState('')

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

  return (
    <>
      <TopBar title="멤버 관리" back={`/c/${slug}/admin`} />
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
            <p className="small muted">등번호는 0~99로 입력하세요. 비우고 저장하면 미지정으로 바뀌어요.</p>
            {list.data.map((m) => <MemberRow key={`${m.memberId}-${m.name}-${m.jerseyNumber}`} m={m} onSaved={list.reload} />)}
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
      {jerseyBad ? <span className="small" style={{ color: 'var(--loss)' }}>등번호는 0~99 사이의 정수로 입력하세요.</span> : null}
      <div className="row between member-admin-actions">
        {dirty ? <button type="button" className="btn sm primary" disabled={busy || jerseyBad || nameBad} onClick={save}>{busy ? '저장 중…' : '저장'}</button> : <span />}
        <span className="row small muted">
          {m.active ? '활동' : '비활성'}
          <Switch checked={m.active} label={`${m.name} 활동 여부`}
            onChange={async (v) => { if (!busy && await run(() => api.updateMember(m.memberId, { active: v }))) onSaved() }} />
        </span>
      </div>
    </div>
  )
}
