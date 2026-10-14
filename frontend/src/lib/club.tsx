// 클럽 컨텍스트: URL의 slug → 클럽 정보, API, 관리자 모드, 실시간(WebSocket) 구독

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { makeApi, type Api } from '../api/endpoints'
import type { Club, WsMessage } from '../api/types'
import { clearAdminToken, getAdminToken, onAuthChange, setAdminToken } from './authStore'

type Listener = (m: WsMessage) => void

interface ClubCtx {
  slug: string
  club: Club | null
  api: Api
  isAdmin: boolean
  login: (pin: string) => Promise<void>
  logout: () => void
  connected: boolean
  subscribe: (fn: Listener) => () => void
  pinOpen: boolean
  setPinOpen: (v: boolean) => void
}

const Ctx = createContext<ClubCtx | null>(null)

export function ClubProvider({ slug, children }: { slug: string; children: ReactNode }) {
  const api = useMemo(() => makeApi(slug), [slug])
  const [club, setClub] = useState<Club | null>(null)
  const [hasToken, setHasToken] = useState(() => !!getAdminToken(slug))
  const [connected, setConnected] = useState(false)
  const [pinOpen, setPinOpen] = useState(false)
  const listeners = useRef(new Set<Listener>())

  useEffect(() => onAuthChange(() => setHasToken(!!getAdminToken(slug))), [slug])

  useEffect(() => {
    let alive = true
    api
      .club()
      .then((c) => {
        if (!alive) return
        setClub(c)
        if (!c.isAdmin && getAdminToken(slug)) clearAdminToken(slug) // 서버가 인정하지 않는 토큰 정리
      })
      .catch(() => alive && setClub(null))
    return () => {
      alive = false
    }
  }, [api, slug, hasToken])

  // ---- WebSocket: 끊기면 지수 백오프로 재접속, 25초마다 ping
  useEffect(() => {
    let ws: WebSocket | null = null
    let retry = 0
    let timer: number | undefined
    let ping: number | undefined
    let closed = false

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${window.location.host}/ws/clubs/${encodeURIComponent(slug)}`)
      ws.onopen = () => {
        retry = 0
        setConnected(true)
        ping = window.setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('ping'), 25000)
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WsMessage
          listeners.current.forEach((fn) => fn(msg))
        } catch {
          /* ignore */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        window.clearInterval(ping)
        if (closed) return
        timer = window.setTimeout(connect, Math.min(15000, 1000 * 2 ** retry++))
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(timer)
      window.clearInterval(ping)
      ws?.close()
    }
  }, [slug])

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn)
    return () => {
      listeners.current.delete(fn)
    }
  }, [])

  const login = useCallback(
    async (pin: string) => {
      const r = await api.adminAuth(pin)
      setAdminToken(slug, r.accessToken, r.expiresAt)
    },
    [api, slug],
  )
  const logout = useCallback(() => clearAdminToken(slug), [slug])

  const value = useMemo<ClubCtx>(
    () => ({ slug, club, api, isAdmin: hasToken, login, logout, connected, subscribe, pinOpen, setPinOpen }),
    [slug, club, api, hasToken, login, logout, connected, subscribe, pinOpen],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useClub(): ClubCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('ClubProvider 밖에서 useClub 사용')
  return v
}

/** 실시간 이벤트 구독. handler는 최신 값을 참조하도록 ref로 보관. */
export function useClubEvent(handler: Listener) {
  const { subscribe } = useClub()
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => subscribe((m) => ref.current(m)), [subscribe])
}
