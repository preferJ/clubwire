import { Link } from 'react-router-dom'
import type { ArticleMilestone } from '../api/types'

/** 본문에 썼는지와 관계없이 기사 생성 당시의 일정 이정표를 보여 준다. */
export function ArticleMilestones({ milestones, slug }: {
  milestones?: ArticleMilestone[]
  slug: string
}) {
  if (!milestones?.length) return null

  return (
    <div className="article-milestones">
      <table>
        <caption>이번 일정 이정표</caption>
        <colgroup>
          <col className="player-col" />
          <col className="record-col" />
          <col className="remaining-col" />
        </colgroup>
        <thead>
          <tr><th scope="col">선수</th><th scope="col">기록</th><th scope="col">남은 수</th></tr>
        </thead>
        <tbody>
          {milestones.map((m) => (
            <tr key={m.insightId}>
              <th scope="row"><Link to={`/c/${slug}/members/${m.memberId}`}>{m.name}</Link></th>
              <td>{m.record}</td>
              <td className="remaining">{m.remaining}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
