import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useState, useEffect, type ReactNode } from 'react'

export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'clubwire.theme'
const isTheme = (value: unknown): value is ThemeMode => value === 'dark' || value === 'light'

function readPreference(): ThemeMode | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return isTheme(value) ? value : null
  } catch {
    return null
  }
}

interface ThemeContextValue {
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
  setDefaultTheme: (theme: ThemeMode) => void
  resetTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

/** 방문자 선택을 우선하고, 선택하지 않았다면 현재 클럽의 기본 테마를 따른다. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemeMode | null>(readPreference)
  const [defaultTheme, updateDefaultTheme] = useState<ThemeMode>('dark')
  const theme = preference ?? defaultTheme

  const setTheme = useCallback((next: ThemeMode) => {
    if (!isTheme(next)) return
    setPreference(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // 브라우저 저장소가 막혀 있어도 현재 창의 테마는 변경한다.
    }
  }, [])
  const setDefaultTheme = useCallback((next: ThemeMode) => {
    updateDefaultTheme(isTheme(next) ? next : 'dark')
  }, [])
  const resetTheme = useCallback(() => {
    setPreference(null)
    try {
      window.localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY || event.key === null) {
        setPreference(isTheme(event.newValue) ? event.newValue : null)
      }
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f4f6f9' : '#12161c')
  }, [theme])

  const value = useMemo(() => ({ theme, setTheme, setDefaultTheme, resetTheme }), [theme, setTheme, setDefaultTheme, resetTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('ThemeProvider 밖에서 useTheme 사용')
  return value
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const label = next === 'light' ? '화이트 모드로 전환' : '다크 모드로 전환'
  return (
    <button type="button" className="theme-toggle" aria-label={label} title={label} onClick={() => setTheme(next)}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {next === 'light' ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" /></>
          : <path d="M20.7 13.5A9 9 0 0 1 10.5 3.3a9 9 0 1 0 10.2 10.2Z" />}
      </svg>
    </button>
  )
}
