import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/client'
import type { MatchState } from '../api/types'
import { useToast } from './toast'

interface AsyncState<T> {
  data: T | undefined
  error: unknown
  loading: boolean
}

/** 조회용: deps가 바뀌면 다시 불러온다. reload()는 화면 깜빡임 없이 갱신. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<AsyncState<T>>({ data: undefined, error: undefined, loading: true })
  const seq = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(fn, deps)

  const run = useCallback(
    async (silent: boolean) => {
      const my = ++seq.current
      if (!silent) setState((s) => ({ ...s, loading: true, error: undefined }))
      try {
        const data = await load()
        if (my === seq.current) setState({ data, error: undefined, loading: false })
      } catch (error) {
        if (my === seq.current) setState((s) => ({ data: s.data, error, loading: false }))
      }
    },
    [load],
  )

  useEffect(() => {
    run(false)
  }, [run])

  return {
    ...state,
    reload: useCallback(() => run(true), [run]),
    setData: useCallback((d: T) => setState((s) => ({ ...s, data: d })), []),
  }
}

/** 쓰기용: 진행 중 표시 + 실패 시 토스트 */
export function useAction() {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, okMessage?: string): Promise<T | undefined> => {
      setBusy(true)
      try {
        const r = await fn()
        if (okMessage) toast.show(okMessage)
        return r
      } catch (e) {
        toast.error(errorMessage(e))
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [toast],
  )
  return { busy, run }
}

/**
 * 타이머: 서버는 매초 보내지 않는다. 시작 시각/일시정지 누적/서버 시각으로 클라이언트가 계산.
 * (서버와 기기 시계 차이는 serverTime으로 보정)
 */
export function useMatchClock(m: MatchState | null | undefined) {
  const offset = useRef(0)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (m?.serverTime) offset.current = Date.parse(m.serverTime) - Date.now()
  }, [m?.serverTime, m?.version])

  const running = m?.status === 'RUNNING'
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(t)
  }, [running])

  if (!m) return { elapsed: 0, remaining: 0, overtime: 0, progress: 0 }
  let elapsed = m.elapsedSec
  if (m.startedAt) {
    const started = Date.parse(m.startedAt)
    if (m.status === 'RUNNING') elapsed = (now + offset.current - started) / 1000 - m.pausedSeconds
    else if (m.status === 'PAUSED' && m.pausedAt) elapsed = (Date.parse(m.pausedAt) - started) / 1000 - m.pausedSeconds
  }
  elapsed = Math.max(0, elapsed)
  const remaining = m.durationSec - elapsed
  return {
    elapsed,
    remaining: Math.max(0, remaining),
    overtime: Math.max(0, -remaining),
    progress: Math.min(1, elapsed / Math.max(1, m.durationSec)),
  }
}
