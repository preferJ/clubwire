// A08 기사 검토: 게시 / 반려 / 다시 쓰기, 자동 게시 설정

import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { Article, ArticleStatus, InsightPayload } from '../../api/types'
import { ArticleMilestones } from '../../components/ArticleMilestones'
import { Icon } from '../../components/Icon'
import { Empty, ErrorBox, Loading, Switch, Tags, TopBar } from '../../components/ui'
import { useClub, useClubEvent } from '../../lib/club'
import { ARTICLE_TYPE_LABEL, fmtAwardValue, fmtDateTime } from '../../lib/format'
import { useAction, useAsync } from '../../lib/hooks'

const TABS: { key: string; label: string; statuses: ArticleStatus[] }[] = [
  { key: 'review', label: '검토 대기', statuses: ['PENDING', 'GENERATED', 'FAILED'] },
  { key: 'published', label: '게시됨', statuses: ['PUBLISHED'] },
  { key: 'others', label: '반려 · 이전판', statuses: ['REJECTED', 'SUPERSEDED'] },
]

const STATUS_LABEL: Record<ArticleStatus, string> = {
  PENDING: '작성 중',
  GENERATED: '검토 대기',
  PUBLISHED: '게시됨',
  REJECTED: '반려',
  FAILED: '작성 실패',
  SUPERSEDED: '이전판',
}

export function ArticlesAdminPage() {
  const { api, slug } = useClub()
  const [params] = useSearchParams()
  const sessionId = Number(params.get('sessionId')) || undefined
  const previewOnly = params.get('articleType') === 'PRE_MATCH'
  const [tab, setTab] = useState('review')
  const [open, setOpen] = useState<number | null>(() => Number(params.get('articleId')) || null)
  const list = useAsync(() => api.articles({ all: true, limit: 100, sessionId }), [api, sessionId])
  const config = useAsync(() => api.config(), [api])
  const { busy, run } = useAction()
  useClubEvent((m) => {
    if (m.type === 'ARTICLE_UPDATED') list.reload()
  })

  const auto = config.data?.items.find((i) => i.key === 'ARTICLE_PUBLISH_MODE')?.value === 'AUTO'
  const toggleAuto = async (v: boolean) => {
    const r = await run(() => api.updateConfig({ ARTICLE_PUBLISH_MODE: v ? 'AUTO' : 'MANUAL' }), v ? '프리뷰를 제외한 기사는 바로 게시돼요' : '이제 검토 후 게시해요')
    if (r) config.setData(r)
  }

  const current = TABS.find((t) => t.key === tab)!
  const articles = (list.data ?? []).filter((a) => !previewOnly || a.articleType === 'PRE_MATCH')
  const rows = articles.filter((a) => current.statuses.includes(a.status))
  const count = (key: string) => articles.filter((a) => TABS.find((t) => t.key === key)!.statuses.includes(a.status)).length

  return (
    <>
      <TopBar title="기사 검토" back={sessionId ? `/c/${slug}/sessions/${sessionId}` : `/c/${slug}/admin`}
        right={<span className="row small muted">자동 게시(프리뷰 제외)<Switch checked={!!auto} onChange={toggleAuto} label="자동 게시" /></span>} />
      <div className="tabs" role="tablist" aria-label="기사 상태" style={{ background: 'var(--card)' }}>
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>
            {t.label} {count(t.key) ? count(t.key) : ''}
          </button>
        ))}
      </div>
      <main className="page">
        {sessionId ? <div className="row between small"><span>{previewOnly ? '이 일정의 프리뷰 기사' : '이 일정의 기사'}</span><Link to={`/c/${slug}/admin/articles`}>전체 기사 보기</Link></div> : null}
        {list.error ? <ErrorBox error={list.error} onRetry={list.reload} />
          : !list.data ? <Loading />
            : rows.length === 0 ? <Empty>해당하는 기사가 없어요.</Empty>
              : rows.map((a) => (
                <ArticleReviewCard key={a.articleId} a={a} open={open === a.articleId} busy={busy}
                  onSaved={list.reload}
                  onToggle={() => setOpen(open === a.articleId ? null : a.articleId)}
                  onAction={async (action) => {
                    const fn = action === 'publish' ? api.publishArticle : action === 'reject' ? api.rejectArticle : api.regenerateArticle
                    const msg = action === 'publish' ? '게시했어요' : action === 'reject' ? '반려했어요' : '새 버전을 쓰고 있어요'
                    if (await run(() => fn(a.articleId), msg)) list.reload()
                  }} />
              ))}
      </main>
    </>
  )
}

function ArticleReviewCard({ a, open, busy, onToggle, onAction, onSaved }: {
  a: Article
  open: boolean
  busy: boolean
  onToggle: () => void
  onSaved: () => void
  onAction: (action: 'publish' | 'reject' | 'regenerate') => void
}) {
  const { api, slug } = useClub()
  const detail = useAsync(() => (open ? api.article(a.articleId) : Promise.resolve(null)), [api, a.articleId, open, a.status])
  const d = detail.data
  const [draft, setDraft] = useState<{ title: string; summary: string; content: string; usedInsightIds: number[] } | null>(null)
  const save = useAction()
  const editable = !a.publishedAt && ['GENERATED', 'REJECTED'].includes(a.status)
  const editing = !!draft && open && editable
  const locked = busy || save.busy
  const saveDraft = async () => {
    if (!draft) return
    const updated = await save.run(() => api.updateArticle(a.articleId, { ...draft, usedInsightIds: insights.length ? draft.usedInsightIds : undefined }), '기사 수정을 저장했어요')
    if (updated) {
      detail.setData(updated)
      setDraft(null)
      onSaved()
    }
  }
  const insights = d?.requestJson?.insights ?? []
  const used = new Set(d?.usedInsightIds ?? [])

  return (
    <article className="card stack" style={{ gap: 10 }}>
      <div className="row between">
        <span className="row">
          <span className={`status-badge ${a.status === 'PUBLISHED' ? 'green' : a.status === 'GENERATED' ? 'gold' : ''}`}>{STATUS_LABEL[a.status]}</span>
          <span className="small muted">{ARTICLE_TYPE_LABEL[a.articleType]} · {a.generationNo}차</span>
          {a.basic ? <span className="status-badge">기본형</span> : null}
        </span>
        <span className="small muted">{fmtDateTime(a.createdAt)}</span>
      </div>
      <Tags tags={a.tags} />
      <button type="button" onClick={() => { setDraft(null); onToggle() }} disabled={locked || editing} aria-expanded={open}
        style={{ border: 0, background: 'transparent', padding: 0, textAlign: 'left', color: 'var(--ink)' }}>
        <div className="headline" style={{ fontSize: 20 }}>{a.title ?? (a.status === 'PENDING' ? 'AI가 기사를 쓰는 중…' : '(제목 없음)')}</div>
        {a.summary ? <p style={{ fontSize: 14, fontWeight: 600, marginTop: 6 }}>{a.summary}</p> : null}
      </button>
      {a.errorMessage && (a.status === 'FAILED' || a.basic) ? (
        <div className="notice warn small">
          {a.errorMessage}{a.basic ? ' · [다시 쓰기]를 누르면 AI로 다시 써 봐요.' : ''}
        </div>
      ) : null}

      {open ? (
        detail.error ? <ErrorBox error={detail.error} onRetry={detail.reload} /> : !d ? <Loading rows={1} /> : (
          <>
            {editing && draft ? (
              <form className="stack" onSubmit={(e) => { e.preventDefault(); void saveDraft() }}>
                <label className="field">제목
                  <input aria-label="제목" className="input" required maxLength={200} value={draft.title} disabled={locked}
                    onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
                </label>
                <label className="field">요약
                  <textarea aria-label="요약" className="input" style={{ height: 'auto', padding: 12 }} rows={3} maxLength={500} value={draft.summary} disabled={locked}
                    onChange={(e) => setDraft({ ...draft, summary: e.target.value })} />
                </label>
                <label className="field">본문
                  <textarea aria-label="본문" className="input" style={{ height: 'auto', padding: 12 }} required rows={12} maxLength={16000} value={draft.content} disabled={locked}
                    onChange={(e) => setDraft({ ...draft, content: e.target.value })} />
                </label>
                {insights.length ? (
                  <fieldset className="stack" disabled={locked} aria-describedby={`used-facts-help-${a.articleId}`}
                    style={{ margin: 0, padding: 0, border: 0, minWidth: 0, gap: 6 }}>
                    <legend className="small" style={{ fontWeight: 700, marginBottom: 6 }}>기사에 쓴 사실</legend>
                    <p id={`used-facts-help-${a.articleId}`} className="small muted">
                      본문에 추가하거나 뺀 사실을 맞춰 선택하면 아래 이정표 표에도 반영돼요.
                    </p>
                    {insights.map((i) => (
                      <label key={i.id} className="check" style={{ alignItems: 'flex-start', fontSize: 13 }}>
                        <input type="checkbox" checked={draft.usedInsightIds.includes(i.id)}
                          onChange={(e) => setDraft({ ...draft, usedInsightIds: e.target.checked
                            ? [...draft.usedInsightIds, i.id] : draft.usedInsightIds.filter((id) => id !== i.id) })} />
                        <span>{INSIGHT_LABEL[i.type] ?? i.type} · {describeInsight(i)}</span>
                      </label>
                    ))}
                  </fieldset>
                ) : null}
                <div className="grid2">
                  <button type="button" className="btn sm" disabled={locked} onClick={() => setDraft(null)}>취소</button>
                  <button type="submit" className="btn sm primary" disabled={locked || !draft.title.trim() || !draft.content.trim()}>수정 저장</button>
                </div>
              </form>
            ) : <div className="article-body">{(d.content ?? '').split(/\n{2,}/).map((p, i) => <p key={i} style={{ fontSize: 14 }}>{p}</p>)}</div>}
            {editable && !editing ? <button type="button" className="btn sm" disabled={locked || detail.loading}
              onClick={() => setDraft({ title: d.title ?? '', summary: d.summary ?? '', content: d.content ?? '', usedInsightIds: [...d.usedInsightIds] })}>기사 수정</button> : null}
            <ArticleMilestones milestones={d.unusedMilestones ?? []} slug={slug} />
            {insights.length ? (
              <details className="card flat" open>
                <summary>기사에 쓴 사실 {insights.filter((i) => used.has(i.id)).length}건 · 미사용 {insights.filter((i) => !used.has(i.id)).length}건</summary>
                <ul className="stack" style={{ margin: 0, padding: 0, listStyle: 'none', gap: 6, fontSize: 13 }}>
                  {insights.map((i) => (
                    <li key={i.id} className="row between" style={{ opacity: used.has(i.id) ? 1 : 0.55 }}>
                      <span><b>{INSIGHT_LABEL[i.type] ?? i.type}</b> · {describeInsight(i)}</span>
                      <span className="mono muted">{i.importance}</span>
                    </li>
                  ))}
                </ul>
                <p className="small muted" style={{ marginTop: 8 }}>오른쪽 숫자는 중요도(관리자에게만 보임)</p>
              </details>
            ) : null}
            {a.status === 'PUBLISHED' ? <Link className="btn sm" to={`/c/${slug}/articles/${a.articleId}`}>게시된 화면 보기</Link> : null}
          </>
        )
      ) : null}

      <div className="grid3">
        <button type="button" className="btn sm danger" disabled={locked || editing || !['GENERATED', 'PUBLISHED', 'FAILED'].includes(a.status)} onClick={() => onAction('reject')}>반려</button>
        <button type="button" className="btn sm" disabled={locked || editing || a.status === 'PENDING'} onClick={() => onAction('regenerate')}>
          <Icon name="refresh" size={16} stroke={2} />다시 쓰기
        </button>
        <button type="button" className="btn sm primary" disabled={locked || editing || !['GENERATED', 'REJECTED', 'SUPERSEDED'].includes(a.status)} onClick={() => onAction('publish')}>게시</button>
      </div>
    </article>
  )
}

const INSIGHT_LABEL: Record<string, string> = {
  RETURN_PLAYER: '복귀', RETURN_PLAYER_RESULT: '복귀전', FIRST_APPEARANCE: '첫 출전', WIN_STREAK: '연승',
  SCORING_STREAK: '연속 골', MILESTONE_EXPECTED: '기록 도전', MILESTONE_ACHIEVED: '기록 달성', RARE_PAIR: '오랜만의 조합',
  CLOSE_MATCH_EXPECTED: '접전 예상', LATE_WINNER: '결승골', COMEBACK_WIN: '역전승', UPSET_WIN: '이변', HAT_TRICK: '해트트릭',
  TITLE_AWARDED: '타이틀', DUO_REUNITED: '황금 듀오', NEMESIS_MATCH: '천적 매치', JINX_PAIR: '징크스',
  SCORING_RACE: '득점왕 레이스', ATTENDANCE_STREAK: '개근', REVENGE_RESULT: '복수 결과', ASSIST_COMBO: '골 콤비',
  UNBEATEN_TEAM: '무패 팀', CLEAN_SHEET: '철벽', FIRST_GOAL: '첫 골', FIRST_ASSIST: '첫 도움', PERSONAL_BEST_GOALS: '개인 최다 골',
}

const REVENGE_LABEL: Record<string, string> = { REVENGE: '설욕', HELD: '천적 계속', EVEN: '무승부' }

const names = (ms: { name: string }[] | undefined) => (ms ?? []).map((m) => m.name).join(' · ')

/** 관리자 검토용: Insight 사실을 한국어 한 줄로 */
function describeInsight(i: InsightPayload): string {
  const f = i.facts as Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
  const name = f.member?.name ?? i.subject?.name ?? ''
  const game = f.gameNo ? `${f.gameNo}경기 ` : ''
  switch (i.type) {
    case 'RETURN_PLAYER': return `${name}, ${f.daysSinceLastAppearance}일 만에 출전`
    case 'RETURN_PLAYER_RESULT': return `${name}, ${f.daysSinceLastAppearance}일 만의 복귀전 ${f.goalsToday}골 ${f.winsToday}승`
    case 'FIRST_APPEARANCE': return `${name}, 첫 출전`
    case 'WIN_STREAK': return `${name}, ${f.streak}연승${f.ongoing ? ' 이어감' : ' 중'}`
    case 'SCORING_STREAK': return `${name}, ${f.streak}개 일정 연속 골`
    case 'MILESTONE_EXPECTED': return `${name}, 통산 ${f.metricLabel} ${f.milestone}까지 ${f.remaining}`
    case 'MILESTONE_ACHIEVED': return `${name}, 통산 ${f.metricLabel} ${f.milestone} 달성`
    case 'RARE_PAIR': return `${(f.members ?? []).map((m: { name: string }) => m.name).join(' · ')}, ${f.neverSameTeam ? '처음' : `${f.sessionsSinceLastSameTeam}일정 만에`} 같은 팀`
    case 'CLOSE_MATCH_EXPECTED': return '팀 간 전력이 매우 균형적'
    case 'LATE_WINNER': return `${game}${name}, 종료 ${f.remainingSec}초 전 결승골`
    case 'COMEBACK_WIN': return `${game}TEAM ${f.winnerTeam}, ${f.maxDeficit}골 차 역전`
    case 'UPSET_WIN': return `${game}TEAM ${f.winnerTeam}, 열세 예상 뒤집고 승리`
    case 'HAT_TRICK': return `${game}${name}, ${f.goals}골`
    case 'DUO_REUNITED':
    case 'JINX_PAIR':
      return `${names(f.members)}, 같은 팀 ${f.sameTeamMatches}경기 ${f.sameTeamWins}승 ${f.sameTeamDraws}무 ${f.sameTeamLosses}패`
    case 'NEMESIS_MATCH': return `${name}, ${f.rival?.name} 상대 ${f.memberWins}승 ${f.draws}무 ${f.rivalWins}패`
    case 'SCORING_RACE': return `${f.month}월 득점 ${f.leader?.name} ${f.leaderGoals}골 · ${f.chaser?.name} ${f.chaserGoals}골`
    case 'ATTENDANCE_STREAK': return `${name}, ${f.streak}일정 연속 출전`
    case 'REVENGE_RESULT':
      return `${name} vs ${f.rival?.name} 오늘 ${f.memberWinsToday}승 ${f.drawsToday}무 ${f.rivalWinsToday}패 (${REVENGE_LABEL[f.outcome] ?? f.outcome})`
    case 'ASSIST_COMBO': return `${f.assister?.name} → ${f.scorer?.name}, 오늘 ${f.countToday}골 (통산 ${f.careerCount})`
    case 'UNBEATEN_TEAM': return `TEAM ${f.teamCode}, ${f.games}경기 ${f.wins}승 ${f.draws}무${f.perfect ? ' 전승' : ''}`
    case 'CLEAN_SHEET': return `TEAM ${f.teamCode}, ${f.games}경기 중 ${f.cleanSheets}경기 무실점`
    case 'FIRST_GOAL': return `${name}, 첫 골${f.debutDay ? ' (데뷔전)' : ''}`
    case 'FIRST_ASSIST': return `${name}, 첫 도움${f.debutDay ? ' (데뷔전)' : ''}`
    case 'PERSONAL_BEST_GOALS': return `${name}, 하루 ${f.goalsToday}골 (이전 최다 ${f.previousBest})`
    case 'TITLE_AWARDED': return `${name}, ${f.titleName}${fmtAwardValue(f) ? ` (${fmtAwardValue(f)})` : ''}`
    default: return name
  }
}
