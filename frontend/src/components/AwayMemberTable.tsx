// 선수별 원정 기록 표(기록 탭 '원정' 전체 · 상대별 상세에서 같이 씀). 정렬 칩: 골 · 도움 · 승률 · 경기

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AwayOverview } from '../api/types'
import { pct } from '../lib/format'

type SortKey = 'goals' | 'assists' | 'winRate' | 'games'
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'goals', label: '골' },
  { key: 'assists', label: '도움' },
  { key: 'winRate', label: '승률' },
  { key: 'games', label: '경기' },
]

export function AwayMemberTable({ slug, members }: { slug: string; members: AwayOverview['members'] }) {
  const [sort, setSort] = useState<SortKey>('goals')
  const rows = useMemo(
    () => [...members].sort((a, b) => ((b[sort] ?? -1) as number) - ((a[sort] ?? -1) as number)
      || (sort === 'goals' ? b.assists - a.assists : 0) || b.games - a.games),
    [members, sort],
  )
  return (
    <>
      <div className="chips" role="group" aria-label="정렬">
        {SORTS.map((s) => (
          <button key={s.key} type="button" className="chip" aria-pressed={sort === s.key} onClick={() => setSort(s.key)}>{s.label}</button>
        ))}
      </div>
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
    </>
  )
}
