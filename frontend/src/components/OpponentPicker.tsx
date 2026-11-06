// 원정팀 고르기: 원정팀 목록에서만 선택. 목록에 없으면 아래 [직접추가]로 같은 화면에서 등록하고 바로 선택한다.

import { useEffect, useState } from 'react'
import type { Opponent } from '../api/types'
import { useClub } from '../lib/club'
import { useAction, useAsync } from '../lib/hooks'
import { Loading, TeamBadge } from './ui'

export function OpponentPicker({ value, onChange, label = '원정팀' }: {
  value: number | null
  onChange: (o: Opponent) => void
  label?: string
}) {
  const { api } = useClub()
  const list = useAsync(() => api.opponents(), [api])
  const { busy, run } = useAction()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  useEffect(() => {
    if (!adding) setName('')
  }, [adding])

  const add = async () => {
    const o = await run(() => api.createOpponent(name.trim()))
    if (!o) return
    list.setData([...(list.data ?? []).filter((x) => x.opponentId !== o.opponentId), o]
      .sort((a, b) => a.name.localeCompare(b.name, 'ko')))
    onChange(o)  // 추가한 팀(같은 이름이 있으면 그 팀)을 바로 선택
    setAdding(false)
  }

  const items = list.data ?? []
  return (
    <section className="stack opponent-picker" style={{ gap: 8 }} aria-label={`${label} 고르기`}>
      <h3 className="small muted" style={{ fontWeight: 700 }}>{label} 목록에서 고르기</h3>
      {list.error ? <p className="small muted">원정팀 목록을 불러오지 못했어요.</p> : !list.data ? <Loading rows={1} /> : items.length === 0 ? (
        <p className="small muted">아직 등록된 원정팀이 없어요. 아래 [직접추가]로 만들어 주세요.</p>
      ) : (
        <div className="grid2" role="radiogroup" aria-label={label} style={{ gap: 6 }}>
          {items.map((o) => (
            <button key={o.opponentId} type="button" className="pick opponent-pick" role="radio" aria-checked={value === o.opponentId}
              aria-pressed={value === o.opponentId} onClick={() => onChange(o)}>
              <TeamBadge code={o.name.trim()[0]} size={22} opponent />
              <span>{o.name}</span>
            </button>
          ))}
        </div>
      )}
      {adding ? (
        <div className="row" style={{ gap: 6 }}>
          <input className="input" style={{ flex: 1 }} value={name} maxLength={50} autoFocus placeholder="새 원정팀 이름"
            aria-label="새 원정팀 이름" onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && name.trim() && !busy) add() }} />
          <button type="button" className="btn primary" disabled={busy || !name.trim()} onClick={add}>추가</button>
          <button type="button" className="btn" disabled={busy} onClick={() => setAdding(false)}>취소</button>
        </div>
      ) : (
        <button type="button" className="btn block" onClick={() => setAdding(true)}>+ 직접추가</button>
      )}
    </section>
  )
}
