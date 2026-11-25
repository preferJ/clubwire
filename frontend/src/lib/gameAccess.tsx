import { Link } from 'react-router-dom'
import { request } from '../api/client'
import { useClub, useClubEvent } from './club'
import { useAsync } from './hooks'
import { useUserAuth } from './userAuth'

interface Access { sessionId: number; canControl: boolean; reason: string | null; viewer: string }

export function useSessionAccess(sessionId?: number) {
  const { slug, isAdmin } = useClub()
  const auth = useUserAuth()
  const viewer = `${slug}:${auth.user?.userId ?? ''}:${isAdmin}`
  const access = useAsync(async (): Promise<Access | null> => sessionId
    ? { ...await request<Omit<Access, 'viewer'>>(slug, 'GET', `/sessions/${sessionId}/access`), viewer }
    : null, [slug, sessionId, viewer])
  useClubEvent((m) => {
    if (m.type === 'RECONNECTED' || m.type === 'ACCOUNT_UPDATED'
      || ((m.type === 'SESSION_UPDATED' || m.type === 'TEAMS_UPDATED') && m.sessionId === sessionId)) access.reload()
  })
  const current = access.data?.sessionId === sessionId && access.data?.viewer === viewer ? access.data : null
  return { canControl: isAdmin || (!access.error && current?.canControl === true),
    loading: auth.loading || (!current && access.loading), reason: current?.reason,
    error: access.error, reload: access.reload }
}

export function GameAccessNotice({ access }: { access: ReturnType<typeof useSessionAccess> }) {
  const { slug } = useClub()
  if (access.canControl || access.reason === 'SESSION_CLOSED') return null
  if (access.loading) return <p className="small muted">경기 참여 권한 확인 중…</p>
  if (access.error) return <button type="button" className="btn sm" onClick={access.reload}>경기 참여 권한 다시 확인</button>
  return (
    <div className="notice gray" style={{ flexDirection: 'column', gap: 8 }}>
      <p>{access.reason === 'ATTENDANCE_REQUIRED' ? '이 일정의 참석자만 경기를 조작할 수 있어요.'
        : access.reason === 'LINK_REQUIRED' ? '선수 계정 연결이 승인되면 참석한 일정을 진행할 수 있어요.'
          : '카카오 로그인 후 선수 계정을 연결하면 참석한 일정을 진행할 수 있어요.'}</p>
      <Link to={`/c/${slug}/account`} className="btn sm">내 계정 확인</Link>
    </div>
  )
}
