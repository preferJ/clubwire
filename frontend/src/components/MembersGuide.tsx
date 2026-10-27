import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '../api/client'
import { useClub, useClubEvent } from '../lib/club'
import { fmtDateTime } from '../lib/format'
import { Icon } from './Icon'
import { Sheet } from './ui'
import {
  fetchYprRules, parseGuideText, YPR_DEFAULT_RULES_TEXT, YPR_DEFAULT_RULES_UPDATED_AT, YPR_SOURCE_URL,
  type YprRules,
} from '../lib/yprGuide'

type RulesState = { status: 'loading' | 'live' | 'fallback' | 'saved' | 'error'; data: YprRules | null; error?: string }

export function MembersGuide() {
  const { api } = useClub()
  const [open, setOpen] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [rules, setRules] = useState<RulesState>({ status: 'loading', data: null })
  const close = useCallback(() => setOpen(false), [])

  useClubEvent((message) => {
    if (message.type === 'CLUB_CONTENT_UPDATED' && open) setAttempt((n) => n + 1)
  })

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setRules({ status: 'loading', data: null })
    const load = async () => {
      try {
        const saved = await api.clubContent()
        if (controller.signal.aborted) return
        if (saved.operatingRules !== null) {
          setRules({ status: 'saved', data: { text: saved.operatingRules, updatedAt: fmtDateTime(saved.operatingRulesUpdatedAt) } })
          return
        }
        try {
          const data = await fetchYprRules(controller.signal)
          if (!controller.signal.aborted) setRules({ status: 'live', data })
        } catch {
          if (!controller.signal.aborted) setRules({
            status: 'fallback', data: { text: YPR_DEFAULT_RULES_TEXT, updatedAt: YPR_DEFAULT_RULES_UPDATED_AT },
          })
        }
      } catch (error) {
        if (!controller.signal.aborted) setRules({ status: 'error', data: null, error: errorMessage(error) })
      }
    }
    void load()
    return () => controller.abort()
  }, [api, open, attempt])

  return (
    <>
      <button type="button" className="btn block members-guide-trigger" onClick={() => setOpen(true)}>
        <Icon name="info" size={18} />운영 수칙
      </button>
      <Sheet open={open} onClose={close} labelledBy="members-guide-title">
        <div className="members-guide">
          <div className="row between members-guide-heading">
            <h2 id="members-guide-title">운영 수칙</h2>
            <button type="button" className="icon-btn" aria-label="안내 닫기" onClick={close}><Icon name="close" /></button>
          </div>
          {rules.status === 'loading' ? <p className="muted" role="status">최신 운영 수칙을 불러오는 중이에요…</p> : null}
          {rules.status === 'error' ? (
            <div className="notice warn members-guide-warning" role="alert">
              <p>{rules.error || '운영 수칙을 불러오지 못했어요.'}</p>
              <button type="button" className="btn sm" onClick={() => setAttempt((v) => v + 1)}>다시 불러오기</button>
            </div>
          ) : null}
          {rules.status === 'fallback' ? (
            <div className="notice warn members-guide-warning" role="status">
              <p>최신 운영 수칙을 불러오지 못해 2026-06-08 기본 수칙을 표시합니다.</p>
              <button type="button" className="btn sm" onClick={() => setAttempt((v) => v + 1)}>다시 불러오기</button>
            </div>
          ) : null}
          {rules.data ? (
            <>
              <p className="small muted">
                {rules.status === 'saved' ? '클럽 운영 수칙' : rules.status === 'live' ? '최신 운영 수칙' : '기본 운영 수칙'}
                {rules.data.updatedAt ? ` · 최종 수정 ${rules.data.updatedAt}` : ''}
              </p>
              {rules.data.text.trim() ? <RulesText text={rules.data.text} /> : <p className="muted">등록된 운영 수칙이 없습니다.</p>}
            </>
          ) : null}
          {rules.status === 'live' || rules.status === 'fallback' ? (
            <a className="btn sm members-guide-source" href={YPR_SOURCE_URL} target="_blank" rel="noopener noreferrer">YPR 원문 보기 ↗</a>
          ) : null}
        </div>
      </Sheet>
    </>
  )
}

export function RulesText({ text }: { text: string }) {
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
