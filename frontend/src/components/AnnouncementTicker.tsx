import { useState, type CSSProperties } from 'react'
import type { AnnouncementSize } from '../api/types'
import { Icon } from './Icon'
import '../styles/club-content.css'

/** 한 줄 공지. 복제된 문구는 화면 낭독기에 한 번만 전달한다. size = 글자 · 높이 3단계(관리자 설정, 기본 medium) */
export function AnnouncementTicker({ text, size = 'medium' }: { text: string | null | undefined; size?: AnnouncementSize }) {
  const [paused, setPaused] = useState(false)
  const notice = text?.replace(/\s+/g, ' ').trim() ?? ''
  if (!notice) return null
  const style = { '--announcement-duration': `${Math.max(18, Math.min(90, notice.length * 0.35))}s` } as CSSProperties

  return (
    <aside className={`announcement-ticker size-${size}${paused ? ' is-paused' : ''}`} aria-label="클럽 공지" style={style}>
      <span className="announcement-label">공지</span>
      <div className="announcement-window" role="region" aria-label={notice} tabIndex={0} title={notice}>
        <div className="announcement-track" key={notice} aria-hidden="true">
          <span className="announcement-copy">{notice}</span>
          <span className="announcement-copy">{notice}</span>
        </div>
      </div>
      <button type="button" className="announcement-pause" aria-label={paused ? '공지 흐름 재생' : '공지 흐름 일시정지'}
        aria-pressed={paused} onClick={() => setPaused((v) => !v)}>
        <Icon name={paused ? 'play' : 'pause'} size={12} stroke={2} />
      </button>
    </aside>
  )
}
