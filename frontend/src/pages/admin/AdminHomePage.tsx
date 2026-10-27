// 관리자 메뉴

import { Link, useNavigate } from 'react-router-dom'
import { Icon } from '../../components/Icon'
import { TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAsync } from '../../lib/hooks'

export function AdminHomePage() {
  const { slug, api, logout, club } = useClub()
  const nav = useNavigate()
  const pending = useAsync(() => api.articles({ all: true, limit: 50 }), [api])
  const waiting = (pending.data ?? []).filter((a) => a.status === 'GENERATED' || a.status === 'FAILED').length

  const items = [
    { to: `/c/${slug}/admin/sessions/new`, icon: 'calendar', label: '새 일정 만들기', sub: '날짜 · 참석자 · 게스트' },
    { to: `/c/${slug}/sessions`, icon: 'calendar', label: '일정 운영', sub: '팀 편성 · 경기 진행 · 일정마감' },
    { to: `/c/${slug}/admin/articles`, icon: 'wire', label: '기사 검토', sub: waiting ? `검토 대기 ${waiting}건` : '게시 · 반려 · 다시 쓰기' },
    { to: `/c/${slug}/admin/members`, icon: 'users', label: '멤버 관리', sub: '추가 · 이름·등번호 수정 · 비활성화' },
    { to: `/c/${slug}/admin/content`, icon: 'info', label: '운영 수칙 · 공지', sub: '운영 수칙 수정 · 와이어 상단 공지' },
    { to: `/c/${slug}/admin/settings`, icon: 'settings', label: '운영 설정', sub: '경기 시간 · 팀 편성 · 기사 게시 방식 · 암호' },
  ]

  return (
    <>
      <TopBar title="관리자 메뉴" sub={club?.clubName} back={`/c/${slug}`} />
      <main className="page tight">
        {items.map((it) => (
          <Link key={it.to + it.label} to={it.to} className="list-row" style={{ minHeight: 64 }}>
            <span className="row" style={{ gap: 12 }}>
              <span className="avatar" style={{ width: 40, height: 40, background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}><Icon name={it.icon} /></span>
              <span className="stack" style={{ gap: 0 }}><b>{it.label}</b><span className="small muted">{it.sub}</span></span>
            </span>
            <Icon name="chevron" />
          </Link>
        ))}
        <button type="button" className="btn block" style={{ marginTop: 12 }} onClick={() => { logout(); nav(`/c/${slug}`) }}>
          관리자 모드 끄기
        </button>
      </main>
    </>
  )
}
