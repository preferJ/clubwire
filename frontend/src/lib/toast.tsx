import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

interface Toast {
  id: number
  text: string
  kind: 'info' | 'error'
}

interface ToastApi {
  show: (text: string) => void
  error: (text: string) => void
}

const Ctx = createContext<ToastApi>({ show: () => {}, error: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, kind: Toast['kind']) => {
    const id = Date.now() + Math.random()
    setItems((xs) => [...xs.slice(-1), { id, text, kind }])
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === 'error' ? 4500 : 1800)
  }, [])
  const api = useMemo(() => ({ show: (t: string) => push(t, 'info'), error: (t: string) => push(t, 'error') }), [push])
  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toast-wrap" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind === 'error' ? 'error' : ''}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export const useToast = () => useContext(Ctx)
