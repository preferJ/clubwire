// fetch 래퍼: /api/clubs/{slug} 접두사, 관리자 토큰, 에러 형식({error:{code,message}}) 통일

import { clearAdminToken, getAdminToken } from '../lib/authStore'

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

function qs(query?: Query): string {
  if (!query) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function request<T>(
  slug: string,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  options: { body?: unknown; query?: Query } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getAdminToken(slug)
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(`/api/clubs/${encodeURIComponent(slug)}${path}${qs(options.query)}`, {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error
    const code = err?.code ?? `HTTP_${res.status}`
    if (res.status === 401 && token && ['TOKEN_EXPIRED', 'INVALID_TOKEN', 'ADMIN_REQUIRED'].includes(code)) {
      clearAdminToken(slug) // 만료된 관리자 모드는 자동 해제
    }
    throw new ApiError(res.status, code, err?.message ?? '요청을 처리하지 못했습니다.')
  }
  return data as T
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return '알 수 없는 오류가 발생했습니다.'
}
