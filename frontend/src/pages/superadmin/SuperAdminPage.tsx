import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { superadminApi, type ManagedClub, type ManagedClubCreate, type ManagedClubUpdate } from '../../api/superadmin'
import { Icon } from '../../components/Icon'
import { Empty, ErrorBox, Loading, Sheet, TopBar } from '../../components/ui'
import { useAsync } from '../../lib/hooks'
import { clearSuperAdminToken, getSuperAdminToken, onSuperAdminAuthChange, setSuperAdminToken } from '../../lib/superadminAuthStore'
import { useToast } from '../../lib/toast'
import './superadmin.css'

/** 서비스 슈퍼관리자 화면. ClubProvider 없이 동작한다. */
export function SuperAdminPage() {
  const { pathname } = useLocation()
  const [token, setToken] = useState(getSuperAdminToken)
  useEffect(() => onSuperAdminAuthChange(() => setToken(getSuperAdminToken())), [])
  const session = useAsync(async () => token ? { token, me: await superadminApi.me() } : null, [token])

  if (!token) return <SuperAdminLogin />
  if (session.error) {
    return (
      <div className="app">
        <TopBar title="슈퍼관리자" right={<LogoutButton />} />
        <main className="page"><ErrorBox error={session.error} onRetry={session.reload} /></main>
      </div>
    )
  }
  if (!session.data || session.data.token !== token) {
    return <div className="app"><TopBar title="슈퍼관리자" /><main className="page"><Loading rows={2} /></main></div>
  }
  return pathname.replace(/\/+$/, '') === '/admin/teams' ? <ManagedTeamsPage /> : <SuperAdminHome />
}

function LogoutButton() {
  return <button type="button" className="btn sm" onClick={clearSuperAdminToken}>로그아웃</button>
}

function SuperAdminLogin() {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy || !password) return
    setBusy(true)
    setError(null)
    try {
      const auth = await superadminApi.login(password)
      setPassword('')
      setSuperAdminToken(auth.accessToken, auth.expiresAt)
    } catch (reason) {
      setError(errorMessage(reason))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="app">
      <TopBar title="슈퍼관리자 로그인" back="/" />
      <main className="page superadmin-login">
        <div className="stack" style={{ gap: 8 }}>
          <div className="eyebrow">CLUBWIRE ADMIN</div>
          <h2>관리자 PIN을 입력하세요</h2>
          <p className="small muted">서비스에 등록된 팀을 관리합니다.</p>
        </div>
        <form className="card stack" onSubmit={submit}>
          <label className="field">관리자 PIN
            <input className="input" type="password" name="superadmin-pin" inputMode="numeric" autoComplete="current-password"
              required maxLength={64} value={password} disabled={busy} autoFocus
              onChange={(event) => { setPassword(event.target.value); setError(null) }} />
          </label>
          {error ? <p role="alert" className="small" style={{ color: 'var(--warn-ink)' }}>{error}</p> : null}
          <button type="submit" className="btn primary lg" disabled={busy || !password}>{busy ? '확인 중…' : '로그인'}</button>
        </form>
      </main>
    </div>
  )
}

function SuperAdminHome() {
  return (
    <div className="app">
      <TopBar title="슈퍼관리자" back="/" right={<LogoutButton />} />
      <main className="page">
        <Link to="/admin/teams" className="list-row" style={{ minHeight: 80 }}>
          <span className="row" style={{ gap: 12 }}>
            <span className="avatar" style={{ background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}><Icon name="users" /></span>
            <span className="stack" style={{ gap: 2 }}><b>팀 관리</b><span className="small muted">팀 조회 · 생성 · 수정 · 제거 · 복원</span></span>
          </span>
          <Icon name="chevron" />
        </Link>
      </main>
    </div>
  )
}

function ManagedTeamsPage() {
  const list = useAsync(() => superadminApi.clubs(), [])
  const [filter, setFilter] = useState<'active' | 'removed'>('active')
  // undefined: 닫힘, null: 생성, 객체: 해당 팀 수정. 재조회로 입력 중인 폼을 초기화하지 않는다.
  const [editor, setEditor] = useState<ManagedClub | null | undefined>(undefined)
  const [removal, setRemoval] = useState<ManagedClub | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const operationPending = useRef(false)
  const toast = useToast()
  const clubs = list.data ?? []
  const activeCount = clubs.filter((club) => club.active).length
  const removedCount = clubs.length - activeCount
  const visible = clubs.filter((club) => club.active === (filter === 'active'))
  const startOperation = () => {
    if (operationPending.current) return false
    operationPending.current = true
    setSaving(true)
    setOperationError(null)
    return true
  }
  const finishOperation = () => {
    operationPending.current = false
    setSaving(false)
  }
  const updateList = (updated: ManagedClub) => {
    list.setData(clubs.some((club) => club.clubId === updated.clubId)
      ? clubs.map((club) => club.clubId === updated.clubId ? updated : club) : [...clubs, updated])
    void list.reload()
  }
  const closeEditor = () => {
    if (operationPending.current) return
    setEditor(undefined)
    setSaveError(null)
  }
  const closeRemoval = () => {
    if (operationPending.current) return
    setRemoval(null)
    setRemoveError(null)
  }
  const save = async (body: ManagedClubCreate | ManagedClubUpdate) => {
    if (editor === undefined || !startOperation()) return
    setSaveError(null)
    try {
      const updated = editor ? await superadminApi.updateClub(editor.clubId, body)
        : await superadminApi.createClub(body as ManagedClubCreate)
      toast.show(editor ? '팀 정보를 저장했어요' : '팀을 생성했어요')
      if (!editor) setFilter('active')
      setEditor(undefined)
      updateList(updated)
    } catch (reason) {
      setSaveError(errorMessage(reason))
    } finally {
      finishOperation()
    }
  }
  const remove = async () => {
    if (!removal || !startOperation()) return
    setRemoveError(null)
    try {
      const updated = await superadminApi.removeClub(removal.clubId)
      updateList(updated)
      setRemoval(null)
      toast.show('팀을 제거했어요. 제거된 팀에서 복원할 수 있어요.')
    } catch (reason) {
      setRemoveError(errorMessage(reason))
    } finally {
      finishOperation()
    }
  }
  const restore = async (club: ManagedClub) => {
    if (!startOperation()) return
    try {
      const updated = await superadminApi.restoreClub(club.clubId)
      updateList(updated)
      toast.show('팀을 복원했어요')
    } catch (reason) {
      setOperationError(errorMessage(reason))
    } finally {
      finishOperation()
    }
  }
  return (
    <div className="app">
      <TopBar title="팀 관리" back="/admin" right={<LogoutButton />} />
      <main className="page">
        <div className="row between">
          <span className="small muted">{list.data ? `전체 ${clubs.length}개 팀` : '등록된 팀'}</span>
          <button type="button" className="btn primary sm" disabled={saving} onClick={() => { setSaveError(null); setEditor(null) }}>
            <Icon name="plus" size={16} />팀 생성
          </button>
        </div>
        <div className="chips" role="group" aria-label="팀 상태">
          <button type="button" className="chip" aria-pressed={filter === 'active'} disabled={saving}
            onClick={() => { setFilter('active'); setOperationError(null) }}>운영 중인 팀 {list.data ? activeCount : ''}</button>
          <button type="button" className="chip" aria-pressed={filter === 'removed'} disabled={saving}
            onClick={() => { setFilter('removed'); setOperationError(null) }}>제거된 팀 {list.data ? removedCount : ''}</button>
        </div>
        {operationError ? <p role="alert" className="notice warn small">{operationError}</p> : null}
        {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : !list.data ? <Loading />
          : visible.length === 0 ? <Empty>{filter === 'removed' ? '제거된 팀이 없습니다.'
            : clubs.length ? '운영 중인 팀이 없습니다. 새 팀을 생성하거나 제거된 팀을 복원해 주세요.' : '등록된 팀이 없습니다. 새 팀을 생성해 주세요.'}</Empty>
            : visible.map((club) => (
              <article key={club.clubId} className="card stack superadmin-team-card">
                <div className="row between">
                  <div className="stack" style={{ gap: 4, minWidth: 0 }}>
                    <h2 style={{ fontSize: 18, overflowWrap: 'anywhere' }}>{club.clubName}</h2>
                    <span className="small muted">/c/{club.clubSlug}</span>
                  </div>
                  <span className={`status-badge ${club.active ? 'green' : ''}`}>{club.active ? '운영 중' : '운영 중지'}</span>
                </div>
                <dl className="superadmin-team-counts">
                  <div><dt>멤버</dt><dd>{club.memberCount}명</dd></div>
                  <div><dt>일정</dt><dd>{club.sessionCount}개</dd></div>
                  <div><dt>기사</dt><dd>{club.articleCount}건</dd></div>
                </dl>
                <p className="small muted">{club.sportType} · {club.timezone}</p>
                <div className="grid2">
                  {club.active ? <Link className="btn sm" to={`/c/${encodeURIComponent(club.clubSlug)}`}>팀 화면 보기</Link>
                    : <button type="button" className="btn sm primary" disabled={saving} onClick={() => { void restore(club) }}>팀 복원</button>}
                  <button type="button" className="btn sm" disabled={saving}
                    onClick={() => { setSaveError(null); setEditor(club) }}>팀 수정</button>
                </div>
                {club.active ? <button type="button" className="btn sm danger" disabled={saving}
                  onClick={() => { setRemoveError(null); setRemoval(club) }}>팀 제거</button> : null}
              </article>
            ))}
      </main>
      <Sheet open={editor !== undefined} onClose={closeEditor} labelledBy="managed-team-form-title">
        {editor !== undefined ? (
          <ManagedTeamForm key={editor?.clubId ?? 'new'} club={editor} busy={saving} error={saveError} onSave={save} onCancel={closeEditor} />
        ) : null}
      </Sheet>
      <Sheet open={removal !== null} onClose={closeRemoval} labelledBy="managed-team-remove-title">
        {removal ? <div className="stack">
          <h2 id="managed-team-remove-title">팀을 제거할까요?</h2>
          <p><b>{removal.clubName}</b> 팀의 운영을 중지합니다.</p>
          <p className="small muted">
            멤버·일정·경기·기사 기록은 보존됩니다. 팀 화면과 해당 팀의 관리자 화면에 접근할 수 없게 되며,
            나중에 제거된 팀 목록에서 복원할 수 있습니다.
          </p>
          {removeError ? <p role="alert" className="small" style={{ color: 'var(--warn-ink)' }}>{removeError}</p> : null}
          <div className="grid2">
            <button type="button" className="btn" disabled={saving} onClick={closeRemoval}>취소</button>
            <button type="button" className="btn danger" disabled={saving} onClick={() => { void remove() }}>{saving ? '제거 중…' : '제거하기'}</button>
          </div>
        </div> : null}
      </Sheet>
    </div>
  )
}

function ManagedTeamForm({ club, busy, error, onSave, onCancel }: {
  club: ManagedClub | null
  busy: boolean
  error: string | null
  onSave: (body: ManagedClubCreate | ManagedClubUpdate) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName] = useState(club?.clubName ?? '')
  const [slug, setSlug] = useState(club?.clubSlug ?? '')
  const [timezone, setTimezone] = useState(club?.timezone ?? 'Asia/Seoul')
  const [pin, setPin] = useState('')
  const valid = name.trim().length > 0 && /^[a-z0-9_-]{1,50}$/.test(slug.trim())
    && timezone.trim().length > 0 && (club && pin === '' ? true : pin.length >= 4 && pin.length <= 64)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (busy || !valid) return
    const body = { clubName: name.trim(), clubSlug: slug.trim(), timezone: timezone.trim() }
    void onSave(club ? { ...body, ...(pin ? { adminPin: pin } : {}) } : { ...body, adminPin: pin })
  }
  return (
    <form className="stack" onSubmit={submit}>
      <h2 id="managed-team-form-title">{club ? '팀 수정' : '팀 생성'}</h2>
      <label className="field">팀 이름
        <input className="input" name="club-name" required maxLength={100} value={name} disabled={busy}
          onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="field">팀 주소
        <input className="input" name="club-slug" required maxLength={50} pattern="[a-z0-9_-]{1,50}" autoCapitalize="off" autoCorrect="off" spellCheck={false}
          value={slug} disabled={busy} onChange={(event) => setSlug(event.target.value.toLowerCase())} aria-describedby="managed-team-slug-help" />
        <span id="managed-team-slug-help" className="small muted">영문 소문자·숫자·밑줄·하이픈을 사용합니다. /c/{slug || 'team-address'}</span>
        {club ? <span className="small muted">주소를 바꾸면 기존 팀 링크도 새 주소로 바꿔야 합니다.</span> : null}
      </label>
      <label className="field">시간대
        <input className="input" name="club-timezone" required maxLength={50} value={timezone} disabled={busy}
          onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Seoul" />
      </label>
      <label className="field">{club ? '새 팀 관리자 PIN (변경할 때만 입력)' : '팀 관리자 PIN'}
        <input className="input" type="password" name="club-admin-pin" inputMode="numeric" autoComplete="new-password"
          required={!club} minLength={4} maxLength={64} value={pin} disabled={busy} onChange={(event) => setPin(event.target.value)} />
        <span className="small muted">팀 운영진이 해당 팀의 관리자 모드에 들어갈 때 사용합니다.</span>
      </label>
      {error ? <p role="alert" className="small" style={{ color: 'var(--warn-ink)' }}>{error}</p> : null}
      <div className="grid2">
        <button type="button" className="btn" disabled={busy} onClick={onCancel}>취소</button>
        <button type="submit" className="btn primary" disabled={busy || !valid}>{busy ? '저장 중…' : club ? '저장' : '팀 생성'}</button>
      </div>
    </form>
  )
}
