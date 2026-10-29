// S05 선수 기록 (+ 수상 이력: 최근 5개 가로 넘김) · 프로필(등번호 · 가입일 · 출생연도, 관리자 모드에서 입력) · 케미(풋살 피치 | 궁합 티어표)

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import type { Award, MemberProfile } from '../api/types'
import { Chemistry } from '../components/Chemistry'
import { ErrorBox, Loading, TopBar } from '../components/ui'
import { useClub } from '../lib/club'
import { fmtAwardPeriod, fmtAwardValue, fmtFullDate, initials, pct, RESULT_LABEL } from '../lib/format'
import { useAction, useAsync } from '../lib/hooks'
import '../styles/member-numbers.css'

const EMPTY_PROFILE: MemberProfile = { joinedAt: null, birthYear: null, jerseyNumber: null }
/** 수상 이력 카드로 보여 줄 개수(나머지는 [전체 보기]) */
const AWARD_CARDS = 5
/** 케미: 자주 같은 팀 · 맞붙은 선수 몇 명까지 받을지(피치는 5명, 티어표는 전부) */
const CHEMISTRY_TOP = 10

export function PlayerPage() {
  const { memberId } = useParams()
  const id = Number(memberId)
  const { api, slug, isAdmin } = useClub()
  const detail = useAsync(() => api.memberDetail(id, CHEMISTRY_TOP), [api, id])
  const awards = useAsync(() => api.awards({ memberId: id }), [api, id])

  if (detail.error) return <><TopBar title="선수 기록" back /><ErrorBox error={detail.error} onRetry={detail.reload} /></>
  const d = detail.data
  if (!d) return <><TopBar title="선수 기록" back /><div className="page"><Loading /></div></>
  const s = d.summary
  const profile = d.profile ?? EMPTY_PROFILE
  const meta = [profile.joinedAt ? `${fmtFullDate(profile.joinedAt)} 가입` : '', profile.birthYear ? `${profile.birthYear}년생` : '']
    .filter(Boolean).join(' · ')
  const streak = leadingWins(d.recentForm.map((r) => r.result))
  const titleCounts = countTitles(awards.data ?? [])

  return (
    <>
      <TopBar title="선수 기록" back />
      <header className="stack" style={{ gap: 12, padding: '16px 16px 18px', background: 'var(--card)', borderBottom: '1px solid var(--line)' }}>
        <div className="row" style={{ gap: 14 }}>
          <span className="avatar" style={{ width: 64, height: 64, fontSize: 18 }}>{initials(s.name)}</span>
          <div className="stack member-profile-copy" style={{ gap: 6 }}>
            <div className="member-name-line">
              <h1 className="club-name">{s.name}</h1>
              {profile.jerseyNumber != null ? <span className="member-jersey member-jersey-large" aria-label={`등번호 ${profile.jerseyNumber}`}>#{profile.jerseyNumber}</span> : null}
            </div>
            {meta ? <span className="small muted">{meta}</span> : null}
            <div className="tags">
              {titleCounts.map(([name, n]) => <span key={name} className="tag gold">{name} ×{n}</span>)}
              {streak >= 2 ? <span className="tag green">{streak}연승 중</span> : null}
              {!s.active ? <span className="tag">비활성</span> : null}
            </div>
          </div>
        </div>
      </header>

      <main className="page">
        {isAdmin ? <ProfileEditor key={`${id}-${profile.joinedAt}-${profile.birthYear}-${profile.jerseyNumber}`} memberId={id} profile={profile} onSaved={detail.reload} /> : null}

        <div className="grid3">
          <Stat label="경기" value={s.games} />
          <Stat label="승률" value={pct(s.winRate)} />
          <Stat label="승 무 패" value={`${s.wins}·${s.draws}·${s.losses}`} />
          <Stat label="골" value={s.goals} />
          <Stat label="도움" value={s.assists} />
          <Stat label="출전 일정" value={s.sessionsAttended} />
        </div>

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>최근 {d.recentForm.length || 5}경기</h2>
          {d.recentForm.length === 0 ? <p className="small muted">확정된 경기가 아직 없어요.</p> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 6 }}>
              {d.recentForm.map((r) => (
                <div key={r.matchId} className={`form-cell ${r.result}`} title={`${r.sessionDate} ${r.gameNo}경기`}>
                  <b>{RESULT_LABEL[r.result]}</b>
                  <span>{[r.goals ? `${r.goals}골` : '', r.assists ? `${r.assists}도움` : ''].filter(Boolean).join(' ') || '-'}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <AwardStrip awards={awards.data ?? []} />

        <section className="section">
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>케미</h2>
          <Chemistry slug={slug} me={s.name} teammates={d.frequentTeammates} opponents={d.frequentOpponents} />
        </section>
      </main>
    </>
  )
}

/** 수상 이력: 최근(기간 끝 날짜 순) 5개를 카드로 가로 넘김. 더 있으면 마지막 칸 [전체 n개] → 아래 목록 */
function AwardStrip({ awards }: { awards: Award[] }) {
  const [all, setAll] = useState(false)
  const sorted = [...awards].sort((a, b) => b.periodEnd.localeCompare(a.periodEnd) || b.createdAt.localeCompare(a.createdAt))
  const cards = sorted.slice(0, AWARD_CARDS)
  return (
    <section className="section">
      <div className="row between">
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>수상 이력</h2>
        {sorted.length > 1 ? <span className="small muted">옆으로 넘겨 보기 · 전체 {sorted.length}개</span> : null}
      </div>
      {sorted.length === 0 ? <p className="small muted">아직 받은 타이틀이 없어요.</p> : (
        <div className="award-strip" role="list" aria-label="최근 수상">
          {cards.map((a) => (
            <div key={a.memberTitleId} className="award-card" role="listitem">
              <span className="tag gold">{a.titleName}</span>
              <b className="num">{cardValue(a)}</b>
              <span className="small muted">{fmtAwardPeriod(a)}{a.facts?.tied ? ' · 공동' : ''}</span>
            </div>
          ))}
          {sorted.length > AWARD_CARDS ? (
            <button type="button" className="award-card more" role="listitem" aria-expanded={all} onClick={() => setAll((v) => !v)}>
              <b>{all ? '접기' : `전체 ${sorted.length}개`}</b>
              <span className="small muted">{all ? '목록 닫기' : '아래에 목록으로'}</span>
            </button>
          ) : null}
        </div>
      )}
      {all ? sorted.map((a) => (
        <div key={a.memberTitleId} className="list-row">
          <span className="row"><span className="tag gold">{a.titleName}</span></span>
          <span className="small muted">{fmtAwardPeriod(a)}{fmtAwardValue(a.facts) ? ` · ${fmtAwardValue(a.facts)}` : ''}</span>
        </div>
      )) : null}
    </section>
  )
}

/** 카드 가운데 큰 글씨: '3골' · '+4.2%' · '10회 연속'('공동'은 아래 작은 글씨로) */
function cardValue(a: Award): string {
  if (a.facts?.metric === 'attendStreak') return `${a.facts.value}회 연속`
  return fmtAwardValue(a.facts ? { ...a.facts, tied: false } : null) || '수상'
}

/** 관리자 모드: 등번호 · 가입일 · 출생연도 입력. 비우고 저장하면 지운다 */
function ProfileEditor({ memberId, profile, onSaved }: { memberId: number; profile: MemberProfile; onSaved: () => void }) {
  const { api } = useClub()
  const { busy, run } = useAction()
  const [joined, setJoined] = useState(profile.joinedAt ?? '')
  const [birth, setBirth] = useState(profile.birthYear ? String(profile.birthYear) : '')
  const [jersey, setJersey] = useState(profile.jerseyNumber != null ? String(profile.jerseyNumber) : '')
  const thisYear = new Date().getFullYear()
  const birthYear = birth ? Number(birth) : null
  const birthBad = birthYear !== null && (birth.length !== 4 || birthYear < 1900 || birthYear > thisYear)
  const jerseyNumber = jersey === '' ? null : Number(jersey)
  const jerseyBad = jersey !== '' && !/^\d{1,2}$/.test(jersey)
  const dirty = joined !== (profile.joinedAt ?? '') || birthYear !== profile.birthYear || jerseyNumber !== (profile.jerseyNumber ?? null)

  const save = async () => {
    if (birthBad || jerseyBad || busy) return
    const done = await run(() => api.updateMember(memberId, { joinedAt: joined || null, birthYear, jerseyNumber }), '선수 정보를 저장했어요')
    if (done) onSaved()
  }

  return (
    <section className="card stack" style={{ gap: 10 }} aria-label="선수 정보 입력">
      <div className="row between">
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>선수 정보</h2>
        <span className="admin-pill">관리자</span>
      </div>
      <div className="grid2">
        <label className="field">등번호
          <input className="input" inputMode="numeric" pattern="[0-9]{1,2}" placeholder="미지정" value={jersey}
            aria-invalid={jerseyBad} onChange={(e) => setJersey(e.target.value)} />
        </label>
        <label className="field">출생연도
          <input className="input" inputMode="numeric" placeholder="예: 1992" value={birth} aria-invalid={birthBad}
            onChange={(e) => setBirth(e.target.value.replace(/\D/g, '').slice(0, 4))} />
        </label>
        <label className="field">가입일
          <input className="input" type="date" value={joined} onChange={(e) => setJoined(e.target.value)} />
        </label>
      </div>
      {jerseyBad ? <span className="small" style={{ color: 'var(--danger-ink)' }}>등번호는 0~99 사이의 정수로 입력하세요.</span> : null}
      {birthBad
        ? <span className="small" style={{ color: 'var(--danger-ink)' }}>출생연도는 1900~{thisYear} 사이 4자리로 입력하세요.</span>
        : <span className="small muted">등번호는 0~99로 입력하세요. 칸을 비우고 저장하면 해당 정보가 지워져요.</span>}
      <button type="button" className="btn primary block" disabled={busy || !dirty || birthBad || jerseyBad} onClick={save}>
        {busy ? '저장 중…' : '저장'}
      </button>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  )
}

function leadingWins(results: string[]): number {
  let n = 0
  for (const r of results) {
    if (r === 'W') n++
    else break
  }
  return n
}

function countTitles(awards: Award[]): [string, number][] {
  const m = new Map<string, number>()
  awards.forEach((a) => m.set(a.titleName, (m.get(a.titleName) ?? 0) + 1))
  return [...m.entries()]
}
