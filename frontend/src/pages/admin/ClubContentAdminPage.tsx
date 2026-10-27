import { useEffect, useState } from 'react'
import { errorMessage } from '../../api/client'
import { AnnouncementTicker } from '../../components/AnnouncementTicker'
import { RulesText } from '../../components/MembersGuide'
import { ErrorBox, Loading, TopBar } from '../../components/ui'
import { useClub } from '../../lib/club'
import { useAction } from '../../lib/hooks'
import { fetchYprRules, YPR_DEFAULT_RULES_TEXT } from '../../lib/yprGuide'
import '../../styles/club-content.css'

const RULES_LIMIT = 20000
const ANNOUNCEMENT_LIMIT = 500

export function ClubContentAdminPage() {
  const { api, slug } = useClub()
  const [attempt, setAttempt] = useState(0)
  const [initial, setInitial] = useState<{ rules: string; announcement: string } | null>(null)
  const [rules, setRules] = useState('')
  const [announcement, setAnnouncement] = useState('')
  const [loadError, setLoadError] = useState<unknown>()
  const [saveError, setSaveError] = useState('')
  const [sourceNote, setSourceNote] = useState('')
  const { busy, run } = useAction()

  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    setInitial(null)
    setLoadError(undefined)
    setSaveError('')
    setSourceNote('')
    const load = async () => {
      try {
        const saved = await api.clubContent()
        let text = saved.operatingRules
        let note = ''
        if (text === null) {
          try {
            const original = await fetchYprRules(controller.signal)
            text = original.text
            note = `현재 YPR 운영 수칙(${original.updatedAt})을 불러왔어요. 수정 후 저장하면 선수단에 반영됩니다.`
          } catch {
            text = YPR_DEFAULT_RULES_TEXT
            note = 'YPR 원문을 불러오지 못해 2026-06-08 기본 수칙으로 시작합니다. 내용을 확인한 뒤 저장하세요.'
          }
        }
        if (!alive) return
        setRules(text)
        setAnnouncement(saved.announcement)
        setInitial({ rules: text, announcement: saved.announcement })
        setSourceNote(note)
      } catch (error) {
        if (alive) setLoadError(error)
      }
    }
    void load()
    return () => { alive = false; controller.abort() }
  }, [api, attempt])

  const rulesChanged = initial !== null && rules !== initial.rules
  const announcementChanged = initial !== null && announcement !== initial.announcement
  const changed = rulesChanged || announcementChanged
  const tooLong = rules.length > RULES_LIMIT || announcement.length > ANNOUNCEMENT_LIMIT

  const save = async () => {
    if (!initial || !changed || tooLong || busy) return
    setSaveError('')
    const body = { ...(rulesChanged ? { operatingRules: rules } : {}), ...(announcementChanged ? { announcement } : {}) }
    const saved = await run(async () => {
      try {
        return await api.updateClubContent(body)
      } catch (error) {
        setSaveError(errorMessage(error))
        throw error
      }
    }, '운영 수칙과 공지를 저장했어요')
    if (!saved) return
    const savedRules = saved.operatingRules ?? rules
    setInitial({ rules: savedRules, announcement: saved.announcement })
    setRules(savedRules)
    setAnnouncement(saved.announcement)
    if (rulesChanged) setSourceNote('저장한 운영 수칙이 선수단에 표시됩니다.')
  }

  return (
    <>
      <TopBar title="운영 수칙 · 공지" back={`/c/${slug}/admin`} />
      {loadError ? <ErrorBox error={loadError} onRetry={() => setAttempt((n) => n + 1)} /> : !initial ? (
        <main className="page"><Loading /></main>
      ) : (
        <main className="page club-content-editor">
          <section className="card stack" style={{ gap: 10 }}>
            <h2><label htmlFor="club-announcement">상단 공지사항</label></h2>
            <p className="small muted">와이어 상단에 한 줄로 흘러갑니다. 비우고 저장하면 공지가 숨겨집니다.</p>
            <textarea id="club-announcement" className="content-textarea" rows={3} maxLength={ANNOUNCEMENT_LIMIT}
              value={announcement} disabled={busy} onChange={(e) => setAnnouncement(e.target.value)}
              placeholder="예: 이번 주 토요일 경기는 오전 8시 시작입니다. 참석 투표를 확인해 주세요." />
            <p className="club-content-counter">{announcement.length.toLocaleString()} / {ANNOUNCEMENT_LIMIT.toLocaleString()}자</p>
            {announcement.trim() ? <AnnouncementTicker text={announcement} /> : null}
          </section>

          <section className="card stack" style={{ gap: 10 }}>
            <h2><label htmlFor="club-operating-rules">운영 수칙</label></h2>
            <p className="small muted">선수단의 운영 수칙 버튼에서 확인할 수 있습니다. 제목은 #, 소제목은 ##, 목록은 -로 작성할 수 있어요.</p>
            {sourceNote ? <p className="small muted" role="status">{sourceNote}</p> : null}
            <textarea id="club-operating-rules" className="content-textarea rules" rows={16} maxLength={RULES_LIMIT}
              value={rules} disabled={busy} onChange={(e) => setRules(e.target.value)} placeholder="클럽 운영 수칙을 작성하세요." />
            <p className="club-content-counter">{rules.length.toLocaleString()} / {RULES_LIMIT.toLocaleString()}자</p>
            <p className="small muted">내용을 모두 지우고 저장하면 운영 수칙도 비워집니다.</p>
            <details className="club-content-preview">
              <summary>운영 수칙 미리보기</summary>
              {rules.trim() ? <RulesText text={rules} /> : <p className="small muted">등록된 운영 수칙이 없습니다.</p>}
            </details>
          </section>
          {tooLong ? <p className="club-content-error" role="alert">입력 가능한 글자 수를 확인해 주세요.</p> : null}
          {saveError ? <p className="club-content-error" role="alert">{saveError}</p> : null}
        </main>
      )}
      {initial ? (
        <div className="bar-actions">
          <button type="button" className="btn primary lg block" disabled={busy || !changed || tooLong} onClick={save}>
            {busy ? '저장 중…' : changed ? '변경 사항 저장' : '변경 사항 없음'}
          </button>
        </div>
      ) : null}
    </>
  )
}
