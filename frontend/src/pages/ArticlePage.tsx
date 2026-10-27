// S02 기사 상세

import { useEffect } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ArticleMilestones } from '../components/ArticleMilestones'
import { Icon } from '../components/Icon'
import { ErrorBox, Loading, Tags, TopBar, type FromState } from '../components/ui'
import { useClub } from '../lib/club'
import { ARTICLE_TYPE_LABEL, fmtDateTime, initials } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { markArticleRead } from '../lib/readStore'
import { useToast } from '../lib/toast'

export function ArticlePage() {
  const { articleId } = useParams()
  const { api, slug, isAdmin } = useClub()
  const from = (useLocation().state as FromState | null)?.from  // 기록 탭 지난 기사에서 왔으면 그리로 돌아감
  const toast = useToast()
  const art = useAsync(() => api.article(Number(articleId)), [api, articleId])
  const sessionId = art.data?.sessionId
  const session = useAsync(() => (sessionId ? api.session(sessionId) : Promise.resolve(null)), [api, sessionId])
  const loadedId = art.data?.articleId
  useEffect(() => {
    if (loadedId) markArticleRead(slug, loadedId)  // 와이어 소식함의 새 소식 점을 끈다
  }, [slug, loadedId])

  const share = async () => {
    const url = window.location.href
    try {
      if (navigator.share) await navigator.share({ title: art.data?.title ?? 'Clubwire', url })
      else {
        await navigator.clipboard.writeText(url)
        toast.show('링크를 복사했어요')
      }
    } catch {
      /* 사용자가 취소 */
    }
  }

  const a = art.data
  // 이달의 MVP 기사는 그 달 마지막 일정에 붙어 있을 뿐 한 일정의 기사가 아님 → 일정 제목 · 이날 경기 결과는 숨김
  const monthly = a?.articleType === 'MONTHLY_MVP'
  const results = monthly ? [] : (session.data?.matches ?? []).filter((m) => m.status === 'FINISHED')

  return (
    <>
      <TopBar title={<span className="eyebrow">THE WIRE</span>} back={from?.path ?? `/c/${slug}`}
        right={<button type="button" className="icon-btn" aria-label="공유" onClick={share}><Icon name="share" /></button>} />
      {art.error ? (
        <ErrorBox error={art.error} onRetry={art.reload} />
      ) : !a ? (
        <div className="page"><Loading /></div>
      ) : (
        <article className="page" style={{ background: 'var(--card)', minHeight: 'calc(100vh - 60px)', gap: 14 }}>
          <Tags tags={a.tags} />
          <h1 className="headline" style={{ fontSize: 28 }}>{a.title}</h1>
          <div className="small muted">
            {session.data && !monthly ? `${session.data.title} · ` : ''}
            {ARTICLE_TYPE_LABEL[a.articleType]} · {fmtDateTime(a.publishedAt ?? a.createdAt)}
          </div>
          {a.summary ? <p style={{ fontSize: 16, fontWeight: 600, lineHeight: 1.6 }}>{a.summary}</p> : null}
          <div className="article-body">
            {(a.content ?? '').split(/\n{2,}/).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>

          <ArticleMilestones milestones={a.unusedMilestones ?? []} slug={slug} />

          {a.members.length ? (
            <section className="section">
              <h2 className="small muted" style={{ fontWeight: 700 }}>이 기사에 나온 선수</h2>
              <div className="row wrap">
                {a.members.map((m) => (
                  <Link key={m.memberId} to={`/c/${slug}/members/${m.memberId}`} className="row"
                    style={{ minHeight: 40, padding: '0 12px 0 4px', borderRadius: 20, border: '1px solid var(--line)', color: 'var(--ink)', fontWeight: 600, fontSize: 14 }}>
                    <span className="avatar" style={{ width: 32, height: 32, fontSize: 12 }}>{initials(m.name)}</span>
                    {m.name}
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {results.length ? (
            <section className="stack" style={{ gap: 6, padding: '12px 14px', borderRadius: 12, background: 'var(--bg)' }}>
              <h2 className="small muted" style={{ fontWeight: 700 }}>이날 경기 결과</h2>
              {results.map((m) => (
                <div key={m.matchId} className="row between" style={{ fontSize: 14 }}>
                  <span className="muted">{m.gameNo}경기</span>
                  <span>TEAM {m.teamA.teamCode} <b className="mono">{m.teamA.score} : {m.teamB.score}</b> TEAM {m.teamB.teamCode}</span>
                </div>
              ))}
            </section>
          ) : null}

          <div className="row small muted">
            <Icon name="info" size={14} />
            {a.basic ? '경기 기록으로 자동 작성한 기본형 기사입니다.'
              : monthly ? '월 마감 때 경기 기록을 바탕으로 AI가 작성해 자동 게시했습니다.'
                : '경기 기록을 바탕으로 AI가 작성하고 운영진이 게시했습니다.'}
          </div>
          {isAdmin ? <Link className="btn sm" to={`/c/${slug}/admin/articles`}>기사 검토로</Link> : null}
        </article>
      )}
    </>
  )
}
