import { useCallback, useEffect, useState } from 'react'
import { Icon } from './Icon'
import { Sheet } from './ui'
import {
  fetchYprRules, parseGuideText, YPR_DEFAULT_RULES_TEXT, YPR_DEFAULT_RULES_UPDATED_AT, YPR_SOURCE_URL,
  type YprRules,
} from '../lib/yprGuide'

// 승점제 정적 원문: hesse429/YPR index.html#panel-info
// 출처 커밋: 63804e179ce75a223ea44d317eca14ecc7430191. 운영 수칙은 이 안내와 달리 공개 문서를 매번 읽는다.
const POINTS_RULES = [
  ['동률 처리', '승수가 같으면 상위 등수로 공동 배정합니다. 예) A팀 3승, B팀 3승, C팀 1승 → A·B팀 공동 1위로 각 3점, C팀은 3위로 1점.'],
  ['무승부', '무승부 경기는 승점에 반영하지 않습니다.'],
  ['원정매칭', '원정 매칭일 경우 참여선수는 전원 승점 3점을 획득합니다.'],
  ['🪽 페어플레이', '매주 팀별로 선정된 페어플레이 선수는 소속 팀 순위 점수에 +1점 보너스를 받습니다. 동점표가 나오면 동점자 전원이 보너스를 받습니다. 경기종료 후 한 시간내로 페어플레이어를 선정해주세요.'],
  ['시상 시기', '시상은 매달 말에 진행하며, 시상 후 승점은 매달 초기화됩니다.'],
  ['시상 제외', '누적 승점이 동점일 경우 해당 분기 수상자는 선정하지 않습니다.'],
] as const

const BADGES = [
  ['1회', '🥉 동메달'], ['2회', '🥈 은메달'], ['3회', '🥇 금메달'], ['4회', '🏆 트로피'],
  ['5회', '👑 왕관'], ['6회 이상', '👽 외계인'], ['이 주의 페어플레이어', '🪽 날개'],
] as const

type RulesState = { status: 'loading' | 'live' | 'fallback'; data: YprRules | null }

export function MembersGuide() {
  const [active, setActive] = useState<'points' | 'rules' | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [rules, setRules] = useState<RulesState>({ status: 'loading', data: null })
  const close = useCallback(() => setActive(null), [])

  useEffect(() => {
    if (active !== 'rules') return
    const controller = new AbortController()
    setRules({ status: 'loading', data: null })
    fetchYprRules(controller.signal).then((data) => {
      if (!controller.signal.aborted) setRules({ status: 'live', data })
    }).catch(() => {
      if (!controller.signal.aborted) setRules({
        status: 'fallback', data: { text: YPR_DEFAULT_RULES_TEXT, updatedAt: YPR_DEFAULT_RULES_UPDATED_AT },
      })
    })
    return () => controller.abort()
  }, [active, attempt])

  return (
    <>
      <div className="grid2 members-guide-actions" aria-label="팀 안내">
        <button type="button" className="btn" onClick={() => setActive('points')}><Icon name="trophy" size={18} />승점제 안내</button>
        <button type="button" className="btn" onClick={() => setActive('rules')}><Icon name="info" size={18} />운영 수칙</button>
      </div>
      <Sheet open={active !== null} onClose={close} labelledBy="members-guide-title">
        <div className="members-guide">
          <div className="row between members-guide-heading">
            <h2 id="members-guide-title">{active === 'points' ? '승점제 안내' : '운영 수칙'}</h2>
            <button type="button" className="icon-btn" aria-label="안내 닫기" onClick={close}><Icon name="close" /></button>
          </div>
          {active === 'points' ? <PointsGuide /> : (
            <>
              {rules.status === 'loading' ? <p className="muted" role="status">최신 운영 수칙을 불러오는 중이에요…</p> : null}
              {rules.status === 'fallback' ? (
                <div className="notice warn members-guide-warning" role="status">
                  <p>최신 운영 수칙을 불러오지 못해 2026-06-08 기본 수칙을 표시합니다.</p>
                  <button type="button" className="btn sm" onClick={() => setAttempt((v) => v + 1)}>다시 불러오기</button>
                </div>
              ) : null}
              {rules.data ? (
                <>
                  <p className="small muted">{rules.status === 'live' ? '최신 운영 수칙' : '기본 운영 수칙'} · 최종 수정 {rules.data.updatedAt}</p>
                  <RulesText text={rules.data.text} />
                </>
              ) : null}
            </>
          )}
          <a className="btn sm members-guide-source" href={YPR_SOURCE_URL} target="_blank" rel="noopener noreferrer">YPR 원문 보기 ↗</a>
        </div>
      </Sheet>
    </>
  )
}

function PointsGuide() {
  return (
    <div className="members-guide-points">
      <section>
        <h3>승점 획득 방법</h3>
        <h4>순위 배점</h4>
        <p>매주 밀어내기에서 많은 승을 챙긴 팀부터 순서대로 승점을 부여합니다. 1위 팀 선수들은 3점, 2위 팀은 2점, 3위 팀은 1점을 각각 받습니다.</p>
        <table>
          <caption className="sr-only">팀 순위별 승점</caption>
          <thead><tr><th scope="col">순위</th><th scope="col">승점</th></tr></thead>
          <tbody>{[['1위 팀', '3점'], ['2위 팀', '2점'], ['3위 팀', '1점']].map(([rank, points]) => (
            <tr key={rank}><th scope="row">{rank}</th><td>{points}</td></tr>
          ))}</tbody>
        </table>
        {POINTS_RULES.map(([title, text]) => <div className="members-guide-rule" key={title}><h4>{title}</h4><p>{text}</p></div>)}
      </section>
      <section>
        <h3>🏅 수상 배지 안내</h3>
        <table>
          <caption className="sr-only">수상 횟수별 배지</caption>
          <thead><tr><th scope="col">수상 횟수</th><th scope="col">배지</th></tr></thead>
          <tbody>{BADGES.map(([count, badge]) => <tr key={count}><th scope="row">{count}</th><td>{badge}</td></tr>)}</tbody>
        </table>
      </section>
      <p className="small muted">승점제 안내는 YPR 원문 기준입니다. 변경사항은 원문에서 확인해 주세요.</p>
    </div>
  )
}

function RulesText({ text }: { text: string }) {
  return (
    <div className="members-guide-rules">
      {parseGuideText(text).map((block, i) => block.kind === 'list'
        ? <ul key={i}>{block.items.map((item, j) => <li key={j}>{item}</li>)}</ul>
        : block.kind === 'heading' ? <h3 key={i}>{block.text}</h3>
          : block.kind === 'subheading' ? <h4 key={i}>{block.text}</h4>
            : <p key={i}>{block.text}</p>)}
    </div>
  )
}
