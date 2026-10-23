import type { ArticleType, GameStatus, SessionStatus } from '../api/types'

/** 팀(조끼) 색: 어두운 화면 위에서 보이고, 흰 글자가 읽히는 색(대비 4.5 이상) */
const TEAM_COLORS: Record<string, string> = {
  A: '#2563eb',
  B: '#c2410c',
  C: '#7c3aed',
  D: '#0f766e',
  E: '#be185d',
  F: '#4d7c0f',
}

/** 팀 색(색만으로 구분하지 않도록 화면에는 항상 팀 글자도 같이 표시). 앱 전체가 어두운 테마라 onDark와 무관하게 같은 색 */
export function teamColor(code: string | null | undefined, onDark = false): string {
  void onDark
  return TEAM_COLORS[code ?? ''] ?? '#52525b'
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

/** 'YYYY-MM-DD' → '10월 17일 (토)' */
export function fmtDate(d: string | null | undefined, withWeekday = true): string {
  if (!d) return ''
  const [y, m, day] = d.split('-').map(Number)
  const dt = new Date(y, m - 1, day)
  return `${m}월 ${day}일${withWeekday ? ` (${WEEKDAYS[dt.getDay()]})` : ''}`
}

/** 'YYYY-MM-DD' → '2021.03.14' */
export function fmtFullDate(d: string | null | undefined): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${y}.${m}.${day}`
}

export function fmtShortDate(d: string | null | undefined): string {
  if (!d) return ''
  const [, m, day] = d.split('-').map(Number)
  return `${m}.${day}`
}

/** ISO(UTC) → 현지 'M월 D일 HH:mm' */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const dt = new Date(iso)
  const hh = String(dt.getHours()).padStart(2, '0')
  const mm = String(dt.getMinutes()).padStart(2, '0')
  return `${dt.getMonth() + 1}월 ${dt.getDate()}일 ${hh}:${mm}`
}

export function fmtClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 해당 날짜가 속한 주(월~일) */
export function weekRange(iso: string): [string, string] {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  const diff = (dt.getDay() + 6) % 7
  const mon = new Date(y, m - 1, d - diff)
  const sun = new Date(y, m - 1, d - diff + 6)
  const f = (x: Date) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
  return [f(mon), f(sun)]
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name.length >= 3 ? name.slice(-2) : name
}

export const ARTICLE_TYPE_LABEL: Record<ArticleType, string> = {
  PRE_MATCH: '프리뷰',
  POST_MATCH: '경기 기사',
  SESSION_RECAP: '마감 기사',
  MONTHLY_MVP: '이달의 MVP',
}

/** 상승률 표시: 4.2 → '+4.2%' */
export function fmtRise(v: number | null | undefined): string {
  if (v === null || v === undefined) return ''
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

/** 타이틀 기간: 이달의 MVP는 '9월', 주간은 '9.21–9.27' */
export function fmtAwardPeriod(a: { titleCode: string; periodStart: string; periodEnd: string }): string {
  if (a.titleCode.startsWith('MONTHLY_')) return `${Number(a.periodStart.slice(5, 7))}월`  // 이달의 MVP · 득점왕 · 도움왕
  if (a.periodStart === a.periodEnd) return fmtShortDate(a.periodStart)  // 연속 참가 등 일정 하루 단위
  return `${fmtShortDate(a.periodStart)}–${fmtShortDate(a.periodEnd)}`
}

/** 타이틀 수상 값: 득점왕 '3골', 도움왕 '2도움', 이달의 MVP '+4.2%' (+ 공동). 연속 참가는 이름에 횟수가 있어 빈 값 */
export function fmtAwardValue(facts: { metric?: string; value?: number; tied?: boolean } | null | undefined): string {
  if (!facts || facts.value === undefined || facts.value === null || facts.metric === 'attendStreak') return ''
  const v = facts.metric === 'risePercent' ? fmtRise(facts.value)
    : `${facts.value}${facts.metric === 'assists' ? '도움' : facts.metric === 'wins' ? '승' : '골'}`
  return `${v}${facts.tied ? ' · 공동' : ''}`
}

export const SESSION_STATUS_LABEL: Record<SessionStatus, string> = {
  OPEN: '모집 중',
  CONFIRMED: '일정확정',
  IN_PROGRESS: '진행 중',
  CLOSED: '마감',
  CANCELLED: '취소',
}

export const GAME_STATUS_LABEL: Record<GameStatus, string> = {
  READY: '대기',
  RUNNING: 'LIVE',
  PAUSED: '일시정지',
  FINISHED: '종료',
  CANCELLED: '취소',
}

export const RESULT_LABEL: Record<string, string> = { W: '승', D: '무', L: '패' }

export function pct(rate: number | null | undefined): string {
  return rate == null ? '-' : `${Math.round(rate * 100)}%`
}

/** 태그 → 시안의 색 */
export function tagTone(tag: string): string {
  if (tag === '마감') return 'dark'
  if (tag === '프리뷰') return 'green'
  if (['복귀', '데뷔', '페어', '듀오', '콤비'].includes(tag)) return 'blue'
  if (['타이틀', '마일스톤', '신기록', '개근', '무패', '철벽'].includes(tag)) return 'gold'
  return 'warm'
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** 'YYYY-MM-DD'까지 남은 날: D-3 / D-DAY / D+1 (기기 날짜 기준) */
export function dday(d: string): string {
  const [y, m, day] = d.split('-').map(Number)
  const now = new Date()
  const diff = Math.round((Date.UTC(y, m - 1, day) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000)
  return diff === 0 ? 'D-DAY' : diff > 0 ? `D-${diff}` : `D+${-diff}`
}

/** 오늘 날짜 '2026.10.22 수' */
export function fmtToday(): string {
  const now = new Date()
  return `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')} ${WEEKDAYS[now.getDay()]}`
}
