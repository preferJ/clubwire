// 케미: 자주 같은 팀이 된 선수 · 자주 맞붙은 선수를 [풋살 피치 | 궁합 티어표] 두 가지로 보여 준다(기본 = 피치).
// - 풋살 피치: 우리 반쪽 = 자주 같은 팀 5명, 상대 반쪽 = 자주 맞붙은 5명. 경기 수가 많을수록 나(가운데)와 가까운 자리,
//   원 크기 = 경기 수, 테두리 색 = 승률 3단계. 이름 아래에 숫자(경기 · 승률 / 승 무 패)를 같이 써서 색만으로 읽지 않게
// - 궁합 티어표: 같은 팀은 찰떡 / 보통 / 상극, 상대는 먹잇감 / 호각 / 천적 칸에 나눠 담기
// 색: 파랑(50%↑) · 회색(30~50%) · 주황(30%↓) — 빨강/초록과 달리 색약에도 구분되는 짝. 선수를 누르면 그 선수 화면

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { initials } from '../lib/format'

export interface MateLink {
  memberId: number
  name: string | null
  matches: number
  wins: number
  draws: number
  winRate: number | null
}

export interface RivalLink {
  memberId: number
  name: string | null
  matches: number
  wins: number
  draws: number
  losses: number
}

type Tier = 'hi' | 'mid' | 'lo'
/** 승률 3단계: 50% 이상 / 30% 미만(3팀 풋살은 무승부가 많아 평균 승률이 35~40%대) */
const HI = 0.5
const LO = 0.3
const PITCH_PLAYERS = 5

function tierOf(wins: number, matches: number): Tier {
  if (!matches) return 'mid'
  const r = wins / matches
  return r >= HI ? 'hi' : r < LO ? 'lo' : 'mid'
}

const pctText = (wins: number, matches: number) => (matches ? `${Math.round((wins / matches) * 100)}%` : '-')

type View = 'pitch' | 'tiers'

export function Chemistry({ slug, me, teammates, opponents }: {
  slug: string
  me: string
  teammates: MateLink[]
  opponents: RivalLink[]
}) {
  const [view, setView] = useState<View>('pitch')
  if (!teammates.length && !opponents.length) return <p className="small muted">기록이 쌓이면 보여요.</p>
  return (
    <>
      <div className="seg" role="group" aria-label="케미 보기 방식">
        <button type="button" aria-pressed={view === 'pitch'} onClick={() => setView('pitch')}>풋살 피치</button>
        <button type="button" aria-pressed={view === 'tiers'} onClick={() => setView('tiers')}>궁합 티어표</button>
      </div>
      <div className="chem-legend">
        {view === 'pitch' ? <span className="chem-key"><i className="size" />원 크기 = 경기 수</span> : null}
        <span className="chem-key"><i className="c hi" />승률 50%↑</span>
        <span className="chem-key"><i className="c mid" />30~50%</span>
        <span className="chem-key"><i className="c lo" />30%↓</span>
      </div>
      {view === 'pitch'
        ? <Pitch slug={slug} me={me} teammates={teammates.slice(0, PITCH_PLAYERS)} opponents={opponents.slice(0, PITCH_PLAYERS)} />
        : <Tiers slug={slug} teammates={teammates} opponents={opponents} />}

    </>
  )
}

// ------------------------------------------------------------------ 풋살 피치
const W = 362
const H = 548
const MID = H / 2
/** 경기 수 순위 → 자리(1·2위 = 하프라인 쪽 공격수, 3·4위 = 수비, 5위 = 골키퍼). 이름 · 숫자는 원 아래에 쓰므로
 *  아래쪽 반은 거울 위치보다 조금 위로 올려 둔다 */
const TOP_SLOTS: [number, number][] = [[104, 208], [W - 104, 208], [68, 124], [W - 68, 124], [W / 2, 52]]
const BOTTOM_SLOTS: [number, number][] = [[104, 330], [W - 104, 330], [68, 408], [W - 68, 408], [W / 2, 478]]

interface Spot {
  id: number
  name: string
  x: number
  y: number
  r: number
  tier: Tier
  stat: string
  title: string
}

function Pitch({ slug, me, teammates, opponents }: { slug: string; me: string; teammates: MateLink[]; opponents: RivalLink[] }) {
  const maxM = Math.max(1, ...teammates.map((m) => m.matches), ...opponents.map((m) => m.matches))
  const radius = (m: number) => 13 + 8 * (m / maxM)
  const spots: Spot[] = [
    ...teammates.map((m, i): Spot => {
      const losses = m.matches - m.wins - m.draws
      return {
        id: m.memberId, name: m.name ?? '', x: TOP_SLOTS[i][0], y: TOP_SLOTS[i][1], r: radius(m.matches),
        tier: tierOf(m.wins, m.matches), stat: `${m.matches}경기 · ${pctText(m.wins, m.matches)}`,
        title: `${m.name}: 같은 팀 ${m.matches}경기 ${m.wins}승 ${m.draws}무 ${losses}패`,
      }
    }),
    ...opponents.map((m, i): Spot => ({
      id: m.memberId, name: m.name ?? '', x: BOTTOM_SLOTS[i][0], y: BOTTOM_SLOTS[i][1], r: radius(m.matches),
      tier: tierOf(m.wins, m.matches), stat: `${m.wins}승 ${m.draws}무 ${m.losses}패`,
      title: `${m.name} 상대로 ${m.matches}경기 ${m.wins}승 ${m.draws}무 ${m.losses}패`,
    })),
  ]
  const summary = `${me}의 케미 피치. 우리 팀(자주 같은 팀): ${teammates.map((m) => `${m.name} ${m.matches}경기`).join(', ') || '없음'}. `
    + `상대(자주 맞붙은): ${opponents.map((m) => `${m.name} ${m.wins}승 ${m.draws}무 ${m.losses}패`).join(', ') || '없음'}.`

  return (
    <figure className="chem-pitch">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
        <rect x={1} y={1} width={W - 2} height={H - 2} rx={14} className="pitch-turf" />
        <line x1={1} y1={MID} x2={W - 1} y2={MID} className="pitch-line" />
        <circle cx={W / 2} cy={MID} r={44} className="pitch-line" />
        <path d={`M${W / 2 - 70} 1 v36 a70 30 0 0 0 140 0 v-36`} className="pitch-line" />
        <path d={`M${W / 2 - 70} ${H - 1} v-36 a70 30 0 0 1 140 0 v36`} className="pitch-line" />
        <text x={12} y={22} className="pitch-side">우리 팀</text>
        <text x={12} y={36} className="pitch-side sub">자주 같은 팀</text>
        <text x={12} y={H - 26} className="pitch-side">상대</text>
        <text x={12} y={H - 12} className="pitch-side sub">자주 맞붙은</text>

        <circle cx={W / 2} cy={MID} r={24} className="pitch-me" />
        <text x={W / 2} y={MID + 5} textAnchor="middle" className="pitch-me-text">{initials(me)}</text>

        {spots.map((p) => (
          <Link key={`${p.y < MID ? 't' : 'b'}${p.id}`} to={`/c/${slug}/members/${p.id}`} className="pitch-node" aria-label={p.title}>
            <title>{p.title}</title>
            <circle cx={p.x} cy={p.y} r={p.r} className={`pitch-dot ${p.tier}`} />
            <text x={p.x} y={p.y + 4} textAnchor="middle" className="pitch-ini">{initials(p.name)}</text>
            <text x={p.x} y={p.y + p.r + 15} textAnchor="middle" className="pitch-name">{p.name}</text>
            <text x={p.x} y={p.y + p.r + 30} textAnchor="middle" className="pitch-stat">{p.stat}</text>
          </Link>
        ))}
      </svg>
    </figure>
  )
}

// ------------------------------------------------------------------ 궁합 티어표
const MATE_TIERS: { tier: Tier; title: string; note: string }[] = [
  { tier: 'hi', title: '찰떡', note: '승률 50%↑' },
  { tier: 'mid', title: '보통', note: '30~50%' },
  { tier: 'lo', title: '상극', note: '30%↓' },
]
const RIVAL_TIERS: { tier: Tier; title: string; note: string }[] = [
  { tier: 'hi', title: '먹잇감', note: '내 승률 50%↑' },
  { tier: 'mid', title: '호각', note: '30~50%' },
  { tier: 'lo', title: '천적', note: '30%↓' },
]

function Tiers({ slug, teammates, opponents }: { slug: string; teammates: MateLink[]; opponents: RivalLink[] }) {
  return (
    <>
      <h3 className="tier-head">같은 팀 궁합</h3>
      <TierTable slug={slug} rows={MATE_TIERS} items={teammates.map((m) => ({
        id: m.memberId, name: m.name ?? '', tier: tierOf(m.wins, m.matches), matches: m.matches,
        stat: `${m.matches}경기 ${pctText(m.wins, m.matches)}`,
      }))} />
      <h3 className="tier-head">맞대결 상성</h3>
      <TierTable slug={slug} rows={RIVAL_TIERS} items={opponents.map((m) => ({
        id: m.memberId, name: m.name ?? '', tier: tierOf(m.wins, m.matches), matches: m.matches,
        stat: `${m.wins}-${m.draws}-${m.losses}`,
      }))} />
    </>
  )
}

function TierTable({ slug, rows, items }: {
  slug: string
  rows: { tier: Tier; title: string; note: string }[]
  items: { id: number; name: string; tier: Tier; matches: number; stat: string }[]
}) {
  return (
    <div className="tier-table">
      {rows.map((r) => {
        const inTier = items.filter((x) => x.tier === r.tier).sort((a, b) => b.matches - a.matches)
        return (
          <div key={r.tier} className="tier-row">
            <div className="tier-name">{r.title}<small>{r.note}</small></div>
            <div className="tier-chips">
              {inTier.length ? inTier.map((x) => (
                <Link key={x.id} to={`/c/${slug}/members/${x.id}`} className={`tier-chip ${x.tier}`}>
                  <b>{initials(x.name)}</b>{x.name}<span>{x.stat}</span>
                </Link>
              )) : <span className="tier-empty">없음</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
