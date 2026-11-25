import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { userAuthApi, type UserSession } from '../api/userAuth'
import { setUserCsrfToken } from './userSessionStore'

interface UserAuthValue extends Omit<UserSession, 'csrfToken'> {
  loading: boolean
  error: unknown
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<UserAuthValue | null>(null)

/** 공개 화면은 로그인 없이 이용한다. 로그인 정보·선수 연결은 별도 계정 화면에서 관리한다. */
export function UserAuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<UserSession>({ user: null, configured: false, csrfToken: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const sequence = useRef(0)
  const loggingOut = useRef(false)

  const refresh = useCallback(async () => {
    if (loggingOut.current) return
    const current = ++sequence.current
    try {
      const next = await userAuthApi.me()
      if (current !== sequence.current) return
      setUserCsrfToken(next.csrfToken)
      setSession(next)
      setError(null)
    } catch (err) {
      if (current !== sequence.current) return
      setError(err)
      setSession((old) => ({ ...old, user: null, csrfToken: null }))
      setUserCsrfToken(null)
    } finally {
      if (current === sequence.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const onFocus = () => { void refresh() }
    window.addEventListener('focus', onFocus)
    return () => { sequence.current++; window.removeEventListener('focus', onFocus) }
  }, [refresh])

  const logout = useCallback(async () => {
    if (loggingOut.current) return
    loggingOut.current = true
    // 로그아웃 도중 도착한 이전 /me 응답이 로그인 상태를 복원하지 못하도록 한다.
    sequence.current++
    try {
      await userAuthApi.logout()
      sequence.current++
      setUserCsrfToken(null)
      setSession((old) => ({ ...old, user: null, csrfToken: null }))
      setError(null)
      setLoading(false)
    } finally {
      loggingOut.current = false
    }
  }, [])

  const value = useMemo<UserAuthValue>(() => ({ user: session.user, configured: session.configured, loading, error, refresh, logout }),
    [session, loading, error, refresh, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useUserAuth() {
  const value = useContext(Ctx)
  if (!value) throw new Error('UserAuthProvider 밖에서 useUserAuth 사용')
  return value
}
