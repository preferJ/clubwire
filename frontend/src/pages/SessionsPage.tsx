// 일정 탭: 일정 목록

import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { ClubBar, Empty, ErrorBox, Loading } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDate, SESSION_STATUS_LABEL } from '../lib/format'
import { useAsync } from '../lib/hooks'

export function SessionsPage() {
  const { api, slug, isAdmin } = useClub()
  const list = useAsync(() => api.sessions(50), [api])
  useClubEvent((m) => {
    if (m.type === 'SESSION_UPDATED') list.reload()
  })

  return (
    <>
      <ClubBar title="일정" />
      <main className="page tight">
        {isAdmin ? (
          <Link to={`/c/${slug}/admin/sessions/new`} className="btn primary block">
            <Icon name="plus" size={18} stroke={2} />새 일정 만들기
          </Link>
        ) : null}
        {list.error ? (
          <ErrorBox error={list.error} onRetry={list.reload} />
        ) : list.loading && !list.data ? (
          <Loading />
        ) : (list.data ?? []).length === 0 ? (
          <Empty>아직 일정이 없어요.</Empty>
        ) : (
          (list.data ?? []).map((s) => (
            <Link key={s.sessionId} to={`/c/${slug}/sessions/${s.sessionId}`} className="list-row" style={{ minHeight: 64 }}>
              <div className="stack" style={{ gap: 2 }}>
                <b>{fmtDate(s.sessionDate)} · {s.title}</b>
                <span className="small muted">
                  참석 {s.attendeeCount}명{s.guestCount ? ` · 게스트 ${s.guestCount}` : ''}{s.teamCount ? ` · ${s.teamCount}팀` : ''}
                  {s.location ? ` · ${s.location}` : ''}
                </span>
              </div>
              <span className={`status-badge ${s.status === 'IN_PROGRESS' ? 'green' : ''}`}
                style={s.status === 'CANCELLED' ? { textDecoration: 'line-through' } : undefined}>
                {SESSION_STATUS_LABEL[s.status]}
              </span>
            </Link>
          ))
        )}
      </main>
    </>
  )
}
