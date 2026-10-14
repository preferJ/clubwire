// 멤버 탭: 멤버 목록 → 선수 기록

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { AdminButton, Empty, ErrorBox, Loading } from '../components/ui'
import { useClub } from '../lib/club'
import { initials, pct } from '../lib/format'
import { useAsync } from '../lib/hooks'

export function MembersPage() {
  const { api, slug, isAdmin } = useClub()
  const stats = useAsync(() => api.memberStats(), [api])
  const [q, setQ] = useState('')
  const list = (stats.data ?? []).filter((m) => m.active && m.name.includes(q.trim()))

  return (
    <>
      <header className="home-head">
        <h1 className="club-name">멤버</h1>
        <AdminButton />
      </header>
      <main className="page tight">
        <label className="check" style={{ gap: 8 }}>
          <Icon name="search" size={18} />
          <input type="search" placeholder="이름 검색" aria-label="이름 검색" value={q} onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, border: 0, outline: 'none', background: 'transparent', fontSize: 15 }} />
        </label>
        {isAdmin ? <Link to={`/c/${slug}/admin/members`} className="btn sm">멤버 관리(추가 · 비활성화)</Link> : null}
        {stats.error ? (
          <ErrorBox error={stats.error} onRetry={stats.reload} />
        ) : stats.loading && !stats.data ? (
          <Loading />
        ) : list.length === 0 ? (
          <Empty>멤버가 없어요.</Empty>
        ) : (
          list.map((m) => (
            <Link key={m.memberId} to={`/c/${slug}/members/${m.memberId}`} className="list-row" style={{ minHeight: 60 }}>
              <div className="row" style={{ gap: 12 }}>
                <span className="avatar" style={{ width: 40, height: 40, fontSize: 13 }}>{initials(m.name)}</span>
                <div className="stack" style={{ gap: 0 }}>
                  <b>{m.name}</b>
                  <span className="small muted">{m.games}경기 · 승률 {pct(m.winRate)} · {m.goals}골 {m.assists}도움</span>
                </div>
              </div>
              {m.mvpCount ? <span className="tag gold">MVP ×{m.mvpCount}</span> : <Icon name="chevron" />}
            </Link>
          ))
        )}
      </main>
    </>
  )
}
