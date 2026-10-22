// A02 일정 만들기 · 참석 (새 일정 / 모집 중 일정의 참석자 수정)

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Icon } from '../../components/Icon'
import { ErrorBox, Loading, Stepper, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { todayIso } from '../../lib/format'
import { useAction, useAsync } from '../../lib/hooks'

export function SessionFormPage() {
  const { sessionId } = useParams()
  const editId = sessionId ? Number(sessionId) : null
  const { api, slug } = useClub()
  const nav = useNavigate()
  const { busy, run } = useAction()
  const members = useAsync(() => api.members(), [api])
  const existing = useAsync(() => (editId ? api.session(editId) : Promise.resolve(null)), [api, editId])

  const [date, setDate] = useState(nextSaturday())
  const [title, setTitle] = useState('')
  const [location, setLocation] = useState('')
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [guests, setGuests] = useState(0)
  const [q, setQ] = useState('')

  useEffect(() => {
    const s = existing.data
    if (!s) return
    setDate(s.sessionDate)
    setTitle(s.title)
    setLocation(s.location ?? '')
    setPicked(new Set(s.attendees.map((a) => a.memberId)))
    setGuests(s.guests.length)
  }, [existing.data])

  const list = useMemo(() => (members.data ?? []).filter((m) => m.name.includes(q.trim())), [members.data, q])
  const toggle = (id: number) => setPicked((p) => {
    const n = new Set(p)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })

  const save = async () => {
    const ok = await run(async () => {
      let id = editId
      if (!id) {
        const s = await api.createSession({ sessionDate: date, title: title.trim() || undefined, location: location.trim() || undefined })
        id = s.sessionId
      } else {
        await api.updateSession(id, { sessionDate: date, title: title.trim() || undefined, location: location.trim() || undefined })
      }
      const before = new Set(existing.data?.attendees.map((a) => a.memberId) ?? [])
      const add = [...picked].filter((x) => !before.has(x))
      const remove = [...before].filter((x) => !picked.has(x))
      if (add.length) await api.addAttendees(id, add)
      for (const mId of remove) await api.removeAttendee(id, mId)
      const curGuests = existing.data?.guests ?? []
      if (guests > curGuests.length) await api.addGuests(id, guests - curGuests.length)
      for (const g of curGuests.slice(guests)) await api.removeGuest(id, g.guestId)
      return id
    }, '저장했어요')
    if (ok) nav(`/c/${slug}/admin/sessions/${ok}/teams`)
  }

  if (members.error) return <ErrorBox error={members.error} onRetry={members.reload} />
  if (!members.data || (editId && !existing.data)) return <div className="page"><Loading /></div>

  const headcount = picked.size + guests
  return (
    <>
      <TopBar title={editId ? '참석자 수정' : '새 일정'} back right={<span className="admin-pill">관리자 모드</span>} />
      <main className="page">
        <div className="grid2">
          <label className="field">날짜<input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <label className="field">장소<input className="input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="장소" /></label>
        </div>
        <label className="field">제목<input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="비우면 '날짜 정기 경기'" /></label>

        <section className="section">
          <div className="row between">
            <h2 style={{ fontSize: 15, fontWeight: 700 }}>참석 <span style={{ color: 'var(--accent-ink)' }}>{picked.size}</span><span className="muted" style={{ fontWeight: 500 }}> / {members.data.length}명</span></h2>
            <button type="button" className="btn sm" onClick={() => setPicked(picked.size === members.data!.length ? new Set() : new Set(members.data!.map((m) => m.memberId)))}>
              {picked.size === members.data.length ? '전체 해제' : '전체 선택'}
            </button>
          </div>
          <label className="check" style={{ gap: 8 }}>
            <Icon name="search" size={18} />
            <input type="search" placeholder="이름 검색" aria-label="이름 검색" value={q} onChange={(e) => setQ(e.target.value)}
              style={{ flex: 1, border: 0, outline: 'none', background: 'transparent', fontSize: 15 }} />
          </label>
          <div className="grid2" style={{ gap: 6 }}>
            {list.map((m) => (
              <label key={m.memberId} className="check">
                <input type="checkbox" checked={picked.has(m.memberId)} onChange={() => toggle(m.memberId)} />
                {m.name}
              </label>
            ))}
          </div>
          {members.data.length === 0 ? <p className="small muted">먼저 멤버를 등록하세요(관리자 메뉴 → 멤버 관리).</p> : null}
        </section>

        <section className="card flat row between">
          <div className="stack" style={{ gap: 2 }}>
            <b>게스트</b>
            <span className="small muted">인원수에만 포함, 기록은 남지 않아요</span>
          </div>
          <Stepper value={guests} onChange={setGuests} max={20} label="게스트 수" />
        </section>
      </main>
      <div className="bar-actions">
        <button type="button" className="btn primary lg block" disabled={busy || headcount < 4} onClick={save}>
          {busy ? '저장 중…' : `저장하고 팀 편성으로 · 총 ${headcount}명`}
        </button>
      </div>
    </>
  )
}

function nextSaturday(): string {
  const d = new Date()
  d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7))
  const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return iso < todayIso() ? todayIso() : iso
}
