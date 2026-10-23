// S06 기록실: 개인 기록 / 수상 내역 / 기사(지난 기사) 탭. 탭·태그는 주소(?tab=articles&tag=천적)에 둬서 기사 상세에서 돌아와도 유지

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { Article, Award, MemberStat } from '../api/types'
import { ArticleCard } from '../components/ArticleCard'
import { ClubBar, Empty, ErrorBox, Loading } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtAwardPeriod, fmtAwardValue, fmtDate, fmtShortDate, pct, todayIso, weekRange } from '../lib/format'
import { useAction, useAsync } from '../lib/hooks'

type RecordsTab = 'stats' | 'awards' | 'articles'
const RECORDS_TABS: RecordsTab[] = ['stats', 'awards', 'articles']

/** 기사 태그 칩(와이어에서 옮겨 옴) */
const TAGS = ['전체', '마감', '프리뷰', '이달의 MVP', '복귀', '연승', '결승골', '역전', '타이틀',
  '듀오', '천적', '콤비', '무패', '철벽', '신기록', '레이스', '개근', '징크스', '데뷔']
const ARTICLE_PAGE = 20

type SortKey = 'goals' | 'assists' | 'winRate' | 'games'
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'goals', label: '골' },
  { key: 'assists', label: '도움' },
  { key: 'winRate', label: '승률' },
  { key: 'games', label: '경기' },
]

export function RecordsPage() {
  const { api } = useClub()
  const [params, setParams] = useSearchParams()
  const tab: RecordsTab = RECORDS_TABS.find((t) => t === params.get('tab')) ?? 'stats'
  const setTab = (t: RecordsTab) => setParams(t === 'stats' ? {} : { tab: t }, { replace: true })
  const stats = useAsync(() => api.memberStats(), [api])
  const awards = useAsync(() => api.awards({}), [api])
  useClubEvent((m) => {
    if (m.type === 'TITLE_UPDATED' || m.type === 'SESSION_UPDATED') {
      stats.reload()
      awards.reload()
    }
  })

  return (
    <>
      <ClubBar title="기록실" />
      <div className="tabs" role="tablist" aria-label="기록 보기" style={{ margin: '0 16px' }}>
        <button type="button" role="tab" aria-selected={tab === 'stats'} onClick={() => setTab('stats')}>개인 기록</button>
        <button type="button" role="tab" aria-selected={tab === 'awards'} onClick={() => setTab('awards')}>수상 내역</button>
        <button type="button" role="tab" aria-selected={tab === 'articles'} onClick={() => setTab('articles')}>기사</button>
      </div>
      <main className="page">
        {tab === 'stats' ? (
          <StatsTab stats={stats.data} awards={awards.data ?? []} error={stats.error} loading={stats.loading} reload={stats.reload} />
        ) : tab === 'awards' ? (
          <AwardsTab />
        ) : (
          <ArticlesTab />
        )}
      </main>
    </>
  )
}

function ThisWeek({ awards }: { awards: Award[] }) {
  const { slug } = useClub()
  const [from, to] = weekRange(todayIso())
  // 이번 주 수상이 없으면 가장 최근 주를 보여준다
  const latestStart = awards.reduce<string | null>((acc, a) => (!acc || a.periodStart > acc ? a.periodStart : acc), null)
  const weekStart = awards.some((a) => a.periodStart === from) ? from : latestStart
  if (!weekStart) return null
  const items = awards.filter((a) => a.periodStart === weekStart)
  const end = items[0]?.periodEnd ?? to
  return (
    <section className="stack" style={{ gap: 10, padding: 14, borderRadius: 'var(--radius-s)', background: 'var(--night)', border: '1px solid var(--line)', color: '#fff' }}>
      <div className="row between">
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>{weekStart === from ? '이번 주 타이틀' : '최근 타이틀'}</h2>
        <span className="small" style={{ color: 'var(--night-muted)' }}>{fmtShortDate(weekStart)} – {fmtShortDate(end)}</span>
      </div>
      <div className="grid3">
        {items.map((a) => (
          <Link key={a.memberTitleId} to={`/c/${slug}/members/${a.memberId}`} className="stack"
            style={{ gap: 4, padding: 10, borderRadius: 12, background: 'var(--night-2)', color: '#fff' }}>
            <span style={{ fontSize: 11, color: 'var(--gold)', fontWeight: 700 }}>{a.titleName.replace('이주의 ', '')}</span>
            <span style={{ fontSize: 15, fontWeight: 700 }}>{a.memberName}</span>
            <span style={{ fontSize: 11, color: 'var(--night-muted)' }}>{awardNote(a)}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}

function StatsTab({ stats, awards, error, loading, reload }: {
  stats: MemberStat[] | undefined
  awards: Award[]
  error: unknown
  loading: boolean
  reload: () => void
}) {
  const { slug } = useClub()
  const [sort, setSort] = useState<SortKey>('goals')
  const rows = useMemo(
    () => [...(stats ?? [])].filter((s) => s.games > 0)
      .sort((a, b) => ((b[sort] ?? -1) as number) - ((a[sort] ?? -1) as number) || b.games - a.games),
    [stats, sort],
  )
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (loading && !stats) return <Loading />
  return (
    <>
      <ThisWeek awards={awards} />
      <div className="chips" role="group" aria-label="정렬">
        {SORTS.map((s) => (
          <button key={s.key} type="button" className="chip" aria-pressed={sort === s.key} onClick={() => setSort(s.key)}>{s.label}</button>
        ))}
      </div>
      {rows.length === 0 ? <Empty>확정된 경기 기록이 아직 없어요.</Empty> : (
        <div className="table-box">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">이름</th>
                <th scope="col" className={sort === 'games' ? 'sorted' : ''}>경기</th>
                <th scope="col" className={sort === 'winRate' ? 'sorted' : ''}>승-무-패</th>
                <th scope="col" className={sort === 'goals' ? 'sorted' : ''}>골</th>
                <th scope="col" className={sort === 'assists' ? 'sorted' : ''}>도움</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.memberId}>
                  <td style={{ fontWeight: 700 }}>{i + 1}</td>
                  <td><Link to={`/c/${slug}/members/${r.memberId}`}>{r.name}</Link></td>
                  <td>{r.games}</td>
                  <td className="muted">{r.wins}-{r.draws}-{r.losses}{sort === 'winRate' ? ` (${pct(r.winRate)})` : ''}</td>
                  <td style={{ fontWeight: sort === 'goals' ? 700 : 400 }}>{r.goals}</td>
                  <td style={{ fontWeight: sort === 'assists' ? 700 : 400 }}>{r.assists}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------------ 수상 내역: 기간(기본 이번 달) + 상 별 조회
const ATTEND_PREFIX = 'ATTEND_STREAK_'  // 연속 참가 10~50회는 칩 하나로 묶음

type Period = { kind: 'month'; month: string } | { kind: 'year' } | { kind: 'all' }

/** 주소의 period: 'YYYY-MM' | 'year' | 'all'. 없으면 이번 달 */
function parsePeriod(raw: string | null): Period {
  if (raw === 'year' || raw === 'all') return { kind: raw }
  if (raw && /^\d{4}-\d{2}$/.test(raw)) return { kind: 'month', month: raw }
  return { kind: 'month', month: todayIso().slice(0, 7) }
}

function shiftMonth(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + n, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function periodRange(p: Period): { from?: string; to?: string } {
  if (p.kind === 'all') return {}
  if (p.kind === 'year') { const y = todayIso().slice(0, 4); return { from: `${y}-01-01`, to: `${y}-12-31` } }
  const [y, m] = p.month.split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  return { from: `${p.month}-01`, to: `${p.month}-${String(last).padStart(2, '0')}` }
}

function periodLabel(p: Period): string {
  if (p.kind === 'all') return '전체 기간'
  if (p.kind === 'year') return `${todayIso().slice(0, 4)}년`
  const [y, m] = p.month.split('-')
  return `${y}년 ${Number(m)}월`
}

function AwardsTab() {
  const { api, slug } = useClub()
  const [params, setParams] = useSearchParams()
  const period = parsePeriod(params.get('period'))
  const title = params.get('title') ?? ''
  const range = periodRange(period)
  const types = useAsync(() => api.titleTypes(), [api])
  const awards = useAsync(() => api.awards({ ...range, ...(title ? { titleCode: title } : {}), limit: 1000 }),
    [api, range.from, range.to, title])
  useClubEvent((m) => {
    if (m.type === 'TITLE_UPDATED' || m.type === 'SESSION_UPDATED') awards.reload()
  })

  const set = (next: { period?: string | null; title?: string | null }) => {
    const q = new URLSearchParams(params)
    q.set('tab', 'awards')
    for (const [k, v] of Object.entries(next)) {
      if (v) q.set(k, v)
      else q.delete(k)
    }
    setParams(q, { replace: true })
  }
  const thisMonth = todayIso().slice(0, 7)
  const month = period.kind === 'month' ? period.month : thisMonth
  const goMonth = (n: number) => {
    const m = period.kind === 'month' ? shiftMonth(month, n) : thisMonth
    set({ period: m === thisMonth ? null : m })
  }
  // 상 칩: 활성 타이틀 종류(표시 순서), 연속 참가 n회는 하나로
  const chips: { code: string; label: string }[] = []
  for (const t of types.data ?? []) {
    if (t.titleCode.startsWith(ATTEND_PREFIX)) {
      if (!chips.some((c) => c.code === ATTEND_PREFIX)) chips.push({ code: ATTEND_PREFIX, label: '연속 참가' })
    } else chips.push({ code: t.titleCode, label: t.titleName })
  }

  const list = [...(awards.data ?? [])].sort((a, b) => b.periodEnd.localeCompare(a.periodEnd) || a.titleCode.localeCompare(b.titleCode))
  const groups = new Map<string, Award[]>()
  list.forEach((a) => groups.set(fmtAwardPeriod(a), [...(groups.get(fmtAwardPeriod(a)) ?? []), a]))
  const tally = new Map<number, { name: string; n: number }>()
  list.forEach((a) => tally.set(a.memberId, { name: a.memberName ?? '', n: (tally.get(a.memberId)?.n ?? 0) + 1 }))
  const top = [...tally.entries()].sort((x, y) => y[1].n - x[1].n).slice(0, 5)

  return (
    <>
      <div className="period-bar" role="group" aria-label="기간">
        <div className="month-nav" data-active={period.kind === 'month'}>
          <button type="button" className="icon-btn" aria-label="이전 달" onClick={() => goMonth(-1)}>◀</button>
          <button type="button" className="month-label" onClick={() => set({ period: null })}
            aria-label={`월별 보기: ${periodLabel({ kind: 'month', month })}`}>
            {Number(month.slice(5))}월{month.slice(0, 4) !== thisMonth.slice(0, 4) ? <small>{month.slice(0, 4)}</small> : null}
          </button>
          <button type="button" className="icon-btn" aria-label="다음 달" disabled={period.kind === 'month' && month >= thisMonth}
            onClick={() => goMonth(1)}>▶</button>
        </div>
        <button type="button" className="chip" aria-pressed={period.kind === 'year'} onClick={() => set({ period: 'year' })}>올해</button>
        <button type="button" className="chip" aria-pressed={period.kind === 'all'} onClick={() => set({ period: 'all' })}>전체</button>
      </div>
      <div className="chips" role="group" aria-label="상 종류">
        <button type="button" className="chip" aria-pressed={!title} onClick={() => set({ title: null })}>전체</button>
        {chips.map((c) => (
          <button key={c.code} type="button" className="chip" aria-pressed={title === c.code} onClick={() => set({ title: c.code })}>{c.label}</button>
        ))}
      </div>

      {awards.error ? <ErrorBox error={awards.error} onRetry={awards.reload} /> : !awards.data ? <Loading /> : list.length === 0 ? (
        <Empty>{periodLabel(period)}{title ? ` · ${chips.find((c) => c.code === title)?.label ?? ''}` : ''} 수상 기록이 없어요.</Empty>
      ) : (
        <>
          <p className="small muted" style={{ margin: 0 }}>{periodLabel(period)} · 수상 {list.length}건 · {tally.size}명</p>
          <section className="card stack" style={{ gap: 8 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700 }}>많이 받은 선수</h2>
            {top.map(([memberId, t], i) => (
              <Link key={memberId} to={`/c/${slug}/members/${memberId}`} className="row between" style={{ color: 'var(--ink)', minHeight: 32 }}>
                <span><b>{i + 1}</b>&nbsp;&nbsp;{t.name}</span>
                <span className="tag gold">{t.n}회</span>
              </Link>
            ))}
          </section>
          {[...groups.entries()].map(([label, items]) => (
            <section key={label} className="section">
              <h2 className="small muted" style={{ fontWeight: 700 }}>{label}</h2>
              {items.map((a) => (
                <Link key={a.memberTitleId} to={`/c/${slug}/members/${a.memberId}`} className="list-row">
                  <span className="row"><span className="tag gold">{a.titleName}</span><b>{a.memberName}</b></span>
                  <span className="small muted">{awardNote(a)}</span>
                </Link>
              ))}
            </section>
          ))}
        </>
      )}
    </>
  )
}

/** 지난 기사: 태그로 거르고, 일정 날짜별로 묶고, 20개씩 더 불러오기 */
function ArticlesTab() {
  const { api, slug } = useClub()
  const [params, setParams] = useSearchParams()
  const tag = TAGS.find((t) => t === params.get('tag')) ?? '전체'
  const query = tag === '전체' ? {} : { tag }
  const first = useAsync(() => api.articles({ ...query, limit: ARTICLE_PAGE }), [api, tag])
  const [more, setMore] = useState<Article[]>([])
  const [end, setEnd] = useState(false)
  const { busy, run } = useAction()
  useClubEvent((m) => {
    if (m.type === 'ARTICLE_UPDATED') first.reload()
  })
  // 첫 페이지가 바뀌면(태그 변경·새 기사) 이어 붙인 페이지는 버리고 처음부터
  useEffect(() => {
    setMore([])
    setEnd((first.data?.length ?? 0) < ARTICLE_PAGE)
  }, [first.data])

  const list = [...(first.data ?? []), ...more]
  const loadMore = async () => {
    const last = list[list.length - 1]
    if (!last) return
    const page = await run(() => api.articles({ ...query, limit: ARTICLE_PAGE, beforeId: last.articleId }))
    if (!page) return
    setMore((m) => [...m, ...page])
    if (page.length < ARTICLE_PAGE) setEnd(true)
  }
  const from = { path: `/c/${slug}/records?${params.toString()}`, tab: 'records' as const }

  return (
    <>
      <div className="chips" role="group" aria-label="기사 태그">
        {TAGS.map((t) => (
          <button key={t} type="button" className="chip" aria-pressed={tag === t}
            onClick={() => setParams(t === '전체' ? { tab: 'articles' } : { tab: 'articles', tag: t }, { replace: true })}>
            {t}
          </button>
        ))}
      </div>
      {first.error ? (
        <ErrorBox error={first.error} onRetry={first.reload} />
      ) : first.loading && !first.data ? (
        <Loading />
      ) : list.length === 0 ? (
        <Empty>{tag === '전체' ? '아직 게시된 기사가 없어요.' : `'${tag}' 기사가 아직 없어요.`}</Empty>
      ) : (
        <>
          {groupBySession(list).map(([date, items]) => (
            <section key={date} className="section">
              <h2 className="small muted" style={{ fontWeight: 700 }}>{date ? `${fmtDate(date)} 일정` : '일정 없음'}</h2>
              {items.map((a) => <ArticleCard key={a.articleId} a={a} slug={slug} lead={false} from={from} />)}
            </section>
          ))}
          {end ? (
            <p className="small muted" style={{ textAlign: 'center' }}>마지막 기사예요</p>
          ) : (
            <button type="button" className="btn block" disabled={busy} onClick={loadMore}>더 불러오기</button>
          )}
        </>
      )}
    </>
  )
}

/** 일정 날짜별 묶음(최근 일정 먼저, 묶음 안은 게시 순서 그대로) */
function groupBySession(list: Article[]): [string, Article[]][] {
  const groups = new Map<string, Article[]>()
  list.forEach((a) => groups.set(a.sessionDate ?? '', [...(groups.get(a.sessionDate ?? '') ?? []), a]))
  return [...groups.entries()].sort(([a], [b]) => b.localeCompare(a))
}

function awardNote(a: Award): string {
  if (a.awardMethod === 'MANUAL') return '운영진 선정'
  return fmtAwardValue(a.facts)
}
