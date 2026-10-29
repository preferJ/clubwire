import { ApiError } from './client'
import { clearSuperAdminToken, getSuperAdminToken } from '../lib/superadminAuthStore'

export interface ManagedClub {
  clubId: number
  clubSlug: string
  clubName: string
  sportType: string
  timezone: string
  active: boolean
  memberCount: number
  sessionCount: number
  articleCount: number
}

export interface ManagedClubCreate {
  clubSlug: string
  clubName: string
  adminPin: string
  sportType?: string
  timezone?: string
}

export interface ManagedClubUpdate {
  clubSlug?: string
  clubName?: string
  adminPin?: string
  timezone?: string
}

interface SuperAdminAuth {
  accessToken: string
  tokenType: string
  expiresAt: string
}

async function request<T>(method: 'GET' | 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown, authenticated = true): Promise<T> {
  const token = authenticated ? getSuperAdminToken() : null
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`/api/admin${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    // HTTP 오류에서는 아래의 기본 오류 메시지를 사용한다.
  }
  if (!response.ok) {
    // 이전 요청의 실패가 새 로그인 토큰을 지우지 않게 한다.
    if (response.status === 401 && token && getSuperAdminToken() === token) clearSuperAdminToken()
    const error = (data as { error?: { code?: string; message?: string } } | null)?.error
    throw new ApiError(response.status, error?.code ?? `HTTP_${response.status}`,
      error?.message ?? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.')
  }
  return data as T
}

export const superadminApi = {
  login: (password: string) => request<SuperAdminAuth>('POST', '/auth', { password }, false),
  me: async () => {
    const result = await request<{ role: 'SUPER_ADMIN' }>('GET', '/me')
    if (result.role !== 'SUPER_ADMIN') {
      clearSuperAdminToken()
      throw new ApiError(401, 'SUPER_ADMIN_REQUIRED', '전체 관리자 로그인이 필요합니다.')
    }
    return result
  },
  clubs: () => request<ManagedClub[]>('GET', '/clubs'),
  createClub: (body: ManagedClubCreate) => request<ManagedClub>('POST', '/clubs', body),
  updateClub: (clubId: number, body: ManagedClubUpdate) => request<ManagedClub>('PATCH', `/clubs/${clubId}`, body),
  removeClub: (clubId: number) => request<ManagedClub>('DELETE', `/clubs/${clubId}`),
  restoreClub: (clubId: number) => request<ManagedClub>('POST', `/clubs/${clubId}/restore`),
}
