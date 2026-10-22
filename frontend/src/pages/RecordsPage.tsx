// S06 기록실: 개인 기록 / 수상 내역 / 기사(지난 기사) 탭. 탭·태그는 주소(?tab=articles&tag=천적)에 둬서 기사 상세에서 돌아와도 유지

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { Article, Award, MemberStat } from '../api/types'
import { ArticleCard } from '../components/ArticleCard'
import { AdminButton, Empty, ErrorBox, Loading } from '../components/ui'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDate, fmtShortDate, pct, todayIso, weekRange } from '../lib/format'
import { useAction, useAsync } from '../lib/hooks'

type RecordsTab = 'stats' | 'awards' | 'articles'
const RECORDS_TABS: RecordsTab[] = ['stats', 'awards', 'articles']

/** 기사 태그 칩(와이어에서 옮겨 옴) */
const TAGS = ['전체', '마감', '프리뷰', '복귀', '연승', '결승골', '역전', '타이틀',
  '듀오', '천적', '콤비', '무패', '철벽', '신기록', '레이스', '개근', '징크스', '데뷔']
const ARTICLE_PAGE = 20

type SortKey = 'goals' | 'assists' | 'winRate' | 'games' | 'mvpCount'
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'goals', label: '골' },
  { key: 'assists', label: '도움' },
  { key: 'winRate', label: '승률' },
  { key: 'games', label: '경기' },
  { key: 'mvpCount', label: 'MVP' },
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
      <header className="home-head">
        <h1 className="club-name">기록실</h1>
        <AdminButton />
      </header>
      <div className="tabs" role="tablist" aria-label="기록 보기" style={{ margin: '0 16px' }}>
        <button type="button" role="tab" aria-selected={tab === 'stats'} onClick={() => setTab('stats')}>개인 기록</button>
        <button type="button" role="tab" aria-selected={tab === 'awards'} onClick={() => setTab('awards')}>수상 내역</button>
        <button type="button" role="tab" aria-selected={tab === 'articles'} onClick={() => setTab('articles')}>기사</button>
      </div>
      <main className="page">
        {tab === 'stats' ? (
          <StatsTab stats={stats.data} awards={awards.data ?? []} error={stats.error} loading={stats.loading} reload={stats.reload} />
        ) : tab === 'awards' ? (
          <AwardsTab awards={awards.data} error={awards.error} reload={awards.reload} />
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
    <section className="stack" style={{ gap: 10, padding: 14, borderRadius: 16, background: 'var(--night)', color: '#fff' }}>
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
                <th scope="col" className={sort === 'mvpCount' ? 'sorted' : ''}>MVP</th>
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
                  <td>{r.mvpCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function AwardsTab({ awards, error, reload }: { awards: Award[] | undefined; error: unknown; reload: () => void }) {
  const { slug } = useClub()
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!awards) return <Loading />
  if (awards.length === 0) return <Empty>아직 수여된 타이틀이 없어요.<br />[일정마감] 때 득점왕 · 도움왕이 자동으로 정해져요.</Empty>
  const weeks = new Map<string, Award[]>()
  awards.forEach((a) => weeks.set(a.periodStart, [...(weeks.get(a.periodStart) ?? []), a]))
  const tally = new Map<string, { name: string; n: number; memberId: number }>()
  awards.forEach((a) => {
    const t = tally.get(String(a.memberId)) ?? { name: a.memberName ?? '', n: 0, memberId: a.memberId }
    t.n++
    tally.set(String(a.memberId), t)
  })
  const top = [...tally.values()].sort((a, b) => b.n - a.n).slice(0, 5)

  return (
    <>
      <section className="card stack" style={{ gap: 8 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>타이틀 많이 받은 선수</h2>
        {top.map((t, i) => (
          <Link key={t.memberId} to={`/c/${slug}/members/${t.memberId}`} className="row between" style={{ color: 'var(--ink)', minHeight: 32 }}>
            <span><b>{i + 1}</b>&nbsp;&nbsp;{t.name}</span>
            <span className="tag gold">{t.n}회</span>
          </Link>
        ))}
      </section>
      {[...weeks.entries()].map(([start, list]) => (
        <section key={start} className="section">
          <h2 className="small muted" style={{ fontWeight: 700 }}>{fmtShortDate(start)} – {fmtShortDate(list[0].periodEnd)}</h2>
          {list.map((a) => (
            <Link key={a.memberTitleId} to={`/c/${slug}/members/${a.memberId}`} className="list-row">
              <span className="row"><span className="tag gold">{a.titleName}</span><b>{a.memberName}</b></span>
              <span className="small muted">{awardNote(a)}</span>
            </Link>
          ))}
        </section>
      ))}
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
  const unit = a.facts?.metric === 'assists' ? '도움' : a.facts?.metric === 'wins' ? '승' : '골'
  return `${a.facts?.value ?? ''}${unit}${a.facts?.tied ? ' · 공동' : ''}`
}
