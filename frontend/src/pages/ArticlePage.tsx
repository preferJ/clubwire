// S02 기사 상세

import { Link, useParams } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { ErrorBox, Loading, Tags, TopBar } from '../components/ui'
import { useClub } from '../lib/club'
import { fmtDateTime, initials } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { useToast } from '../lib/toast'

export function ArticlePage() {
  const { articleId } = useParams()
  const { api, slug, isAdmin } = useClub()
  const toast = useToast()
  const art = useAsync(() => api.article(Number(articleId)), [api, articleId])
  const sessionId = art.data?.sessionId
  const session = useAsync(() => (sessionId ? api.session(sessionId) : Promise.resolve(null)), [api, sessionId])

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
  const results = (session.data?.matches ?? []).filter((m) => m.status === 'FINISHED')

  return (
    <>
      <TopBar title={<span className="eyebrow">THE WIRE</span>} back={`/c/${slug}`}
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
            {session.data ? `${session.data.title} · ` : ''}
            {a.articleType === 'PRE_MATCH' ? '프리뷰' : '마감 기사'} · {fmtDateTime(a.publishedAt ?? a.createdAt)}
          </div>
          {a.summary ? <p style={{ fontSize: 16, fontWeight: 600, lineHeight: 1.6 }}>{a.summary}</p> : null}
          <div className="article-body">
            {(a.content ?? '').split(/\n{2,}/).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>

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
            경기 기록을 바탕으로 AI가 작성하고 운영진이 게시했습니다.
          </div>
          {isAdmin ? <Link className="btn sm" to={`/c/${slug}/admin/articles`}>기사 검토로</Link> : null}
        </article>
      )}
    </>
  )
}
