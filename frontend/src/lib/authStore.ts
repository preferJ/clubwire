// 관리자 토큰 저장소(클럽별). 브라우저 저장소가 막혀 있어도 메모리로 동작한다.

const memory = new Map<string, { token: string; expiresAt: number }>()
const key = (slug: string) => `clubwire.admin.${slug}`
const listeners = new Set<() => void>()

function read(slug: string): { token: string; expiresAt: number } | null {
  try {
    const raw = window.localStorage.getItem(key(slug))
    if (raw) return JSON.parse(raw)
  } catch {
    /* 저장소 사용 불가 → 메모리 */
  }
  return memory.get(slug) ?? null
}

export function getAdminToken(slug: string): string | null {
  const v = read(slug)
  if (!v) return null
  if (v.expiresAt && Date.now() > v.expiresAt) {
    clearAdminToken(slug)
    return null
  }
  return v.token
}

export function setAdminToken(slug: string, token: string, expiresAtIso: string): void {
  const v = { token, expiresAt: Date.parse(expiresAtIso) || 0 }
  memory.set(slug, v)
  try {
    window.localStorage.setItem(key(slug), JSON.stringify(v))
  } catch {
    /* ignore */
  }
  listeners.forEach((fn) => fn())
}

export function clearAdminToken(slug: string): void {
  memory.delete(slug)
  try {
    window.localStorage.removeItem(key(slug))
  } catch {
    /* ignore */
  }
  listeners.forEach((fn) => fn())
}

export function onAuthChange(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
