import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useClub } from '../lib/club'
import { tagTone, teamColor } from '../lib/format'
import { Icon } from './Icon'

/** 상단 바(뒤로 + 제목 + 오른쪽 영역) */
export function TopBar({ title, sub, back, right, dark }: {
  title: ReactNode
  sub?: ReactNode
  back?: string | true
  right?: ReactNode
  dark?: boolean
}) {
  const nav = useNavigate()
  return (
    <header className={`topbar ${dark ? 'dark' : ''}`}>
      {back ? (
        typeof back === 'string' ? (
          <Link to={back} className="icon-btn" aria-label="뒤로" style={{ color: 'inherit' }}>
            <Icon name="back" size={22} />
          </Link>
        ) : (
          <button type="button" className="icon-btn" aria-label="뒤로" onClick={() => nav(-1)}>
            <Icon name="back" size={22} />
          </button>
        )
      ) : (
        <span style={{ width: 10 }} />
      )}
      <div className="title">
        <h1>{title}</h1>
        {sub ? <span>{sub}</span> : null}
      </div>
      {right}
    </header>
  )
}

const SHIELD = 'M20 2 L37 7 V22 C37 33 30 40 20 44 C10 40 3 33 3 22 V7 Z'

/** 클럽 엠블럼: 흰 방패 + 클럽 색 세로 줄무늬 + 이름 띠 */
export function Crest({ name, size = 44 }: { name: string; size?: number }) {
  const short = name.trim()
  const label = (short.length <= 4 ? short : short.slice(0, 3)).toUpperCase()
  return (
    <svg width={size} height={(size * 46) / 40} viewBox="0 0 40 46" role="img" aria-label={`${short} 엠블럼`} style={{ flex: 'none' }}>
      <path d={SHIELD} fill="#fff" />
      <rect x="7" y="8" width="5" height="26" style={{ fill: 'var(--accent)' }} />
      <rect x="17.5" y="4" width="5" height="38" style={{ fill: 'var(--accent)' }} />
      <rect x="28" y="8" width="5" height="26" style={{ fill: 'var(--accent)' }} />
      <rect x="3" y="15" width="34" height="11" style={{ fill: 'var(--bg)' }} />
      <text x="20" y="23.8" textAnchor="middle" fontFamily="Barlow Condensed, sans-serif" fontWeight={800}
        fontSize={label.length > 3 ? 8 : 10} fill="#fff">{label}</text>
      <path d={SHIELD} fill="none" strokeWidth={1.5} style={{ stroke: 'var(--bg)' }} />
    </svg>
  )
}

/** 탭 첫 화면 머리: 클럽 색 줄무늬 띠 + 엠블럼 + 제목(+ 작은 글씨: 없으면 클럽 이름) + 관리자 버튼. children은 둘째 줄(와이어의 날짜·다음 일정) */
export function ClubBar({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  const { club, slug } = useClub()
  return (
    <header className="club-bar">
      <div className="club-row">
        <Crest name={club?.clubName ?? slug} />
        <div className="club-title">
          <h1>{title}</h1>
          <span>{sub ?? club?.clubName ?? ''}</span>
        </div>
        <AdminButton onDark />
      </div>
      {children}
    </header>
  )
}

/** 관리자 모드 표시(누르면 관리자 메뉴) / 관리자 아니면 자물쇠(누르면 PIN) */
export function AdminButton({ onDark }: { onDark?: boolean }) {
  const { isAdmin, setPinOpen } = useClub()
  const { slug } = useClub()
  if (isAdmin) {
    return (
      <Link to={`/c/${slug}/admin`} className="admin-pill">
        <Icon name="lock" size={13} stroke={2} />관리자
      </Link>
    )
  }
  return (
    <button type="button" className={`icon-btn ${onDark ? '' : 'round'}`} aria-label="관리자 모드" onClick={() => setPinOpen(true)}>
      <Icon name="lock" />
    </button>
  )
}

export type TabKey = 'home' | 'sessions' | 'records' | 'members'

/** 목록 → 상세로 갈 때 Link state로 넘기는 출처. 상세 화면의 [뒤로]와 하단 탭 강조에 쓴다(예: 기록 탭의 지난 기사 → 기사 상세) */
export interface FromState {
  from?: { path: string; tab: TabKey }
}

/** 지금 주소가 어느 탭 소속인지: 기사→와이어, 경기→일정, 선수→선수단. 관리자 화면은 강조 없음 */
export function tabOf(pathname: string, slug: string): TabKey | null {
  const base = `/c/${slug}`
  if (!pathname.startsWith(base)) return null
  const rest = pathname.slice(base.length)
  if (rest === '' || rest === '/' || /^\/articles(\/|$)/.test(rest)) return 'home'
  if (/^\/(sessions|matches)(\/|$)/.test(rest)) return 'sessions'
  if (/^\/records(\/|$)/.test(rest)) return 'records'
  if (/^\/members(\/|$)/.test(rest)) return 'members'
  return null
}

export function BottomNav() {
  const { slug } = useClub()
  const { pathname, state } = useLocation()
  const current = (state as FromState | null)?.from?.tab ?? tabOf(pathname, slug)
  const items = [
    { key: 'home', to: `/c/${slug}`, label: '와이어', icon: 'wire' },
    { key: 'sessions', to: `/c/${slug}/sessions`, label: '일정', icon: 'calendar' },
    { key: 'records', to: `/c/${slug}/records`, label: '기록', icon: 'trophy' },
    { key: 'members', to: `/c/${slug}/members`, label: '선수단', icon: 'users' },
  ]
  return (
    <nav className="bottom-nav" aria-label="주요 메뉴">
      {items.map((it) => (
        <Link key={it.key} to={it.to} className={current === it.key ? 'active' : ''}
          aria-current={current === it.key ? 'page' : undefined}>
          <Icon name={it.icon} size={22} />
          {it.label}
        </Link>
      ))}
    </nav>
  )
}

export function TeamBadge({ code, size = 26, onDark }: { code: string | null | undefined; size?: number; onDark?: boolean }) {
  return (
    <span className="team-badge" style={{ width: size, height: size, background: teamColor(code, onDark), fontSize: size * 0.5 }}>
      {code ?? '?'}
    </span>
  )
}

export function Tags({ tags }: { tags: string[] }) {
  if (!tags.length) return null
  return (
    <div className="tags">
      {tags.map((t) => (
        <span key={t} className={`tag ${tagTone(t)}`}>
          {t}
        </span>
      ))}
    </div>
  )
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="불러오는 중">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 72 }} />
      ))}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="state-box">
      <p>{errorMessage(error)}</p>
      {onRetry ? (
        <button type="button" className="btn sm" style={{ marginTop: 12 }} onClick={onRetry}>
          다시 시도
        </button>
      ) : null}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state-box">{children}</div>
}

/** 바텀시트(배경 누르거나 Esc로 닫힘). 하단 탭 메뉴까지 덮고, 열려 있는 동안 스크롤은 시트 안에서만 */
export function Sheet({ open, onClose, labelledBy, children }: {
  open: boolean
  onClose: () => void
  labelledBy: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  useEffect(() => {
    if (!open) return
    // 시트가 열려 있는 동안 뒤 화면 스크롤 잠금(휠·드래그는 시트 안에서만)
    const body = document.body
    const prev = body.style.overflow
    body.style.overflow = 'hidden'
    return () => { body.style.overflow = prev }
  }, [open])
  if (!open) return null
  // body로 바로 그린다: 부모(.bar-actions 등 sticky + z-index)의 층에 갇히면 하단 탭 메뉴 아래로 깔린다
  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-labelledby={labelledBy} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}>
        <span className="grabber" />
        {children}
      </div>
    </div>,
    document.body,
  )
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} className="switch" onClick={() => onChange(!checked)}>
      <span />
    </button>
  )
}

export function Stepper({ value, onChange, min = 0, max = 99, label }: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  label: string
}) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" aria-label={`${label} 줄이기`} onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min}>−</button>
      <output aria-live="polite">{value}</output>
      <button type="button" aria-label={`${label} 늘리기`} onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max}>+</button>
    </div>
  )
}
