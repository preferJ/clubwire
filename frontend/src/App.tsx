import { useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { PinSheet } from './components/PinSheet'
import { BottomNav, Empty, TopBar } from './components/ui'
import { ClubProvider, useClub } from './lib/club'
import { ToastProvider } from './lib/toast'
import { ArticlePage } from './pages/ArticlePage'
import { HomePage } from './pages/HomePage'
import { MatchPage } from './pages/MatchPage'
import { MembersPage } from './pages/MembersPage'
import { PlayerPage } from './pages/PlayerPage'
import { RecordsPage } from './pages/RecordsPage'
import { SessionPage } from './pages/SessionPage'
import { SessionsPage } from './pages/SessionsPage'
import { AdminHomePage } from './pages/admin/AdminHomePage'
import { ArticlesAdminPage } from './pages/admin/ArticlesAdminPage'
import { ClosePage } from './pages/admin/ClosePage'
import { ClubContentAdminPage } from './pages/admin/ClubContentAdminPage'
import { ClubAppearancePage } from './pages/admin/ClubAppearancePage'
import { MembersAdminPage } from './pages/admin/MembersAdminPage'
import { SessionFormPage } from './pages/admin/SessionFormPage'
import { SettingsPage } from './pages/admin/SettingsPage'
import { TeamsPage } from './pages/admin/TeamsPage'
import { SuperAdminPage } from './pages/superadmin/SuperAdminPage'

function ClubLayout() {
  const { slug = '' } = useParams()
  return (
    <ClubProvider key={slug} slug={slug}>
      <Outlet />
      <PinSheet />
    </ClubProvider>
  )
}

/** 클럽 화면 공통 틀: 모든 화면(상세·관리자 포함)에 아래 탭 메뉴를 고정 표시 */
function TabShell() {
  return (
    <div className="app with-nav">
      <Outlet />
      <BottomNav />
    </div>
  )
}

/** 관리자 전용 화면: 관리자 모드가 아니면 PIN 입력 유도 */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin, setPinOpen, slug } = useClub()
  if (isAdmin) return <>{children}</>
  return (
    <>
      <TopBar title="관리자 전용" back={`/c/${slug}`} />
      <Empty>
        <p>관리자 모드에서만 볼 수 있어요.</p>
        <button type="button" className="btn primary" style={{ marginTop: 16 }} onClick={() => setPinOpen(true)}>
          관리자 모드 켜기
        </button>
      </Empty>
    </>
  )
}

function Landing() {
  const def = ((import.meta.env.VITE_DEFAULT_CLUB as string | undefined) ?? 'ypr').trim()
  const nav = useNavigate()
  const [slug, setSlug] = useState('')
  if (def) return <Navigate to={`/c/${def}`} replace />
  return (
    <div className="app">
      <div className="page" style={{ paddingTop: 80 }}>
        <div className="eyebrow">CLUBWIRE</div>
        <h1 className="club-name">클럽 주소를 입력하세요</h1>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            if (slug.trim()) nav(`/c/${slug.trim()}`)
          }}
        >
          <label className="field">
            클럽 주소
            <input className="input" value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="예: ypr" autoCapitalize="off" />
          </label>
          <button className="btn primary lg" type="submit">들어가기</button>
        </form>
      </div>
    </div>
  )
}

const admin = (el: ReactNode) => <RequireAdmin>{el}</RequireAdmin>

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/admin" element={<SuperAdminPage />} />
          <Route path="/admin/teams" element={<SuperAdminPage />} />
          <Route path="/c/:slug" element={<ClubLayout />}>
            <Route element={<TabShell />}>
              <Route index element={<HomePage />} />
              <Route path="sessions" element={<SessionsPage />} />
              <Route path="records" element={<RecordsPage />} />
              <Route path="members" element={<MembersPage />} />
              <Route path="articles/:articleId" element={<ArticlePage />} />
              <Route path="sessions/:sessionId" element={<SessionPage />} />
              <Route path="matches/:matchId" element={<MatchPage />} />
              <Route path="members/:memberId" element={<PlayerPage />} />
              <Route path="admin" element={admin(<AdminHomePage />)} />
              <Route path="admin/sessions/new" element={admin(<SessionFormPage />)} />
              <Route path="admin/sessions/:sessionId/attendance" element={admin(<SessionFormPage />)} />
              <Route path="admin/sessions/:sessionId/teams" element={admin(<TeamsPage />)} />
              <Route path="admin/sessions/:sessionId/close" element={admin(<ClosePage />)} />
              <Route path="admin/articles" element={admin(<ArticlesAdminPage />)} />
              <Route path="admin/members" element={admin(<MembersAdminPage />)} />
              <Route path="admin/content" element={admin(<ClubContentAdminPage />)} />
              <Route path="admin/appearance" element={admin(<ClubAppearancePage />)} />
              <Route path="admin/settings" element={admin(<SettingsPage />)} />
            </Route>
          </Route>
          <Route path="*" element={<div className="app"><Empty>페이지를 찾을 수 없어요.</Empty></div>} />
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  )
}
