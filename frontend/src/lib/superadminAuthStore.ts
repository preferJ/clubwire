// 서비스 전체 관리자 인증. 클럽별 관리자 토큰과 별도로 보관한다.

interface SuperAdminSession {
  token: string
  expiresAt: number
}

const STORAGE_KEY = 'clubwire.superadmin'
let memory: SuperAdminSession | null = null
const listeners = new Set<() => void>()

function read(): SuperAdminSession | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const value: unknown = JSON.parse(raw)
      if (value && typeof value === 'object' && 'token' in value && 'expiresAt' in value
        && typeof value.token === 'string' && value.token.length > 0
        && typeof value.expiresAt === 'number' && Number.isFinite(value.expiresAt)) {
        return { token: value.token, expiresAt: value.expiresAt }
      }
    }
  } catch {
    // 브라우저 저장소를 사용할 수 없으면 메모리를 사용한다.
  }
  return memory
}

export function getSuperAdminToken(): string | null {
  const session = read()
  if (!session) return null
  if (Date.now() >= session.expiresAt) {
    clearSuperAdminToken()
    return null
  }
  return session.token
}

export function setSuperAdminToken(token: string, expiresAtIso: string): void {
  const expiresAt = Date.parse(expiresAtIso)
  if (!token || !Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
    throw new Error('관리자 인증 정보가 올바르지 않습니다. 다시 로그인해 주세요.')
  }
  memory = { token, expiresAt }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(memory))
  } catch {
    // 저장소 사용이 막힌 환경에서도 현재 창에서는 인증을 유지한다.
  }
  listeners.forEach((listener) => listener())
}

export function clearSuperAdminToken(): void {
  memory = null
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
  listeners.forEach((listener) => listener())
}

export function onSuperAdminAuthChange(listener: () => void): () => void {
  listeners.add(listener)
  const storageListener = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY || event.key === null) {
      // 다른 창에서 로그아웃한 뒤 메모리 인증만 남지 않게 한다.
      memory = null
      listener()
    }
  }
  window.addEventListener('storage', storageListener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', storageListener)
  }
}
