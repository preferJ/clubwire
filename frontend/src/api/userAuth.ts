import { ApiError, request } from './client'
import { getUserCsrfToken } from '../lib/userSessionStore'

export interface SignedInUser {
  userId: number
  nickname: string
}

export interface UserSession {
  configured: boolean
  user: SignedInUser | null
  csrfToken: string | null
}

export type AccountRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED' | 'REVOKED'

export interface AccountRequest {
  requestId: number
  memberId: number
  name: string
  status: AccountRequestStatus
  createdAt: string
}

export interface ClubAccount extends UserSession {
  link: { memberId: number; name: string } | null
  request: AccountRequest | null
}

export interface AccountAdminList {
  requests: (AccountRequest & { userId: number; nickname: string })[]
  links: { linkId: number; userId: number; nickname: string; memberId: number; name: string; approvedAt: string }[]
}

async function authRequest<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const csrf = getUserCsrfToken()
  if (method !== 'GET' && csrf) headers['X-CSRF-Token'] = csrf
  const response = await fetch(`/api/auth${path}`, { method, headers, credentials: 'same-origin' })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, data?.error?.code ?? `HTTP_${response.status}`,
      data?.error?.message ?? '로그인 정보를 확인하지 못했습니다.')
  }
  return data as T
}

export const userAuthApi = {
  me: () => authRequest<UserSession>('/me'),
  logout: () => authRequest<{ ok: boolean }>('/logout', 'POST'),
  loginUrl: (slug: string) => `/api/auth/kakao/login?${new URLSearchParams({ clubSlug: slug })}`,
  account: (slug: string) => request<ClubAccount>(slug, 'GET', '/account'),
  requestLink: (slug: string, memberId: number) => request<ClubAccount>(slug, 'POST', '/account/link', { body: { memberId } }),
  cancelRequest: (slug: string) => request<ClubAccount>(slug, 'DELETE', '/account/link'),
  accounts: (slug: string) => request<AccountAdminList>(slug, 'GET', '/admin/accounts'),
  approve: (slug: string, requestId: number) => request(slug, 'POST', `/admin/accounts/${requestId}/approve`),
  reject: (slug: string, requestId: number) => request(slug, 'POST', `/admin/accounts/${requestId}/reject`),
  revoke: (slug: string, linkId: number) => request(slug, 'DELETE', `/admin/accounts/${linkId}`),
}
